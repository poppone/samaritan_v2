"""
Procura GAMEPLAY REALE del gioco di cui parla lo Short.

Perche' Steam e non YouTube:
  I trailer e gli screenshot sullo store Steam sono asset che l'EDITORE
  pubblica apposta per essere diffusi. Scaricarli dal CDN pubblico non viola
  nulla. Scaricare gameplay da YouTube, anche con licenza Creative Commons,
  viola invece i Termini di Servizio di YouTube: pessima idea quando e'
  proprio YouTube la piattaforma su cui vuoi monetizzare.

Sul Content ID: l'audio originale viene SEMPRE scartato (-an in ffmpeg) e
sostituito dalla voce sintetica. L'audio e' il canale su cui il Content ID
rivendica nel 90% dei casi, quindi il rischio residuo e' basso.

Catena delle fonti:
  1. Trailer ufficiali Steam del gioco esatto  (gameplay vero)
  2. Screenshot ufficiali Steam animati in Ken Burns  (gioco esatto, statico)
  3. Pexels  (stock generico, solo se il gioco non e' identificabile)

Sullo stesso gioco non esce due volte lo stesso materiale: quanti Short sono
gia' usciti su quel titolo decide da che punto dell'elenco si comincia a
pescare trailer e screenshot, e da che secondo del trailer si taglia. Senza,
due video sullo stesso gioco a settimane di distanza montano le stesse
identiche clip, che e' il modo piu' rapido per farsi riconoscere come canale
automatizzato.
"""
import json
import os
import re
import subprocess
from difflib import SequenceMatcher
from urllib.parse import quote, urljoin

import requests

import config

STEAM_SEARCH = "https://steamcommunity.com/actions/SearchApps/{}"
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"

# Steam ha migrato tutti i trailer a HLS: non esistono piu' link mp4 diretti.
# Servono ffmpeg e il parsing del manifest per estrarre un mp4 utilizzabile.
RISOLUZIONE_PREFERITA = 1080
SALTA_INTRO_SEC = 10        # i primi secondi dei trailer sono loghi degli studi
DURATA_SCARICO_SEC = 45     # abbastanza materiale per ricavarne spezzoni vari

# Sotto questa somiglianza il risultato Steam viene rifiutato: meglio stock
# generico che gameplay di un gioco diverso da quello di cui parla lo Short.
SOGLIA_CORRISPONDENZA = 0.72

# Rete di sicurezza per le abbreviazioni che il modello a volte usa comunque
ALIAS_GIOCHI = {
    "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V",
    "gta san andreas": "Grand Theft Auto San Andreas",
    "cs2": "Counter-Strike 2",
    "cs go": "Counter-Strike 2",
    "csgo": "Counter-Strike 2",
    "witcher 3": "The Witcher 3: Wild Hunt",
    "the witcher 3": "The Witcher 3: Wild Hunt",
    "rdr2": "Red Dead Redemption 2",
    "bg3": "Baldur's Gate 3",
    "pubg": "PUBG: BATTLEGROUNDS",
    "tarkov": "Escape from Tarkov",
}


def _ffmpeg():
    """Trova ffmpeg. moviepy lo installa via imageio-ffmpeg, quindi e'
    disponibile anche quando non e' nel PATH di sistema."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ===========================================================================
# RICERCA DEL GIOCO SU STEAM
# ===========================================================================
def _varianti_nome(nome):
    """Genera nomi alternativi: 'Elden Ring: Shadow of the Erdtree' non sempre
    matcha, 'Elden Ring' si'."""
    nome = nome.strip()
    varianti = [nome]
    senza_sottotitolo = re.split(r"[:\-–]", nome)[0].strip()
    if senza_sottotitolo and senza_sottotitolo != nome:
        varianti.append(senza_sottotitolo)
    senza_anno = re.sub(r"\b(19|20)\d{2}\b", "", nome).strip()
    if senza_anno and senza_anno not in varianti:
        varianti.append(senza_anno)
    return varianti


def _normalizza(testo):
    testo = testo.lower().replace("&", "and")
    testo = re.sub(r"[^\w\s]", " ", testo)
    return re.sub(r"\s+", " ", testo).strip()


ROMANI = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
          "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def _numero_sequel(nome):
    """Estrae il numero del capitolo ('V', '2', 'IV') dal nome del gioco.

    Indispensabile: la somiglianza testuale fra 'Grand Theft Auto V' e
    'Grand Theft Auto IV: The Complete Edition' e' 0.97, ma sono due giochi
    diversi. Un solo carattere separa quasi tutti i sequel.
    """
    token = None
    for parola in _normalizza(nome).split():
        if parola.isdigit():
            token = int(parola)
        elif parola in ROMANI:
            token = ROMANI[parola]
    return token


def _somiglianza(richiesto, ufficiale):
    """Quanto il risultato Steam corrisponde davvero a cio' che abbiamo chiesto.

    Serve perche' la ricerca Steam restituisce SEMPRE qualcosa: cercando
    'Minecraft' (che su Steam non esiste) risponde 'Minecraft Dungeons', un
    gioco diverso. Montare quel gameplay su uno Short che parla di Minecraft
    sarebbe peggio che usare stock generico.
    """
    a = _normalizza(richiesto)
    b = _normalizza(ufficiale)
    if a == b:
        return 1.0

    # Capitoli diversi della stessa saga: rifiuto netto, qualunque sia la
    # somiglianza testuale. Vale anche per 'Portal' contro 'Portal 2'.
    if _numero_sequel(richiesto) != _numero_sequel(ufficiale):
        return 0.0

    # Confronta anche col nome senza sottotitolo, cosi' 'Witcher 3' matcha
    # 'The Witcher 3: Wild Hunt' ma 'Minecraft' non matcha 'Minecraft Dungeons'
    base = _normalizza(re.split(r"[:\-–]", ufficiale)[0])
    return max(
        SequenceMatcher(None, a, b).ratio(),
        SequenceMatcher(None, a, base).ratio(),
    )


def video_gia_fatti(gioco):
    """Quanti Short sono gia' usciti su questo gioco, secondo la cronologia.

    Il confronto e' fra il nome che ha scritto il modello e quelli che aveva
    scritto le volte precedenti, non col nome ufficiale di Steam: sono la
    stessa penna, quindi si assomigliano molto piu' di quanto 'GTA 6'
    assomigli a 'Grand Theft Auto VI'. Gli alias noti sono appianati prima.
    """
    if not gioco:
        return 0
    cercato = ALIAS_GIOCHI.get(_normalizza(gioco), gioco)
    try:
        with open(config.FILE_CRONOLOGIA, "r", encoding="utf-8") as f:
            cronologia = json.load(f)
    except Exception:
        return 0
    if not isinstance(cronologia, list):
        return 0

    quanti = 0
    for elemento in cronologia:
        if not isinstance(elemento, dict):
            continue
        passato = (elemento.get("gioco") or "").strip()
        if not passato:
            continue
        passato = ALIAS_GIOCHI.get(_normalizza(passato), passato)
        if _somiglianza(passato, cercato) >= SOGLIA_CORRISPONDENZA:
            quanti += 1
    return quanti


def ruota(elementi, salto):
    """Stessa lista, cominciando da un altro punto. Lista vuota: niente da fare."""
    if not elementi:
        return elementi
    inizio = salto % len(elementi)
    return elementi[inizio:] + elementi[:inizio]


def cerca_gioco_steam(nome):
    """Ritorna (appid, nome_ufficiale) oppure (None, None)."""
    nome = ALIAS_GIOCHI.get(_normalizza(nome), nome)

    migliore = (0.0, None, None)
    for variante in _varianti_nome(nome):
        try:
            r = requests.get(STEAM_SEARCH.format(quote(variante)), timeout=12)
            r.raise_for_status()
            risultati = r.json()
        except Exception as e:
            print(f"[Gameplay] Ricerca Steam '{variante}' fallita: {e}")
            continue

        for risultato in (risultati or [])[:5]:
            nome_ufficiale = risultato.get("name", "")
            punteggio = _somiglianza(variante, nome_ufficiale)
            if punteggio > migliore[0]:
                migliore = (punteggio, risultato.get("appid"), nome_ufficiale)

    punteggio, appid, nome_ufficiale = migliore
    if appid and punteggio >= SOGLIA_CORRISPONDENZA:
        print(f"[Gameplay] '{nome}' -> Steam: {nome_ufficiale} "
              f"(appid {appid}, match {punteggio:.2f})")
        return appid, nome_ufficiale

    if appid:
        print(f"[Gameplay] '{nome}' scartato: il risultato piu' vicino era "
              f"'{nome_ufficiale}' (match {punteggio:.2f}, serve "
              f"{SOGLIA_CORRISPONDENZA}). Meglio lo stock che il gioco sbagliato.")
    else:
        print(f"[Gameplay] '{nome}' non trovato su Steam.")
    return None, None


def dettagli_gioco(appid):
    try:
        r = requests.get(
            STEAM_DETAILS,
            params={"appids": appid, "l": "english"},
            timeout=20,
        )
        r.raise_for_status()
        blocco = r.json().get(str(appid), {})
        if not blocco.get("success"):
            return None
        return blocco.get("data")
    except Exception as e:
        print(f"[Gameplay] Dettagli Steam non disponibili: {e}")
        return None


# ===========================================================================
# DOWNLOAD DEI TRAILER (HLS -> mp4)
# ===========================================================================
def _scegli_variante_hls(url_master):
    """Legge il manifest HLS e ritorna l'URL della variante di qualita'
    piu' vicina a 1080p senza superarla."""
    try:
        r = requests.get(url_master, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[Gameplay] Manifest HLS non leggibile: {e}")
        return None

    righe = r.text.splitlines()
    varianti = []
    for i, riga in enumerate(righe):
        if not riga.startswith("#EXT-X-STREAM-INF"):
            continue
        if i + 1 >= len(righe):
            continue
        match_res = re.search(r"RESOLUTION=\d+x(\d+)", riga)
        altezza = int(match_res.group(1)) if match_res else 0
        varianti.append((altezza, urljoin(url_master, righe[i + 1].strip())))

    if not varianti:
        return url_master        # playlist singola, usabile direttamente

    accettabili = [v for v in varianti if v[0] <= RISOLUZIONE_PREFERITA]
    scelta = max(accettabili or varianti, key=lambda v: v[0])
    print(f"[Gameplay] Variante HLS scelta: {scelta[0]}p")
    return scelta[1]


def _estrai_mp4(url_stream, destinazione, salta=SALTA_INTRO_SEC):
    """Usa ffmpeg per trasformare lo stream HLS in un mp4 locale SENZA AUDIO."""
    comando = [
        _ffmpeg(), "-y", "-loglevel", "error",
        "-ss", str(salta),
        "-i", url_stream,
        "-t", str(DURATA_SCARICO_SEC),
        "-an",                       # audio scartato: azzera il rischio Content ID
        "-c:v", "copy",
        destinazione,
    ]
    try:
        subprocess.run(comando, check=True, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"[Gameplay] Remux fallito ({e}), riprovo con ricodifica...")
        comando[comando.index("copy")] = "libx264"
        comando.insert(-1, "-preset")
        comando.insert(-1, "veryfast")
        try:
            subprocess.run(comando, check=True, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception as e2:
            print(f"[Gameplay] Anche la ricodifica e' fallita: {e2}")
            return False

    return os.path.exists(destinazione) and os.path.getsize(destinazione) > 100_000


def scarica_trailer_steam(appid, dati, quanti=3, salto=0):
    """Scarica i trailer ufficiali come mp4 muti. Ritorna i percorsi locali.

    `salto` e' quanti Short sono gia' usciti su questo gioco: sposta sia il
    punto da cui si comincia a pescare nell'elenco, sia il secondo da cui si
    taglia lo spezzone, cosi' il secondo video sullo stesso titolo non monta
    gli stessi fotogrammi del primo.
    """
    filmati = dati.get("movies", []) or []
    if not filmati:
        return []

    # I trailer marcati 'highlight' sono quelli principali scelti dall'editore
    # e restano davanti: la rotazione avviene dentro i due gruppi, cosi' il
    # video di ripasso cambia materiale ma non ripiega sugli scarti.
    principali = [m for m in filmati if m.get("highlight", False)]
    altri = [m for m in filmati if not m.get("highlight", False)]
    filmati = ruota(principali, salto) + ruota(altri, salto)

    # Un trailer dura in genere un paio di minuti: spostarsi di venti secondi
    # per ogni passaggio da' quattro inquadrature d'apertura diverse prima di
    # tornare al punto di partenza.
    inizio = SALTA_INTRO_SEC + (salto % 4) * 20
    tentativi = [inizio]
    if inizio != SALTA_INTRO_SEC:
        tentativi.append(SALTA_INTRO_SEC)   # trailer troppo corto per il salto
    tentativi.append(0)                     # piu' corto anche dell'intro

    percorsi = []
    for filmato in filmati:
        if len(percorsi) >= quanti:
            break

        url_master = filmato.get("hls_h264") or filmato.get("hls")
        if not url_master:
            mp4 = filmato.get("mp4", {})
            url_master = mp4.get("max") or mp4.get("480")
        if not url_master:
            continue

        url_stream = _scegli_variante_hls(url_master) if ".m3u8" in url_master else url_master
        if not url_stream:
            continue

        destinazione = os.path.join(config.DIR_TEMP, f"steam_{appid}_{filmato['id']}.mp4")
        nome_breve = filmato.get("name", "")[:48]
        print(f"[Gameplay] Scarico trailer ufficiale: {nome_breve}")

        for salta in tentativi:
            if _estrai_mp4(url_stream, destinazione, salta=salta):
                percorsi.append(destinazione)
                break

    print(f"[Gameplay] {len(percorsi)} trailer ufficiali pronti.")
    return percorsi


def scarica_screenshot_steam(appid, dati, quanti=4, salto=0):
    """Screenshot ufficiali in 1920x1080: usati come inserti animati.

    `salto` sposta il punto di partenza nell'elenco: un gioco con dodici
    screenshot ne ha tre gruppi diversi prima di ripetersi.
    """
    screenshot = ruota(dati.get("screenshots", []) or [], salto * quanti)
    percorsi = []

    for shot in screenshot[:quanti * 2]:
        if len(percorsi) >= quanti:
            break
        url = shot.get("path_full")
        if not url:
            continue
        destinazione = os.path.join(config.DIR_TEMP, f"shot_{appid}_{shot['id']}.jpg")
        try:
            contenuto = requests.get(url, timeout=30).content
            if len(contenuto) < 20_000:
                continue
            with open(destinazione, "wb") as f:
                f.write(contenuto)
            percorsi.append(destinazione)
        except Exception as e:
            print(f"[Gameplay] Screenshot non scaricato: {e}")

    if percorsi:
        print(f"[Gameplay] {len(percorsi)} screenshot ufficiali pronti.")
    return percorsi


# ===========================================================================
# PUNTO DI INGRESSO
# ===========================================================================
def procura_materiale(gioco=None, query_pexels="gameplay", minimo=3):
    """Ritorna una lista di sorgenti [{tipo, path, gioco}] per il montaggio.

    tipo = 'video' | 'immagine'
    """
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    sorgenti = []
    nome_ufficiale = None

    if gioco and config.USA_STEAM:
        appid, nome_ufficiale = cerca_gioco_steam(gioco)
        if appid:
            dati = dettagli_gioco(appid)
            if dati:
                # Quante volte abbiamo gia' parlato di questo gioco: decide da
                # dove si pesca, cosi' il materiale non si ripete.
                salto = video_gia_fatti(gioco)
                if salto:
                    print(f"[Gameplay] Short numero {salto + 1} su "
                          f"'{nome_ufficiale}': cambio materiale.")
                for percorso in scarica_trailer_steam(appid, dati,
                                                      config.STEAM_MAX_TRAILER,
                                                      salto):
                    sorgenti.append({"tipo": "video", "path": percorso,
                                     "gioco": nome_ufficiale})
                for percorso in scarica_screenshot_steam(
                        appid, dati, config.STEAM_MAX_SCREENSHOT, salto):
                    sorgenti.append({"tipo": "immagine", "path": percorso,
                                     "gioco": nome_ufficiale})

    if len(sorgenti) >= minimo:
        print(f"[Gameplay] Materiale UFFICIALE di '{nome_ufficiale}': "
              f"{len(sorgenti)} sorgenti.")
        return sorgenti, nome_ufficiale

    # ------------------------------------------------- Fallback su Pexels
    mancanti = max(minimo - len(sorgenti), 2)
    print(f"[Gameplay] Materiale ufficiale insufficiente: "
          f"integro con {mancanti} clip Pexels.")
    from maker import scarica_clip_sfondo
    for percorso in scarica_clip_sfondo(query_pexels, quante=mancanti):
        sorgenti.append({"tipo": "video", "path": percorso, "gioco": None})

    return sorgenti, nome_ufficiale


if __name__ == "__main__":
    import sys
    nome = sys.argv[1] if len(sys.argv) > 1 else "Cyberpunk 2077"
    materiale, ufficiale = procura_materiale(nome)
    print(f"\nGioco: {ufficiale or 'non identificato'}")
    for s in materiale:
        dimensione = os.path.getsize(s["path"]) / 1_000_000
        print(f"  [{s['tipo']:9}] {dimensione:6.1f} MB  {s['path']}")
