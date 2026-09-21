"""
Il diario pubblico di Samaritan: i Reel che lo vendono.

I video del canale parlano di videogiochi. Questi no: questi parlano di
Samaritan stesso, e servono a una cosa sola, far scrivere in DM qualcuno che
vuole la stessa macchina sul proprio canale. Il formato e' il diario: ogni
giorno un numero vero, detto ad alta voce e scritto grande in mezzo allo
schermo. Non c'e' niente da girare, perche' i numeri Samaritan li ha gia' in
casa: quanti video ha pubblicato da solo, quante visualizzazioni hanno fatto,
quante ore del suo tempo sono servite (zero, ed e' quello il punto).

**Questo file non tocca YouTube.** Non lo importa nessuno dei moduli della
pipeline del canale, non scrive su `cronologia_trend.json` (ha una memoria
sua, `promo_cronologia.json`), non tocca la miniatura e non passa mai da
`uploader.py`. Usa il montaggio di `maker.py` perche' riscriverlo sarebbe
tempo buttato, ma solo i pezzi che leggono e basta.

Sui numeri: le visualizzazioni sono quelle dell'API Analytics, che sono circa
2,5 volte meno di quelle che si leggono nell'app di YouTube Studio. E' una
scelta: in un video che vende, il numero piu' basso e' quello che non si puo'
contestare.

Uso:
    python promo.py            # scrive, monta e pubblica il Reel di oggi
    python promo.py --prova    # monta il Reel ma non lo pubblica
"""
import os
import re
import json
import time
import random
import datetime

import config

FILE_DIARIO = os.path.join(config.DIR_PROGETTO, "promo_cronologia.json")
FILE_REEL = os.path.join(config.DIR_OUTPUT, "samaritan_reel.mp4")
FILE_AUDIO = os.path.join(config.DIR_TEMP, "audio_promo.mp3")

# Lo sfondo non e' gameplay: e' materiale d'atmosfera da stock. Cambia a ogni
# Reel, altrimenti il profilo diventa una fila di video identici.
QUERY_SFONDO = [
    "artificial intelligence technology",
    "computer code screen",
    "server room lights",
    "programmer typing night",
    "abstract data visualization",
    "robot machine working",
]

# Quanti Reel indietro si guarda per non ripetere lo stesso attacco.
MEMORIA_DIARIO = 6

MIN_PAROLE = 40
MAX_PAROLE = 85

# Quanto resta in mezzo allo schermo la scheda con i numeri.
SCHEDA_SECONDI = 6.0


# ===========================================================================
# MEMORIA DEL DIARIO
# ===========================================================================
def carica_diario():
    """I Reel gia' usciti. Lista vuota se il file non c'e' ancora."""
    try:
        with open(FILE_DIARIO, "r", encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, list) else []
    except Exception:
        return []


def salva_nel_diario(voce):
    diario = carica_diario()
    diario.append(voce)
    diario = diario[-200:]
    try:
        with open(FILE_DIARIO, "w", encoding="utf-8") as f:
            json.dump(diario, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning Promo] Diario non salvato ({e}): "
              f"il prossimo Reel potrebbe ripetersi.")


# ===========================================================================
# I NUMERI VERI
# ===========================================================================
def _leggi_json(percorso, vuoto):
    try:
        with open(percorso, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return vuoto


def raccogli_numeri(oggi=None):
    """Quello che Samaritan ha fatto finora, in cifre.

    Legge i file direttamente invece di passare da brain.py e analyst.py: cosi'
    un guasto nella pipeline del canale non porta giu' anche il Reel, e questo
    modulo non tira dentro mezzo progetto per contare sei numeri.
    """
    oggi = oggi or datetime.date.today().isoformat()

    cronologia = _leggi_json(config.FILE_CRONOLOGIA, [])
    cronologia = [v for v in cronologia if isinstance(v, dict)]
    performance = _leggi_json(config.FILE_PERFORMANCE, {}).get("video", {})

    pubblicati = [v for v in cronologia if v.get("video_id")]
    giorni = sorted({v.get("data", "") for v in cronologia if v.get("data")})

    views = sum(int(m.get("views", 0) or 0) for m in performance.values())
    iscritti = sum(int(m.get("subscribersGained", 0) or 0)
                   for m in performance.values())

    # Il video andato meglio, con il titolo ripescato dalla cronologia: senza
    # titolo il numero da solo non racconta niente.
    migliore_id, migliore_views = "", 0
    for video_id, metriche in performance.items():
        v = int(metriche.get("views", 0) or 0)
        if v > migliore_views:
            migliore_id, migliore_views = video_id, v
    titoli = {v.get("video_id"): v.get("titolo", "") for v in cronologia}

    return {
        "giorno": len(carica_diario()) + 1,
        "video": len(pubblicati),
        "video_oggi": sum(1 for v in cronologia if v.get("data") == oggi),
        "giorni_attivi": len(giorni),
        "views": views,
        "iscritti": iscritti,
        "migliore_titolo": titoli.get(migliore_id, ""),
        "migliore_views": migliore_views,
    }


def _cifra(numero):
    """12345 -> '12.345', come si scrive in italiano."""
    return f"{int(numero):,}".replace(",", ".")


# ===========================================================================
# IL TESTO
# ===========================================================================
_SYSTEM = (
    "Sei il copywriter di un creator italiano. Scrivi il parlato di un Reel "
    "verticale da 25-30 secondi che racconta Samaritan, un programma che "
    "pubblica video su YouTube da solo: sceglie la notizia, scrive il testo, "
    "monta, mette i sottotitoli e carica, senza nessuno davanti al computer. "
    "Parli in prima persona, come il creator che l'ha costruito. Tono diretto "
    "e concreto, zero gergo da pubblicita', zero superlativi, niente emoji. "
    "I numeri sono veri: usali cosi' come sono, non arrotondarli in su."
)

_RICHIESTA = (
    "Rispondi SOLO con un oggetto JSON con due campi: \"titolo\" (massimo 60 "
    "caratteri, e' il testo che appare in alto nel video) e \"script\" (il "
    "parlato, {minimo}-{massimo} parole). Regole per lo script: la prima frase "
    "deve essere un amo di massimo otto parole; dentro devono comparire detti "
    "a voce almeno due dei numeri qui sotto; l'ultima frase deve invitare a "
    "scrivere in DM chi vuole la stessa cosa sul proprio canale. Niente "
    "hashtag, niente elenchi, solo frasi parlate.\n\n"
    "I numeri di oggi:\n{numeri}\n"
)


def _numeri_in_chiaro(numeri):
    righe = [
        f"- giorno {numeri['giorno']} da quando racconto questa cosa",
        f"- {numeri['video']} video pubblicati da solo",
        f"- {_cifra(numeri['views'])} visualizzazioni in tutto",
        f"- {numeri['iscritti']} iscritti arrivati",
        f"- {numeri['video_oggi']} video usciti oggi",
        "- 0 ore del mio tempo per produrli",
    ]
    if numeri["migliore_titolo"]:
        righe.append(f"- il video andato meglio ha fatto "
                     f"{_cifra(numeri['migliore_views'])} visualizzazioni")
    return "\n".join(righe)


def _estrai_json(testo):
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        raise ValueError("nessun JSON nella risposta")
    return json.loads(testo[inizio:fine + 1])


def _aperture_recenti():
    return {(v.get("script", "")[:24] or "").lower() for v in carica_diario()[-MEMORIA_DIARIO:]}


def _diario_di_ripiego(numeri):
    """Il testo da usare quando l'intelligenza artificiale non risponde.

    Non e' una toppa qualunque: un Reel al giorno che salta e' un giorno di
    profilo fermo. Le varianti ruotano sul numero del giorno, cosi' due Reel
    di fila non aprono uguale.
    """
    varianti = [
        ("Questo video non l'ho montato io",
         f"Questo video non l'ho montato io. Nemmeno quelli di ieri. "
         f"Ho scritto un programma che sceglie la notizia del giorno, scrive il "
         f"testo, monta e pubblica da solo: sono {numeri['video']} video finora, "
         f"{_cifra(numeri['views'])} visualizzazioni, e zero ore del mio tempo. "
         f"Io guardo solo i numeri la sera. Se lo vuoi sul tuo canale scrivimi in DM."),
        ("Giorno {g}: il canale va avanti senza di me".format(g=numeri["giorno"]),
         f"Giorno {numeri['giorno']}. Oggi sono usciti {max(numeri['video_oggi'], 1)} video "
         f"e io non ho toccato niente. Il programma legge le notizie di gaming, "
         f"sceglie la piu' grossa, la scrive, la monta con la voce e i sottotitoli "
         f"e la carica su YouTube. In tutto siamo a {_cifra(numeri['views'])} "
         f"visualizzazioni e {numeri['iscritti']} iscritti. "
         f"Lo monto anche sul tuo canale: scrivimi in DM."),
        ("Ho smesso di montare video a mano",
         f"Ho smesso di montare video a mano. Adesso ci pensa un programma: "
         f"{numeri['video']} video pubblicati, {_cifra(numeri['views'])} "
         f"visualizzazioni, {numeri['iscritti']} iscritti, e nessuna sera passata "
         f"davanti al computer a tagliare clip. Ci mette venti minuti da solo, "
         f"tre volte al giorno. Se ti serve la stessa cosa, scrivimi in DM."),
    ]
    return varianti[(numeri["giorno"] - 1) % len(varianti)]


def scrivi_diario(numeri):
    """Il testo del Reel di oggi: {titolo, script}.

    Prova con Groq, e se non risponde usa il testo di ripiego. Qui il ripiego
    ci sta, al contrario che in brain.py: la' un testo generico verrebbe
    pubblicato sul canale al posto di una notizia vera, qui il contenuto sono
    i numeri, che sono veri comunque.
    """
    aperture = _aperture_recenti()
    try:
        from groq import Groq
        cliente = Groq(api_key=config.GROQ_API_KEY)
        richiesta = _RICHIESTA.format(minimo=MIN_PAROLE, massimo=MAX_PAROLE,
                                      numeri=_numeri_in_chiaro(numeri))

        for modello in config.GROQ_MODELLI:
            for tentativo in (1, 2):
                try:
                    print(f"[Promo] {modello} - tentativo {tentativo}...")
                    risposta = cliente.chat.completions.create(
                        model=modello,
                        messages=[{"role": "system", "content": _SYSTEM},
                                  {"role": "user", "content": richiesta}],
                        temperature=0.9,
                        max_tokens=1200,
                    )
                    dati = _estrai_json(risposta.choices[0].message.content or "")
                    titolo = re.sub(r"\s+", " ", str(dati.get("titolo", ""))).strip()
                    script = re.sub(r"\s+", " ", str(dati.get("script", ""))).strip()

                    if not titolo or not (MIN_PAROLE <= len(script.split()) <= MAX_PAROLE):
                        print("[Promo] Risposta fuori misura, riprovo.")
                        continue
                    if script[:24].lower() in aperture:
                        print("[Promo] Apre come un Reel recente, riprovo.")
                        continue

                    print(f"[Promo] OK - '{titolo}' ({len(script.split())} parole)")
                    return {"titolo": titolo[:60], "script": script, "scritto_da": modello}
                except Exception as e:
                    print(f"[Promo] {modello}: {e}")
    except Exception as e:
        print(f"[Promo] Groq non utilizzabile ({e}).")

    titolo, script = _diario_di_ripiego(numeri)
    print(f"[Promo] Uso il testo di ripiego: '{titolo}'")
    return {"titolo": titolo, "script": script, "scritto_da": "ripiego"}


def costruisci_didascalia(dati, numeri):
    """La didascalia del Reel: quella che deve far scrivere in DM.

    Su Instagram i link nel testo non sono cliccabili, quindi la chiamata e'
    il DM, non un indirizzo che nessuno digitera' a mano.
    """
    righe = [
        dati["titolo"],
        "",
        f"Giorno {numeri['giorno']}. {numeri['video']} video pubblicati in automatico, "
        f"{_cifra(numeri['views'])} visualizzazioni, zero ore di montaggio.",
        "",
        f"Lo installo anche sul tuo canale: {config.CONTATTO_PROMO}.",
        "",
        "#automazione #intelligenzaartificiale #creatorlife #youtubeshorts "
        "#facciamolodasolo #reels",
    ]
    return "\n".join(righe)


# ===========================================================================
# IL VIDEO
# ===========================================================================
def crea_scheda_numeri(numeri, stile):
    """La scheda che compare in mezzo allo schermo con i numeri scritti grandi.

    E' il pezzo che distingue questi Reel dagli Short di gaming: li' i numeri
    non ci sono, qui sono il contenuto. Detto a voce un numero scivola via,
    scritto grande si ferma.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    from maker import _carica_font

    voci = [
        ("VIDEO PUBBLICATI DA SOLO", _cifra(numeri["video"])),
        ("VISUALIZZAZIONI", _cifra(numeri["views"])),
        ("ORE DEL MIO TEMPO", "0"),
    ]

    larghezza = int(config.VIDEO_W * 0.84)
    font_etichetta = _carica_font(34)
    font_valore = _carica_font(96)
    pad, passo = 52, 176

    altezza = pad * 2 + passo * len(voci)
    img = Image.new("RGBA", (larghezza, altezza), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, larghezza - 1, altezza - 1], radius=34,
                           fill=(0, 0, 0, 215),
                           outline=stile["colore_evidenza"], width=5)

    y = pad
    for etichetta, valore in voci:
        w = draw.textlength(etichetta, font=font_etichetta)
        draw.text(((larghezza - w) / 2, y), etichetta,
                  font=font_etichetta, fill=(235, 235, 235, 255))
        w = draw.textlength(valore, font=font_valore)
        draw.text(((larghezza - w) / 2, y + 46), valore, font=font_valore,
                  fill=stile["colore_evidenza"], stroke_width=4, stroke_fill="black")
        y += passo

    return np.array(img)


def monta_reel(dati, numeri):
    """Monta il Reel e ritorna il percorso del file, o None."""
    from moviepy import AudioFileClip, ImageClip, CompositeVideoClip

    import veste
    from voice import genera_voce_samaritan, pulisci_testo
    from maker import (scarica_clip_sfondo, costruisci_sfondo_montato,
                       genera_sottotitoli_clips, crea_progress_bar,
                       crea_banner_titolo)

    os.makedirs(config.DIR_OUTPUT, exist_ok=True)
    stile = veste.scegli_veste()

    # ElevenLabs no: il credito serve ai video del canale, e la sua rotazione
    # delle voci scriverebbe sulla cronologia di YouTube. Vedi voice.py.
    audio_path = genera_voce_samaritan(dati["script"], output_filename=FILE_AUDIO,
                                       permetti_elevenlabs=False)
    if not audio_path:
        print("[Errore Promo] Voce non generata: mi fermo.")
        return None

    query = random.choice(QUERY_SFONDO)
    sorgenti = [{"tipo": "video", "path": p, "gioco": None}
                for p in scarica_clip_sfondo(query, quante=4)]
    if not sorgenti:
        print("[Errore Promo] Nessuna clip di sfondo: mi fermo.")
        return None

    audio_clip = AudioFileClip(audio_path)
    durata = audio_clip.duration + 0.4

    sfondo = costruisci_sfondo_montato(sorgenti, durata, stile)
    if sfondo is None:
        print("[Errore Promo] Montaggio dello sfondo fallito: mi fermo.")
        audio_clip.close()
        return None

    livelli = [sfondo.with_duration(durata).with_audio(audio_clip)]

    try:
        banner = (
            ImageClip(crea_banner_titolo(pulisci_testo(dati["titolo"]).upper(),
                                         int(config.VIDEO_W * 0.92)))
            .with_start(0).with_duration(min(4.0, durata))
            .with_position(("center", int(config.VIDEO_H * 0.07)))
        )
        livelli.append(banner)
    except Exception as e:
        print(f"[Warning Promo] Banner saltato: {e}")

    # La scheda entra a un terzo del video e resta finche' c'e' tempo. Sta in
    # alto perche' i sottotitoli occupano la fascia bassa dello schermo.
    try:
        inizio = max(durata / 3.0, 1.0)
        scheda = (
            ImageClip(crea_scheda_numeri(numeri, stile))
            .with_start(inizio)
            .with_duration(min(SCHEDA_SECONDI, max(durata - inizio - 0.3, 1.0)))
            .with_position(("center", int(config.VIDEO_H * 0.22)))
        )
        livelli.append(scheda)
    except Exception as e:
        print(f"[Warning Promo] Scheda dei numeri saltata: {e}")

    if stile["barra"]:
        spessore, colore_barra = stile["barra"]
        try:
            livelli.extend(crea_progress_bar(durata, altezza=spessore,
                                             colore=colore_barra))
        except Exception as e:
            print(f"[Warning Promo] Progress bar saltata: {e}")

    try:
        livelli.extend(genera_sottotitoli_clips(audio_path, dati["titolo"], "", stile))
    except Exception as e:
        print(f"[Warning Promo] Sottotitoli saltati: {e}")

    finale = CompositeVideoClip(
        livelli, size=(config.VIDEO_W, config.VIDEO_H)).with_duration(durata)

    print(f"[Promo] Rendering {config.VIDEO_W}x{config.VIDEO_H} "
          f"@{config.FPS}fps ({durata:.1f}s)...")
    finale.write_videofile(FILE_REEL, fps=config.FPS, codec="libx264",
                           audio_codec="aac", preset="medium", threads=4)

    finale.close()
    audio_clip.close()
    return FILE_REEL


# ===========================================================================
# LAVORAZIONE COMPLETA
# ===========================================================================
def esegui_promo(pubblica=True):
    print("=" * 62)
    print(f"SAMARITAN PROMO | Reel per Instagram | {config.NOME_PROMO}")
    print("=" * 62)

    numeri = raccogli_numeri()
    print(f"[Promo] Giorno {numeri['giorno']}: {numeri['video']} video, "
          f"{_cifra(numeri['views'])} visualizzazioni, "
          f"{numeri['iscritti']} iscritti.")

    dati = scrivi_diario(numeri)
    print("-" * 62)
    print(dati["script"])
    print("-" * 62)

    video_path = monta_reel(dati, numeri)
    if not video_path:
        import notifier
        notifier.notifica_errore("Reel Instagram: montaggio fallito.")
        return None

    didascalia = costruisci_didascalia(dati, numeri)

    media_id = None
    if pubblica:
        import instagram
        media_id = instagram.pubblica_reel(video_path, didascalia)
    else:
        print("[Promo] Prova: il Reel non viene pubblicato.")
        print(didascalia)

    salva_nel_diario({
        "timestamp": int(time.time()),
        "data": datetime.date.today().isoformat(),
        "titolo": dati["titolo"],
        "script": dati["script"],
        "scritto_da": dati["scritto_da"],
        "numeri": numeri,
        "media_id": media_id,
    })

    # La notifica e' l'unico modo che ha lui di vedere cosa e' uscito senza
    # aprire Instagram. Se Telegram non e' configurato, non fa niente.
    try:
        import notifier
        stato = "PUBBLICATO" if media_id else "NON PUBBLICATO"
        notifier.invia_video(
            video_path,
            f"<b>Reel Instagram - {stato}</b>\n\n<b>{dati['titolo']}</b>",
        )
    except Exception as e:
        print(f"[Warning Promo] Notifica saltata: {e}")

    print("=" * 62)
    print("REEL PRONTO" + (f" -> {media_id}" if media_id else " (non pubblicato)"))
    print("=" * 62)
    return media_id


if __name__ == "__main__":
    import sys
    import traceback
    try:
        esegui_promo(pubblica="--prova" not in sys.argv)
    except Exception:
        traccia = traceback.format_exc()
        print(traccia)
        try:
            import notifier
            notifier.notifica_errore(f"Reel Instagram:\n{traccia}")
        except Exception:
            pass
        sys.exit(1)
