"""
Notifica Telegram opzionale: il tuo "umano nel loop" da 10 secondi.

Perche' conta: YouTube distingue i contenuti assistiti dall'AI (leciti) da
quelli mass-produced senza supervisione (non monetizzabili). Ricevere ogni
video sul telefono e poter cancellare al volo quelli sbagliati e' il modo
piu' economico di restare dalla parte giusta di quella linea.

Se le variabili TELEGRAM_* non sono configurate, il modulo non fa nulla
e non blocca mai la pipeline.
"""
import html
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


def _didascalia_tiktok(dati):
    """Il testo pronto per TikTok, o stringa vuota se non si riesce a produrlo.

    brain lo importo qui dentro e non in cima al file apposta: se un giorno
    quella funzione cambia o sparisce, il massimo che succede e' che manca la
    didascalia, non che salta la notifica del video appena pubblicato.
    """
    try:
        from brain import costruisci_didascalia_tiktok
        return costruisci_didascalia_tiktok(dati)
    except Exception as e:
        print(f"[Warning Telegram] Didascalia TikTok non preparata: {e}")
        return ""


def invia_didascalia_tiktok(dati):
    """Secondo messaggio: la didascalia da copiare con un tocco.

    Il video che Samaritan produce va bene su TikTok cosi' com'e' (verticale
    1080x1920, MP4, mezzo minuto): l'unica cosa che manca per ripubblicarlo a
    mano e' il testo. Su Telegram un blocco <code> si copia toccandolo, quindi
    la didascalia sta in un messaggio tutto suo: video dal messaggio sopra,
    testo da qui.
    """
    if not config.TELEGRAM_ATTIVO:
        return False
    didascalia = _didascalia_tiktok(dati)
    if not didascalia:
        return False
    return invia_messaggio(
        "<b>Didascalia per TikTok</b> (tocca il testo per copiarlo)\n\n"
        f"<code>{html.escape(didascalia, quote=False)}</code>\n\n"
        "Quando pubblichi, attiva l'etichetta \"Contenuto generato dall'IA\": "
        "su YouTube Samaritan la dichiara da solo, su TikTok la spunta e' tua."
    )


def notifica_pubblicazione(dati, video_id, percorso_video):
    """Riepilogo di fine pipeline con link diretto al video."""
    if not config.TELEGRAM_ATTIVO:
        return

    if video_id:
        url = (f"https://youtu.be/{video_id}" if config.VIDEO_LUNGO
               else f"https://youtube.com/shorts/{video_id}")
    else:
        url = "(upload fallito: il video resta tra gli artefatti della lavorazione)"
    if not video_id:
        stato = "CARICAMENTO FALLITO"
    elif config.PRIVACY_STATUS == "public":
        stato = "PUBBLICATO"
    else:
        stato = "IN ATTESA DI APPROVAZIONE"

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

    # Il file e' gia' pronto per TikTok: gli manca solo la didascalia. Vale
    # solo per gli Short: su TikTok un 16:9 da otto minuti non si pubblica.
    if not config.VIDEO_LUNGO:
        invia_didascalia_tiktok(dati)


def notifica_errore(messaggio):
    invia_messaggio(f"<b>Samaritan - ERRORE</b>\n\n<pre>{messaggio[:1500]}</pre>")


def notifica_salto(motivo):
    """Una lavorazione partita che non produce niente, detto apposta.

    Senza questo messaggio una lavorazione che si ferma perche' l'uscita e'
    gia' coperta e una che non e' mai partita sembrano uguali dal telefono:
    silenzio in tutti e due i casi.
    """
    invia_messaggio(f"<b>Samaritan - NIENTE DA FARE</b>\n\n{html.escape(motivo, quote=False)}")
