"""Vocale del mattino di Finch, il direttore della stanza degli agenti.

Legge il testo dalla variabile TESTO, lo legge con una voce italiana gratuita
di Edge-TTS (il credito ElevenLabs resta ai video del canale) e lo manda su
Telegram come audio. Lo lancia Finch con il workflow "Vocale di Finch".
"""
import asyncio
import os
import sys

import edge_tts
import requests

VOCE = os.environ.get("FINCH_VOCE") or "it-IT-GiuseppeNeural"
LIMITE_CARATTERI = 2500


async def _sintetizza(testo, percorso):
    await edge_tts.Communicate(text=testo, voice=VOCE).save(percorso)


def main():
    testo = (os.environ.get("TESTO") or "").strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not testo:
        sys.exit("Testo vuoto: niente da leggere")
    if not token or not chat:
        sys.exit("Mancano TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    testo = testo[:LIMITE_CARATTERI]
    percorso = "vocale_finch.mp3"
    asyncio.run(_sintetizza(testo, percorso))
    with open(percorso, "rb") as audio:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendAudio",
            data={"chat_id": chat, "title": "Finch, il punto del mattino",
                  "performer": "Finch", "caption": testo[:1024]},
            files={"audio": audio},
            timeout=60,
        )
    if not r.ok:
        sys.exit(f"Telegram ha rifiutato l'audio: {r.status_code} {r.text[:200]}")
    print(f"[Finch] Vocale inviato ({len(testo)} caratteri, voce {VOCE})")


if __name__ == "__main__":
    main()
