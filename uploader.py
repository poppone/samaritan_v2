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
import profilo

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

# Dove Google scambia il refresh token con un token di accesso.
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _credenziali_da_secret():
    """Le credenziali costruite da YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN, o None.

    E' il modo della pagina di installazione: chi compra Samaritan non ha un
    terminale per lanciare setup_secrets.py, quindi l'autorizzazione la fa
    il suo browser e nei Secrets finiscono tre stringhe invece di un pickle.
    Niente viene scritto su disco: il token di accesso vive in memoria per
    la durata della lavorazione.
    """
    if not (config.YOUTUBE_CLIENT_ID and config.YOUTUBE_CLIENT_SECRET
            and config.YOUTUBE_REFRESH_TOKEN):
        return None
    from google.oauth2.credentials import Credentials
    credenziali = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    credenziali.refresh(Request())
    return credenziali


def ottieni_credenziali():
    """Credenziali OAuth condivise fra uploader e analyst.

    token.pickle, se c'e', vince: e' il modo di sempre di popponetv. Senza,
    si provano i tre Secrets della pagina di installazione, e solo alla fine
    l'autorizzazione dal browser in locale con client_secret.json.
    """
    credenziali = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            credenziali = pickle.load(token)
    else:
        dai_secret = _credenziali_da_secret()
        if dai_secret is not None:
            return dai_secret

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


def token_youtube_scaduto():
    """True solo se Google risponde che il token non vale piu' (invalid_grant).

    Si chiede prima di scrivere e montare il video: il 4 ottobre 2026 il
    token era scaduto e nove lavorazioni hanno scritto lo script, prenotato
    la notizia e montato il video per poi cadere al caricamento, mandando
    su Telegram solo una traccia d'errore. Ogni altro problema (rete, Google
    lento, file mancante) non ferma niente: ci riprova il caricamento.
    """
    try:
        ottieni_credenziali()
    except Exception as e:
        return "invalid_grant" in str(e)
    return False


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
            # 20 = Gaming per Poppone TV; la decide il profilo del canale.
            "categoryId": profilo.attivo().categoria_youtube,
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
