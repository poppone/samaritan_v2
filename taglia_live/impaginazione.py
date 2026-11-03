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
# Il ritaglio e' largo sette volte il volto: testa intera, cappello e spalle.
# Con 3.2 si vedeva mezza faccia sgranata (prova del 3/11 su Phantom Blade).
ALLARGA_VOLTO = 7.0


def _mediana(valori):
    ordinati = sorted(valori)
    n = len(ordinati)
    meta = n // 2
    return ordinati[meta] if n % 2 else (ordinati[meta - 1] + ordinati[meta]) / 2


def _pari(v):
    """ffmpeg vuole misure pari con yuv420p."""
    return int(v) // 2 * 2


def _vicini(a, b):
    """Stesso posto: centri a meno di una larghezza di volto."""
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    lato = max(a[2], b[2])
    return abs(ax - bx) < lato and abs(ay - by) < lato


FERMO_PX = 3          # un volto che in tutta la clip si sposta meno di cosi' e' disegnato
MINIMO_PER_FERMO = 4  # servono almeno questi fotogrammi per dire che non si muove

ZONE = {
    "alto-destra": (0.5, 0.0, 1.0, 0.5), "alto-sinistra": (0.0, 0.0, 0.5, 0.5),
    "basso-destra": (0.5, 0.5, 1.0, 1.0), "basso-sinistra": (0.0, 0.5, 0.5, 1.0),
    "destra": (0.5, 0.0, 1.0, 1.0), "sinistra": (0.0, 0.0, 0.5, 1.0),
    "alto": (0.0, 0.0, 1.0, 0.5), "basso": (0.0, 0.5, 1.0, 1.0),
}


def zona_webcam(testo, w, h):
    """Da "alto-destra" (vedi ZONE) o "x,y,larghezza,altezza" (pixel, o
    frazioni se tutti <= 1) al rettangolo (x0, y0, x1, y1) in pixel.
    None se il testo e' vuoto o non si capisce."""
    testo = (testo or "").strip().lower()
    if not testo:
        return None
    if testo in ZONE:
        x0, y0, x1, y1 = ZONE[testo]
        return x0 * w, y0 * h, x1 * w, y1 * h
    try:
        x, y, zw, zh = (float(v) for v in testo.split(","))
    except ValueError:
        return None
    if max(x, y, zw, zh) <= 1:
        x, y, zw, zh = x * w, y * h, zw * w, zh * h
    return x, y, x + zw, y + zh


def _centro(r):
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def nella_zona(volti_per_fotogramma, zona):
    """Solo i volti col centro dentro la zona della webcam."""
    if not zona:
        return volti_per_fotogramma
    x0, y0, x1, y1 = zona
    return [[r for r in v if x0 <= _centro(r)[0] <= x1 and y0 <= _centro(r)[1] <= y1]
            for v in volti_per_fotogramma]


def senza_volti_fermi(volti_per_fotogramma):
    """Via i volti che non si muovono mai: i ritratti dell'interfaccia (HUD)
    di giochi come Pax Dei sono fermi al pixel, chi sta in webcam no."""
    tutti = [r for v in volti_per_fotogramma for r in v]
    fermi = []
    for r in tutti:
        stessi = [_centro(x) for v in volti_per_fotogramma for x in v if _vicini(r, x)]
        if len(stessi) < MINIMO_PER_FERMO:
            continue
        xs, ys = [c[0] for c in stessi], [c[1] for c in stessi]
        if max(xs) - min(xs) <= FERMO_PX and max(ys) - min(ys) <= FERMO_PX:
            fermi.append(r)
    return [[r for r in v if not any(_vicini(r, f) for f in fermi)]
            for v in volti_per_fotogramma]


def volto_tipico(volti_per_fotogramma):
    """Il volto che resta fermo nello stesso posto (la webcam), poi la mediana.

    Non il piu' grande: i volti dei personaggi del gioco sono spesso piu'
    grandi della webcam ma si spostano da un fotogramma all'altro. Si tiene
    il posto in cui un volto compare nel maggior numero di fotogrammi; a
    parita', il volto piu' grande.
    """
    tutti = [r for v in volti_per_fotogramma for r in v]
    if not tutti:
        return None, 0.0
    def presenze(r):
        return sum(1 for v in volti_per_fotogramma if any(_vicini(r, x) for x in v))
    migliore = max(tutti, key=lambda r: (presenze(r), r[2] * r[3]))
    scelti = []
    for v in volti_per_fotogramma:
        vicini = [x for x in v if _vicini(migliore, x)]
        if vicini:
            scelti.append(max(vicini, key=lambda r: r[2] * r[3]))
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


def scegli(volti_per_fotogramma, w, h, zona=None):
    """("centro", None) oppure ("divisa", {"cam": (x,y,w,h), "gioco": (x,y,w,h)}).

    zona: il rettangolo di zona_webcam() se lo streamer ha detto dove sta la
    webcam; senza, si scartano solo i volti che non si muovono mai.
    """
    if not volti_per_fotogramma:
        return "centro", None
    if zona:
        volti_per_fotogramma = nella_zona(volti_per_fotogramma, zona)
    else:
        volti_per_fotogramma = senza_volti_fermi(volti_per_fotogramma)
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
    """Distanza dal fondo: nel terzo basso del gioco per la divisa (sulla
    giunta coprivano la barra del boss, che sta in alto), sotto la scena per
    il centro."""
    return 480 if impaginazione == "divisa" else 520
