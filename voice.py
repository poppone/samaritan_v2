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


_API_ELEVENLABS = "https://api.elevenlabs.io/v1"
# L'id della voce si risolve una volta sola per processo: e' una chiamata di
# rete in piu' e il nome non cambia a meta' esecuzione.
_voce_risolta = None


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


def _risolvi_voce(chiave):
    """Ritorna l'id della voce da usare.

    `ELEVENLABS_VOCE` accetta il nome che si legge sul sito, perche' e' quello
    che un umano ha sotto gli occhi, oppure direttamente un id. Vuoto: si
    prende la prima voce dell'account.
    """
    global _voce_risolta
    if _voce_risolta:
        return _voce_risolta

    richiesta = (config.ELEVENLABS_VOCE or "").strip()
    voci = _elenco_voci(chiave)
    if not voci:
        raise RuntimeError("l'account ElevenLabs non ha nessuna voce")

    if richiesta:
        for voce in voci:
            if voce.get("name", "").strip().lower() == richiesta.lower():
                _voce_risolta = voce["voice_id"]
                return _voce_risolta
        # Non e' un nome noto: forse e' gia' un id.
        if any(voce.get("voice_id") == richiesta for voce in voci):
            _voce_risolta = richiesta
            return _voce_risolta
        nomi = ", ".join(sorted(v.get("name", "?") for v in voci))
        raise RuntimeError(
            f"voce '{richiesta}' non trovata nell'account. Disponibili: {nomi}"
        )

    _voce_risolta = voci[0]["voice_id"]
    print(f"[Samaritan Voice] Nessuna voce indicata: uso "
          f"'{voci[0].get('name', _voce_risolta)}'.")
    return _voce_risolta


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


def genera_voce_samaritan(testo, output_filename=None):
    """Genera l'audio dello script. Ritorna il path del file o None."""
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    if output_filename is None:
        output_filename = os.path.join(config.DIR_TEMP, "audio.mp3")

    testo_pulito = pulisci_testo(testo)
    if not testo_pulito:
        print("[Errore Voice] Testo vuoto dopo la pulizia.")
        return None

    # --- Tentativo 1: ElevenLabs (la voce piu' realistica) ---
    if config.ELEVENLABS_API_KEY:
        try:
            print(f"[Samaritan Voice] Sintesi ElevenLabs "
                  f"({config.ELEVENLABS_MODELLO}, {len(testo_pulito)} caratteri)...")
            _sintetizza_elevenlabs(testo_pulito, output_filename)

            if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                print(f"[Samaritan Voice] Audio ElevenLabs salvato: {output_filename}")
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

        tts = gTTS(text=testo_pulito, lang=config.LINGUA, tld="it", slow=False)
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
