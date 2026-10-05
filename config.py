"""
Configurazione centralizzata di Samaritan.

Tutti i segreti vivono qui e SOLO qui, letti da variabili d'ambiente
(.env in locale, GitHub Secrets su Actions). Nessuna chiave hardcoded.
"""
import os
import sys

import profilo

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
# Di cosa parla il canale, dove cerca le notizie, da dove prende il materiale:
# tutto in canale.json (vedi profilo.py). Senza file e' Poppone TV di sempre.
# Il profilo si legge qui all'avvio apposta: un file sbagliato deve fermare la
# lavorazione subito, con un messaggio chiaro, e non a meta' montaggio.
try:
    PROFILO = profilo.attivo()
except profilo.ProfiloNonValido as e:
    print(f"[Config] ERRORE: {e}")
    print("         Controlla il file (vedi canale.esempio.json) o toglilo per "
          "tornare al profilo predefinito.")
    sys.exit(1)

# Le variabili d'ambiente vincono sul file: il workflow di popponetv le
# imposta gia' e deve continuare a funzionare com'e'.
NOME_CANALE = _get("NOME_CANALE", PROFILO.nome_canale)
# Handle YouTube: finisce nella descrizione di ogni video come link al canale.
HANDLE_CANALE = _get("HANDLE_CANALE", PROFILO.handle)

# Lingua, uscita coperta, orario di pubblicazione e voce di questa run: li
# decide risolvi_uscita() qui sotto, a partire dal profilo del canale.
#
# SLOT e' quale delle uscite giornaliere sta coprendo questa run ('14:00',
# '18:00'...), oppure vuoto per le run lanciate a mano. Non e' l'ora di
# pubblicazione, che e' ORARIO_USCITA: SLOT serve solo a non pubblicare due
# volte lo stesso video quando una run arriva in ritardo e un'altra l'ha gia'
# fatto. Di norma i due valori coincidono; la run di recupero invece ha SLOT
# pieno e ORARIO_USCITA vuoto, perche' recupera un'uscita saltata e la
# pubblica subito.
LINGUA = "it"
SLOT = ""
ORARIO_USCITA = ""
VOCE_TTS = ""
# L'uscita del profilo coperta da questa run ({'orario', 'lingua'}), o None.
USCITA_SCELTA = None
# Vero quando questa e' una partenza notturna senza un'uscita da coprire: un
# canale con due uscite al giorno lascia libere due partenze su quattro.
NESSUNA_USCITA = False
# L'istante dell'uscita coperta (secondi epoch), deciso da main.prepara_uscita
# e scritto in cronologia accanto a SLOT.
USCITA = None
# La run di recupero non sa in partenza quale uscita le tocchera': lo decide
# leggendo la cronologia, e con esso sceglie lingua e voce fra queste due.
RECUPERO = _get("RECUPERO", "") not in ("", "0", "false", "False")
VOCE_TTS_IT = _get("VOCE_TTS_IT", "it-IT-GiuseppeMultilingualNeural")
VOCE_TTS_EN = _get("VOCE_TTS_EN", "en-US-AndrewMultilingualNeural")
# Le voci "Multilingual" sono le piu' nuove di Microsoft e suonano meno
# sintetiche. Se un giorno Edge-TTS ne rifiuta una, voice.py riprova con la
# voce classica della stessa lingua prima di cadere su gTTS.
VOCE_TTS_RISERVA = {"it": "it-IT-DiegoNeural", "en": "en-US-AndrewNeural"}


def risolvi_uscita():
    """Decide quale uscita copre questa run, e da li' lingua, orari e voce.

    Prima questi valori li scriveva il workflow, uno per cron, con gli orari
    di Poppone TV dentro le espressioni. Ora il workflow dice solo QUALE
    partenza e' (USCITA_CRON, da 1 a 4) oppure, per le run a mano, quale
    uscita coprire (USCITA_RICHIESTA: il numero nella giornata o l'orario);
    orario e lingua arrivano dal profilo.

    Le variabili d'ambiente ORARIO_USCITA, SLOT, LINGUA e VOCE_TTS, quando
    ci sono, vincono: servono alle prove in locale. Il workflow passa LINGUA
    solo per le run a mano che non coprono un'uscita.
    """
    global LINGUA, SLOT, ORARIO_USCITA, VOCE_TTS, USCITA_SCELTA, NESSUNA_USCITA
    cron = _get("USCITA_CRON", "")
    richiesta = _get("USCITA_RICHIESTA", "")
    uscita = None
    NESSUNA_USCITA = False
    if cron:
        if not cron.isdigit():
            raise profilo.ProfiloNonValido(
                f"USCITA_CRON deve essere il numero della partenza, non '{cron}'.")
        uscita = profilo.uscita_del_cron(PROFILO, int(cron))
        NESSUNA_USCITA = uscita is None
    elif richiesta:
        uscita = profilo.uscita_richiesta(PROFILO, richiesta)
    USCITA_SCELTA = uscita

    ORARIO_USCITA = _get("ORARIO_USCITA", uscita["orario"] if uscita else "")
    SLOT = _get("SLOT", uscita["orario"] if uscita else "")
    # Senza un'uscita (run a mano, riserva prima che scelga) la lingua e'
    # comunque una di quelle in cui il canale pubblica. Il menu della run a
    # mano parte da 'it', e anche il video di prova della pagina di
    # installazione: un canale solo inglese non deve uscirne in italiano.
    # Per Poppone TV, che pubblica in tutt'e due, non cambia niente.
    lingue_del_canale = [u["lingua"] for u in PROFILO.uscite_in_ordine]
    LINGUA = _get("LINGUA", uscita["lingua"] if uscita else lingue_del_canale[0])
    if not uscita and (LINGUA or "").lower() not in lingue_del_canale:
        print(f"[Config] Il canale non pubblica in '{LINGUA}': questa run "
              f"esce in '{lingue_del_canale[0]}'.")
        LINGUA = lingue_del_canale[0]
    # La voce segue la lingua: prima il workflow la sceglieva con la stessa
    # espressione della lingua, ripetuta.
    VOCE_TTS = _get("VOCE_TTS",
                    VOCE_TTS_EN if (LINGUA or "").lower() == "en" else VOCE_TTS_IT)


try:
    risolvi_uscita()
except profilo.ProfiloNonValido as e:
    print(f"[Config] ERRORE: {e}")
    sys.exit(1)

# ------------------------------------------ Credenziali YouTube (senza file)
# Il secondo modo di collegare YouTube, quello della pagina di installazione:
# tre Secrets invece di client_secret.json e token.pickle in base64. Se c'e'
# token.pickle vince lui (vedi uploader.ottieni_credenziali).
YOUTUBE_CLIENT_ID = _get("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = _get("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = _get("YOUTUBE_REFRESH_TOKEN")

# ------------------------------------------------------------------ Voce (TTS)
# Voce neurale Microsoft Edge. Voci italiane disponibili:
#   it-IT-GiuseppeMultilingualNeural (maschile, la piu' naturale -> predefinita)
#   it-IT-DiegoNeural     (maschile, energico, riserva)
#   it-IT-IsabellaNeural  (femminile, brillante)
#   it-IT-GiuseppeNeural  (maschile, caldo)
# VOCE_TTS, la voce di questa run, la sceglie risolvi_uscita() in base alla
# lingua: VOCE_TTS_IT o VOCE_TTS_EN, se la variabile non c'e'.
VOCE_VELOCITA = _get("VOCE_VELOCITA", "+12%")   # gli Shorts virali parlano veloce
# Tono naturale: alzarlo (era +8Hz) rendeva la voce piu' metallica.
VOCE_PITCH = _get("VOCE_PITCH", "+0Hz")

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
# Conta solo se il profilo del canale ha materiale 'steam': un canale che non
# parla di videogiochi su Steam non ci va mai (vedi gameplay._usa_steam).
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
# il caso delle run lanciate a mano. ORARIO_USCITA lo sceglie risolvi_uscita()
# dalle uscite del profilo; il fuso e' quello del profilo. Vedi orari.py.
FUSO_USCITA = _get("FUSO_USCITA", PROFILO.fuso)

# ------------------------------------------------ Notifiche Telegram (opzionali)
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
TELEGRAM_ATTIVO = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ------------------------------------------- Instagram (i Reel promozionali)
# Profilo SEPARATO da quello di gaming: qui Samaritan racconta se stesso e
# vende l'installazione, non parla di videogiochi. Se queste variabili non ci
# sono, promo.py produce il Reel su disco e non pubblica niente: nessun pezzo
# della pipeline YouTube le legge.
INSTAGRAM_TOKEN = _get("INSTAGRAM_TOKEN")
INSTAGRAM_USER_ID = _get("INSTAGRAM_USER_ID")
INSTAGRAM_ATTIVO = bool(INSTAGRAM_TOKEN and INSTAGRAM_USER_ID)
INSTAGRAM_API = _get("INSTAGRAM_API", "v25.0")

# Come si chiama Samaritan sul profilo Instagram e dove si compra.
NOME_PROMO = _get("NOME_PROMO", "Samaritan")
CONTATTO_PROMO = _get("CONTATTO_PROMO", "scrivimi in DM")

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
