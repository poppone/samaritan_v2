"""
Montaggio video di Samaritan.

Senza gameplay registrato a mano, la qualita' visiva deve nascere dall'EDITING.
Cosa fa questo modulo che la versione precedente non faceva:

  1. Scarica PIU' clip (default 4) invece di una sola
  2. Monta con uno STACCO ogni 2-3 secondi: l'occhio non ha tempo di annoiarsi
  3. Applica uno ZOOM lento (Ken Burns) su ogni stacco: movimento costante
  4. Normalizza tutto a 1080x1920 reali (scale-to-cover + crop centrale)
  5. Disegna una PROGRESS BAR: da' la sensazione di "manca poco, finisco"
  6. Mostra il TITOLO come banner nei primi secondi (hook visivo)
  7. Sottotitoli parola-per-parola con animazione "pop" e keyword evidenziate
"""
import os
import re
import random

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    ColorClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

import config
from voice import genera_voce_samaritan, pulisci_testo

# Query di riserva: sempre azione di gioco reale, mai panorami generici
FALLBACK_QUERY = [
    "video game action",
    "fps shooter gameplay",
    "esports tournament",
    "racing game",
    "arcade neon gaming",
    "gamer playing console",
]

GIALLO = "#FFE600"
VERDE = "#00FF9C"

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",        # Ubuntu (Actions)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",                                 # Windows
    "arialbd.ttf",
    "arial.ttf",
]


def _carica_font(dimensione):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, dimensione)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ===========================================================================
# DOWNLOAD CLIP DI SFONDO
# ===========================================================================
def _cerca_clip_pexels(query, gia_scaricati):
    """Ritorna una lista di URL di video verticali per la query data."""
    headers = {"Authorization": config.PEXELS_API_KEY}
    query_pulita = re.sub(r"\b(vertical|short|shorts)\b", "", query,
                          flags=re.IGNORECASE).strip()
    url = "https://api.pexels.com/videos/search"
    params = {"query": query_pulita, "orientation": "portrait", "per_page": 15}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        r.raise_for_status()
        video_trovati = r.json().get("videos", [])
    except Exception as e:
        print(f"[Warning Pexels] Ricerca '{query_pulita}' fallita: {e}")
        return []

    risultati = []
    for video in video_trovati:
        if video["id"] in gia_scaricati:
            continue
        # Preferisci il file verticale con la risoluzione piu' vicina a 1080x1920
        file_verticali = [
            f for f in video.get("video_files", [])
            if f.get("height", 0) >= f.get("width", 1)
        ] or video.get("video_files", [])
        if not file_verticali:
            continue
        migliore = min(
            file_verticali,
            key=lambda f: abs(f.get("height", 0) - config.VIDEO_H),
        )
        risultati.append((video["id"], migliore["link"]))
    return risultati


def scarica_clip_sfondo(query, quante=None):
    """Scarica piu' clip di gameplay, variando la query per avere materiale
    visivamente diverso da cui montare gli stacchi."""
    quante = quante or config.NUM_CLIP_SFONDO
    os.makedirs(config.DIR_TEMP, exist_ok=True)

    query_da_provare = [query] + random.sample(FALLBACK_QUERY, len(FALLBACK_QUERY))
    percorsi, gia_scaricati = [], set()

    for q in query_da_provare:
        if len(percorsi) >= quante:
            break
        for video_id, link in _cerca_clip_pexels(q, gia_scaricati):
            if len(percorsi) >= quante:
                break
            destinazione = os.path.join(config.DIR_TEMP, f"bg_{video_id}.mp4")
            try:
                print(f"[Samaritan Maker] Download clip '{q}' (id {video_id})...")
                dati = requests.get(link, timeout=60).content
                if len(dati) < 50_000:            # file sospettosamente piccolo
                    continue
                with open(destinazione, "wb") as f:
                    f.write(dati)
                percorsi.append(destinazione)
                gia_scaricati.add(video_id)
            except Exception as e:
                print(f"[Warning Pexels] Download fallito: {e}")

    if not percorsi:
        print("[Errore Pexels] Nessuna clip di sfondo scaricata.")
    else:
        print(f"[Samaritan Maker] {len(percorsi)} clip pronte per il montaggio.")
    return percorsi


# ===========================================================================
# NORMALIZZAZIONE VERTICALE
# ===========================================================================
def _normalizza_verticale(clip):
    """Scala la clip per COPRIRE 1080x1920, poi ritaglia al centro.
    Evita le bande nere quando Pexels restituisce formati anomali."""
    W, H = config.VIDEO_W, config.VIDEO_H
    fattore = max(W / clip.w, H / clip.h)
    clip = clip.resized((round(clip.w * fattore), round(clip.h * fattore)))
    return clip.cropped(
        width=W, height=H,
        x_center=clip.w / 2, y_center=clip.h / 2,
    )


def _applica_zoom(clip, intensita=0.08):
    """Ken Burns: zoom lento e continuo. Il movimento costante trattiene l'occhio."""
    try:
        durata = clip.duration
        zoomata = clip.resized(lambda t: 1 + intensita * (t / max(durata, 0.01)))
        return CompositeVideoClip(
            [zoomata.with_position("center")],
            size=(config.VIDEO_W, config.VIDEO_H),
        ).with_duration(durata)
    except Exception as e:
        print(f"[Warning Maker] Zoom non applicato ({e}), uso la clip statica.")
        return clip


# ===========================================================================
# MONTAGGIO CON STACCHI
# ===========================================================================
def costruisci_sfondo_montato(percorsi_clip, durata_totale):
    """Alterna le clip con uno stacco ogni 2-3 secondi fino a coprire l'audio."""
    sorgenti = []
    for p in percorsi_clip:
        try:
            sorgenti.append(VideoFileClip(p).without_audio())
        except Exception as e:
            print(f"[Warning Maker] Clip illeggibile {p}: {e}")

    if not sorgenti:
        return None

    segmenti, tempo_coperto, indice = [], 0.0, 0
    while tempo_coperto < durata_totale:
        sorgente = sorgenti[indice % len(sorgenti)]
        indice += 1

        durata_stacco = random.uniform(config.STACCO_MIN, config.STACCO_MAX)
        durata_stacco = min(durata_stacco, durata_totale - tempo_coperto)
        if durata_stacco < 0.4:
            break

        # Se la sorgente e' piu' corta dello stacco, usa quello che c'e'
        if sorgente.duration <= durata_stacco:
            pezzo = sorgente.subclipped(0, sorgente.duration)
            durata_stacco = sorgente.duration
        else:
            inizio_max = sorgente.duration - durata_stacco
            inizio = random.uniform(0, max(inizio_max, 0))
            pezzo = sorgente.subclipped(inizio, inizio + durata_stacco)

        pezzo = _applica_zoom(_normalizza_verticale(pezzo))
        segmenti.append(pezzo)
        tempo_coperto += durata_stacco

    print(f"[Samaritan Maker] Montaggio: {len(segmenti)} stacchi "
          f"in {tempo_coperto:.1f}s (media {tempo_coperto/len(segmenti):.1f}s/stacco)")
    return concatenate_videoclips(segmenti, method="compose")


# ===========================================================================
# GRAFICA
# ===========================================================================
def crea_immagine_parola(testo, font_size=115, colore=GIALLO):
    """Renderizza una parola in PNG trasparente, con bordo nero spesso
    per restare leggibile su qualunque sfondo."""
    font = _carica_font(font_size)

    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = misura.textbbox((0, 0), testo, font=font)
    testo_w, testo_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    bordo, pad_x, pad_y = 9, 44, 28
    img = Image.new(
        "RGBA",
        (testo_w + bordo * 2 + pad_x * 2, testo_h + bordo * 2 + pad_y * 2),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(img).text(
        (pad_x + bordo - bbox[0], pad_y + bordo - bbox[1]),
        testo, font=font, fill=colore, stroke_width=bordo, stroke_fill="black",
    )
    return np.array(img)


def crea_banner_titolo(testo, larghezza_max, font_size=64):
    """Banner del titolo mostrato nei primi secondi: hook visivo per chi
    guarda senza audio (una fetta enorme del pubblico Shorts)."""
    font = _carica_font(font_size)
    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    parole, righe, riga = testo.split(), [], ""
    for parola in parole:
        tentativo = f"{riga} {parola}".strip()
        if misura.textlength(tentativo, font=font) <= larghezza_max - 80:
            riga = tentativo
        else:
            if riga:
                righe.append(riga)
            riga = parola
    if riga:
        righe.append(riga)
    righe = righe[:3]

    altezza_riga = font_size + 18
    img = Image.new(
        "RGBA", (larghezza_max, altezza_riga * len(righe) + 40), (0, 0, 0, 165)
    )
    draw = ImageDraw.Draw(img)
    for i, riga in enumerate(righe):
        w = draw.textlength(riga, font=font)
        draw.text(
            ((larghezza_max - w) / 2, 20 + i * altezza_riga),
            riga, font=font, fill="white", stroke_width=3, stroke_fill="black",
        )
    return np.array(img)


def crea_progress_bar(durata, passi=60):
    """Barra di avanzamento in cima al video: piccolo trucco di retention,
    comunica 'manca poco' e riduce lo swipe-away."""
    clips, altezza = [], 12
    sfondo = (
        ColorClip(size=(config.VIDEO_W, altezza), color=(20, 20, 20))
        .with_duration(durata)
        .with_position((0, 0))
        .with_opacity(0.55)
    )
    clips.append(sfondo)

    passo = durata / passi
    for i in range(1, passi + 1):
        larghezza = max(int(config.VIDEO_W * i / passi), 1)
        clips.append(
            ColorClip(size=(larghezza, altezza), color=(255, 230, 0))
            .with_start(passo * (i - 1))
            .with_duration(passo)
            .with_position((0, 0))
        )
    return clips


# ===========================================================================
# SOTTOTITOLI
# ===========================================================================
def genera_sottotitoli_clips(audio_path, titolo=""):
    """Sottotitoli parola-per-parola sincronizzati con Whisper."""
    import whisper

    print(f"[Samaritan Subtitles] Trascrizione con modello '{config.WHISPER_MODEL}'...")
    modello = whisper.load_model(config.WHISPER_MODEL)
    risultato = modello.transcribe(
        audio_path, language=config.LINGUA, word_timestamps=True
    )

    # Parole "calde" (nomi di gioco dal titolo + numeri) evidenziate in verde
    parole_chiave = {
        w.upper() for w in re.findall(r"\b[A-Za-z]{4,}\b", titolo)
    }

    clips = []
    y = int(config.VIDEO_H * 0.58)   # sopra la UI degli Shorts, sotto il centro

    for segmento in risultato.get("segments", []):
        for info in segmento.get("words", []):
            parola = info["word"].strip().upper()
            if not parola:
                continue

            inizio = info["start"]
            durata = max(info["end"] - inizio, 0.25)

            evidenzia = parola.strip(".,!?").isdigit() or parola.strip(".,!?") in parole_chiave
            img = crea_immagine_parola(
                parola, colore=VERDE if evidenzia else GIALLO
            )

            clip = (
                ImageClip(img)
                .with_start(inizio)
                .with_duration(durata)
                .with_position(("center", y))
            )
            # Animazione "pop": la parola entra crescendo. Sembra un dettaglio,
            # ma e' cio' che distingue un montaggio curato da uno automatico.
            try:
                clip = clip.resized(lambda t: min(1.0, 0.80 + 2.2 * t))
            except Exception:
                pass
            clips.append(clip)

    print(f"[Samaritan Subtitles] {len(clips)} parole sincronizzate.")
    return clips


# ===========================================================================
# PIPELINE DI RENDERING
# ===========================================================================
def assembla_video_finale(testo_per_audio=None, query_video="gameplay",
                          titolo="", tema="Gaming"):
    os.makedirs(config.DIR_OUTPUT, exist_ok=True)
    print("\n--- SAMARITAN MAKER: PRODUZIONE VIDEO ---")

    if not testo_per_audio:
        from brain import genera_script_samaritan
        dati = genera_script_samaritan(tema)
        testo_per_audio = dati["script"]
        query_video = dati["query_video"]
        titolo = dati["titolo"]

    audio_path = genera_voce_samaritan(testo_per_audio)
    if not audio_path:
        print("[Errore Maker] Audio non generato: interrompo.")
        return None

    percorsi_clip = scarica_clip_sfondo(query_video)
    if not percorsi_clip:
        print("[Errore Maker] Nessuna clip di sfondo: interrompo.")
        return None

    audio_clip = AudioFileClip(audio_path)
    durata = audio_clip.duration + 0.4          # coda per non tagliare l'ultima parola

    sfondo = costruisci_sfondo_montato(percorsi_clip, durata)
    if sfondo is None:
        print("[Errore Maker] Montaggio dello sfondo fallito: interrompo.")
        audio_clip.close()
        return None

    sfondo = sfondo.with_duration(durata).with_audio(audio_clip)
    livelli = [sfondo]

    # Banner titolo nei primi 2.5 secondi (hook per chi guarda in mute)
    if titolo:
        try:
            testo_banner = pulisci_testo(titolo).upper()
            banner = (
                ImageClip(crea_banner_titolo(testo_banner, int(config.VIDEO_W * 0.92)))
                .with_start(0)
                .with_duration(min(2.5, durata))
                .with_position(("center", int(config.VIDEO_H * 0.17)))
            )
            livelli.append(banner)
        except Exception as e:
            print(f"[Warning Maker] Banner titolo saltato: {e}")

    # Progress bar
    try:
        livelli.extend(crea_progress_bar(durata))
    except Exception as e:
        print(f"[Warning Maker] Progress bar saltata: {e}")

    # Sottotitoli
    try:
        livelli.extend(genera_sottotitoli_clips(audio_path, titolo))
    except Exception as e:
        print(f"[Warning Maker] Sottotitoli saltati: {e}")

    finale = CompositeVideoClip(
        livelli, size=(config.VIDEO_W, config.VIDEO_H)
    ).with_duration(durata)

    output_file = os.path.join(config.DIR_OUTPUT, "samaritan_short_subbed.mp4")
    print(f"[Samaritan Maker] Rendering {config.VIDEO_W}x{config.VIDEO_H} "
          f"@{config.FPS}fps ({durata:.1f}s)...")
    finale.write_videofile(
        output_file,
        fps=config.FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )

    for c in (audio_clip, sfondo, finale):
        try:
            c.close()
        except Exception:
            pass

    print("\nVIDEO GENERATO CON SUCCESSO!")
    return output_file


if __name__ == "__main__":
    assembla_video_finale()
