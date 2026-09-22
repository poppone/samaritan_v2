"""
Configurazione centralizzata di Samaritan.

Tutti i segreti vivono qui e SOLO qui, letti da variabili d'ambiente
(.env in locale, GitHub Secrets su Actions). Nessuna chiave hardcoded.
"""
import os
import sys

# Caricamento .env opzionale: su GitHub Actions le variabili arrivano dai Secrets
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get(nome, default=None, obbligatoria=False):
    valore = os.getenv(nome)
    if isinstance(valore, str):
        valore = valore.strip()
    # Su GitHub Actions una variabile di repository non impostata arriva come
    # stringa VUOTA, non come assente: con os.getenv(nome, default) il default
    # non scatterebbe mai e la configurazione resterebbe a mani vuote.
    if not valore:
        valore = default
        if isinstance(valore, str):
            valore = valore.strip()
    # Scarta i placeholder rimasti nel .env
    if valore and valore.startswith("inserisci_qui"):
        valore = None
    if obbligatoria and not valore:
        print(f"[Config] ERRORE: la variabile '{nome}' non e' configurata.")
        print(f"         Impostala nel file .env (locale) o nei GitHub Secrets (Actions).")
        sys.exit(1)
    return valore


# ---------------------------------------------------------------- API esterne
GROQ_API_KEY = _get("GROQ_API_KEY", obbligatoria=True)
PEXELS_API_KEY = _get("PEXELS_API_KEY", obbligatoria=True)

# ElevenLabs: voce piu' realistica di Edge-TTS, ma a consumo. Se la chiave non
# c'e' o il credito finisce, voice.py ripiega da solo su Edge-TTS: il video
# esce comunque, con la voce di prima.
ELEVENLABS_API_KEY = _get("ELEVENLABS_API_KEY")
# Nome della voce come appare su elevenlabs.io, oppure il suo id. Vuoto = si
# usa la prima voce dell'account. Si possono elencare piu' nomi separati da
# virgola: in quel caso Samaritan li alterna, un video a testa a giro.
ELEVENLABS_VOCE = _get("ELEVENLABS_VOCE", "")
ELEVENLABS_VOCI = [v.strip() for v in ELEVENLABS_VOCE.split(",") if v.strip()]
# multilingual_v2 e' il modello con la resa migliore in italiano; turbo costa
# meno della meta' ma suona piu' piatto.
ELEVENLABS_MODELLO = _get("ELEVENLABS_MODELLO", "eleven_multilingual_v2")
# Stabilita bassa = piu' espressivo e piu' variabile; alta = piu' monotono.
ELEVENLABS_STABILITA = float(_get("ELEVENLABS_STABILITA", "0.45"))
ELEVENLABS_SOMIGLIANZA = float(_get("ELEVENLABS_SOMIGLIANZA", "0.8"))

# Modelli Groq da provare, in ordine di preferenza. Groq sposta i modelli fra i
# piani senza preavviso: quando uno non e' piu' accessibile risponde 404 e
# Samaritan ripiega sul testo finto, in silenzio. Per cambiarli basta il Secret
# GROQ_MODELLI (nomi separati da virgola), senza rimettere mano al codice.
# Elenco aggiornato: https://console.groq.com/docs/models
_GROQ_MODELLI_DEFAULT = "openai/gpt-oss-120b,openai/gpt-oss-20b"
GROQ_MODELLI = [
    m.strip() for m in _get("GROQ_MODELLI", _GROQ_MODELLI_DEFAULT).split(",") if m.strip()
] or _GROQ_MODELLI_DEFAULT.split(",")

# ------------------------------------------------------------ Identita canale
NOME_CANALE = _get("NOME_CANALE", "Poppone TV")
# Handle YouTube: finisce nella descrizione di ogni video come link al canale.
HANDLE_CANALE = _get("HANDLE_CANALE", "@PopponeTV")
LINGUA = _get("LINGUA", "it")

# Quale delle uscite giornaliere sta coprendo questa run ('14:00', '18:00',
# '21:00'), oppure vuoto per le run lanciate a mano. Non e' l'ora di
# pubblicazione, che e' ORARIO_USCITA piu' sotto: SLOT serve solo a non
# pubblicare due volte lo stesso video quando una run arriva in ritardo e
# un'altra l'ha gia' fatto. Di norma i due valori coincidono; la run di
# recupero invece ha SLOT pieno e ORARIO_USCITA vuoto, perche' recupera
# un'uscita saltata e la pubblica subito.
SLOT = _get("SLOT", "")
# La run di recupero non sa in partenza quale uscita le tocchera': lo decide
# leggendo la cronologia, e con esso sceglie lingua e voce fra queste due.
RECUPERO = _get("RECUPERO", "") not in ("", "0", "false", "False")
VOCE_TTS_IT = _get("VOCE_TTS_IT", "it-IT-DiegoNeural")
VOCE_TTS_EN = _get("VOCE_TTS_EN", "en-US-AndrewNeural")

# ------------------------------------------------------------------ Voce (TTS)
# Voce neurale Microsoft Edge. Voci italiane disponibili:
#   it-IT-DiegoNeural     (maschile, energico  -> consigliata per il gaming)
#   it-IT-IsabellaNeural  (femminile, brillante)
#   it-IT-GiuseppeNeural  (maschile, caldo)
VOCE_TTS = _get("VOCE_TTS", "it-IT-DiegoNeural")
VOCE_VELOCITA = _get("VOCE_VELOCITA", "+12%")   # gli Shorts virali parlano veloce
VOCE_PITCH = _get("VOCE_PITCH", "+8Hz")         # leggermente piu alto = piu "sveglio"

# -------------------------------------------------------------- Formato video
# Samaritan produce due cose diverse con la stessa pipeline:
#
#   Short  9:16, mezzo minuto, tre al giorno. E' quello che il canale fa da
#          sempre.
#   Lungo  16:9, otto minuti, uno al giorno. Serve alla seconda porta del
#          programma partner YouTube: 1.000 iscritti piu' 4.000 ore di
#          visione in 12 mesi. Le ore guardate sugli Short NON contano per
#          quella soglia, quindi un canale di soli Short quella porta non la
#          apre mai, e l'altra (10 milioni di visualizzazioni in 90 giorni)
#          e' fuori portata di due ordini di grandezza.
#
# Quasi tutto il resto del codice non sa quale dei due sta facendo: legge le
# misure da qui e si comporta di conseguenza.
VIDEO_LUNGO = _get("VIDEO_LUNGO", "") not in ("", "0", "false", "False")

# Quanto dura il video lungo e in quante parti e' diviso. Le parti non sono un
# dettaglio di scrittura: ognuna ha il suo pezzo di audio, e da quelle durate
# escono i capitoli veri della descrizione YouTube.
MINUTI_VIDEO_LUNGO = float(_get("MINUTI_VIDEO_LUNGO", "8"))
SEZIONI_VIDEO_LUNGO = int(_get("SEZIONI_VIDEO_LUNGO", "6"))

# ---------------------------------------------------------------- Rendering
# I valori qui sotto li imposta applica_formato(), perche' quasi tutti
# cambiano fra Short e video lungo. Sono dichiarati prima solo per avere un
# posto dove leggerli.
VIDEO_W = VIDEO_H = FPS = 0
STACCO_MIN = STACCO_MAX = 0.0
NUM_CLIP_SFONDO = 0
PRESET_RENDER = ""
WHISPER_MODEL = _get("WHISPER_MODEL", "base")   # 'tiny' sbaglia troppe parole in italiano

# ------------------------------------------------- Gameplay reale (Steam)
# Usa trailer e screenshot UFFICIALI del gioco di cui parla il video, invece
# di stock generico. Se il gioco non e' su Steam, si ripiega su Pexels.
USA_STEAM = _get("USA_STEAM", "1") not in ("0", "false", "False")
STEAM_MAX_TRAILER = STEAM_MAX_SCREENSHOT = SECONDI_TRAILER = 0
# I trailer Steam sono 16:9: dentro uno Short vengono inseriti in un 9:16 con
# sfondo sfocato, e questo valore ingrandisce il riquadro di gameplay
# (1.0 = larghezza piena). Nel video lungo il formato coincide e non serve.
ZOOM_GAMEPLAY = float(_get("ZOOM_GAMEPLAY", "1.18"))


def applica_formato(lungo=None):
    """Imposta le misure che dipendono dal formato del video.

    Si chiama una volta all'import, e una seconda volta dalla lavorazione di
    recupero: quella non sa in partenza se le tocchera' rifare uno Short o il
    video lungo, lo scopre leggendo la cronologia, e a quel punto le misure
    gia' calcolate sarebbero quelle sbagliate.

    Ogni valore resta sovrascrivibile da variabile d'ambiente: il formato
    decide solo il valore di partenza.
    """
    global VIDEO_LUNGO, VIDEO_W, VIDEO_H, FPS, STACCO_MIN, STACCO_MAX
    global NUM_CLIP_SFONDO, PRESET_RENDER, VOCE_VELOCITA, MAX_CLIP_MIE
    global STEAM_MAX_TRAILER, STEAM_MAX_SCREENSHOT, SECONDI_TRAILER

    if lungo is not None:
        VIDEO_LUNGO = bool(lungo)

    VIDEO_W = int(_get("VIDEO_W", "1920" if VIDEO_LUNGO else "1080"))
    VIDEO_H = int(_get("VIDEO_H", "1080" if VIDEO_LUNGO else "1920"))
    FPS = int(_get("FPS", "30"))

    # Durata di ogni stacco di montaggio. Nello Short sotto i 3 secondi
    # l'occhio non si annoia mai; nel video lungo lo stesso ritmo darebbe piu'
    # di cento stacchi al minuto e stancherebbe, quindi si respira.
    STACCO_MIN = float(_get("STACCO_MIN", "4.0" if VIDEO_LUNGO else "2.0"))
    STACCO_MAX = float(_get("STACCO_MAX", "7.5" if VIDEO_LUNGO else "3.2"))
    NUM_CLIP_SFONDO = int(_get("NUM_CLIP_SFONDO", "8" if VIDEO_LUNGO else "4"))

    # Otto minuti in 1080p con il preset 'medium' non stanno dentro il tempo
    # massimo di una lavorazione su GitHub. 'veryfast' costa qualche mega in
    # piu' di file e fa risparmiare piu' della meta' del tempo.
    PRESET_RENDER = _get("PRESET_RENDER", "veryfast" if VIDEO_LUNGO else "medium")

    # Gli Short virali parlano veloce. Un video da otto minuti letto alla
    # stessa velocita' diventa faticoso dopo il secondo minuto.
    VOCE_VELOCITA = _get("VOCE_VELOCITA", "+4%" if VIDEO_LUNGO else "+12%")

    # Otto minuti chiedono molto piu' materiale di trenta secondi, altrimenti
    # le stesse inquadrature tornano cinque volte.
    STEAM_MAX_TRAILER = int(_get("STEAM_MAX_TRAILER", "6" if VIDEO_LUNGO else "3"))
    STEAM_MAX_SCREENSHOT = int(_get("STEAM_MAX_SCREENSHOT",
                                    "12" if VIDEO_LUNGO else "4"))
    # Quanti secondi si prendono da ogni trailer ufficiale. Quarantacinque
    # bastano a uno Short; per il video lungo si scarica il trailer intero,
    # che e' proprio la richiesta di popponetv del 22 settembre 2026.
    SECONDI_TRAILER = int(_get("SECONDI_TRAILER", "240" if VIDEO_LUNGO else "45"))
    MAX_CLIP_MIE = int(_get("MAX_CLIP_MIE", "8" if VIDEO_LUNGO else "2"))

# ---------------------------------------------------------------- Pubblicazione
# 'public' = pubblica subito | 'private' = attende la tua approvazione manuale
PRIVACY_STATUS = _get("PRIVACY_STATUS", "public")

# A che ora il video deve COMPARIRE sul canale, ora locale del fuso qui sotto.
# Non e' l'ora in cui parte la pipeline: GitHub fa partire le run schedulate
# con ritardi da un'ora a tre e mezza, quindi il video si carica in anticipo e
# YouTube lo rende pubblico da solo all'istante esatto. Vuoto = subito, ed e'
# il caso delle run lanciate a mano. Lo imposta il workflow, un orario per
# ciascun cron. Vedi orari.py.
ORARIO_USCITA = _get("ORARIO_USCITA", "")
FUSO_USCITA = _get("FUSO_USCITA", "Europe/Rome")

# ------------------------------------------------ Notifiche Telegram (opzionali)
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
TELEGRAM_ATTIVO = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ---------------------------------------------------------------------- File
# Percorsi ASSOLUTI ancorati alla cartella del progetto: il codice funziona
# anche se lanciato da una directory di lavoro diversa (Task Scheduler, cron,
# doppio click sul .bat da un'altra cartella).
DIR_PROGETTO = os.path.dirname(os.path.abspath(__file__))

FILE_CRONOLOGIA = os.path.join(DIR_PROGETTO, "cronologia_trend.json")
FILE_PERFORMANCE = os.path.join(DIR_PROGETTO, "performance.json")
DIR_TEMP = os.path.join(DIR_PROGETTO, "temp_assets")
DIR_OUTPUT = os.path.join(DIR_PROGETTO, "output_videos")

# Le clip girate da popponetv: l'unico materiale originale del canale, tutto
# il resto viene dagli store. Una sottocartella per categoria ('guida',
# 'fortnite') e si montano solo nei video di quella categoria, altrimenti
# stonano piu' di quanto aggiungano. MAX_CLIP_MIE dice quante ne entrano al
# massimo in un video, e nel lungo sono molte di piu': e' li' che il
# materiale originale conta davvero, perche' un video di otto minuti fatto
# solo di trailer si legge come un montaggio automatico.
DIR_CLIP_MIE = os.path.join(DIR_PROGETTO, "clip_mie")
MAX_CLIP_MIE = 0     # impostata da applica_formato()

# Miniatura personalizzata. Senza, YouTube estrae un fotogramma a caso: nella
# griglia del canale si vede, e si vede male.
FILE_MINIATURA = os.path.join(DIR_OUTPUT, "samaritan_miniatura.jpg")

os.makedirs(DIR_TEMP, exist_ok=True)
os.makedirs(DIR_OUTPUT, exist_ok=True)

# Le misure che dipendono dal formato. Ultima riga del modulo, cosi' vale sia
# quando si importa config sia quando la lavorazione di recupero la richiama
# per cambiare formato a meta' strada.
applica_formato()
