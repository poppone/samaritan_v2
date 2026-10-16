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

from taglia_live import punteggio  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(QUI), ".env"))
    load_dotenv(os.path.join(QUI, ".env"))
except ImportError:
    pass

CANALE = os.getenv("TWITCH_CANALE", "popponetv").strip()
REPO = os.getenv("CLIP_REPO", "poppone/samaritan_v2").strip()
TOKEN = os.getenv("GITHUB_TOKEN_CLIP", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODELLI = [m.strip() for m in os.getenv(
    "GROQ_MODELLI", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
WHISPER = os.getenv("WHISPER_MODELLO_CLIP", "small").strip()
TWITCH_DL = os.getenv("TWITCHDOWNLOADER", "TwitchDownloaderCLI").strip()
QUANTE = int(os.getenv("CLIP_PER_LIVE", "5"))

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


def chat_live(vod_id, cartella):
    """[(secondo, autore, testo), ...] o [] se TwitchDownloaderCLI non c'e'."""
    if not shutil.which(TWITCH_DL) and not os.path.exists(TWITCH_DL):
        print("[Chat] TwitchDownloaderCLI non trovato: conto solo l'audio.")
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


def trascrivi(percorso):
    """Parole con i tempi. GPU se c'e' (sotto gli 8 GB basta 'small')."""
    global _modello
    from faster_whisper import WhisperModel
    if _modello is None:
        try:
            _modello = WhisperModel(WHISPER, device="cuda",
                                    compute_type="int8_float16")
        except Exception:
            print("[Whisper] GPU non disponibile, uso la CPU.")
            _modello = WhisperModel(WHISPER, device="cpu", compute_type="int8")
    segmenti, _ = _modello.transcribe(percorso, language="it",
                                      word_timestamps=True, vad_filter=True)
    parole = []
    for seg in segmenti:
        for p in seg.words or []:
            parole.append((p.start, p.end, p.word.strip()))
    return parole


def _tempo_ass(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def scrivi_ass(parole, percorso, per_riga=4):
    """Sottotitoli grandi a gruppi di poche parole, come negli Short."""
    righe = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Outline, Shadow, Alignment, MarginV",
        "Style: Base,Arial,78,&H00FFFFFF,&H00000000,&H64000000,1,6,2,2,520", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Text",
    ]
    for i in range(0, len(parole), per_riga):
        gruppo = parole[i:i + per_riga]
        testo = " ".join(p[2] for p in gruppo).upper().replace("{", "").replace("}", "")
        righe.append(f"Dialogue: 0,{_tempo_ass(gruppo[0][0])},"
                     f"{_tempo_ass(gruppo[-1][1])},Base,{testo}")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")


def monta_verticale(sorgente, sottotitoli, uscita):
    """16:9 al centro su sfondo sfocato 9:16, sottotitoli bruciati.

    ffmpeg gira dentro la cartella del lavoro e riceve il nome nudo del file
    .ass: su Windows i due punti di 'C:' rompono il filtro 'ass'.
    """
    cartella = os.path.dirname(sottotitoli)
    filtro = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
              "crop=1080:1920,boxblur=25:2,eq=brightness=-0.08[sfondo];"
              "[0:v]scale=1080:-2[primo];"
              "[sfondo][primo]overlay=(W-w)/2:(H-h)/2,"
              f"ass={os.path.basename(sottotitoli)}[v]")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(sorgente),
         "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
         "-af", "loudnorm=I=-14:TP=-1.5", "-c:v", "libx264", "-preset", "medium",
         "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac",
         "-b:a", "160k", "-movflags", "+faststart", os.path.abspath(uscita)],
        cwd=cartella, check=True)


# --------------------------------------------------------------------------
# Titolo e descrizione
# --------------------------------------------------------------------------

def proponi_testi(trascritto, gioco, titolo_live):
    base_desc = (f"Dalla live su Twitch: https://twitch.tv/{CANALE}\n"
                 f"{('Gioco: ' + gioco) if gioco else ''}\n\n#shorts #twitch #gaming")
    ripiego = {"titolo": (gioco + " - " if gioco else "") + "dalla live di popponetv",
               "descrizione": base_desc}
    if not GROQ_KEY or not trascritto.strip():
        return ripiego
    from groq import Groq
    client = Groq(api_key=GROQ_KEY)
    domanda = (
        "Sei l'editor degli Short YouTube di popponetv, streamer italiano. "
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
    scelti = punteggio.candidati(valori, quante=QUANTE)
    nomi_chat = sorted({m[1] for m in messaggi if m[1]})
    print(f"[Analisi] {len(energia) // 60} minuti, {len(messaggi)} messaggi, "
          f"{len(scelti)} momenti")

    release = None
    schede = []
    for inizio, fine, punti, _picco in scelti:
        cid = f"{vod_id}_{inizio:05d}"
        grezzo = os.path.join(cartella, f"{cid}_grezzo.mp4")
        finale = os.path.join(cartella, f"{cid}.mp4")
        ass = os.path.join(cartella, f"{cid}.ass")
        print(f"[Clip] {cid}: {inizio // 60}:{inizio % 60:02d}, {fine - inizio}s, punti {punti}")

        scarica_pezzo(vod_id, inizio, fine, grezzo)
        parole = trascrivi(grezzo)
        testo = " ".join(p[2] for p in parole)
        scrivi_ass(parole, ass)
        monta_verticale(grezzo, ass, finale)

        avvisi = punteggio.controlla_testo(testo, nomi_chat)
        punti = punteggio.applica_penalita(punti, avvisi)
        gioco = gioco_al_secondo(info, inizio)
        testi = proponi_testi(testo, gioco, titolo_live)

        scheda = {
            "id": cid, "titolo": testi["titolo"], "descrizione": testi["descrizione"],
            "gioco": gioco, "data_live": data_live.date().isoformat(),
            "secondo_inizio_vod": inizio, "durata": fine - inizio,
            "punteggio": punti, "lingua": "it", "video_url": None,
            "stato": "da_approvare", "voti": {}, "orario": None, "youtube_id": None,
            "avvisi": avvisi, "trascrizione": testo[:1500],
        }
        if not prova:
            release = release or release_del_giorno()
            scheda["video_url"] = carica_video(release, finale, f"{cid}.mp4")
            scrivi_scheda(scheda)
            print(f"[Consegna] {cid} -> {CARTELLA_REPO}/{cid}.json")
        else:
            with open(os.path.join(cartella, f"{cid}.json"), "w", encoding="utf-8") as f:
                json.dump(scheda, f, ensure_ascii=False, indent=2)
        os.remove(grezzo)
        schede.append(scheda)
    return schede


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
