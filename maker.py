"""
Montaggio video di Samaritan.

La qualita' visiva nasce dall'EDITING, non da riprese fatte a mano:

  1. Materiale UFFICIALE del gioco (trailer + screenshot Steam) via gameplay.py
  2. Stacco ogni 2-3 secondi: l'occhio non ha tempo di annoiarsi
  3. Zoom lento (Ken Burns) su ogni stacco: movimento costante
  4. Sorgenti di proporzioni diverse dall'uscita inserite su sfondo sfocato
  5. Progress bar, banner del titolo, sottotitoli

Lo stesso montaggio produce due formati, e le misure le legge da config:
lo Short 9:16 da mezzo minuto (sottotitoli una parola per volta, enormi, al
centro) e il video lungo 16:9 da otto minuti (sottotitoli a frase, in basso).
Su otto minuti la forma dello Short vorrebbe oltre mille clip sovrapposti,
uno per parola, e non e' solo una questione di gusto.

La VESTE (colori, altezze, barra, banner, verso dello zoom, ritmo degli
stacchi) non e' fissa: la sceglie `veste.py` e cambia a ogni video, cosi' due
Short di fila non si somigliano. Qui dentro non ci sono piu' costanti grafiche
da leggere: tutto quello che si vede arriva dal dizionario `stile`.
"""
import os
import re
import random

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    ColorClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

import config
import veste
from voice import genera_voce_samaritan, pulisci_testo

FALLBACK_QUERY = [
    "video game action",
    "fps shooter gameplay",
    "esports tournament",
    "racing game",
    "arcade neon gaming",
    "gamer playing console",
]

# Colore di riserva del testo, usato solo da chi chiama queste funzioni senza
# passare una veste: i colori veri stanno in veste.py.
GIALLO = "#FFE600"

# Veste di riserva: serve a chi chiama una singola funzione di questo modulo
# (test, prove a mano) senza passare da assembla_video_finale.
STILE_BASE = veste.VESTI[0]

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",        # Ubuntu (Actions)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",                                 # Windows
    "arialbd.ttf",
    "arial.ttf",
]

# VideoFileClip aperti, riusati fra i vari stacchi della stessa sorgente
_CACHE_VIDEO = {}


def _carica_font(dimensione):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, dimensione)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ===========================================================================
# PEXELS (fallback quando il gioco non e' identificabile)
# ===========================================================================
def _orizzontale():
    """Il video che stiamo montando e' piu' largo che alto?"""
    return config.VIDEO_W >= config.VIDEO_H


def _cerca_clip_pexels(query, gia_scaricati):
    headers = {"Authorization": config.PEXELS_API_KEY}
    query_pulita = re.sub(r"\b(vertical|short|shorts)\b", "", query,
                          flags=re.IGNORECASE).strip()

    # Chiedere a Pexels clip gia' del verso giusto evita di montare un video
    # verticale dentro una cornice orizzontale, dove resterebbe una striscia
    # stretta in mezzo a due bande sfocate.
    orizzontale = _orizzontale()
    verso = "landscape" if orizzontale else "portrait"

    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query_pulita, "orientation": verso, "per_page": 15},
            timeout=12,
        )
        r.raise_for_status()
        video_trovati = r.json().get("videos", [])
    except Exception as e:
        print(f"[Warning Pexels] Ricerca '{query_pulita}' fallita: {e}")
        return []

    risultati = []
    for video in video_trovati:
        if video["id"] in gia_scaricati:
            continue
        if orizzontale:
            adatti = [f for f in video.get("video_files", [])
                      if f.get("width", 0) >= f.get("height", 1)]
        else:
            adatti = [f for f in video.get("video_files", [])
                      if f.get("height", 0) >= f.get("width", 1)]
        adatti = adatti or video.get("video_files", [])
        if not adatti:
            continue
        migliore = min(adatti,
                       key=lambda f: abs(f.get("height", 0) - config.VIDEO_H))
        risultati.append((video["id"], migliore["link"]))
    return risultati


def scarica_clip_sfondo(query, quante=None):
    """Scarica clip stock verticali da Pexels."""
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
                print(f"[Samaritan Maker] Download clip stock '{q}'...")
                dati = requests.get(link, timeout=60).content
                if len(dati) < 50_000:
                    continue
                with open(destinazione, "wb") as f:
                    f.write(dati)
                percorsi.append(destinazione)
                gia_scaricati.add(video_id)
            except Exception as e:
                print(f"[Warning Pexels] Download fallito: {e}")

    return percorsi


# ===========================================================================
# ADATTAMENTO AL FORMATO VERTICALE
# ===========================================================================
def _sfondo_sfocato(frame, durata, luminosita=0.42):
    """Sfondo a tutto schermo ricavato dal frame stesso: sfocato e scurito.

    La sfocatura viene fatta in miniatura e poi ingrandita: e' ~50 volte piu'
    veloce che sfocare a piena risoluzione e il risultato e' identico,
    visto che l'immagine e' comunque fuori fuoco.

    La miniatura tiene le proporzioni dell'uscita, non un 9:16 fisso: con le
    proporzioni sbagliate il ritaglio prende la parte sbagliata del fotogramma
    e lo sfondo del video lungo esce stirato.
    """
    W, H = config.VIDEO_W, config.VIDEO_H
    lato = 192
    if W >= H:
        piccolo_w, piccolo_h = lato, max(round(lato * H / W), 1)
    else:
        piccolo_w, piccolo_h = max(round(lato * W / H), 1), lato

    img = Image.fromarray(frame)
    fattore = max(piccolo_w / img.width, piccolo_h / img.height)
    img = img.resize((max(int(img.width * fattore), piccolo_w),
                      max(int(img.height * fattore), piccolo_h)), Image.BILINEAR)

    sinistra = (img.width - piccolo_w) // 2
    alto = (img.height - piccolo_h) // 2
    img = img.crop((sinistra, alto, sinistra + piccolo_w, alto + piccolo_h))

    img = img.filter(ImageFilter.GaussianBlur(4))
    img = ImageEnhance.Brightness(img).enhance(luminosita)   # scurito: il primo piano spicca
    img = img.resize((W, H), Image.BILINEAR)

    return ImageClip(np.array(img)).with_duration(durata)


# Quanto le proporzioni della sorgente possono discostarsi da quelle
# dell'uscita prima di rinunciare al pieno schermo. Dentro questa forbice il
# ritaglio toglie un bordo e non si nota; fuori toglierebbe meta' scena.
TOLLERANZA_PIENO_SCHERMO = (0.72, 1.30)


def _adatta_al_formato(clip, durata, stile=None):
    """Porta qualunque sorgente alle misure dell'uscita (9:16 o 16:9).

    - Sorgenti con le proporzioni dell'uscita -> scale-to-cover + ritaglio
      centrale, cioe' schermo pieno. E' il caso dei trailer Steam nel video
      lungo, che sono 16:9 come lui, e delle clip verticali nello Short.
    - Tutte le altre -> riquadro centrale su sfondo sfocato ricavato dal
      fotogramma stesso. E' il caso dei trailer 16:9 dentro uno Short, e delle
      clip girate col telefono dentro il video lungo.
    """
    W, H = config.VIDEO_W, config.VIDEO_H
    stile = stile or STILE_BASE

    proporzione_uscita = W / max(H, 1)
    proporzione_clip = clip.w / max(clip.h, 1)
    minimo, massimo = TOLLERANZA_PIENO_SCHERMO

    # --- Stesse proporzioni: riempie tutto lo schermo ---
    if minimo <= proporzione_clip / proporzione_uscita <= massimo:
        fattore = max(W / clip.w, H / clip.h)
        scalato = clip.resized((round(clip.w * fattore), round(clip.h * fattore)))
        return scalato.cropped(width=W, height=H,
                               x_center=scalato.w / 2, y_center=scalato.h / 2)

    # --- Proporzioni diverse: riquadro + sfondo sfocato ---
    if W >= H:
        # Uscita orizzontale: e' l'altezza a fare da vincolo, e il riquadro
        # sta al centro. Qui dentro finiscono le clip verticali di popponetv,
        # girate col telefono, che nel 16:9 non possono riempire lo schermo.
        altezza_fg = int(H * 0.94)
        larghezza_fg = max(round(altezza_fg * clip.w / max(clip.h, 1)), 2)
        if larghezza_fg > W * 0.94:
            larghezza_fg = int(W * 0.94)
            altezza_fg = max(round(larghezza_fg * clip.h / max(clip.w, 1)), 2)
        posizione = ("center", "center")
    else:
        # Uscita verticale: e' la larghezza a fare da vincolo, e l'altezza del
        # riquadro la decide la veste.
        larghezza_fg = int(W * config.ZOOM_GAMEPLAY)
        altezza_fg = max(round(larghezza_fg * clip.h / max(clip.w, 1)), 2)
        altezza_max = int(H * 0.62)
        if altezza_fg > altezza_max:
            altezza_fg = altezza_max
            larghezza_fg = max(round(altezza_fg * clip.w / max(clip.h, 1)), 2)
        posizione = ("center", int(H * stile["y_gameplay"]))

    primo_piano = clip.resized((larghezza_fg, altezza_fg))

    try:
        istante = min(clip.duration / 2, max(clip.duration - 0.05, 0))
        sfondo = _sfondo_sfocato(clip.get_frame(istante), durata,
                                 stile["luminosita_sfondo"])
    except Exception as e:
        print(f"[Warning Maker] Sfondo sfocato non generato ({e}), uso il nero.")
        sfondo = ColorClip(size=(W, H), color=(0, 0, 0)).with_duration(durata)

    return CompositeVideoClip(
        [sfondo, primo_piano.with_position(posizione)],
        size=(W, H),
    ).with_duration(durata)


# Il nome di prima, quando Samaritan faceva solo Short verticali.
_adatta_a_verticale = _adatta_al_formato


def _applica_zoom(clip, durata, intensita=0.08, verso="dentro"):
    """Ken Burns: zoom lento e continuo, il movimento trattiene l'occhio.

    Il verso fa piu' differenza di quanta sembri: "dentro" stringe sul
    dettaglio, "fuori" apre sulla scena. Lo stesso spezzone montato nei due
    versi si legge come due inquadrature diverse.
    """
    try:
        if verso == "fuori":
            def fattore(t):
                return 1 + intensita * (1 - t / max(durata, 0.01))
        else:
            def fattore(t):
                return 1 + intensita * (t / max(durata, 0.01))
        zoomata = clip.resized(fattore)
        return CompositeVideoClip(
            [zoomata.with_position("center")],
            size=(config.VIDEO_W, config.VIDEO_H),
        ).with_duration(durata)
    except Exception as e:
        print(f"[Warning Maker] Zoom non applicato ({e}).")
        return clip


# ===========================================================================
# MONTAGGIO
# ===========================================================================
def _apri_video(percorso):
    if percorso not in _CACHE_VIDEO:
        _CACHE_VIDEO[percorso] = VideoFileClip(percorso).without_audio()
    return _CACHE_VIDEO[percorso]


def _prepara_segmento(sorgente, durata, stile=None, verso="dentro"):
    """Costruisce un singolo stacco gia' in formato 1080x1920."""
    stile = stile or STILE_BASE
    intensita = stile["intensita_zoom"]

    if sorgente["tipo"] == "immagine":
        base = ImageClip(sorgente["path"]).with_duration(durata)
        # Sugli screenshot lo zoom e' piu' marcato: senza, sembrerebbero fermi
        return _applica_zoom(_adatta_al_formato(base, durata, stile), durata,
                             intensita=intensita * 2, verso=verso)

    video = _apri_video(sorgente["path"])
    if video.duration <= durata:
        pezzo = video.subclipped(0, video.duration)
        durata = video.duration
    else:
        inizio = random.uniform(0, video.duration - durata)
        pezzo = video.subclipped(inizio, inizio + durata)

    return _applica_zoom(_adatta_al_formato(pezzo, durata, stile), durata,
                         intensita=intensita, verso=verso)


def costruisci_sfondo_montato(sorgenti, durata_totale, stile=None):
    """Alterna le sorgenti con uno stacco ogni 2-3 secondi.

    Video e immagini vengono mescolati: i trailer danno movimento, gli
    screenshot danno inquadrature pulite del gioco. La veste decide quanto
    durano gli stacchi (`ritmo`) e da che verso si muove lo zoom.
    """
    stile = stile or STILE_BASE
    utilizzabili = [s for s in sorgenti if os.path.exists(s["path"])]
    if not utilizzabili:
        return None

    random.shuffle(utilizzabili)
    # I video per primi: il video deve APRIRE con movimento, non con uno statico
    utilizzabili.sort(key=lambda s: s["tipo"] != "video")

    segmenti, coperto, indice = [], 0.0, 0
    while coperto < durata_totale:
        sorgente = utilizzabili[indice % len(utilizzabili)]
        indice += 1

        durata = random.uniform(config.STACCO_MIN * stile["ritmo"],
                                config.STACCO_MAX * stile["ritmo"])
        durata = min(durata, durata_totale - coperto)
        if durata < 0.4:
            break

        # "alternato" cambia verso a ogni stacco: il montaggio respira invece
        # di spingere sempre nella stessa direzione per tutto il video.
        if stile["zoom"] == "alternato":
            verso = "dentro" if len(segmenti) % 2 == 0 else "fuori"
        else:
            verso = stile["zoom"]

        try:
            segmento = _prepara_segmento(sorgente, durata, stile, verso)
        except Exception as e:
            print(f"[Warning Maker] Sorgente scartata ({sorgente['path']}): {e}")
            utilizzabili = [s for s in utilizzabili if s is not sorgente]
            if not utilizzabili:
                break
            continue

        segmenti.append(segmento)
        coperto += segmento.duration

    if not segmenti:
        return None

    n_video = sum(1 for s in utilizzabili if s["tipo"] == "video")
    print(f"[Samaritan Maker] Veste '{stile['nome']}', zoom {stile['zoom']}.")
    print(f"[Samaritan Maker] {len(segmenti)} stacchi in {coperto:.1f}s "
          f"(media {coperto / len(segmenti):.1f}s) da {len(utilizzabili)} sorgenti "
          f"({n_video} video, {len(utilizzabili) - n_video} immagini)")

    return concatenate_videoclips(segmenti, method="compose")


# ===========================================================================
# GRAFICA
# ===========================================================================
def crea_immagine_parola(testo, font_size=115, colore=GIALLO):
    bordo, pad_x, pad_y = 9, 44, 28
    larghezza_utile = config.VIDEO_W * 0.94 - 2 * (bordo + pad_x)
    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # Le vesti usano corpi diversi, e una parola lunga scritta grande uscirebbe
    # dallo schermo: si rimpicciolisce finche' non ci sta. Meglio una parola
    # piu' piccola che una parola tagliata a meta'.
    while font_size > 60:
        font = _carica_font(font_size)
        if misura.textlength(testo, font=font) <= larghezza_utile:
            break
        font_size -= 6

    font = _carica_font(font_size)
    bbox = misura.textbbox((0, 0), testo, font=font)
    testo_w, testo_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

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
    font = _carica_font(font_size)
    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    righe, riga = [], ""
    for parola in testo.split():
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
    img = Image.new("RGBA",
                    (larghezza_max, altezza_riga * len(righe) + 40),
                    (0, 0, 0, 165))
    draw = ImageDraw.Draw(img)
    for i, riga in enumerate(righe):
        w = draw.textlength(riga, font=font)
        draw.text(((larghezza_max - w) / 2, 20 + i * altezza_riga),
                  riga, font=font, fill="white", stroke_width=3, stroke_fill="black")
    return np.array(img)


def _manda_a_capo(draw, testo, font, larghezza_max):
    """Spezza il testo in righe che stanno dentro larghezza_max."""
    righe, corrente = [], ""
    for parola in testo.split():
        tentativo = f"{corrente} {parola}".strip()
        if not corrente or draw.textlength(tentativo, font=font) <= larghezza_max:
            corrente = tentativo
        else:
            righe.append(corrente)
            corrente = parola
    if corrente:
        righe.append(corrente)
    return righe


def crea_miniatura(frame, testo, percorso=None, colore=GIALLO):
    """Miniatura verticale ricavata dallo sfondo, con l'amo scritto grande.

    Senza miniatura personalizzata YouTube estrae un fotogramma a caso. Nel
    feed Shorts non cambia niente, perche' il video parte da solo; cambia nella
    griglia del canale e nella ricerca, dove nove fotogrammi casuali in fila
    sono la differenza fra un canale e un archivio.
    """
    W, H = config.VIDEO_W, config.VIDEO_H
    percorso = percorso or config.FILE_MINIATURA

    img = Image.fromarray(np.uint8(frame)).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.BILINEAR)
    img = ImageEnhance.Brightness(img).enhance(0.55)   # il testo deve staccare

    testo = (testo or "").strip()
    if testo:
        draw = ImageDraw.Draw(img)
        margine = int(W * 0.08)
        dimensione, font, righe = 150, None, [testo]
        # Parte grande e rimpicciolisce finche' non sta in tre righe: i titoli
        # corti restano enormi, quelli lunghi restano comunque leggibili.
        for dimensione in range(150, 59, -10):
            font = _carica_font(dimensione)
            righe = _manda_a_capo(draw, testo, font, W - 2 * margine)
            if len(righe) <= 3:
                break
        altezza_riga = int(dimensione * 1.18)
        y = (H - altezza_riga * len(righe)) // 2
        for riga in righe:
            larghezza = draw.textlength(riga, font=font)
            draw.text(((W - larghezza) / 2, y), riga, font=font, fill=colore,
                      stroke_width=max(4, dimensione // 18), stroke_fill="black")
            y += altezza_riga

    # YouTube rifiuta le miniature oltre i 2 MB. A questa risoluzione non ci si
    # arriva quasi mai, ma su un fotogramma molto rumoroso puo' succedere.
    for qualita in (88, 78, 68, 58):
        img.save(percorso, "JPEG", quality=qualita, optimize=True)
        if os.path.getsize(percorso) <= 2 * 1024 * 1024:
            break
    print(f"[Samaritan Maker] Miniatura pronta: {os.path.basename(percorso)}")
    return percorso


def crea_progress_bar(durata, passi=60, altezza=12, colore=(255, 230, 0)):
    """La barra sta sempre in cima: in fondo la coprirebbe l'interfaccia di
    YouTube. Quello che cambia da una veste all'altra e' spessore e colore."""
    clips = []
    clips.append(
        ColorClip(size=(config.VIDEO_W, altezza), color=(20, 20, 20))
        .with_duration(durata).with_position((0, 0)).with_opacity(0.55)
    )
    passo = durata / passi
    for i in range(1, passi + 1):
        clips.append(
            ColorClip(size=(max(int(config.VIDEO_W * i / passi), 1), altezza),
                      color=colore)
            .with_start(passo * (i - 1)).with_duration(passo).with_position((0, 0))
        )
    return clips


# ===========================================================================
# SOTTOTITOLI
# ===========================================================================
def crea_immagine_frase(testo, font_size=52, colore="white",
                        larghezza_max=None):
    """Una riga (o due) di sottotitolo, su fascia scura semitrasparente.

    E' il sottotitolo del video lungo. Quello dello Short e' un'altra cosa:
    una parola per volta, enorme, al centro. Su otto minuti quella forma
    diventa insopportabile, e soprattutto costerebbe un clip di montaggio per
    ogni parola, cioe' oltre mille clip sovrapposti in un video solo.
    """
    larghezza_max = larghezza_max or int(config.VIDEO_W * 0.80)
    font = _carica_font(font_size)
    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    righe = _manda_a_capo(misura, testo, font, larghezza_max - 60)[:2]

    altezza_riga = font_size + 16
    img = Image.new("RGBA",
                    (larghezza_max, altezza_riga * len(righe) + 32),
                    (0, 0, 0, 150))
    draw = ImageDraw.Draw(img)
    for i, riga in enumerate(righe):
        w = draw.textlength(riga, font=font)
        draw.text(((larghezza_max - w) / 2, 16 + i * altezza_riga),
                  riga, font=font, fill=colore,
                  stroke_width=3, stroke_fill="black")
    return np.array(img)


def _sottotitoli_a_frase(risultato, stile):
    """I sottotitoli del video lungo: una frase per volta, in basso."""
    clips = []
    y = int(config.VIDEO_H * 0.80)
    corpo = max(int(config.VIDEO_H * 0.048), 30)

    for segmento in risultato.get("segments", []):
        testo = (segmento.get("text") or "").strip()
        if not testo:
            continue
        inizio = segmento.get("start", 0)
        durata = max(segmento.get("end", inizio) - inizio, 0.4)
        try:
            clips.append(
                ImageClip(crea_immagine_frase(testo, font_size=corpo,
                                              colore=stile["colore_testo"]))
                .with_start(inizio).with_duration(durata)
                .with_position(("center", y))
            )
        except Exception as e:
            print(f"[Warning Maker] Sottotitolo saltato: {e}")

    print(f"[Samaritan Subtitles] {len(clips)} frasi sincronizzate.")
    return clips


def genera_sottotitoli_clips(audio_path, titolo="", gioco="", stile=None):
    import whisper

    stile = stile or STILE_BASE

    print(f"[Samaritan Subtitles] Trascrizione con modello '{config.WHISPER_MODEL}'...")
    modello = whisper.load_model(config.WHISPER_MODEL)
    risultato = modello.transcribe(audio_path, language=config.LINGUA,
                                   word_timestamps=not config.VIDEO_LUNGO)

    if config.VIDEO_LUNGO:
        return _sottotitoli_a_frase(risultato, stile)

    parole_chiave = {w.upper() for w in re.findall(r"\b[A-Za-z]{4,}\b",
                                                   f"{titolo} {gioco}")}
    clips = []
    y = int(config.VIDEO_H * stile["y_sottotitoli"])

    for segmento in risultato.get("segments", []):
        for info in segmento.get("words", []):
            parola = info["word"].strip().upper()
            if not parola:
                continue

            inizio = info["start"]
            durata = max(info["end"] - inizio, 0.25)
            nudo = parola.strip(".,!?;:")
            evidenzia = nudo.isdigit() or nudo in parole_chiave

            colore = (stile["colore_evidenza"] if evidenzia
                      else stile["colore_testo"])
            clip = (
                ImageClip(crea_immagine_parola(
                    parola, font_size=stile["corpo_sottotitoli"], colore=colore))
                .with_start(inizio).with_duration(durata)
                .with_position(("center", y))
            )
            try:
                clip = clip.resized(lambda t: min(1.0, 0.80 + 2.2 * t))
            except Exception:
                pass
            clips.append(clip)

    print(f"[Samaritan Subtitles] {len(clips)} parole sincronizzate.")
    return clips


# ===========================================================================
# PIPELINE
# ===========================================================================
def assembla_video_finale(testo_per_audio=None, query_video="gameplay",
                          titolo="", gioco="", tema="Gaming",
                          resoconto=None, audio_pronto=None):
    """Monta il video e lo scrive su disco. Ritorna il percorso, o None.

    `audio_pronto` e' il percorso di un audio gia' sintetizzato: lo passa il
    video lungo, che la voce la genera una sezione per volta per sapere dove
    cade ogni capitolo. Senza, la voce la si genera qui da `testo_per_audio`,
    come ha sempre fatto lo Short.
    """
    os.makedirs(config.DIR_OUTPUT, exist_ok=True)
    print("\n--- SAMARITAN MAKER: PRODUZIONE VIDEO ---")

    # La veste di oggi: colori, altezze, barra, banner, zoom, ritmo. Cambia a
    # ogni video, quindi due Short di fila non si somigliano.
    stile = veste.scegli_veste()

    if not testo_per_audio:
        from brain import genera_script_samaritan
        dati = genera_script_samaritan(tema)
        testo_per_audio = dati["script"]
        query_video = dati["query_video"]
        titolo = dati["titolo"]
        gioco = dati.get("gioco", "")

    audio_path = audio_pronto or genera_voce_samaritan(testo_per_audio)
    if not audio_path:
        print("[Errore Maker] Audio non generato: interrompo.")
        return None

    # Materiale ufficiale del gioco, con ripiego automatico su stock
    from gameplay import procura_materiale
    sorgenti, gioco_ufficiale = procura_materiale(
        gioco=gioco, query_pexels=query_video, minimo=3
    )
    if not sorgenti:
        print("[Errore Maker] Nessun materiale video disponibile: interrompo.")
        return None

    # Qui dentro e' l'unico posto che sa se il materiale e' davvero ufficiale:
    # procura_materiale() ripiega su clip d'archivio senza azzerare 'gioco',
    # quindi chi scrive la descrizione non puo' dedurlo dal nome del gioco.
    # Le sorgenti d'archivio hanno 'gioco' a None, quelle Steam no.
    if resoconto is not None:
        ufficiali = sum(1 for s in sorgenti if s.get("gioco"))
        resoconto["gioco_ufficiale"] = gioco_ufficiale
        resoconto["sorgenti_ufficiali"] = ufficiali
        resoconto["sorgenti_stock"] = len(sorgenti) - ufficiali

    audio_clip = AudioFileClip(audio_path)
    durata = audio_clip.duration + 0.4

    sfondo = costruisci_sfondo_montato(sorgenti, durata, stile)
    if sfondo is None:
        print("[Errore Maker] Montaggio fallito: interrompo.")
        audio_clip.close()
        return None

    sfondo = sfondo.with_duration(durata).with_audio(audio_clip)
    livelli = [sfondo]

    # Banner e barra non ci sono in tutte le vesti: l'assenza e' una scelta,
    # non un errore, ed e' il modo piu' netto per far sembrare diverso il video.
    if titolo and stile["banner"]:
        altezza_banner, secondi_banner = stile["banner"]
        try:
            banner = (
                ImageClip(crea_banner_titolo(pulisci_testo(titolo).upper(),
                                             int(config.VIDEO_W * 0.92)))
                .with_start(0).with_duration(min(secondi_banner, durata))
                .with_position(("center", int(config.VIDEO_H * altezza_banner)))
            )
            livelli.append(banner)
        except Exception as e:
            print(f"[Warning Maker] Banner titolo saltato: {e}")

    if stile["barra"]:
        spessore, colore_barra = stile["barra"]
        try:
            livelli.extend(crea_progress_bar(durata, altezza=spessore,
                                             colore=colore_barra))
        except Exception as e:
            print(f"[Warning Maker] Progress bar saltata: {e}")

    try:
        livelli.extend(genera_sottotitoli_clips(audio_path, titolo,
                                                gioco_ufficiale or gioco, stile))
    except Exception as e:
        print(f"[Warning Maker] Sottotitoli saltati: {e}")

    finale = CompositeVideoClip(livelli,
                                size=(config.VIDEO_W, config.VIDEO_H)
                                ).with_duration(durata)

    nome_file = ("samaritan_video_lungo.mp4" if config.VIDEO_LUNGO
                 else "samaritan_short_subbed.mp4")
    output_file = os.path.join(config.DIR_OUTPUT, nome_file)
    print(f"[Samaritan Maker] Rendering {config.VIDEO_W}x{config.VIDEO_H} "
          f"@{config.FPS}fps ({durata:.1f}s, preset {config.PRESET_RENDER})...")
    finale.write_videofile(output_file, fps=config.FPS, codec="libx264",
                           audio_codec="aac", preset=config.PRESET_RENDER,
                           threads=4)

    # La miniatura si ricava dallo sfondo, non dal composito: sul composito ci
    # sono gia' banner e sottotitoli, e sovrapporci altro testo e' illeggibile.
    # Il file vecchio va tolto PRIMA: se la generazione fallisce, main.py non
    # deve caricare la miniatura del video di ieri.
    if os.path.exists(config.FILE_MINIATURA):
        os.remove(config.FILE_MINIATURA)
    try:
        from brain import testo_miniatura
        istante = min(1.2, max(durata - 0.2, 0.1))
        crea_miniatura(sfondo.get_frame(istante), testo_miniatura(titolo),
                       colore=stile["colore_evidenza"])
    except Exception as e:
        print(f"[Warning Maker] Miniatura saltata: {e}")

    for c in [audio_clip, sfondo, finale] + list(_CACHE_VIDEO.values()):
        try:
            c.close()
        except Exception:
            pass
    _CACHE_VIDEO.clear()

    # Il giro delle vesti avanza solo ora: il video esiste davvero, quindi
    # questa veste e' spesa. Se il rendering fosse fallito, la prossima
    # esecuzione riproverebbe con la stessa invece di saltarla.
    veste.segna_veste(stile["nome"])

    print("\nVIDEO GENERATO CON SUCCESSO!")
    return output_file


if __name__ == "__main__":
    assembla_video_finale()
