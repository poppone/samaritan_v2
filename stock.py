"""
Clip d'archivio (Pexels) coerenti con quello che dice la voce.

Prima lo Short aveva UNA sola ricerca per mezzo minuto di video: Pexels dava
le prime clip di quella ricerca, poi si completava con ricerche di riserva
pescate A CASO dal profilo (un'auto elettrica in carica sotto una notizia di
MotoGP), e le clip si montavano mescolate. Ora:

  1. il cervello scrive una ricerca per ogni pezzo dello script, in ordine
     (brain.pulisci_query_scene): sono le "scene";
  2. per ogni scena si cercano le candidate su Pexels e, con UNA sola
     chiamata al modello per tutto il video, si scartano quelle la cui
     descrizione non c'entra con la scena (brain.scegli_clip_pertinenti);
  3. ogni clip scaricata porta il numero della sua scena, e il montaggio
     (maker.costruisci_sfondo_montato) mette ogni scena nella sua finestra di
     tempo, nell'ordine in cui la voce la dice;
  4. le ricerche di riserva del profilo restano l'ultimissimo ripiego, e si
     prende quella piu' vicina all'argomento, non una a caso.

Qui dentro non c'e' moviepy: la logica si prova nei test senza scaricare
niente.
"""
import math
import os
import re
from urllib.parse import urlparse

import requests

import config
import profilo

# Quante candidate per scena si mandano al giudizio del modello: bastano per
# trovarne una buona e tengono corta la chiamata.
CANDIDATE_PER_SCENA = 6

# Sotto questo numero di clip lo sfondo e' una clip sola ripetuta: e' qui che
# entrano in gioco le ricerche di riserva del profilo.
MINIMO_CLIP = 2

# Sotto questa dimensione il file scaricato non e' un video vero.
BYTE_MINIMI = 50_000


# ===========================================================================
# DESCRIZIONI E VICINANZA
# ===========================================================================
def descrizione_da_url(url):
    """La descrizione di una clip Pexels, ricavata dal suo indirizzo.

    'https://www.pexels.com/video/a-red-car-on-a-race-track-123/' diventa
    'a red car on a race track'. Le clip senza descrizione nell'indirizzo
    ('.../video/123/') tornano stringa vuota.
    """
    percorso = urlparse(url or "").path.strip("/")
    ultimo = percorso.split("/")[-1] if percorso else ""
    ultimo = re.sub(r"-?\d+$", "", ultimo)
    return " ".join(p for p in ultimo.split("-") if p).strip()


def _parole(testo):
    return {p for p in re.findall(r"[a-z0-9]+", (testo or "").lower())
            if len(p) >= 3}


def vicinanza(a, b):
    """Quante parole di `a` ritornano in `b`, anche solo come radice.

    Basta la radice di quattro lettere: 'motorcycle' e 'motorbike' sono
    vicine, 'charging' e 'car' no.
    """
    pa, pb = _parole(a), _parole(b)
    radici_b = {p[:4] for p in pb}
    return sum(1 for p in pa if p in pb or p[:4] in radici_b)


def riserva_in_ordine(riserva, argomento):
    """Le ricerche di riserva, dalla piu' vicina all'argomento.

    A parita' di vicinanza resta l'ordine del profilo: niente sorteggio,
    cosi' sotto una notizia di MotoGP 'race track aerial' passa davanti a
    'electric car charging'.
    """
    return sorted(riserva, key=lambda q: -vicinanza(q, argomento))


# ===========================================================================
# PEXELS
# ===========================================================================
def _orizzontale():
    """Il video che stiamo montando e' piu' largo che alto?"""
    return config.VIDEO_W >= config.VIDEO_H


def cerca_candidate(query, gia_viste):
    """Le clip Pexels di una ricerca, senza scaricarle.

    Ritorna una lista di {id, link, descrizione}, nell'ordine di Pexels.
    """
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
        if video.get("id") in gia_viste:
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
        risultati.append({
            "id": video["id"],
            "link": migliore["link"],
            "descrizione": descrizione_da_url(video.get("url", "")),
        })
    return risultati


def _scarica(candidata, query):
    """Scarica una candidata. Ritorna il percorso, o None."""
    destinazione = os.path.join(config.DIR_TEMP, f"bg_{candidata['id']}.mp4")
    try:
        print(f"[Samaritan Stock] Download clip '{query}' "
              f"({candidata['descrizione'] or 'senza descrizione'})...")
        dati = requests.get(candidata["link"], timeout=60).content
        if len(dati) < BYTE_MINIMI:
            return None
        with open(destinazione, "wb") as f:
            f.write(dati)
        return destinazione
    except Exception as e:
        print(f"[Warning Pexels] Download fallito: {e}")
        return None


def _in_ordine_di_pertinenza(giudicate, buone, trovate):
    """Prima le candidate giudicate buone, nell'ordine del giudizio, poi
    quelle senza descrizione (il modello non le ha potute giudicare)."""
    scelte = [giudicate[j] for j in buone]
    return scelte + [c for c in trovate if not c["descrizione"]]


def scarica_clip_per_scene(scene, quante=None, contesto=""):
    """Scarica le clip d'archivio, almeno una per scena, nell'ordine dato.

    Ritorna una lista di (percorso, indice_scena). `contesto` e' il testo
    della voce: aiuta il modello a capire l'argomento delle scene.
    """
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    riserva = list(profilo.attivo().query_stock_riserva)
    scene = [s.strip() for s in (scene or []) if s and s.strip()]
    if not scene:
        scene = riserva[:1]
    if not scene:
        return []
    quante = max(quante or config.NUM_CLIP_SFONDO or 1, len(scene))
    per_scena = math.ceil(quante / len(scene))

    # 1. Le candidate di ogni scena, senza scaricare niente.
    viste, candidate = set(), []
    for q in scene:
        trovate = cerca_candidate(q, viste)
        viste.update(c["id"] for c in trovate)
        candidate.append(trovate)

    # 2. Un solo giudizio per tutto il video. Si giudicano solo le prime
    # candidate di ogni scena, e solo quelle che hanno una descrizione.
    da_giudicare = [[c for c in trovate if c["descrizione"]][:CANDIDATE_PER_SCENA]
                    for trovate in candidate]
    verdetto = None
    if any(da_giudicare):
        from brain import scegli_clip_pertinenti
        verdetto = scegli_clip_pertinenti(
            scene, [[c["descrizione"] for c in v] for v in da_giudicare],
            contesto)

    scartate = []
    ordinate = []
    for i, trovate in enumerate(candidate):
        if verdetto is None or i not in verdetto:
            # Nessun giudizio: le candidate nell'ordine di Pexels, come prima.
            ordinate.append(trovate)
            continue
        buone = _in_ordine_di_pertinenza(da_giudicare[i], verdetto[i],
                                         trovate)
        ordinate.append(buone)
        tenute = {c["id"] for c in buone}
        fuori = [c for c in da_giudicare[i] if c["id"] not in tenute]
        if fuori:
            print(f"[Samaritan Stock] Scena {i + 1} '{scene[i]}': scartate "
                  f"{len(fuori)} clip fuori tema "
                  f"({'; '.join(c['descrizione'] for c in fuori[:3])}).")
        scartate.extend((c, i) for c in fuori)

    # 3. Almeno una clip per scena, nell'ordine delle scene.
    risultati = []
    for i, lista in enumerate(ordinate):
        prese = 0
        for c in lista:
            if prese >= per_scena:
                break
            percorso = _scarica(c, scene[i])
            if percorso:
                risultati.append((percorso, i))
                prese += 1
        if not prese:
            print(f"[Samaritan Stock] Scena {i + 1} '{scene[i]}': nessuna "
                  f"clip adatta, la copre la scena vicina.")

    # 4. Ultimissimo ripiego: la riserva del profilo, dalla ricerca piu'
    # vicina all'argomento. Le clip vanno alle scene rimaste scoperte.
    if len(risultati) < MINIMO_CLIP and riserva:
        scoperte = [i for i in range(len(scene))
                    if not any(s == i for _, s in risultati)] or [len(scene) - 1]
        argomento = " ".join(scene)
        for q in riserva_in_ordine(riserva, argomento):
            if len(risultati) >= MINIMO_CLIP:
                break
            for c in cerca_candidate(q, viste):
                if len(risultati) >= MINIMO_CLIP:
                    break
                viste.add(c["id"])
                percorso = _scarica(c, q)
                if percorso:
                    scena = scoperte[min(len(risultati), len(scoperte) - 1)]
                    risultati.append((percorso, scena))

    # 5. Meglio una clip scartata che nessun video.
    if not risultati:
        for c, i in scartate:
            percorso = _scarica(c, scene[i])
            if percorso:
                risultati.append((percorso, i))
                break

    print(f"[Samaritan Stock] {len(risultati)} clip per {len(scene)} scene"
          f"{'' if verdetto is not None else ' (senza controllo di pertinenza)'}.")
    return risultati


def scarica_clip_sfondo(query, quante=None):
    """Compatibilita': una sola ricerca, solo i percorsi."""
    return [p for p, _ in scarica_clip_per_scene([query], quante)]


# ===========================================================================
# MONTAGGIO IN ORDINE DI SCENA
# ===========================================================================
def scena_dell_istante(istante, durata_totale, n_scene):
    """Quale scena copre questo istante: le scene si dividono il video in
    parti uguali, nell'ordine in cui la voce le dice."""
    if n_scene <= 1 or durata_totale <= 0:
        return 0
    return min(int(istante / durata_totale * n_scene), n_scene - 1)


def scegli_sorgente(sorgenti, istante, durata_totale, usi):
    """La sorgente del prossimo stacco quando le clip hanno una scena.

    Si pesca fra le clip della scena di quell'istante; se la scena non ne ha,
    fra quelle della scena piu' vicina. Le sorgenti senza scena (trailer
    ufficiali, clip girate in casa) valgono per tutto il video e si
    alternano con le altre. A parita', la meno usata: cosi' due clip della
    stessa scena si alternano invece di ripetere sempre la prima.
    `usi` e' un dizionario {id(sorgente): volte}, aggiornato qui.
    """
    con_scena = [s for s in sorgenti if s.get("scena") is not None]
    libere = [s for s in sorgenti if s.get("scena") is None]
    gruppo = list(libere)
    if con_scena:
        n_scene = max(max(s.get("scene_totali") or 0 for s in con_scena),
                      max(s["scena"] for s in con_scena) + 1)
        corrente = scena_dell_istante(istante, durata_totale, n_scene)
        presenti = sorted({s["scena"] for s in con_scena})
        vicina = min(presenti, key=lambda i: (abs(i - corrente), i))
        gruppo = [s for s in con_scena if s["scena"] == vicina] + libere
    if not gruppo:
        return None
    scelta = min(gruppo, key=lambda s: usi.get(id(s), 0))
    usi[id(scelta)] = usi.get(id(scelta), 0) + 1
    return scelta
