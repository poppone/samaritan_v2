"""
Caricamento su YouTube + autenticazione condivisa.

Nota sulla dichiarazione dei contenuti sintetici:
la versione precedente dichiarava `containsSyntheticMedia: False`, che e' FALSO
(voce sintetica + script generato da un LLM). Dichiarare male e' una violazione
in se'; dichiarare correttamente NON penalizza la monetizzazione ne' la
distribuzione. Ora e' impostato a True.
"""
import os
import pickle
import time
from datetime import timezone

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config

# yt-analytics.readonly serve ad analyst.py per leggere la retention reale.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Percorsi ANCORATI alla cartella del progetto, come tutto il resto in
# config.py: cosi' l'autenticazione funziona anche quando Samaritan viene
# lanciato da una working directory diversa (Task Scheduler, cron, .bat).
TOKEN_FILE = os.path.join(config.DIR_PROGETTO, "token.pickle")
CLIENT_SECRET_FILE = os.path.join(config.DIR_PROGETTO, "client_secret.json")


def ottieni_credenziali():
    """Credenziali OAuth condivise fra uploader e analyst."""
    credenziali = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            credenziali = pickle.load(token)

    if credenziali and credenziali.valid:
        return credenziali

    if credenziali and credenziali.expired and credenziali.refresh_token:
        credenziali.refresh(Request())
    else:
        if not os.path.exists(CLIENT_SECRET_FILE):
            raise FileNotFoundError(
                f"'{CLIENT_SECRET_FILE}' non trovato nella cartella del progetto."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        credenziali = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "wb") as token:
        pickle.dump(credenziali, token)
    return credenziali


def ha_scope_analytics(credenziali):
    """True se il token include il permesso di lettura delle statistiche."""
    scopes = set(getattr(credenziali, "scopes", None) or [])
    return "https://www.googleapis.com/auth/yt-analytics.readonly" in scopes


def autentica_youtube():
    return build("youtube", "v3", credentials=ottieni_credenziali())


def imposta_miniatura(youtube, video_id, percorso):
    """Imposta la miniatura personalizzata. Non e' mai fatale.

    Serve un canale verificato via telefono: se non lo e', YouTube risponde 403
    e il video resta online con un fotogramma estratto a caso. Meglio uno Short
    pubblicato senza miniatura che una pipeline che si ferma qui.
    """
    if not percorso or not os.path.exists(percorso):
        return False
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(percorso, mimetype="image/jpeg"),
        ).execute()
        print("[Upload] Miniatura personalizzata impostata.")
        return True
    except HttpError as e:
        if e.resp.status == 403:
            print("[Warning Upload] Miniatura rifiutata: il canale non e' "
                  "verificato via telefono (Studio > Impostazioni > Canale > "
                  "Idoneita' alle funzioni).")
        else:
            print(f"[Warning Upload] Miniatura non impostata: {e}")
    except Exception as e:
        print(f"[Warning Upload] Miniatura non impostata: {e}")
    return False


def carica_short(filepath, titolo, descrizione, tag=None, privacy=None,
                 miniatura=None, pubblica_alle=None):
    """Carica il video e ritorna l'ID YouTube (o None se fallisce).

    Con `pubblica_alle` il video sale privato e YouTube lo rende pubblico da
    solo a quell'istante: e' l'unico modo di avere un orario preciso, visto
    che la run parte quando vuole GitHub. Vale solo per i video che dovevano
    essere pubblici: una prova privata resta privata.
    """
    privacy = privacy or config.PRIVACY_STATUS
    tag = tag or []

    if not os.path.exists(filepath):
        print(f"[Errore Upload] File non trovato: {filepath}")
        return None

    stato = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,            # dichiarazione corretta
    }
    # YouTube accetta publishAt solo su un video privato: e' proprio cosi' che
    # funziona la programmazione, il video resta privato fino all'istante
    # indicato e poi diventa pubblico da solo.
    if pubblica_alle is not None and privacy == "public":
        stato["privacyStatus"] = "private"
        stato["publishAt"] = pubblica_alle.astimezone(
            timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n[Samaritan Auto-Poster] Caricamento programmato per le "
              f"{pubblica_alle:%H:%M di %d/%m}: {titolo}")
    else:
        print(f"\n[Samaritan Auto-Poster] Caricamento ({privacy}): {titolo}")

    youtube = autentica_youtube()

    body = {
        "snippet": {
            "title": titolo[:100],
            "description": descrizione[:5000],
            "tags": tag[:15],
            "categoryId": "20",                    # 20 = Gaming
        },
        "status": stato,
    }

    media = MediaFileUpload(filepath, chunksize=1024 * 1024 * 4,
                            resumable=True, mimetype="video/mp4")
    richiesta = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    risposta, tentativi = None, 0
    while risposta is None:
        try:
            stato, risposta = richiesta.next_chunk()
            if stato:
                print(f"[Upload] {int(stato.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tentativi < 4:
                tentativi += 1
                attesa = 2 ** tentativi
                print(f"[Network] Errore temporaneo, riprovo fra {attesa}s "
                      f"({tentativi}/4)...")
                time.sleep(attesa)
            else:
                print(f"[Errore Upload] {e}")
                return None

    video_id = risposta.get("id")
    if video_id:
        imposta_miniatura(youtube, video_id, miniatura)
    print(f"\nVIDEO CARICATO: https://youtube.com/shorts/{video_id}")
    return video_id


if __name__ == "__main__":
    percorso = os.path.join(config.DIR_OUTPUT, "samaritan_short_subbed.mp4")
    if os.path.exists(percorso):
        carica_short(
            filepath=percorso,
            titolo="Test Samaritan",
            descrizione="Test di caricamento.",
            tag=["gaming", "shorts"],
            privacy="private",
        )
    else:
        print(f"File non trovato: {percorso}. Genera prima un video con maker.py.")
