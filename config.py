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
    valore = os.getenv(nome, default)
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

# ------------------------------------------------------------ Identita canale
NOME_CANALE = _get("NOME_CANALE", "Poppone TV")
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

# ---------------------------------------------------------------- Pubblicazione
# 'public' = pubblica subito | 'private' = attende la tua approvazione manuale
PRIVACY_STATUS = _get("PRIVACY_STATUS", "public")

# ------------------------------------------------ Notifiche Telegram (opzionali)
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
TELEGRAM_ATTIVO = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ---------------------------------------------------------------------- File
FILE_CRONOLOGIA = "cronologia_trend.json"
FILE_PERFORMANCE = "performance.json"
DIR_TEMP = "temp_assets"
DIR_OUTPUT = "output_videos"
