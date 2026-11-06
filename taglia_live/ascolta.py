# -*- coding: utf-8 -*-
"""
Ascolta le clip montate prima di dar loro un voto.

Il 5/11 le clip di prova sono state votate guardando fotogrammi e
trascrizione dei sottotitoli, senza sentire l'audio: sottotitoli sbagliati e
momenti muti sono passati per buoni. Qui, per ogni mp4 finito, si riascolta
l'audio VERO della clip (quello con i bip) con un Whisper piu' grande di
quello dei sottotitoli e si misura:

  - prima_parola: secondi di silenzio prima che lo streamer parli (l'hook);
  - parole_al_secondo e quota_parlato: quanto si parla davvero;
  - accordo_sottotitoli: quante parole dei sottotitoli il modello grande
    sente anche lui (basso = sottotitoli inventati);
  - stacco_db: quanto il momento piu' forte supera il volume tipico della
    clip (urla, risate, reazioni);
  - silenzio: quota di audio quasi muto.

Scrive ascolto.md (da leggere prima di votare) e ascolto.json nella cartella.
Gira da solo alla fine di ogni live con --prova; a mano:

    python ascolta.py lavoro/2918711304
"""
import json
import os
import re
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))

MODELLO = os.getenv("WHISPER_MODELLO_ASCOLTO", "large-v3-turbo").strip()

_modello = None


# --------------------------------------------------------------------------
# Logica pura (testata in tests/test_clip_live.py)
# --------------------------------------------------------------------------

def _parole_pulite(testo):
    return [p for p in re.findall(r"[a-zà-ù0-9']+", (testo or "").lower()) if len(p) > 1]


def accordo(sottotitoli, sentito):
    """Quota delle parole dei sottotitoli che compaiono anche nel riascolto.

    0..1; None se i sottotitoli sono vuoti. Le parole coperte dal bip
    ("c****") e quelle di una lettera non contano.
    """
    sotto = [p for p in _parole_pulite(sottotitoli) if "*" not in p]
    if not sotto:
        return None
    sentite = set(_parole_pulite(sentito))
    return round(sum(1 for p in sotto if p in sentite) / len(sotto), 2)


def testo_ass(percorso):
    """Il testo dei sottotitoli di un .ass, in ordine."""
    if not os.path.exists(percorso):
        return ""
    righe = []
    with open(percorso, encoding="utf-8") as f:
        for riga in f:
            if riga.startswith("Dialogue:"):
                righe.append(riga.split(",", 4)[-1].strip())
    return " ".join(righe)


def stacco_e_silenzio(db_per_mezzo_secondo, soglia_muto=-45.0):
    """(dB del momento piu' forte sopra la mediana, quota di audio muto)."""
    valori = sorted(db_per_mezzo_secondo)
    if not valori:
        return 0.0, 1.0
    mediana = valori[len(valori) // 2]
    muti = sum(1 for v in valori if v < soglia_muto) / len(valori)
    return round(valori[-1] - mediana, 1), round(muti, 2)


def note(m):
    """Cosa salta all'orecchio, in parole: aiuta il voto, non lo sostituisce."""
    n = []
    if m["prima_parola"] is None:
        n.append("nessuna parola sentita")
    elif m["prima_parola"] > 2.0:
        n.append(f"parte muta ({m['prima_parola']:.1f}s prima della prima parola)")
    if m["parole_al_secondo"] < 1.0:
        n.append("si parla poco")
    if m["accordo_sottotitoli"] is not None and m["accordo_sottotitoli"] < 0.6:
        n.append(f"sottotitoli poco fedeli (accordo {m['accordo_sottotitoli']:.0%})")
    if m["stacco_db"] >= 12:
        n.append(f"reazione forte (+{m['stacco_db']:.0f} dB)")
    if m["silenzio"] > 0.3:
        n.append(f"audio muto per il {m['silenzio']:.0%}")
    return n or ["niente da segnalare"]


# --------------------------------------------------------------------------
# Audio e riascolto
# --------------------------------------------------------------------------

def _audio(percorso):
    import numpy as np
    grezzo = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", percorso, "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0


def _db_per_mezzo_secondo(audio):
    import numpy as np
    passo = 8000
    n = len(audio) // passo
    if n == 0:
        return []
    blocchi = audio[: n * passo].reshape(n, passo)
    rms = np.sqrt((blocchi ** 2).mean(axis=1)) + 1e-9
    return [float(v) for v in 20 * np.log10(rms)]


def _carica():
    global _modello
    if _modello is None:
        from taglia_live import taglia_live as tl
        tl.librerie_cuda()
        from faster_whisper import WhisperModel
        dispositivo = "cpu" if tl.DISPOSITIVO == "cpu" else "cuda"
        _modello = WhisperModel(MODELLO, device=dispositivo,
                                compute_type="int8_float16" if dispositivo == "cuda" else "int8")
    return _modello


def ascolta_clip(mp4):
    audio = _audio(mp4)
    durata = len(audio) / 16000
    segmenti, _ = _carica().transcribe(audio, language="it", word_timestamps=True,
                                       vad_filter=True, beam_size=5)
    parole = [p for s in segmenti for p in (s.words or []) if p.word.strip()]
    sentito = " ".join(p.word.strip() for p in parole)
    parlato = sum(max(0.0, p.end - p.start) for p in parole)
    stacco, muto = stacco_e_silenzio(_db_per_mezzo_secondo(audio))
    m = {
        "clip": os.path.splitext(os.path.basename(mp4))[0],
        "durata": round(durata, 1),
        "prima_parola": round(parole[0].start, 1) if parole else None,
        "parole_al_secondo": round(len(parole) / durata, 2) if durata else 0.0,
        "quota_parlato": round(parlato / durata, 2) if durata else 0.0,
        "accordo_sottotitoli": accordo(testo_ass(mp4[:-4] + ".ass"), sentito),
        "stacco_db": stacco, "silenzio": muto, "sentito": sentito,
    }
    m["note"] = note(m)
    return m


def ascolta_cartella(cartella):
    clip = sorted(f for f in os.listdir(cartella)
                  if f.endswith(".mp4") and not f.endswith("_grezzo.mp4"))
    risultati = []
    for nome in clip:
        try:
            m = ascolta_clip(os.path.join(cartella, nome))
        except Exception as e:
            print(f"[Ascolto] {nome}: {type(e).__name__}: {e}")
            continue
        print(f"[Ascolto] {m['clip']}: {', '.join(m['note'])}")
        risultati.append(m)
    with open(os.path.join(cartella, "ascolto.json"), "w", encoding="utf-8") as f:
        json.dump(risultati, f, ensure_ascii=False, indent=2)
    righe = [f"# Ascolto delle clip ({MODELLO})", "",
             "| clip | durata | prima parola | parole/s | parlato | accordo sottotitoli | stacco | note |",
             "|---|---|---|---|---|---|---|---|"]
    for m in risultati:
        accordo_txt = "-" if m["accordo_sottotitoli"] is None else f"{m['accordo_sottotitoli']:.0%}"
        prima = "-" if m["prima_parola"] is None else f"{m['prima_parola']:.1f}s"
        righe.append(f"| {m['clip']} | {m['durata']:.0f}s | {prima} | {m['parole_al_secondo']:.1f} | "
                     f"{m['quota_parlato']:.0%} | {accordo_txt} | +{m['stacco_db']:.0f} dB | "
                     f"{'; '.join(m['note'])} |")
    righe.append("")
    for m in risultati:
        righe += [f"## {m['clip']}", "", m["sentito"] or "(niente)", ""]
    with open(os.path.join(cartella, "ascolto.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(righe))
    return risultati


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("Uso: python ascolta.py <cartella con le clip>")
    ascolta_cartella(sys.argv[1])
