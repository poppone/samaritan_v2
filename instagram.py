"""
Pubblicazione dei Reel promozionali su Instagram.

Questo modulo NON c'entra niente con YouTube: non lo importa nessuno dei file
della pipeline che pubblica sul canale (main.py, uploader.py, maker.py). Se
Instagram cambia le regole, si rompe l'account nuovo e basta.

Come funziona la pubblicazione, che e' in tre passi e non uno solo:

  1. si apre un "contenitore" vuoto dichiarando che arrivera' un Reel;
  2. si carica dentro il file, in una richiesta a parte (protocollo
     'resumable': il video parte da qui, non serve tenerlo online da
     qualche parte perche' Instagram se lo venga a prendere);
  3. Instagram lo lavora per qualche decina di secondi e solo quando dice
     FINISHED si puo' pubblicare davvero.

Il passo 3 e' il motivo per cui qui si aspetta: pubblicare un contenitore
ancora IN_PROGRESS risponde errore, e il video resterebbe a meta'.

Serve un account Instagram PROFESSIONALE (Impostazioni > Tipo di account) e
un token in INSTAGRAM_TOKEN. Senza le due variabili il modulo non fa nulla e
lo dice, invece di far fallire la lavorazione.
"""
import os
import time

import requests

import config

GRAPH = "https://graph.instagram.com"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload"

# Quanto si aspetta che Instagram finisca di lavorare il video prima di
# arrendersi. Un Reel da 30 secondi di solito e' pronto in meno di un minuto;
# il tetto alto serve solo a non buttare via il lavoro nelle giornate lente.
ATTESA_MAX = 300
ATTESA_PASSO = 10


def _url(percorso):
    return f"{GRAPH}/{config.INSTAGRAM_API}/{percorso}"


def _crea_contenitore(didascalia):
    """Passo 1: annuncia a Instagram che sta per arrivare un Reel."""
    r = requests.post(
        _url(f"{config.INSTAGRAM_USER_ID}/media"),
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": didascalia[:2200],
            # Il Reel finisce anche nella griglia del profilo, non solo nel
            # feed dei Reel: un profilo che vende qualcosa deve avere una
            # griglia piena, altrimenti chi ci arriva non capisce cos'e'.
            "share_to_feed": "true",
            "access_token": config.INSTAGRAM_TOKEN,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def _carica_file(contenitore, percorso):
    """Passo 2: manda i byte del video."""
    dimensione = os.path.getsize(percorso)
    with open(percorso, "rb") as video:
        r = requests.post(
            f"{RUPLOAD}/{config.INSTAGRAM_API}/{contenitore}",
            headers={
                # Qui l'intestazione e' 'OAuth', non 'Bearer': e' un server
                # diverso da quello degli altri due passi e vuole questa.
                "Authorization": f"OAuth {config.INSTAGRAM_TOKEN}",
                "offset": "0",
                "file_size": str(dimensione),
            },
            data=video,
            timeout=600,
        )
    r.raise_for_status()
    return True


def _attendi_pronto(contenitore):
    """Passo 3a: aspetta che Instagram finisca di lavorare il video."""
    scaduto = time.time() + ATTESA_MAX
    while time.time() < scaduto:
        r = requests.get(
            _url(contenitore),
            params={"fields": "status_code,status",
                    "access_token": config.INSTAGRAM_TOKEN},
            timeout=30,
        )
        r.raise_for_status()
        stato = r.json().get("status_code", "")
        if stato == "FINISHED":
            return True
        if stato == "ERROR":
            print(f"[Instagram] Il video e' stato rifiutato: {r.json().get('status')}")
            return False
        print(f"[Instagram] Video in lavorazione ({stato or 'in attesa'})...")
        time.sleep(ATTESA_PASSO)

    print(f"[Instagram] Ancora in lavorazione dopo {ATTESA_MAX}s: mi fermo qui.")
    return False


def _pubblica(contenitore):
    """Passo 3b: rende pubblico il Reel."""
    r = requests.post(
        _url(f"{config.INSTAGRAM_USER_ID}/media_publish"),
        data={"creation_id": contenitore,
              "access_token": config.INSTAGRAM_TOKEN},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def permalink(media_id):
    """Il link pubblico del Reel, se Instagram lo restituisce."""
    try:
        r = requests.get(
            _url(media_id),
            params={"fields": "permalink", "access_token": config.INSTAGRAM_TOKEN},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("permalink", "")
    except Exception:
        return ""


def pubblica_reel(percorso, didascalia):
    """Pubblica il Reel e torna l'id del post, oppure None.

    Non solleva mai: un errore di Instagram non deve far fallire la
    lavorazione, che a quel punto ha gia' prodotto il video su disco.
    """
    if not config.INSTAGRAM_ATTIVO:
        print("[Instagram] INSTAGRAM_TOKEN o INSTAGRAM_USER_ID mancanti: "
              "il Reel resta solo in output_videos/.")
        return None
    if not os.path.exists(percorso):
        print(f"[Instagram] File non trovato: {percorso}")
        return None

    try:
        contenitore = _crea_contenitore(didascalia)
        print(f"[Instagram] Contenitore {contenitore} aperto.")
        _carica_file(contenitore, percorso)
        print("[Instagram] Video caricato, aspetto la lavorazione...")
        if not _attendi_pronto(contenitore):
            return None
        media_id = _pubblica(contenitore)
        print(f"[Instagram] PUBBLICATO: {permalink(media_id) or media_id}")
        return media_id
    except requests.HTTPError as e:
        corpo = ""
        try:
            corpo = e.response.text[:400]
        except Exception:
            pass
        print(f"[Instagram] Errore dalla API: {e} {corpo}")
        return None
    except Exception as e:
        print(f"[Instagram] Pubblicazione fallita: {e}")
        return None
