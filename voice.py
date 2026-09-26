"""
Motore vocale di Samaritan.

Primario  : ElevenLabs (la piu' realistica, a consumo; solo se c'e' la chiave)
Ripiego 1 : Edge-TTS (voci neurali Microsoft, gratuite, buona qualita)
Ripiego 2 : gTTS (robotica, solo se non funziona nient'altro)

La catena e' pensata per non fermare mai la pubblicazione: se ElevenLabs non
risponde, se la chiave e' sbagliata o se il credito e' finito, il video esce
lo stesso con la voce Microsoft, e il log lo dice a chiare lettere.

Il salto da gTTS a Edge-TTS e' il singolo miglioramento con piu' impatto
sulla retention: la voce neurale ha enfasi, respiro e intonazione, quindi
l'hook dei primi 3 secondi "suona" davvero come un hook.
"""
import os
import re
import json
import asyncio

import requests

import config

# Emoji e simboli decorativi: la voce non deve leggerli
_RE_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)


def pulisci_testo(testo):
    """Ripulisce lo script per la sintesi vocale e per i sottotitoli."""
    t = _RE_EMOJI.sub(" ", testo)
    t = re.sub(r"#\w+", " ", t)          # hashtag: non vanno letti
    t = re.sub(r"[*_`>\[\]()]", " ", t)  # residui markdown
    t = t.replace("...", ".").replace("…", ".")
    t = t.replace("-", " ").replace("—", " ").replace("–", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    return t.strip()


# Come la voce deve DIRE certe parole quando la grafia normale la inganna.
# Il caso che ha fatto nascere l'elenco: "segui Poppone TV" in chiusura, letto
# con l'accento sbagliato e "TV" all'inglese. Tocca solo l'audio: titoli,
# descrizioni e sottotitoli restano scritti giusti (vedi grafia_canale).
_PRONUNCE_IT = (
    (re.compile(r"@?\bpoppone\s*tv\b", re.IGNORECASE), "Poppóne tivù"),
    (re.compile(r"\bpoppone\b", re.IGNORECASE), "Poppóne"),
)


def pronuncia(testo):
    """Riscrive per la voce italiana le parole che altrimenti legge male."""
    if (config.LINGUA or "it").lower() != "it":
        return testo
    for regola, detto in _PRONUNCE_IT:
        testo = regola.sub(detto, testo)
    return testo


# Il percorso inverso, per i sottotitoli: Whisper trascrive quello che sente,
# e dopo pronuncia() sente "Poppóne tivù".
_GRAFIA_CANALE = (
    (re.compile(r"\bpop+[oóò]ne\b", re.IGNORECASE), "Poppone"),
    (re.compile(r"\bt[iì]v[uù]\b", re.IGNORECASE), "TV"),
)


def grafia_canale(testo):
    """Riporta il nome del canale alla sua grafia nei sottotitoli."""
    for regola, scritto in _GRAFIA_CANALE:
        testo = regola.sub(scritto, testo)
    return testo


_API_ELEVENLABS = "https://api.elevenlabs.io/v1"
# L'id della voce si risolve una volta sola per processo: e' una chiamata di
# rete in piu' e il nome non cambia a meta' esecuzione.
_voce_risolta = None
# Nome della voce che la rotazione ha scelto per questo video. Si annota solo
# se ElevenLabs produce davvero l'audio: un record che dice 'Davide' mentre il
# video parla Microsoft e' peggio di nessun record.
_nome_scelto = None


def _elenco_voci(chiave):
    risposta = requests.get(
        f"{_API_ELEVENLABS}/voices",
        headers={"xi-api-key": chiave},
        timeout=30,
    )
    if risposta.status_code == 401:
        raise RuntimeError("chiave ElevenLabs non valida")
    risposta.raise_for_status()
    return risposta.json().get("voices", [])


def _carica_cronologia():
    """La memoria storica, o lista vuota se il file manca o e' illeggibile."""
    try:
        with open(config.FILE_CRONOLOGIA, "r", encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, list) else []
    except Exception:
        return []


def _ultima_voce_usata():
    """Il nome della voce dell'ultimo video che l'ha annotata.

    La rotazione si ricorda dove era arrivata guardando qui, non contando i
    video: la cronologia viene tagliata a 200 elementi, quindi un contatore
    si bloccherebbe da solo dopo qualche mese, in silenzio.
    """
    for elemento in reversed(_carica_cronologia()):
        if isinstance(elemento, dict) and elemento.get("voce"):
            return elemento["voce"]
    return None


def _segna_voce_usata(nome):
    """Annota sulla cronologia la voce di questo video.

    Sta qui e non in brain.py perche' e' voice.py a decidere quale voce esce
    davvero: il nome nella variabile puo' non esistere nell'account. Il
    workflow committa gia' questo file, quindi il prossimo giro lo ritrova.
    """
    cronologia = _carica_cronologia()
    if not cronologia or not isinstance(cronologia[-1], dict):
        return
    cronologia[-1]["voce"] = nome
    try:
        with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
            json.dump(cronologia, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning Voice] Voce scelta non annotata ({e}): "
              f"il prossimo video potrebbe ripeterla.")


# ElevenLabs restituisce il nome completo di descrizione, tipo
# "Romario - Credible, Calm and Balanced", mentre sul sito si legge "Romario".
# Chi compila l'impostazione scrive il nome corto, quindi si confronta anche
# quello. Il trattino puo' essere normale, lungo o mediano.
_RE_DESCRIZIONE = re.compile(r"\s+[-–—]\s+")


def _nome_corto(nome):
    """Da 'Romario - Credible, Calm and Balanced' ricava 'Romario'."""
    return _RE_DESCRIZIONE.split(nome.strip(), 1)[0].strip()


def _cerca_voce(voci, richiesta):
    """Trova una voce per nome come si legge sul sito, o per id. None se non c'e'."""
    cercato = richiesta.strip().lower()
    if not cercato:
        return None
    for voce in voci:
        nome = voce.get("name", "").strip()
        if cercato in (nome.lower(), _nome_corto(nome).lower()):
            return voce["voice_id"]
    # Chi incolla il nome intero preso da ElevenLabs si porta dietro le virgole
    # della descrizione, che qui separano una voce dall'altra: quel pezzo
    # arriva troncato. Basta che sia l'inizio del nome vero per riconoscerlo.
    for voce in voci:
        if voce.get("name", "").strip().lower().startswith(cercato):
            return voce["voice_id"]
    if any(voce.get("voice_id") == richiesta for voce in voci):
        return richiesta
    return None


def _risolvi_voce(chiave):
    """Ritorna l'id della voce da usare per questo video.

    `ELEVENLABS_VOCE` accetta il nome che si legge sul sito, perche' e' quello
    che un umano ha sotto gli occhi, oppure direttamente un id. Piu' nomi
    separati da virgola vengono alternati: il video di oggi parte da quello
    dopo l'ultimo usato. Vuoto: si prende la prima voce dell'account.
    """
    global _voce_risolta
    if _voce_risolta:
        return _voce_risolta

    voci = _elenco_voci(chiave)
    if not voci:
        raise RuntimeError("l'account ElevenLabs non ha nessuna voce")

    richieste = config.ELEVENLABS_VOCI
    if not richieste:
        _voce_risolta = voci[0]["voice_id"]
        print(f"[Samaritan Voice] Nessuna voce indicata: uso "
              f"'{voci[0].get('name', _voce_risolta)}'.")
        return _voce_risolta

    # Si riparte da quella dopo l'ultima usata. Se l'ultima non e' piu' in
    # elenco (lista cambiata) si ricomincia dall'inizio. Un nome scritto male
    # fa saltare il suo turno, non l'intera sintesi.
    partenza = 0
    precedente = _ultima_voce_usata()
    if precedente in richieste:
        partenza = (richieste.index(precedente) + 1) % len(richieste)
    ordinate = richieste[partenza:] + richieste[:partenza]

    global _nome_scelto
    for nome in ordinate:
        trovata = _cerca_voce(voci, nome)
        if trovata:
            if len(richieste) > 1:
                print(f"[Samaritan Voice] {len(richieste)} voci a rotazione, "
                      f"questo video usa '{nome}'.")
            _nome_scelto = nome
            _voce_risolta = trovata
            return _voce_risolta
        print(f"[Warning Voice] Voce '{nome}' non e' nell'account, provo la successiva.")

    # Nell'elenco vanno i nomi corti: sono quelli che si leggono sul sito e
    # che vanno scritti nell'impostazione.
    nomi = ", ".join(sorted({_nome_corto(v.get("name", "?")) for v in voci}))
    raise RuntimeError(
        f"nessuna delle voci richieste ({', '.join(richieste)}) esiste "
        f"nell'account. Disponibili: {nomi}"
    )


def _sintetizza_elevenlabs(testo, output_filename):
    chiave = config.ELEVENLABS_API_KEY
    if not chiave:
        raise RuntimeError("ELEVENLABS_API_KEY non configurata")

    voce = _risolvi_voce(chiave)
    risposta = requests.post(
        f"{_API_ELEVENLABS}/text-to-speech/{voce}",
        headers={"xi-api-key": chiave, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={
            "text": testo,
            "model_id": config.ELEVENLABS_MODELLO,
            "voice_settings": {
                "stability": config.ELEVENLABS_STABILITA,
                "similarity_boost": config.ELEVENLABS_SOMIGLIANZA,
                "use_speaker_boost": True,
            },
        },
        timeout=180,
    )
    if risposta.status_code == 401:
        raise RuntimeError("chiave ElevenLabs non valida")
    if risposta.status_code == 402:
        # ElevenLabs risponde 402 sia quando il credito e' finito sia quando la
        # voce richiesta e' riservata ai piani a pagamento: dal codice non si
        # distingue, e la differenza si vede solo dal pannello dell'account.
        raise RuntimeError(
            "ElevenLabs ha rifiutato per pagamento (402): credito del mese "
            "finito, oppure questa voce e' riservata a un piano a pagamento. "
            "Si controlla su elevenlabs.io, in Usage e in Subscription"
        )
    if risposta.status_code == 429:
        raise RuntimeError("credito ElevenLabs esaurito o troppe richieste")
    risposta.raise_for_status()

    with open(output_filename, "wb") as f:
        f.write(risposta.content)


async def _sintetizza_edge(testo, output_filename):
    import edge_tts

    communicate = edge_tts.Communicate(
        text=testo,
        voice=config.VOCE_TTS,
        rate=config.VOCE_VELOCITA,
        pitch=config.VOCE_PITCH,
    )
    await communicate.save(output_filename)


def genera_voce_samaritan(testo, output_filename=None, permetti_elevenlabs=True):
    """Genera l'audio dello script. Ritorna il path del file o None.

    `permetti_elevenlabs=False` salta la voce a pagamento e parte dritto da
    Edge-TTS. Lo usano i Reel promozionali di promo.py, per due motivi: il
    credito ElevenLabs deve restare ai video del canale, che sono quelli che
    portano soldi, e soprattutto la rotazione delle voci annota il proprio
    turno sull'ultimo record della cronologia di YouTube. Un Reel che passa di
    li' scriverebbe una voce addosso a un video che non l'ha mai usata.
    """
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    if output_filename is None:
        output_filename = os.path.join(config.DIR_TEMP, "audio.mp3")

    testo_pulito = pronuncia(pulisci_testo(testo))
    if not testo_pulito:
        print("[Errore Voice] Testo vuoto dopo la pulizia.")
        return None

    # --- Tentativo 1: ElevenLabs (la voce piu' realistica) ---
    if config.ELEVENLABS_API_KEY and permetti_elevenlabs:
        try:
            print(f"[Samaritan Voice] Sintesi ElevenLabs "
                  f"({config.ELEVENLABS_MODELLO}, {len(testo_pulito)} caratteri)...")
            _sintetizza_elevenlabs(testo_pulito, output_filename)

            if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                print(f"[Samaritan Voice] Audio ElevenLabs salvato: {output_filename}")
                # Ora il video parla con questa voce: la rotazione puo' segnare
                # il turno come speso e passare alla prossima.
                if _nome_scelto:
                    _segna_voce_usata(_nome_scelto)
                return output_filename
            raise RuntimeError("ElevenLabs ha prodotto un file vuoto")

        except Exception as e:
            print(f"[Warning Voice] ElevenLabs non utilizzabile ({e}). "
                  f"Il video usera' la voce Microsoft.")

    # --- Tentativo 2: Edge-TTS (voce neurale gratuita) ---
    try:
        print(f"[Samaritan Voice] Sintesi neurale con {config.VOCE_TTS} "
              f"(velocita {config.VOCE_VELOCITA})...")
        asyncio.run(_sintetizza_edge(testo_pulito, output_filename))

        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
            print(f"[Samaritan Voice] Audio neurale salvato: {output_filename}")
            return output_filename
        raise RuntimeError("Edge-TTS ha prodotto un file vuoto")

    except Exception as e:
        print(f"[Warning Voice] Edge-TTS non disponibile ({e}). Passo al fallback gTTS.")

    # --- Tentativo 3: gTTS (ripiego robotico) ---
    try:
        from gtts import gTTS

        # Il dominio decide l'accento: quello italiano su un testo inglese
        # suona sbagliato.
        dominio = "it" if (config.LINGUA or "it").lower() == "it" else "com"
        tts = gTTS(text=testo_pulito, lang=config.LINGUA, tld=dominio, slow=False)
        tts.save(output_filename)
        print(f"[Samaritan Voice] Audio di fallback salvato: {output_filename}")
        return output_filename
    except Exception as e:
        print(f"[Errore Voice] Impossibile generare l'audio: {e}")
        return None


if __name__ == "__main__":
    testo_test = (
        "Stai sbagliando tutto su GTA 6, e nemmeno te ne accorgi. "
        "Questo dettaglio lo ha notato solo lo zero virgola uno per cento dei giocatori."
    )
    genera_voce_samaritan(testo_test)
