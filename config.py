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

# ------------------------------------------------------------------ Voce (TTS)
# Voce neurale Microsoft Edge. Voci italiane disponibili:
#   it-IT-DiegoNeural     (maschile, energico  -> consigliata per il gaming)
#   it-IT-IsabellaNeural  (femminile, brillante)
#   it-IT-GiuseppeNeural  (maschile, caldo)
VOCE_TTS = _get("VOCE_TTS", "it-IT-DiegoNeural")
VOCE_VELOCITA = _get("VOCE_VELOCITA", "+12%")   # gli Shorts virali parlano veloce
VOCE_PITCH = _get("VOCE_PITCH", "+8Hz")         # leggermente piu alto = piu "sveglio"

# ---------------------------------------------------------------- Rendering
VIDEO_W = int(_get("VIDEO_W", "1080"))
VIDEO_H = int(_get("VIDEO_H", "1920"))
FPS = int(_get("FPS", "30"))
# Durata di ogni stacco di montaggio: sotto i 3s l'occhio non si annoia mai
STACCO_MIN = float(_get("STACCO_MIN", "2.0"))
STACCO_MAX = float(_get("STACCO_MAX", "3.2"))
NUM_CLIP_SFONDO = int(_get("NUM_CLIP_SFONDO", "4"))
WHISPER_MODEL = _get("WHISPER_MODEL", "base")   # 'tiny' sbaglia troppe parole in italiano

# ------------------------------------------------- Gameplay reale (Steam)
# Usa trailer e screenshot UFFICIALI del gioco di cui parla lo Short, invece
# di stock generico. Se il gioco non e' su Steam, si ripiega su Pexels.
USA_STEAM = _get("USA_STEAM", "1") not in ("0", "false", "False")
STEAM_MAX_TRAILER = int(_get("STEAM_MAX_TRAILER", "3"))
STEAM_MAX_SCREENSHOT = int(_get("STEAM_MAX_SCREENSHOT", "4"))
# I trailer Steam sono 16:9: vengono inseriti in un 9:16 con sfondo sfocato.
# Questo valore ingrandisce il riquadro di gameplay (1.0 = larghezza piena).
ZOOM_GAMEPLAY = float(_get("ZOOM_GAMEPLAY", "1.18"))

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

# Miniatura personalizzata dello Short. Senza, YouTube estrae un fotogramma a
# caso: nella griglia del canale si vede, e si vede male.
FILE_MINIATURA = os.path.join(DIR_OUTPUT, "samaritan_miniatura.jpg")

os.makedirs(DIR_TEMP, exist_ok=True)
os.makedirs(DIR_OUTPUT, exist_ok=True)
