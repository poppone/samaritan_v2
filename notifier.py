"""
Notifica Telegram opzionale: il tuo "umano nel loop" da 10 secondi.

Perche' conta: YouTube distingue i contenuti assistiti dall'AI (leciti) da
quelli mass-produced senza supervisione (non monetizzabili). Ricevere ogni
video sul telefono e poter cancellare al volo quelli sbagliati e' il modo
piu' economico di restare dalla parte giusta di quella linea.

Se le variabili TELEGRAM_* non sono configurate, il modulo non fa nulla
e non blocca mai la pipeline.
"""
import os

import requests

import config

LIMITE_UPLOAD_BOT = 48 * 1024 * 1024      # i bot Telegram si fermano a ~50MB


def _api(metodo):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"


def invia_messaggio(testo):
    if not config.TELEGRAM_ATTIVO:
        return False
    try:
        r = requests.post(
            _api("sendMessage"),
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": testo,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        return r.ok
    except Exception as e:
        print(f"[Warning Telegram] Invio messaggio fallito: {e}")
        return False


def invia_video(percorso, didascalia=""):
    if not config.TELEGRAM_ATTIVO or not os.path.exists(percorso):
        return False
    if os.path.getsize(percorso) > LIMITE_UPLOAD_BOT:
        return invia_messaggio(didascalia + "\n\n(Video troppo grande per Telegram)")
    try:
        with open(percorso, "rb") as video:
            r = requests.post(
                _api("sendVideo"),
                data={
                    "chat_id": config.TELEGRAM_CHAT_ID,
                    "caption": didascalia[:1024],
                    "parse_mode": "HTML",
                },
                files={"video": video},
                timeout=180,
            )
        return r.ok
    except Exception as e:
        print(f"[Warning Telegram] Invio video fallito: {e}")
        return False


def notifica_pubblicazione(dati, video_id, percorso_video):
    """Riepilogo di fine pipeline con link diretto al video."""
    if not config.TELEGRAM_ATTIVO:
        return

    url = f"https://youtube.com/shorts/{video_id}" if video_id else "(upload fallito)"
    stato = "PUBBLICATO" if config.PRIVACY_STATUS == "public" else "IN ATTESA DI APPROVAZIONE"

    testo = (
        f"<b>Samaritan - {stato}</b>\n\n"
        f"<b>{dati['titolo']}</b>\n"
        f"Formato: <code>{dati['stile']}</code>\n"
        f"Gioco: {dati.get('gioco') or 'non specifico'}\n"
        f"Fonte: {dati.get('fonte') or 'evergreen'}\n\n"
        f"{url}"
    )
    if not invia_video(percorso_video, testo):
        invia_messaggio(testo)


def notifica_errore(messaggio):
    invia_messaggio(f"<b>Samaritan - ERRORE</b>\n\n<pre>{messaggio[:1500]}</pre>")
