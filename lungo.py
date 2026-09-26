# -*- coding: utf-8 -*-
"""
Il video lungo: 16:9, otto minuti, un capitolo per sezione.

Perche' esiste, in una riga: YouTube ha due porte per il programma partner, e
un canale di soli Short ne puo' aprire una sola. La porta degli Short chiede
10 milioni di visualizzazioni in 90 giorni; quella dei video lunghi chiede
1.000 iscritti e 4.000 ore di visione in 12 mesi, e le ore guardate sugli
Short non contano per quella soglia. Sui numeri del canale la prima e' fuori
portata di due ordini di grandezza e la seconda no. Vedi README.

Come e' scritto il testo, e perche' non in un colpo solo:
  1. si chiede al modello una SCALETTA (titolo, gioco, le sezioni con il loro
     titolo e cosa devono dire);
  2. ogni sezione viene scritta con una chiamata sua, sapendo come finiva la
     precedente.
Un video di otto minuti sono circa 1.200 parole: chiederle in una risposta
sola significa farsi troncare a meta' dal tetto dei token, ed e' un guasto
che nello Short e' gia' capitato con testi venti volte piu' corti.

Il vantaggio vero pero' e' un altro: ogni sezione ha il suo pezzo di audio,
quindi si sa quanto dura, quindi i capitoli nella descrizione YouTube sono
timestamp VERI e non stime. I capitoli sono la ragione principale per cui uno
spettatore resta su un video lungo invece di chiuderlo al primo minuto.

Sul materiale video: da qui non si scarica NIENTE da YouTube. Le fonti sono le
stesse dello Short (trailer e screenshot ufficiali Steam, clip girate da
popponetv) e la richiesta di popponetv del 22 settembre 2026 di "reperire
spezzoni online di gameplay vero" e' soddisfatta prendendo i trailer
ufficiali INTERI invece che a spezzoni di 45 secondi
(config.SECONDI_TRAILER). Prendere gameplay dai video di altri e' esattamente
cio' che fa bocciare la domanda di monetizzazione, che e' il motivo per cui
questo modulo esiste.
"""
import json
import os
import re
import subprocess

import config
import brain
from voice import genera_voce_samaritan

# Quante parole al minuto legge la voce. Misurato sugli Short: ~165 a +12%,
# quindi circa 150 alla velocita' piu' calma del video lungo.
PAROLE_AL_MINUTO = 150

# Limiti per singola sezione. Sotto il minimo la sezione non e' un capitolo,
# e' una frase; sopra il massimo il modello comincia a girare a vuoto.
MIN_PAROLE_SEZIONE = 70
MAX_PAROLE_SEZIONE = 320

# Silenzio fra una sezione e l'altra: fa respirare il montaggio e rende netto
# lo stacco di capitolo.
PAUSA_FRA_SEZIONI = 0.6

# YouTube riconosce i capitoli solo se il primo e' a 00:00, se sono almeno
# tre e se ognuno dura almeno dieci secondi.
MIN_CAPITOLI = 3
MIN_SECONDI_CAPITOLO = 10


def parole_per_sezione():
    """Quante parole deve avere ogni sezione per arrivare alla durata voluta."""
    totale = config.MINUTI_VIDEO_LUNGO * PAROLE_AL_MINUTO
    sezioni = max(config.SEZIONI_VIDEO_LUNGO, 1)
    return max(int(round(totale / sezioni)), MIN_PAROLE_SEZIONE)


# ===========================================================================
# SCRITTURA
# ===========================================================================
_SCHEMA_SCALETTA = {
    "name": "scaletta_video_lungo",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titolo": {"type": "string"},
            "gioco": {"type": "string"},
            "query_video": {"type": "string"},
            "descrizione": {"type": "string"},
            "indice_notizia": {"type": "integer"},
            "sezioni": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titolo": {"type": "string"},
                        "contenuto": {"type": "string"},
                    },
                    "required": ["titolo", "contenuto"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["titolo", "gioco", "query_video", "descrizione",
                     "indice_notizia", "sezioni"],
        "additionalProperties": False,
    },
}


def _prompt_scaletta(notizie, titoli_recenti, giochi_recenti):
    lingua = brain._lingua()["nome"]
    quante = config.SEZIONI_VIDEO_LUNGO
    minuti = config.MINUTI_VIDEO_LUNGO

    blocco_notizie = "NESSUNA notizia fresca disponibile."
    if notizie:
        blocco_notizie = "\n".join(
            f"  [{i}] {n['titolo']}  (fonte: {n['fonte']})"
            for i, n in enumerate(notizie)
        )

    return (
        f"Sei l'autore di '{config.NOME_CANALE}', canale YouTube di "
        f"videogiochi. Prepara la SCALETTA di un video da {minuti:.0f} minuti "
        f"su UN SOLO gioco, diviso in {quante} sezioni.\n\n"
        f"LINGUA DELL'OUTPUT: {lingua}. Titolo, titoli delle sezioni e "
        f"descrizione vanno scritti interamente in {lingua}.\n\n"
        "Questo NON e' uno Short. Nessuna fretta, nessun loop, nessun amo da "
        "tre secondi: chi guarda un video lungo vuole capire una cosa a "
        "fondo, e resta solo se ogni sezione gli dice qualcosa che non "
        "sapeva.\n\n"
        f"NOTIZIE GAMING DI OGGI, IN ORDINE DI IMPORTANZA:\n{blocco_notizie}\n\n"
        "REGOLE:\n"
        "1. GIOCO: un solo gioco per tutto il video, col titolo ESATTO e "
        "UFFICIALE come appare sullo store (es: 'Cyberpunk 2077', "
        "'ELDEN RING'). Serve a scaricare i trailer ufficiali di QUEL gioco: "
        "niente abbreviazioni, niente nomi di saghe.\n"
        "2. Il video puo' partire da una delle notizie elencate sopra: in tal "
        "caso metti il suo indice in 'indice_notizia', altrimenti -1. Se non "
        "citi una notizia, NON inventare date di uscita, leak o numeri di "
        "vendita: parla di meccaniche, storia del gioco, segreti, consigli.\n"
        f"3. SEZIONI: esattamente {quante}. Ognuna ha un titolo breve (2-5 "
        "parole, diventa un capitolo YouTube) e un campo 'contenuto' che dice "
        "in due righe COSA va raccontato li' dentro. Le sezioni devono "
        "procedere, non ripetersi: se la seconda e la quarta dicono la stessa "
        "cosa con parole diverse, la scaletta e' sbagliata.\n"
        "4. La prima sezione entra subito nel merito. Vietato aprire con "
        "saluti, con 'in questo video' o con la presentazione del canale.\n"
        "5. L'ultima sezione chiude con un giudizio o una domanda, non con un "
        "riassunto di quello gia' detto.\n"
        "6. TITOLO del video: massimo 70 caratteri, il nome del gioco dentro, "
        "niente maiuscolo integrale, niente '#Shorts'.\n"
        "7. QUERY VIDEO: in INGLESE, 2-4 parole, usata solo come ripiego se "
        "il gioco non si trova sullo store.\n"
        "8. DESCRIZIONE: tre righe che dicono cosa si vede nel video.\n"
        "9. NON riusare questi titoli gia' pubblicati:\n"
        f"   {json.dumps(titoli_recenti, ensure_ascii=False)}\n"
        "10. NON riparlare di questi giochi, gia' usati di recente:\n"
        f"   {json.dumps(giochi_recenti, ensure_ascii=False)}\n\n"
        "Rispondi ESCLUSIVAMENTE con un JSON valido con le chiavi: "
        "'titolo', 'gioco', 'query_video', 'descrizione', 'indice_notizia', "
        "'sezioni'."
    )


def _prompt_sezione(scaletta, indice, sezione, coda_precedente, notizia):
    lingua = brain._lingua()["nome"]
    quante = len(scaletta["sezioni"])
    bersaglio = parole_per_sezione()

    pezzi = [
        f"Stai scrivendo il video di '{config.NOME_CANALE}' su "
        f"{scaletta['gioco'] or 'questo gioco'}, intitolato "
        f"\"{scaletta['titolo']}\".",
        f"LINGUA: {lingua}, e soltanto quella.",
        f"Scrivi SOLO la sezione {indice + 1} di {quante}: "
        f"\"{sezione['titolo']}\".",
        f"Cosa deve dire: {sezione['contenuto']}",
        f"Lunghezza: circa {bersaglio} parole, mai meno di "
        f"{MIN_PAROLE_SEZIONE}.",
    ]

    if notizia:
        pezzi.append(
            f"Questa e' la notizia da cui nasce il video, e gli unici fatti "
            f"di cronaca che puoi affermare sono i suoi: {notizia}"
        )
    else:
        pezzi.append(
            "Non hai una fonte di cronaca: NON affermare date di uscita, "
            "leak, annunci o numeri di vendita. Meccaniche, storia del gioco, "
            "segreti e consigli non hanno bisogno di fonte e vanno benissimo."
        )

    if coda_precedente:
        pezzi.append(
            f"La sezione precedente finiva cosi': \"{coda_precedente}\". "
            "Riparti da li' senza ripeterla e senza annunciare cosa stai per "
            "dire."
        )
    elif indice == 0:
        pezzi.append(
            "E' l'apertura del video: entra subito nel merito. Vietato "
            "salutare, vietato presentare il canale, vietato dire cosa "
            "vedremo."
        )

    if indice == quante - 1:
        pezzi.append(
            f"E' l'ultima sezione: chiudi con un giudizio netto o una domanda "
            f"agli spettatori, e un invito breve a iscriversi a "
            f"{config.NOME_CANALE}."
        )

    pezzi.append(
        "Scrivi SOLO il testo parlato, di seguito, senza titoli, senza "
        "elenchi puntati, senza sigle e senza indicazioni di regia. Verra' "
        "letto da una voce sintetica cosi' com'e'."
    )
    return "\n".join(pezzi)


def _chiedi(system, utente, schema=None, max_tokens=2000):
    """Una chiamata a Groq, provando i modelli configurati in ordine."""
    for modello in config.GROQ_MODELLI:
        for tentativo in (1, 2):
            try:
                parametri = {
                    "model": modello,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": utente},
                    ],
                    "temperature": 0.85,
                    "max_tokens": max_tokens,
                }
                if schema and tentativo == 1:
                    parametri["response_format"] = {
                        "type": "json_schema", "json_schema": schema,
                    }
                if "gpt-oss" in modello:
                    parametri["reasoning_effort"] = "low"

                risposta = brain.client.chat.completions.create(**parametri)
                contenuto = risposta.choices[0].message.content
                if contenuto and contenuto.strip():
                    return contenuto
                print("[Samaritan Lungo] Risposta vuota, riprovo.")
            except Exception as e:
                print(f"[Groq Warning] {modello}: {e}")
    return None


def _pulisci_sezione(testo):
    """Toglie dal parlato quello che la voce non deve leggere."""
    testo = re.sub(r"^\s*#+\s*", "", testo or "", flags=re.MULTILINE)
    # Gli asterischi del grassetto: la voce non li legge (li toglie gia'
    # pulisci_testo) ma finirebbero nei sottotitoli e in cronologia.
    testo = testo.replace("*", "")
    testo = re.sub(r"^\s*(sezione|parte|capitolo)\s*\d+\s*[:.\-]\s*", "",
                   testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+", " ", testo)
    return testo.strip()


def _coda(testo, parole=14):
    return " ".join((testo or "").split()[-parole:])


def genera_video_lungo(tema=None):
    """Scrive il video lungo. Ritorna il pacchetto contenuto, o solleva.

    Il dizionario ha le stesse chiavi dello Short (titolo, script, gioco,
    query_video, descrizione, fonte, fonte_url, stile) piu' 'sezioni', che e'
    quello che serve a produrre audio e capitoli.
    """
    notizie = brain.recupera_trend_gaming_online(tema=tema)

    # Solo i video lunghi gia' usciti: quello che ha detto uno Short da mezzo
    # minuto non vincola un video da otto.
    cronologia = brain._stesso_formato(brain._stessa_lingua(
        [brain._normalizza(v) for v in brain.carica_cronologia()]
    ))
    titoli_recenti = [v.get("titolo", "") for v in cronologia[-12:]]
    giochi_recenti = sorted({
        (v.get("gioco") or "").strip()
        for v in cronologia[-6:] if (v.get("gioco") or "").strip()
    })
    if tema:
        # Un argomento chiesto a mano vince sulla regola anti-ripetizione.
        giochi_recenti = []

    system = _prompt_scaletta(notizie, titoli_recenti, giochi_recenti)
    utente = "Prepara la scaletta del video di oggi."
    if tema:
        utente += (f" Il proprietario del canale ha chiesto un video su questo "
                   f"argomento, ed e' obbligatorio: {tema}.")

    grezza = _chiedi(system, utente, schema=_SCHEMA_SCALETTA, max_tokens=2500)
    if not grezza:
        raise RuntimeError(
            "Nessun modello Groq ha risposto alla scaletta del video lungo: "
            f"provati {', '.join(config.GROQ_MODELLI)}."
        )

    try:
        scaletta = json.loads(grezza)
    except json.JSONDecodeError:
        scaletta = brain._estrai_json(grezza)

    sezioni = [s for s in (scaletta.get("sezioni") or [])
               if (s.get("titolo") or "").strip()]
    if len(sezioni) < MIN_CAPITOLI:
        raise RuntimeError(
            f"La scaletta ha {len(sezioni)} sezioni: ne servono almeno "
            f"{MIN_CAPITOLI} perche' YouTube riconosca i capitoli."
        )
    scaletta["sezioni"] = sezioni

    titolo = brain._pulisci_titolo(str(scaletta.get("titolo", "")))
    gioco = brain._pulisci_nome_gioco(str(scaletta.get("gioco", "")))
    scaletta["titolo"] = titolo
    scaletta["gioco"] = gioco

    fonte, fonte_url = "", ""
    try:
        idx = int(scaletta.get("indice_notizia", -1))
        if 0 <= idx < len(notizie):
            fonte = f"{notizie[idx]['titolo']} ({notizie[idx]['fonte']})"
            fonte_url = notizie[idx].get("link", "")
    except (TypeError, ValueError):
        pass

    print(f"[Samaritan Lungo] '{titolo}' su '{gioco or 'nessun gioco'}', "
          f"{len(sezioni)} sezioni.")
    for i, s in enumerate(sezioni, 1):
        print(f"[Samaritan Lungo]   {i}. {s['titolo']}")

    scritte, coda = [], ""
    for i, sezione in enumerate(sezioni):
        testo = _scrivi_sezione(scaletta, i, sezione, coda, fonte)
        scritte.append({"titolo": sezione["titolo"].strip(), "testo": testo})
        coda = _coda(testo)

    script = "\n\n".join(s["testo"] for s in scritte)
    parole = len(script.split())
    print(f"[Samaritan Lungo] Testo pronto: {parole} parole, "
          f"circa {parole / PAROLE_AL_MINUTO:.1f} minuti.")

    query_video = str(scaletta.get("query_video", "gameplay")).strip()
    if "gameplay" not in query_video.lower():
        query_video = f"{query_video} gameplay"

    risultato = {
        "titolo": titolo,
        "script": script,
        "sezioni": scritte,
        "gioco": gioco,
        "query_video": query_video,
        "descrizione": str(scaletta.get("descrizione", "")).strip(),
        "fonte": fonte,
        "fonte_url": fonte_url,
        "stile": "VIDEO_LUNGO",
    }
    brain.salva_in_cronologia(risultato)
    return risultato


def _scrivi_sezione(scaletta, indice, sezione, coda_precedente, fonte):
    """Il testo parlato di una sezione. Non torna mai vuoto: o scrive, o alza.

    Se il modello risponde troppo corto si riprova una volta dicendogli che e'
    troppo corto; alla seconda si tiene quello che c'e'. Una sezione magra
    accorcia il video, una sezione mancante lo spezza a meta'.
    """
    system = "Scrivi il testo parlato di una sezione di un video di videogiochi."
    utente = _prompt_sezione(scaletta, indice, sezione, coda_precedente, fonte)

    migliore = ""
    for giro in (1, 2):
        grezzo = _chiedi(system, utente, max_tokens=2000)
        testo = _pulisci_sezione(grezzo)
        if len(testo.split()) > len(migliore.split()):
            migliore = testo
        if len(testo.split()) >= MIN_PAROLE_SEZIONE:
            break
        if giro == 1:
            print(f"[Samaritan Lungo] Sezione {indice + 1} troppo corta "
                  f"({len(testo.split())} parole), riprovo.")
            utente += (
                f"\nIl tentativo precedente era di sole {len(testo.split())} "
                f"parole: troppo corto. Scrivine almeno "
                f"{parole_per_sezione()}."
            )

    if not migliore:
        raise RuntimeError(
            f"Sezione {indice + 1} ('{sezione['titolo']}') rimasta vuota: "
            "meglio saltare il video che pubblicarlo mutilato."
        )

    parole = migliore.split()
    if len(parole) > MAX_PAROLE_SEZIONE:
        migliore = " ".join(parole[:MAX_PAROLE_SEZIONE])
        migliore = brain._senza_coda_troncata(migliore) or migliore
    print(f"[Samaritan Lungo] Sezione {indice + 1}/"
          f"{len(scaletta['sezioni'])} '{sezione['titolo']}': "
          f"{len(migliore.split())} parole.")
    return migliore


# ===========================================================================
# AUDIO E CAPITOLI
# ===========================================================================
def _durata_audio(percorso):
    """Durata in secondi di un file audio, letta con ffprobe."""
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", percorso,
    ]
    uscita = subprocess.run(comando, check=True, timeout=60,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return float(uscita.stdout.decode().strip())


def _silenzio(percorso, secondi=PAUSA_FRA_SEZIONI):
    """Un file di silenzio da infilare fra una sezione e l'altra."""
    from gameplay import _ffmpeg
    comando = [
        _ffmpeg(), "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(secondi), "-c:a", "libmp3lame", "-q:a", "9", percorso,
    ]
    subprocess.run(comando, check=True, timeout=60,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return percorso


def produci_audio_e_capitoli(sezioni):
    """Genera l'audio sezione per sezione e lo unisce in un file solo.

    Ritorna (percorso_audio, capitoli), dove capitoli e' una lista di
    (secondi_di_inizio, titolo). I secondi sono misurati sui file veri, non
    stimati sulle parole: un timestamp sbagliato di venti secondi in un video
    lungo e' peggio che non avere capitoli.
    """
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    pezzi, capitoli, istante = [], [], 0.0

    pausa = None
    if PAUSA_FRA_SEZIONI > 0:
        try:
            pausa = _silenzio(os.path.join(config.DIR_TEMP, "pausa.mp3"))
            durata_pausa = _durata_audio(pausa)
        except Exception as e:
            print(f"[Samaritan Lungo] Niente pause fra le sezioni ({e}).")
            pausa, durata_pausa = None, 0.0
    else:
        durata_pausa = 0.0

    for i, sezione in enumerate(sezioni):
        destinazione = os.path.join(config.DIR_TEMP, f"sezione_{i:02d}.mp3")
        percorso = genera_voce_samaritan(sezione["testo"], destinazione)
        if not percorso:
            raise RuntimeError(
                f"Voce non generata per la sezione {i + 1} "
                f"('{sezione['titolo']}')."
            )
        durata = _durata_audio(percorso)

        if pausa and pezzi:
            pezzi.append(pausa)
            istante += durata_pausa

        capitoli.append((istante, sezione["titolo"]))
        pezzi.append(percorso)
        istante += durata

    audio = _unisci_audio(pezzi)
    print(f"[Samaritan Lungo] Audio completo: {istante / 60:.1f} minuti, "
          f"{len(capitoli)} capitoli.")
    return audio, capitoli


def _unisci_audio(pezzi):
    """Attacca i pezzi in un mp3 solo con il demuxer concat di ffmpeg."""
    from gameplay import _ffmpeg

    elenco = os.path.join(config.DIR_TEMP, "sezioni.txt")
    with open(elenco, "w", encoding="utf-8") as f:
        for pezzo in pezzi:
            percorso = os.path.abspath(pezzo).replace("'", r"'\''")
            f.write(f"file '{percorso}'\n")

    destinazione = os.path.join(config.DIR_TEMP, "audio.mp3")
    comando = [
        _ffmpeg(), "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", elenco,
        # Si ricodifica invece di copiare: i pezzi possono avere parametri
        # diversi (la voce di ripiego non e' quella principale) e un mp3
        # concatenato a crudo da parametri diversi si sente scattare.
        "-c:a", "libmp3lame", "-q:a", "4", destinazione,
    ]
    subprocess.run(comando, check=True, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return destinazione


def formatta_capitoli(capitoli):
    """I capitoli come li vuole YouTube nella descrizione: '0:00 Titolo'.

    Torna stringa vuota se non sono validi, invece di scrivere righe che
    YouTube ignorerebbe: meno di tre capitoli, il primo non a zero, o due
    capitoli a meno di dieci secondi l'uno dall'altro.
    """
    if len(capitoli) < MIN_CAPITOLI:
        return ""
    if capitoli[0][0] > 0.5:
        return ""
    for (prima, _), (dopo, _) in zip(capitoli, capitoli[1:]):
        if dopo - prima < MIN_SECONDI_CAPITOLO:
            return ""

    righe = []
    for secondi, titolo in capitoli:
        secondi = int(secondi)
        minuti, resto = divmod(secondi, 60)
        ore, minuti = divmod(minuti, 60)
        marca = (f"{ore}:{minuti:02d}:{resto:02d}" if ore
                 else f"{minuti}:{resto:02d}")
        righe.append(f"{marca} {titolo.strip()}")
    return "\n".join(righe)
