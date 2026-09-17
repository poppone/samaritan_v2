"""
Motore vocale di Samaritan.

Primario  : Edge-TTS (voci neurali Microsoft, gratuite, qualita altissima)
Fallback  : gTTS (robotica, usata solo se Edge-TTS non e' disponibile)

Il salto da gTTS a Edge-TTS e' il singolo miglioramento con piu' impatto
sulla retention: la voce neurale ha enfasi, respiro e intonazione, quindi
l'hook dei primi 3 secondi "suona" davvero come un hook.
"""
import os
import re
import asyncio

import config

# Emoji e simboli decorativi: la voce non deve leggerli
_RE_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)


def pulisci_testo(testo):
    """Ripulisce lo script per la sintesi vocale e per i sottotitoli."""
    t = _RE_EMOJI.sub(" ", testo)
    t = re.sub(r"#\w+", " ", t)          # hashtag: non vanno letti
    t = re.sub(r"[*_`>\[\]()]", " ", t)  # residui markdown
    t = t.replace("...", ".").replace("…", ".")
    t = t.replace("-", " ").replace("—", " ").replace("–", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    return t.strip()


async def _sintetizza_edge(testo, output_filename):
    import edge_tts

    communicate = edge_tts.Communicate(
        text=testo,
        voice=config.VOCE_TTS,
        rate=config.VOCE_VELOCITA,
        pitch=config.VOCE_PITCH,
    )
    await communicate.save(output_filename)


def genera_voce_samaritan(testo, output_filename=None):
    """Genera l'audio dello script. Ritorna il path del file o None."""
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    if output_filename is None:
        output_filename = os.path.join(config.DIR_TEMP, "audio.mp3")

    testo_pulito = pulisci_testo(testo)
    if not testo_pulito:
        print("[Errore Voice] Testo vuoto dopo la pulizia.")
        return None

    # --- Tentativo 1: Edge-TTS (voce neurale) ---
    try:
        print(f"[Samaritan Voice] Sintesi neurale con {config.VOCE_TTS} "
              f"(velocita {config.VOCE_VELOCITA})...")
        asyncio.run(_sintetizza_edge(testo_pulito, output_filename))

        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
            print(f"[Samaritan Voice] Audio neurale salvato: {output_filename}")
            return output_filename
        raise RuntimeError("Edge-TTS ha prodotto un file vuoto")

    except Exception as e:
        print(f"[Warning Voice] Edge-TTS non disponibile ({e}). Passo al fallback gTTS.")

    # --- Tentativo 2: gTTS (fallback robotico) ---
    try:
        from gtts import gTTS

        tts = gTTS(text=testo_pulito, lang=config.LINGUA, tld="it", slow=False)
        tts.save(output_filename)
        print(f"[Samaritan Voice] Audio di fallback salvato: {output_filename}")
        return output_filename
    except Exception as e:
        print(f"[Errore Voice] Impossibile generare l'audio: {e}")
        return None


if __name__ == "__main__":
    testo_test = (
        "Stai sbagliando tutto su GTA 6, e nemmeno te ne accorgi. "
        "Questo dettaglio lo ha notato solo lo zero virgola uno per cento dei giocatori."
    )
    genera_voce_samaritan(testo_test)
