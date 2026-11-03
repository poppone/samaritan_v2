# -*- coding: utf-8 -*-
"""
Taglia le clip dalle live Twitch di popponetv e le consegna a Finch.

Gira sul PC di Davide (taglia_live.bat), NON su GitHub Actions: scaricare e
analizzare VOD di ore brucerebbe i minuti del repository privato.

Per ogni live nuova:
  1. scarica solo l'AUDIO della live (pochi MB l'ora) e ne misura l'energia;
  2. se c'e' TwitchDownloaderCLI, scarica la chat e conta messaggi e reazioni;
  3. trova i momenti migliori (punteggio.py);
  4. per ognuno scarica SOLO quel pezzo di video, lo trascrive con Whisper,
     lo monta verticale 9:16 con i sottotitoli;
  5. propone titolo e descrizione (Groq, se c'e' la chiave);
  6. carica l'mp4 come asset della Release clip-AAAA-MM-GG di samaritan_v2
     e scrive clip_live/da_pubblicare/<id>.json con stato "da_approvare".
Da li' decide Finch. La pubblicazione la fa il workflow clip_live.yml.

Uso:
    python taglia_live.py                 le live nuove (al massimo 2)
    python taglia_live.py --vod 123456    una live precisa
    python taglia_live.py --prova         monta le clip ma non carica niente
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))

from taglia_live import impaginazione, punteggio  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(QUI), ".env"))
    load_dotenv(os.path.join(QUI, ".env"))
except ImportError:
    pass

CANALE = os.getenv("TWITCH_CANALE", "davidedurazzi").strip()
REPO = os.getenv("CLIP_REPO", "poppone/samaritan_v2").strip()
TOKEN = os.getenv("GITHUB_TOKEN_CLIP", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODELLI = [m.strip() for m in os.getenv(
    "GROQ_MODELLI", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
WHISPER = os.getenv("WHISPER_MODELLO_CLIP", "small").strip()
DISPOSITIVO = os.getenv("WHISPER_DISPOSITIVO", "").strip().lower()
TWITCH_DL = os.getenv("TWITCHDOWNLOADER", "TwitchDownloaderCLI").strip()
QUANTE = int(os.getenv("CLIP_PER_LIVE", "5"))
# Versioni lunghe (65-90 s) per TikTok, dai momenti migliori della live. 0 = nessuna.
QUANTE_TIKTOK = int(os.getenv("CLIP_TIKTOK_PER_LIVE", "2"))

LAVORO = os.path.join(QUI, "lavoro")
STATO = os.path.join(QUI, "stato_locale.json")
CARTELLA_REPO = "clip_live/da_pubblicare"
API = "https://api.github.com"


# --------------------------------------------------------------------------
# Stato locale: quali live sono gia' state tagliate
# --------------------------------------------------------------------------

def leggi_stato():
    if not os.path.exists(STATO):
        return {"live_fatte": []}
    with open(STATO, encoding="utf-8") as f:
        return json.load(f)


def salva_stato(stato):
    with open(STATO, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Twitch: elenco live, audio, pezzi di video, chat
# --------------------------------------------------------------------------

def elenco_live(limite=10):
    import yt_dlp
    url = f"https://www.twitch.tv/{CANALE}/videos?filter=archives&sort=time"
    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True,
                           "playlistend": limite}) as ydl:
        info = ydl.extract_info(url, download=False)
    live = []
    for voce in info.get("entries") or []:
        vid = str(voce.get("id", "")).lstrip("v")
        if vid.isdigit():
            live.append(vid)
    return live


def info_live(vod_id):
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        return ydl.extract_info(f"https://www.twitch.tv/videos/{vod_id}",
                                download=False)


def energia_audio(vod_id, cartella):
    """Energia per secondo dell'intera live, scaricando solo l'audio."""
    import numpy as np
    import yt_dlp
    destinazione = os.path.join(cartella, "audio.%(ext)s")
    opzioni = {"format": "Audio_Only/bestaudio/worst", "outtmpl": destinazione,
               "quiet": True, "noprogress": True}
    with yt_dlp.YoutubeDL(opzioni) as ydl:
        info = ydl.extract_info(f"https://www.twitch.tv/videos/{vod_id}")
        percorso = ydl.prepare_filename(info)
    grezzo = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", percorso, "-ac", "1", "-ar", "8000",
         "-f", "s16le", "-"], capture_output=True, check=True).stdout
    campioni = np.frombuffer(grezzo, dtype=np.int16).astype(np.float32)
    secondi = len(campioni) // 8000
    blocchi = campioni[: secondi * 8000].reshape(secondi, 8000)
    rms = np.sqrt((blocchi ** 2).mean(axis=1))
    os.remove(percorso)
    return [float(v) for v in rms]


# Le stesse chiamate che fa il sito di Twitch per mostrare la chat di un VOD
# (e che usa TwitchDownloaderCLI): pubbliche, senza account.
GQL = "https://gql.twitch.tv/gql"
GQL_CLIENT = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
GQL_HASH_CHAT = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"


def chat_gql(vod_id, pagine_max=5000):
    """La chat del VOD senza programmi esterni, pagina per pagina."""
    import requests
    messaggi, cursore = [], None
    for _ in range(pagine_max):
        variabili = {"videoID": vod_id}
        if cursore:
            variabili["cursor"] = cursore
        else:
            variabili["contentOffsetSeconds"] = 0
        r = requests.post(GQL, timeout=30, headers={"Client-Id": GQL_CLIENT}, json=[{
            "operationName": "VideoCommentsByOffsetOrCursor", "variables": variabili,
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": GQL_HASH_CHAT}}}])
        r.raise_for_status()
        commenti = (((r.json()[0].get("data") or {}).get("video") or {})
                    .get("comments") or {})
        lati = commenti.get("edges") or []
        for lato in lati:
            nodo = lato.get("node") or {}
            testo = "".join(f.get("text", "") for f in
                            (nodo.get("message") or {}).get("fragments") or [])
            messaggi.append((nodo.get("contentOffsetSeconds", 0),
                             (nodo.get("commenter") or {}).get("displayName", ""), testo))
        if not lati or not (commenti.get("pageInfo") or {}).get("hasNextPage"):
            break
        cursore = lati[-1].get("cursor")
    return messaggi


def chat_live(vod_id, cartella):
    """[(secondo, autore, testo), ...]: TwitchDownloaderCLI se c'e', altrimenti
    direttamente da Twitch; [] se non va nessuno dei due."""
    if not shutil.which(TWITCH_DL) and not os.path.exists(TWITCH_DL):
        try:
            messaggi = chat_gql(vod_id)
            print(f"[Chat] scaricata da Twitch: {len(messaggi)} messaggi.")
            return messaggi
        except Exception as e:
            print(f"[Chat] ERRORE: chat non scaricata ({e}): conto solo l'audio.")
            return []
    percorso = os.path.join(cartella, "chat.json")
    try:
        subprocess.run([TWITCH_DL, "chatdownload", "--id", vod_id,
                        "-o", percorso, "--collision", "Overwrite"],
                       check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"[Chat] Download fallito ({e}): conto solo l'audio.")
        return []
    with open(percorso, encoding="utf-8") as f:
        dati = json.load(f)
    messaggi = []
    for c in dati.get("comments", []):
        messaggi.append((c.get("content_offset_seconds", 0),
                         (c.get("commenter") or {}).get("display_name", ""),
                         (c.get("message") or {}).get("body", "")))
    return messaggi


def scarica_pezzo(vod_id, inizio, fine, percorso):
    """Solo il pezzo che serve, non la live intera."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    opzioni = {
        "format": "best[height<=1080][fps<=60]/best",
        "outtmpl": percorso,
        "download_ranges": download_range_func(None, [(inizio, fine)]),
        "force_keyframes_at_cuts": True,
        "quiet": True, "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opzioni) as ydl:
        ydl.download([f"https://www.twitch.tv/videos/{vod_id}"])


def gioco_al_secondo(info, secondo):
    """I capitoli di Twitch dicono a che gioco si stava giocando."""
    for capitolo in info.get("chapters") or []:
        if capitolo.get("start_time", 0) <= secondo < capitolo.get("end_time", 1e12):
            return capitolo.get("title") or ""
    return ""


# --------------------------------------------------------------------------
# Trascrizione, sottotitoli, montaggio
# --------------------------------------------------------------------------

_modello = None
_dispositivo = None
NO_PARLATO_MAX = 0.6      # segmenti che per Whisper sono probabilmente silenzio
# avg_logprob sotto questo: parole tirate a indovinare. Davide che parla sopra
# il gioco sta spesso fra -1.0 e -1.2: con -1.0 si perdevano frasi vere.
CONFIDENZA_MIN = -1.4


def _audio_16k(percorso):
    """L'audio della clip come Whisper lo vuole: mono, 16 kHz, float32."""
    import numpy as np
    grezzo = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", percorso, "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0


def _carica_modello(dispositivo):
    from faster_whisper import WhisperModel
    if dispositivo == "cuda":
        return WhisperModel(WHISPER, device="cuda", compute_type="int8_float16")
    return WhisperModel(WHISPER, device="cpu", compute_type="int8")


def _parole(audio):
    # transcribe() e' pigro: gli errori della GPU escono mentre si leggono i
    # segmenti, non quando si chiama. Per questo si legge tutto qui dentro.
    segmenti, _ = _modello.transcribe(audio, language="it",
                                      word_timestamps=True, vad_filter=True)
    parole = []
    for seg in segmenti:
        dette = [p.word.strip() for p in seg.words or []]
        # Via le voci del gioco e quello che Whisper tira a indovinare.
        if (getattr(seg, "no_speech_prob", 0.0) > NO_PARLATO_MAX
                or getattr(seg, "avg_logprob", 0.0) < CONFIDENZA_MIN
                or punteggio.sembra_inglese(dette)):
            continue
        for p in seg.words or []:
            testo = p.word.strip()
            if not testo:
                continue
            # Whisper spezza "c'è" in "c" + "'è": si riattacca, cosi' il
            # sottotitolo non va a capo in mezzo alla parola.
            if parole and testo[0] in "'’":
                inizio, _fine, prima = parole[-1]
                parole[-1] = (inizio, p.end, prima + testo)
                continue
            parole.append((p.start, p.end, testo))
    return parole


def trascrivi(percorso):
    """Parole con i tempi. GPU se funziona davvero, altrimenti CPU.

    WHISPER_DISPOSITIVO=cpu nel .env salta del tutto la prova della GPU.
    Su Windows la GPU NVIDIA spesso si carica ma poi manca cublas64_12.dll
    (le librerie CUDA non sono installate): l'errore arriva alla prima
    trascrizione, e a quel punto si passa alla CPU e si riprova.
    """
    global _modello, _dispositivo
    # L'audio lo decodifica ffmpeg e non faster-whisper: dalla 15 PyAV ha
    # tolto l'opzione metadata_errors che faster-whisper passa ancora ad
    # av.open(), e la trascrizione si fermava con "unexpected keyword".
    audio = _audio_16k(percorso)
    if _modello is None:
        dispositivo = DISPOSITIVO if DISPOSITIVO in ("cpu", "cuda") else "cuda"
        try:
            _modello, _dispositivo = _carica_modello(dispositivo), dispositivo
        except Exception:
            print("[Whisper] GPU non disponibile, uso la CPU.")
            _modello, _dispositivo = _carica_modello("cpu"), "cpu"
    try:
        return _parole(audio)
    except Exception as e:
        if _dispositivo == "cpu":
            raise
        print(f"[Whisper] La GPU non va ({e}): passo alla CPU.")
        _modello, _dispositivo = _carica_modello("cpu"), "cpu"
        return _parole(audio)


def _tempo_ass(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


RIGA_MAX_SECONDI = 3.0    # una riga non resta a schermo piu' di cosi'
RIGA_MAX_CARATTERI = 22   # circa una riga a 78 pt su 1080
PAUSA_NUOVA_RIGA = 0.6    # una pausa nel parlato apre una riga nuova


def gruppi_sottotitoli(parole, per_riga=4):
    """[(inizio, fine, testo), ...] a gruppi di poche parole.

    Un gruppo si chiude a per_riga parole, a RIGA_MAX_CARATTERI o a una
    pausa; non dura piu' di RIGA_MAX_SECONDI (Whisper a volte allunga una
    parola su tutto il silenzio dopo, e la riga restava ferma 12 secondi).
    """
    gruppi, attuale = [], []
    for p in parole:
        if attuale and (len(attuale) >= per_riga
                        or p[0] - attuale[-1][1] > PAUSA_NUOVA_RIGA
                        or len(" ".join(x[2] for x in attuale + [p])) > RIGA_MAX_CARATTERI):
            gruppi.append(attuale)
            attuale = []
        attuale.append(p)
    if attuale:
        gruppi.append(attuale)
    risultato = []
    for g in gruppi:
        inizio = g[0][0]
        fine = min(g[-1][1], g[-1][0] + 1.0, inizio + RIGA_MAX_SECONDI)
        risultato.append((inizio, max(fine, inizio + 0.3), " ".join(x[2] for x in g)))
    return risultato


def scrivi_ass(parole, percorso, per_riga=4, margine=520):
    """Sottotitoli grandi a gruppi di poche parole, come negli Short."""
    righe = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Outline, Shadow, Alignment, MarginV",
        f"Style: Base,Arial,78,&H00FFFFFF,&H00000000,&H64000000,1,6,2,2,{margine}", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Text",
    ]
    for inizio, fine, testo in gruppi_sottotitoli(parole, per_riga):
        testo = testo.upper().replace("{", "").replace("}", "")
        righe.append(f"Dialogue: 0,{_tempo_ass(inizio)},{_tempo_ass(fine)},Base,{testo}")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")


def misure(percorso):
    """Larghezza e altezza del video."""
    uscita = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", percorso],
        capture_output=True, text=True, check=True).stdout.strip()
    w, h = uscita.split(",")[:2]
    return int(w), int(h)


MODELLO_VOLTI = os.path.join(QUI, "modelli", "face_detection_yunet_2023mar.onnx")


def volti_nei_fotogrammi(percorso, durata, quanti=10, ingrandisci=2):
    """I volti trovati in qualche fotogramma, un elenco per fotogramma.

    Si usa YuNet (cv2.FaceDetectorYN), che c'e' sia in OpenCV 4 sia in 5: il
    vecchio CascadeClassifier in OpenCV 5 non c'e' piu'. Il modello (230 KB,
    licenza MIT, da opencv_zoo) sta in taglia_live/modelli/.
    Senza OpenCV o senza modello ritorna [] e la clip resta al centro.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[Webcam] OpenCV non installato: impaginazione al centro.")
        return []
    if not hasattr(cv2, "FaceDetectorYN") or not os.path.exists(MODELLO_VOLTI):
        print("[Webcam] Rilevatore di volti non disponibile: impaginazione al centro.")
        return []
    w, h = misure(percorso)
    # Il volto in una webcam d'angolo e' di 20-30 pixel: a grandezza naturale
    # YuNet lo trova in un fotogramma su sei, ingrandito due volte in tutti.
    rilevatore = cv2.FaceDetectorYN.create(MODELLO_VOLTI, "", (w * ingrandisci, h * ingrandisci),
                                           score_threshold=0.7)
    risultato = []
    for i in range(quanti):
        istante = durata * (i + 0.5) / quanti
        grezzo = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{istante:.2f}", "-i", percorso,
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
            capture_output=True).stdout
        if len(grezzo) != w * h * 3:
            continue
        immagine = np.frombuffer(grezzo, dtype=np.uint8).reshape(h, w, 3)
        if ingrandisci > 1:
            immagine = cv2.resize(immagine, (w * ingrandisci, h * ingrandisci))
        _, volti = rilevatore.detect(immagine)
        risultato.append([] if volti is None else
                         [tuple(int(v / ingrandisci) for v in r[:4]) for r in volti])
    return risultato


def scegli_impaginazione(percorso, durata):
    w, h = misure(percorso)
    scelta, riquadri = impaginazione.scegli(volti_nei_fotogrammi(percorso, durata), w, h)
    print(f"[Webcam] impaginazione: {scelta}")
    return scelta, riquadri


def durata_video(percorso):
    uscita = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", percorso], capture_output=True, text=True).stdout.strip()
    try:
        return float(uscita)
    except ValueError:
        return 0.0


class ClipTronca(Exception):
    """Il montaggio e' finito prima del previsto: la clip non va consegnata."""


class ClipMuta(Exception):
    """Davide parla troppo poco: senza parlato la clip non regge."""


def monta_verticale(sorgente, sottotitoli, uscita, scelta="centro", riquadri=None,
                    inizio=0.0, fine=None):
    """Monta il 9:16 con i sottotitoli bruciati (vedi impaginazione.py).

    inizio/fine tagliano il grezzo (l'hook): i tempi del .ass devono gia'
    essere spostati di conseguenza.
    ffmpeg gira dentro la cartella del lavoro e riceve il nome nudo del file
    .ass: su Windows i due punti di 'C:' rompono il filtro 'ass'.
    """
    cartella = os.path.dirname(sottotitoli)
    filtro = impaginazione.filtro_ffmpeg(scelta, riquadri,
                                         os.path.basename(sottotitoli))
    taglio = ["-ss", f"{inizio:.2f}"]
    if fine is not None:
        taglio += ["-t", f"{fine - inizio:.2f}"]
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *taglio, "-i", os.path.abspath(sorgente),
         "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
         "-af", "loudnorm=I=-14:TP=-1.5", "-c:v", "libx264", "-preset", "medium",
         "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac",
         "-b:a", "160k", "-movflags", "+faststart", os.path.abspath(uscita)],
        cwd=cartella, check=True)
    attesa = (fine if fine is not None else durata_video(sorgente)) - inizio
    ottenuta = durata_video(uscita)
    if ottenuta < attesa - 1.5:
        raise ClipTronca(f"{os.path.basename(uscita)} dura {ottenuta:.1f}s invece di "
                         f"{attesa:.1f}s (montaggio interrotto o grezzo incompleto)")


# --------------------------------------------------------------------------
# Titolo e descrizione
# --------------------------------------------------------------------------

def titolo_di_ripiego(trascritto, gioco):
    """Senza Groq: la frase piu' "forte" del parlato (esclamazioni e domande
    prima, poi la piu' lunga) seguita dal gioco, non piu' "dalla live"."""
    frasi = [f.strip(" ,.;") for f in re.split(r"(?<=[.!?])\s+", trascritto or "")]
    frasi = [f for f in frasi if len(f.split()) >= 3]
    if not frasi:
        return (gioco + " - " if gioco else "") + "dalla live"
    frase = max(frasi, key=lambda f: (f[-1] in "!?", min(len(f), 60)))
    if len(frase) > 60:
        frase = frase[:60].rsplit(" ", 1)[0] + "…"
    frase = frase[0].upper() + frase[1:]
    return f"{frase} | {gioco}" if gioco else frase


def proponi_testi(trascritto, gioco, titolo_live, piattaforma="youtube"):
    etichette = "#twitch #gaming #perte" if piattaforma == "tiktok" else "#shorts #twitch #gaming"
    base_desc = (f"Dalla live su Twitch: https://twitch.tv/{CANALE}\n"
                 f"{('Gioco: ' + gioco) if gioco else ''}\n\n{etichette}")
    ripiego = {"titolo": titolo_di_ripiego(trascritto, gioco), "descrizione": base_desc}
    if not GROQ_KEY:
        print("[Groq] GROQ_API_KEY mancante nel .env: titolo dalla frase migliore.")
        return ripiego
    if not trascritto.strip():
        return ripiego
    from groq import Groq
    client = Groq(api_key=GROQ_KEY)
    domanda = (
        f"Sei l'editor dei video {'TikTok' if piattaforma == 'tiktok' else 'Short YouTube'} "
        "di Davide Durazzi, streamer italiano. "
        "Dal parlato di una clip della sua live proponi un titolo (max 70 "
        "caratteri, italiano, niente clickbait falso, niente emoji in eccesso) "
        "e una descrizione di 1-2 frasi. Non inventare fatti che non sono nel "
        "parlato. Rispondi SOLO con JSON: {\"titolo\": \"...\", \"descrizione\": \"...\"}\n\n"
        f"Gioco: {gioco or 'sconosciuto'}\nTitolo della live: {titolo_live}\n"
        f"Parlato: {trascritto[:2500]}")
    for modello in GROQ_MODELLI:
        try:
            r = client.chat.completions.create(
                model=modello, messages=[{"role": "user", "content": domanda}],
                temperature=0.6, response_format={"type": "json_object"})
            dati = json.loads(r.choices[0].message.content)
            titolo = str(dati.get("titolo", "")).strip()[:100]
            if titolo:
                desc = str(dati.get("descrizione", "")).strip()
                return {"titolo": titolo, "descrizione": f"{desc}\n\n{base_desc}"}
        except Exception as e:
            print(f"[Groq] {modello}: {e}")
    return ripiego


# --------------------------------------------------------------------------
# Consegna: Release per il video, contents API per il JSON
# --------------------------------------------------------------------------

def _gh(metodo, url, **kw):
    import requests
    intestazioni = kw.pop("headers", {})
    intestazioni.update({"Authorization": f"Bearer {TOKEN}",
                         "Accept": "application/vnd.github+json"})
    r = requests.request(metodo, url, headers=intestazioni, timeout=300, **kw)
    return r


def release_del_giorno():
    tag = f"clip-{datetime.now():%Y-%m-%d}"
    r = _gh("GET", f"{API}/repos/{REPO}/releases/tags/{tag}")
    if r.status_code == 200:
        return r.json()
    r = _gh("POST", f"{API}/repos/{REPO}/releases", json={
        "tag_name": tag, "name": f"Clip live {tag[5:]}", "prerelease": True,
        "body": "Clip tagliate dalle live di popponetv, in attesa di Finch."})
    r.raise_for_status()
    return r.json()


def carica_video(release, percorso, nome):
    url = release["upload_url"].split("{")[0] + f"?name={nome}"
    with open(percorso, "rb") as f:
        r = _gh("POST", url, data=f, headers={"Content-Type": "video/mp4"})
    r.raise_for_status()
    return r.json()["url"]          # url API: scaricabile col token anche da privato


def scrivi_scheda(scheda):
    percorso = f"{CARTELLA_REPO}/{scheda['id']}.json"
    contenuto = json.dumps(scheda, ensure_ascii=False, indent=2) + "\n"
    corpo = {"message": f"Clip live {scheda['id']} da approvare",
             "content": base64.b64encode(contenuto.encode("utf-8")).decode("ascii")}
    esistente = _gh("GET", f"{API}/repos/{REPO}/contents/{percorso}")
    if esistente.status_code == 200:
        corpo["sha"] = esistente.json()["sha"]
    r = _gh("PUT", f"{API}/repos/{REPO}/contents/{percorso}", json=corpo)
    r.raise_for_status()


# --------------------------------------------------------------------------
# Una live intera
# --------------------------------------------------------------------------

def taglia(vod_id, prova=False):
    cartella = os.path.join(LAVORO, vod_id)
    os.makedirs(cartella, exist_ok=True)
    info = info_live(vod_id)
    titolo_live = info.get("title") or ""
    data_live = datetime.fromtimestamp(info.get("timestamp") or 0, timezone.utc)
    print(f"\n=== Live {vod_id}: {titolo_live} ({data_live:%d/%m/%Y}) ===")

    energia = energia_audio(vod_id, cartella)
    messaggi = chat_live(vod_id, cartella)
    volume, reazioni = punteggio.chat_per_secondo(messaggi, len(energia))
    valori = punteggio.segnale(energia, volume, reazioni)
    # Si chiedono piu' momenti del necessario: i primi QUANTE vanno su YouTube,
    # le versioni lunghe per TikTok si prendono dai successivi, cosi' le due
    # piattaforme non ricevono lo stesso momento due volte.
    scelti = punteggio.candidati(valori, quante=QUANTE + QUANTE_TIKTOK * 4)
    nomi_chat = sorted({m[1] for m in messaggi if m[1]})
    print(f"[Analisi] {len(energia) // 60} minuti, {len(messaggi)} messaggi, "
          f"{len(scelti)} momenti")

    youtube = [(f"{vod_id}_{inizio:05d}", inizio, fine, punti, "youtube")
               for inizio, fine, punti, _picco in scelti[:QUANTE]]
    # Candidate TikTok in ordine di punteggio; quanto si parla lo dice solo
    # Whisper, quindi si provano finche' QUANTE_TIKTOK hanno parlato a
    # sufficienza (quelle mute vengono scartate da monta_clip).
    tiktok = []
    for _inizio, _fine, punti, picco in scelti[QUANTE:]:
        lunga = punteggio.finestra_tiktok(picco, len(energia))
        if lunga and not any(punteggio.sovrapposte(lunga, (c[1], c[2]))
                             for c in youtube + tiktok):
            tiktok.append((f"{vod_id}_{lunga[0]:05d}_tt", lunga[0], lunga[1],
                           punti, "tiktok"))

    release = None
    schede = []
    fatte_tiktok = 0
    for cid, inizio, fine, punti, piattaforma in youtube + tiktok:
        if piattaforma == "tiktok" and fatte_tiktok >= QUANTE_TIKTOK:
            break
        try:
            scheda = monta_clip(vod_id, info, titolo_live, data_live, cartella, nomi_chat,
                                cid, inizio, fine, punti, piattaforma)
        except ClipMuta as e:
            print(f"[Scartata] Clip {cid}: {e}")
            continue
        except ClipTronca as e:
            print(f"[Errore] Clip {cid} TRONCA, scartata: {e}")
            continue
        except Exception as e:
            print(f"[Errore] Clip {cid} non montata, scartata: {type(e).__name__}: {e}")
            continue
        fatte_tiktok += piattaforma == "tiktok"
        if not prova:
            release = release or release_del_giorno()
            scheda["video_url"] = carica_video(release, os.path.join(cartella, f"{cid}.mp4"),
                                               f"{cid}.mp4")
            scrivi_scheda(scheda)
            print(f"[Consegna] {cid} -> {CARTELLA_REPO}/{cid}.json")
        else:
            with open(os.path.join(cartella, f"{cid}.json"), "w", encoding="utf-8") as f:
                json.dump(scheda, f, ensure_ascii=False, indent=2)
        schede.append(scheda)
    return schede


def monta_clip(vod_id, info, titolo_live, data_live, cartella, nomi_chat,
               cid, inizio, fine, punti, piattaforma):
    """Scarica, trascrive, taglia all'hook e monta una clip; ritorna la scheda."""
    grezzo = os.path.join(cartella, f"{cid}_grezzo.mp4")
    finale = os.path.join(cartella, f"{cid}.mp4")
    ass = os.path.join(cartella, f"{cid}.ass")
    print(f"[Clip] {cid}: {inizio // 60}:{inizio % 60:02d}, {fine - inizio}s, punti {punti}")

    scarica_pezzo(vod_id, inizio, fine, grezzo)
    durata_grezzo = durata_video(grezzo)
    if durata_grezzo < (fine - inizio) - 3:
        raise ClipTronca(f"il pezzo scaricato dura {durata_grezzo:.1f}s "
                         f"invece di {fine - inizio}s")
    parole = trascrivi(grezzo)
    servono = punteggio.parole_minime(piattaforma)
    if len(parole) < servono:
        os.remove(grezzo)
        raise ClipMuta(f"{len(parole)} parole di Davide, ne servono almeno {servono}")
    minimo = 61 if piattaforma == "tiktok" else punteggio.DURATA_MIN
    taglio = punteggio.taglio_hook(parole, durata_grezzo, minimo)
    parole = [(a - taglio[0], b - taglio[0], t) for a, b, t in parole
              if a >= taglio[0] and b <= taglio[1] + 0.5]
    testo = " ".join(p[2] for p in parole)
    print(f"[Hook] {cid}: tengo {taglio[0]:.1f}-{taglio[1]:.1f}s di {durata_grezzo:.0f}s, "
          f"{len(parole)} parole")
    scelta, riquadri = scegli_impaginazione(grezzo, durata_grezzo)
    scrivi_ass(parole, ass, margine=impaginazione.margine_sottotitoli(scelta))
    monta_verticale(grezzo, ass, finale, scelta, riquadri, taglio[0], taglio[1])
    os.remove(grezzo)
    inizio_vero = inizio + int(taglio[0])
    durata = round(taglio[1] - taglio[0])

    avvisi = punteggio.controlla_testo(testo, nomi_chat)
    punti = punteggio.correggi_per_parlato(punti, len(parole))
    punti = punteggio.applica_penalita(punti, avvisi)
    gioco = gioco_al_secondo(info, inizio)
    testi = proponi_testi(testo, gioco, titolo_live, piattaforma)
    return {
        "id": cid, "titolo": testi["titolo"], "descrizione": testi["descrizione"],
        "gioco": gioco, "data_live": data_live.date().isoformat(),
        "secondo_inizio_vod": inizio_vero, "durata": durata,
        "punteggio": punti, "lingua": "it", "video_url": None,
        "stato": "da_approvare", "voti": {}, "orario": None, "youtube_id": None,
        "avvisi": avvisi, "trascrizione": testo[:1500], "impaginazione": scelta,
        "piattaforma": piattaforma,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vod", help="id della live Twitch (i numeri dopo /videos/)")
    parser.add_argument("--prova", action="store_true",
                        help="monta le clip in taglia_live/lavoro ma non carica niente")
    parser.add_argument("--max-live", type=int, default=2)
    args = parser.parse_args()

    for programma in ("ffmpeg",):
        if not shutil.which(programma):
            sys.exit(f"Manca {programma}: installalo e aggiungilo al PATH.")
    if not args.prova and not TOKEN:
        sys.exit("Manca GITHUB_TOKEN_CLIP nel .env (vedi taglia_live/README.md).")

    stato = leggi_stato()
    if args.vod:
        da_fare = [args.vod]
    else:
        da_fare = [v for v in elenco_live() if v not in stato["live_fatte"]]
        da_fare = list(reversed(da_fare[: args.max_live]))
    if not da_fare:
        print("Nessuna live nuova da tagliare.")
        return

    for vod_id in da_fare:
        try:
            schede = taglia(vod_id, prova=args.prova)
        except Exception as e:
            print(f"[Errore] Live {vod_id}: {e}")
            continue
        if not args.prova and vod_id not in stato["live_fatte"]:
            stato["live_fatte"].append(vod_id)
            salva_stato(stato)
        print(f"Live {vod_id}: {len(schede)} clip consegnate a Finch.")


if __name__ == "__main__":
    main()
