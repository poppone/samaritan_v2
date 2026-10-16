# -*- coding: utf-8 -*-
"""
Come si dispone la clip nel 9:16, a seconda di dove sta la webcam.

Logica pura (niente OpenCV, niente ffmpeg): riceve i riquadri dei volti
trovati in qualche fotogramma e decide. Si testa in tests/test_clip_live.py.

Due impaginazioni:
  - "centro": la scena intera al centro su sfondo sfocato. Va bene quando
    Davide e' il soggetto (Contraddittorio, chiacchiere: volto grande) e
    quando un volto non c'e' proprio.
  - "divisa": la webcam ritagliata e ingrandita in alto, il gioco ritagliato
    in basso, i sottotitoli sulla giunta. E' come si fanno gli Short dei
    giochi: nella scena intera rimpicciolita il testo del gioco non si legge
    e la webcam in un angolo diventa un francobollo.
La webcam cambia posto da gioco a gioco, quindi non si scrive da nessuna
parte: si cerca il volto clip per clip.
"""

LARGHEZZA = 1080
ALTEZZA_CAM = 640                     # fascia in alto
ALTEZZA_GIOCO = 1920 - ALTEZZA_CAM    # fascia in basso
RAPPORTO_CAM = LARGHEZZA / ALTEZZA_CAM
RAPPORTO_GIOCO = LARGHEZZA / ALTEZZA_GIOCO

VOLTO_GRANDE = 0.12      # volto oltre il 12% della larghezza: e' il soggetto
QUOTA_FOTOGRAMMI = 0.5   # il volto deve esserci in almeno meta' dei fotogrammi
ALLARGA_VOLTO = 3.2      # la webcam e' circa tre volte il volto


def _mediana(valori):
    ordinati = sorted(valori)
    n = len(ordinati)
    meta = n // 2
    return ordinati[meta] if n % 2 else (ordinati[meta - 1] + ordinati[meta]) / 2


def _pari(v):
    """ffmpeg vuole misure pari con yuv420p."""
    return int(v) // 2 * 2


def volto_tipico(volti_per_fotogramma):
    """Un volto per fotogramma (il piu' grande), poi la mediana: un falso
    positivo in un fotogramma non sposta il ritaglio."""
    scelti = [max(v, key=lambda r: r[2] * r[3]) for v in volti_per_fotogramma if v]
    if not scelti:
        return None, 0.0
    quota = len(scelti) / len(volti_per_fotogramma)
    return tuple(_mediana([r[i] for r in scelti]) for i in range(4)), quota


def riquadro_webcam(volto, w, h):
    """Il ritaglio della webcam attorno al volto, nel formato della fascia alta."""
    x, y, fw, fh = volto
    cx, cy = x + fw / 2, y + fh / 2
    cw = min(w, fw * ALLARGA_VOLTO)
    ch = cw / RAPPORTO_CAM
    if ch > h:
        ch = h
        cw = ch * RAPPORTO_CAM
    rx = min(max(0, cx - cw / 2), w - cw)
    ry = min(max(0, cy - ch / 2), h - ch)
    return _pari(rx), _pari(ry), _pari(cw), _pari(ch)


def riquadro_gioco(cam, w, h):
    """Il ritaglio del gioco: altezza piena, largo quanto serve alla fascia
    bassa. Centrato, ma spostato via dalla webcam quando sta su un lato,
    cosi' non la si vede due volte."""
    gh = h
    gw = min(w, gh * RAPPORTO_GIOCO)
    gx = (w - gw) / 2
    cx, _cy, cw, _ch = cam
    if cx + cw <= w / 2:                    # webcam a sinistra
        gx = max(gx, min(cx + cw, w - gw))
    elif cx >= w / 2:                       # webcam a destra
        gx = min(gx, max(0, cx - gw))
    return _pari(gx), 0, _pari(gw), _pari(gh)


def scegli(volti_per_fotogramma, w, h):
    """("centro", None) oppure ("divisa", {"cam": (x,y,w,h), "gioco": (x,y,w,h)})."""
    if not volti_per_fotogramma:
        return "centro", None
    volto, quota = volto_tipico(volti_per_fotogramma)
    if volto is None or quota < QUOTA_FOTOGRAMMI:
        return "centro", None
    if volto[2] / w > VOLTO_GRANDE:
        return "centro", None
    cam = riquadro_webcam(volto, w, h)
    return "divisa", {"cam": cam, "gioco": riquadro_gioco(cam, w, h)}


def filtro_ffmpeg(impaginazione, riquadri, file_ass):
    """Il filter_complex di ffmpeg per l'impaginazione scelta."""
    if impaginazione == "divisa":
        cx, cy, cw, ch = riquadri["cam"]
        gx, gy, gw, gh = riquadri["gioco"]
        return (f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale={LARGHEZZA}:{ALTEZZA_CAM}[cam];"
                f"[0:v]crop={gw}:{gh}:{gx}:{gy},scale={LARGHEZZA}:{ALTEZZA_GIOCO}[gioco];"
                f"[cam][gioco]vstack,ass={file_ass}[v]")
    return ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=25:2,eq=brightness=-0.08[sfondo];"
            "[0:v]scale=1080:-2[primo];"
            "[sfondo][primo]overlay=(W-w)/2:(H-h)/2,"
            f"ass={file_ass}[v]")


def margine_sottotitoli(impaginazione):
    """Distanza dal fondo: sulla giunta per la divisa, sotto la scena per il centro."""
    return 1920 - ALTEZZA_CAM - 150 if impaginazione == "divisa" else 520
