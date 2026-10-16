"""Vocale del mattino di Finch, il direttore della stanza degli agenti.

Legge il testo dalla variabile TESTO con la voce ElevenLabs scelta da Davide
("Davide - sport commentator", variabile FINCH_VOCE_ELEVENLABS) e lo manda su
Telegram come audio. Se ElevenLabs non risponde (credito finito, chiave
assente) ripiega sulla voce gratuita di Edge-TTS, cosi' il vocale arriva
comunque. Lo lancia Finch una volta al giorno con il workflow "Vocale di Finch".
"""
import asyncio
import os
import sys

import edge_tts
import requests

VOCE = os.environ.get("FINCH_VOCE") or "it-IT-GiuseppeNeural"
VOCE_ELEVENLABS = os.environ.get("FINCH_VOCE_ELEVENLABS") or "Davide"
MODELLO = os.environ.get("ELEVENLABS_MODELLO") or "eleven_multilingual_v2"
API = "https://api.elevenlabs.io/v1"
LIMITE_CARATTERI = 2500


async def _sintetizza(testo, percorso):
    await edge_tts.Communicate(text=testo, voice=VOCE).save(percorso)


def _id_voce(chiave, richiesta):
    """L'id della voce che si chiama (o comincia per) `richiesta`."""
    r = requests.get(f"{API}/voices", headers={"xi-api-key": chiave}, timeout=30)
    r.raise_for_status()
    cercato = richiesta.strip().lower()
    voci = r.json().get("voices", [])
    for voce in voci:
        if voce.get("name", "").strip().lower() == cercato or voce.get("voice_id") == richiesta:
            return voce["voice_id"]
    for voce in voci:
        if voce.get("name", "").strip().lower().startswith(cercato):
            return voce["voice_id"]
    raise RuntimeError(f"voce '{richiesta}' non trovata su ElevenLabs")


def _sintetizza_elevenlabs(chiave, testo, percorso):
    voce = _id_voce(chiave, VOCE_ELEVENLABS)
    r = requests.post(
        f"{API}/text-to-speech/{voce}",
        headers={"xi-api-key": chiave, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={"text": testo, "model_id": MODELLO,
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                                 "use_speaker_boost": True}},
        timeout=180,
    )
    if not r.ok:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    with open(percorso, "wb") as f:
        f.write(r.content)
    if os.path.getsize(percorso) < 1024:
        raise RuntimeError("ElevenLabs ha prodotto un file vuoto")


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
    chiave = os.environ.get("ELEVENLABS_API_KEY")
    usata = VOCE
    try:
        if not chiave:
            raise RuntimeError("ELEVENLABS_API_KEY assente")
        _sintetizza_elevenlabs(chiave, testo, percorso)
        usata = f"ElevenLabs {VOCE_ELEVENLABS}"
    except Exception as e:  # noqa: BLE001 - il vocale deve arrivare comunque
        print(f"[Finch] ElevenLabs non usabile ({e}): uso la voce Microsoft")
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
    print(f"[Finch] Vocale inviato ({len(testo)} caratteri, voce {usata})")


if __name__ == "__main__":
    main()
