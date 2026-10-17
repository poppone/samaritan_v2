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
  0. Trailer dalla pagina ufficiale dell'editore, per i giochi che su Steam
     non ci sono (GTA VI, vedi PAGINE_UFFICIALI)
  1. Trailer ufficiali Steam del gioco esatto  (gameplay vero)
  2. Screenshot ufficiali Steam animati in Ken Burns  (gioco esatto, statico)
  3. Gli altri negozi ufficiali - PlayStation, Epic, Nintendo, Xbox - per le
     esclusive console, che su Steam non ci sono (vedi materiale_dai_negozi)
  4. Pexels  (stock generico, solo se il gioco non e' identificabile)

Un canale che non parla di videogiochi (profilo con materiale 'stock', vedi
profilo.py) salta i passi 0-3: su Steam ci sono solo giochi, e cercarci una
ricetta darebbe un gioco a caso. Resta Pexels, piu' le clip girate in casa.

Sullo stesso gioco non esce due volte lo stesso materiale: quanti Short sono
gia' usciti su quel titolo decide da che punto dell'elenco si comincia a
pescare trailer e screenshot, e da che secondo del trailer si taglia. Senza,
due video sullo stesso gioco a settimane di distanza montano le stesse
identiche clip, che e' il modo piu' rapido per farsi riconoscere come canale
automatizzato.
"""
import html
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote, urljoin

import requests

import config
import profilo

STEAM_SEARCH = "https://steamcommunity.com/actions/SearchApps/{}"
# Senza un browser dichiarato diversi negozi rispondono 403 o 404.
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"

# Steam ha migrato tutti i trailer a HLS: non esistono piu' link mp4 diretti.
# Servono ffmpeg e il parsing del manifest per estrarre un mp4 utilizzabile.
RISOLUZIONE_PREFERITA = 1080
SALTA_INTRO_SEC = 10        # i primi secondi dei trailer sono loghi degli studi
# Quanti secondi si prendono da ogni trailer: config.SECONDI_TRAILER, che vale
# 45 per uno Short e 240 per il video lungo. Otto minuti di montaggio chiedono
# il trailer intero, non uno spezzone: con 45 secondi a testa le stesse
# inquadrature tornerebbero sei o sette volte nello stesso video.

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
    # Su Steam il primo capitolo si chiama "Part I": senza alias il controllo
    # dei sequel lo rifiuta e restano solo i giochi dal nome simile.
    "the last of us": "The Last of Us Part I",
    "the last of us 2": "The Last of Us Part II Remastered",
    "the last of us part 2": "The Last of Us Part II Remastered",
    "the last of us part ii": "The Last of Us Part II Remastered",
    # Nomi di serie: nessun negozio ha un gioco chiamato solo "Pokemon" o
    # "The Legend of Zelda". L'11 ottobre 2026 "Pokemon: Prime Day steals"
    # e "The Legend of Zelda: Nintendo chief..." sono usciti su clip Pexels:
    # meglio il capitolo piu' recente della serie che lo stock.
    "pokemon": "Pokémon Legends: Z-A",
    "zelda": "The Legend of Zelda: Tears of the Kingdom",
    "legend of zelda": "The Legend of Zelda: Tears of the Kingdom",
    "the legend of zelda": "The Legend of Zelda: Tears of the Kingdom",
    # Il 14 ottobre 2026 e' arrivato "Super Mario": stessa storia.
    "mario": "Super Mario Bros. Wonder",
    "super mario": "Super Mario Bros. Wonder",
    "mario kart": "Mario Kart World",
    "donkey kong": "Donkey Kong Bananza",
    "kirby": "Kirby and the Forgotten Land",
    "metroid": "Metroid Prime 4: Beyond",
}

# Serie che le notizie chiamano con uno slogan o un personaggio invece che col
# nome del gioco: basta che il nome contenga la parola. Il 15 ottobre 2026
# "You're Late, 007" (lo slogan di 007 First Light) e' finito su clip Pexels.
ALIAS_PER_PAROLA = {
    "007": "007 First Light",
    "james bond": "007 First Light",
}


def nome_con_alias(nome):
    """Il nome con cui cercare il gioco nei negozi."""
    normale = _normalizza(nome or "")
    if normale in ALIAS_GIOCHI:
        return ALIAS_GIOCHI[normale]
    parole = f" {normale} "
    for parola, gioco in ALIAS_PER_PAROLA.items():
        if f" {parola} " in parole:
            return gioco
    return nome

# Parole che Steam aggiunge al nome dello stesso gioco: edizioni e ristampe.
# Qualunque altra parola in piu' nel nome Steam indica un gioco diverso.
PAROLE_EDIZIONE = {
    "the", "a", "of", "and", "edition", "remastered", "remaster", "remake",
    "enhanced", "legacy", "definitive", "complete", "deluxe", "ultimate",
    "goty", "game", "year", "collection", "anniversary", "hd", "part",
    "director", "directors", "s", "cut", "tm",
}


def _ffmpeg():
    """Trova ffmpeg, preferendo quello di sistema.

    L'ordine conta, e non e' un dettaglio di gusto: il binario che si porta
    dietro imageio-ffmpeg va in segmentation fault sugli stream HLS di Steam.
    Verificato sulle run del 18 e 19 settembre 2026, dove OGNI trailer falliva
    sia in remux sia in ricodifica e il log chiudeva con "0 trailer ufficiali
    pronti": i video uscivano di soli screenshot fermi, mentre il montaggio e'
    costruito sull'idea che i trailer diano il movimento.

    Quello di sistema legge gli stessi stream senza problemi ed e' gia'
    installato dal workflow con apt. imageio resta il ripiego per chi lavora
    in locale senza ffmpeg nel PATH.
    """
    percorso = shutil.which("ffmpeg")
    if percorso:
        return percorso
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
    """Minuscole, senza punteggiatura e senza accenti.

    Gli accenti vanno via perche' il modello scrive 'Pokemon' e 'Ghost of
    Yotei' mentre i negozi scrivono 'Pokemon' con la e accentata e 'Yotei'
    con la o lunga: lasciandoli, i due nomi risultavano due giochi diversi e
    il video finiva su clip generiche.
    """
    # NFD e non NFKD: la seconda trasformerebbe il simbolo del marchio in
    # 'TM', e 'The Last of Us(TM) Part I' diventerebbe un gioco diverso da
    # 'The Last of Us Part I'. Cosi' il simbolo resta e lo togliera' la
    # riga sulla punteggiatura, com'e' sempre stato.
    testo = unicodedata.normalize("NFD", testo.lower())
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = testo.replace("&", "and")
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

    # Una parola che il gioco cercato non ha rende il gioco un altro, anche
    # quando le lettere quasi coincidono. Il 26 settembre 2026 lo Short su
    # The Last of Us e' uscito col gameplay di 'The Last Kich Of Us', un gioco
    # sconosciuto, perche' la somiglianza fra i due nomi era 0.85.
    parole_cercate = set(a.split()) | PAROLE_EDIZIONE
    if not (set(b.split()) <= parole_cercate or set(base.split()) <= parole_cercate):
        return 0.0
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
    cercato = nome_con_alias(gioco)
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
        passato = nome_con_alias(passato)
        if _somiglianza(passato, cercato) >= SOGLIA_CORRISPONDENZA:
            quanti += 1
    return quanti


def ruota(elementi, salto):
    """Stessa lista, cominciando da un altro punto. Lista vuota: niente da fare."""
    if not elementi:
        return elementi
    inizio = salto % len(elementi)
    return elementi[inizio:] + elementi[:inizio]


# ===========================================================================
# LE CLIP GIRATE DA POPPONE
# ===========================================================================
# Sono l'unico materiale originale del canale: trailer e screenshot li
# pubblica l'editore ed escono identici su mille altri canali, mentre due mani
# vere su un volante vero non ce le ha nessun altro. Stanno in
# 'clip_mie/<categoria>/' e si montano SOLO dove sono a tema: un volante
# dentro una notizia su GTA 6 toglie piu' di quanto aggiunga. Una categoria
# puo' essere un genere ('guida') o un gioco solo ('fortnite').
GENERI_CLIP_MIE = {"racing": "guida"}

# I generi su Steam li dichiara l'editore, e i giochi-servizio con tante
# modalita' ci mettono dentro tutto: Marvel Rivals ne dichiara otto, "Racing"
# compreso, ed e' un gioco di supereroi. Il 7 ottobre 2026 lo Short su Marvel
# Rivals e' uscito con dentro le clip del volante di Poppone, che in un gioco
# di supereroi non c'entrano niente.
# Una lista corta e' una scelta, una lista lunga e' un elenco: da sei generi
# in su serve una conferma, e un gioco di guida vero e' dichiarato anche
# Sports o Simulation. Forza Horizon 5: Racing, Simulation, Sports. F1 25:
# Racing, Sports. Marvel Rivals: ne' l'uno ne' l'altro.
MAX_GENERI_CHE_DICONO_QUALCOSA = 5
GENERI_CHE_CONFERMANO = {"sports", "simulation"}

PAROLE_CLIP_MIE = {
    "fortnite": ("fortnite",),
    "guida": (
        "assetto corsa", "forza horizon", "forza motorsport", "gran turismo",
        "need for speed", "formula 1", "f1 2", "f1 24", "f1 25", "f1 26",
        "dirt rally", "wrc", "motogp", "nascar", "trackmania", "the crew",
        "burnout", "rally", "mario kart", "ride 5", "automobilista",
        "le mans ultimate", "iracing", "rfactor",
    ),
}

ESTENSIONI_CLIP = (".mp4", ".mov", ".webm")


def _generi_attendibili(generi):
    """La lista dei generi Steam sta dicendo qualcosa, o sta elencando tutto?

    Vedi il commento su MAX_GENERI_CHE_DICONO_QUALCOSA: una lista lunga vale
    solo se c'e' un genere che conferma quello che ci interessa.
    """
    if not generi:
        return False
    if len(generi) <= MAX_GENERI_CHE_DICONO_QUALCOSA:
        return True
    return bool(set(generi) & GENERI_CHE_CONFERMANO)


def categoria_clip_mie(gioco, dati=None):
    """A quale cartella di clip mie appartiene questo gioco, o None.

    Prima il genere dichiarato da Steam, che e' il dato piu' affidabile;
    poi il nome, perche' un gioco appena annunciato spesso su Steam non c'e'
    ancora ed e' proprio quello di cui parlano le notizie.
    """
    generi = [(genere.get("description") or "").strip().lower()
              for genere in (dati or {}).get("genres") or []]
    if _generi_attendibili(generi):
        for etichetta in generi:
            if etichetta in GENERI_CLIP_MIE:
                return GENERI_CLIP_MIE[etichetta]

    nome = _normalizza(gioco or "")
    if not nome:
        return None
    for categoria, parole in PAROLE_CLIP_MIE.items():
        if any(parola in nome for parola in parole):
            return categoria
    return None


def clip_mie(categoria, salto=0, quante=None):
    """I file di quella categoria, ruotati come trailer e screenshot.

    La rotazione serve alla stessa cosa: due Short sullo stesso gioco non
    devono aprire con la stessa identica clip.
    """
    if not categoria:
        return []
    quante = config.MAX_CLIP_MIE if quante is None else quante
    if quante <= 0:
        return []
    cartella = os.path.join(config.DIR_CLIP_MIE, categoria)
    try:
        nomi = sorted(n for n in os.listdir(cartella)
                      if n.lower().endswith(ESTENSIONI_CLIP))
    except OSError:
        return []
    percorsi = [os.path.join(cartella, n) for n in nomi]
    return ruota(percorsi, salto)[:quante]


def cerca_gioco_steam(nome):
    """Ritorna (appid, nome_ufficiale) oppure (None, None)."""
    nome = nome_con_alias(nome)

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


# Steam tiene nascosti i dettagli dei giochi vietati ai minori (Cyberpunk 2077,
# Elden Ring, Dead Space...) a chi non ha superato il controllo dell'eta', e
# dai server di GitHub la risposta arrivava senza dati: niente trailer, niente
# screenshot, e il video usciva montato solo con clip di repertorio. Questi
# sono i cookie che il sito imposta dopo il controllo dell'eta'.
_COOKIE_ETA = {
    "birthtime": "0",
    "lastagecheckage": "1-January-1990",
    "mature_content": "1",
    "wants_mature_content": "1",
}


def dettagli_gioco(appid):
    """I dettagli Steam del gioco (trailer, screenshot, generi), o None.

    Prova prima la richiesta semplice, poi con il controllo dell'eta' superato
    e il paese esplicito. Ogni fallimento lascia una riga nel log: prima
    un gioco senza materiale spariva in silenzio e il video ripiegava sulle
    clip generiche senza che nessuno se ne accorgesse.
    """
    tentativi = (
        ("semplice", {"appids": appid, "l": "english"}, None),
        ("eta' verificata", {"appids": appid, "l": "english", "cc": "us"}, _COOKIE_ETA),
        ("eta' verificata, Italia", {"appids": appid, "l": "english", "cc": "it"}, _COOKIE_ETA),
    )
    ripiego = None
    motivi = []
    for nome, parametri, cookie in tentativi:
        try:
            r = requests.get(STEAM_DETAILS, params=parametri, cookies=cookie,
                             timeout=20)
            r.raise_for_status()
            blocco = (r.json() or {}).get(str(appid)) or {}
        except Exception as e:
            motivi.append(f"{nome}: {e}")
            continue

        dati = blocco.get("data") if blocco.get("success") else None
        if not dati:
            motivi.append(f"{nome}: Steam risponde senza dati")
            continue
        if dati.get("movies") or dati.get("screenshots"):
            if motivi:
                print(f"[Gameplay] Dettagli Steam ottenuti al tentativo "
                      f"'{nome}' (prima: {'; '.join(motivi)}).")
            return dati
        motivi.append(f"{nome}: nessun trailer ne' screenshot")
        ripiego = ripiego or dati

    print(f"[Gameplay] Materiale Steam non disponibile per {appid}: "
          f"{'; '.join(motivi)}.")
    return ripiego


# ===========================================================================
# DOWNLOAD DEI TRAILER (HLS -> mp4)
# ===========================================================================
def _ffprobe():
    """ffprobe sta accanto a ffmpeg: il workflow li installa insieme con apt."""
    return shutil.which("ffprobe") or "ffprobe"


def _durata_video(url):
    """Quanti secondi dura il filmato, o None se non si riesce a sapere.

    Legge solo l'intestazione, non scarica il video. Se ffprobe non c'e' o il
    filmato non risponde si torna None e chi chiama si arrangia: sapere la
    durata e' un vantaggio, non una condizione per pubblicare.
    """
    comando = [_ffprobe(), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", url]
    try:
        esito = subprocess.run(comando, check=True, timeout=60,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
        durata = float(esito.stdout.decode().strip())
        return durata if durata > 0 else None
    except Exception:
        return None


# Di quanto si sposta il punto di taglio fra uno Short e il successivo sullo
# stesso gioco.
PASSO_TAGLIO_SEC = 15


def punti_di_taglio(url, salto, durata_clip=None):
    """Da che secondo tagliare lo spezzone, coi ripieghi in coda.

    `salto` e' quanti Short sono gia' usciti su quel gioco. Prima il punto si
    spostava di venti secondi per passaggio e dopo quattro tornava al
    principio: su GTA VI, che ha tre soli trailer, il 7 ottobre 2026 sono
    usciti lo Short numero 28 e il 29 nello stesso giorno e montavano quasi
    gli stessi fotogrammi.
    Misurando la durata vera si usa tutto il filmato: 'An Extended Look' dura
    minuti e ne vengono fuori decine di finestre diverse invece di quattro.
    """
    durata_clip = config.SECONDI_TRAILER if durata_clip is None else durata_clip
    ripieghi = [SALTA_INTRO_SEC, 0]
    durata = _durata_video(url)
    if not durata:
        # Senza la durata si torna al criterio di prima: meglio un punto
        # probabile con due ripieghi che nessuno spezzone.
        return _senza_doppioni([SALTA_INTRO_SEC + (salto % 4) * 20] + ripieghi)

    ultimo = durata - durata_clip
    if ultimo <= SALTA_INTRO_SEC:
        # Filmato corto: ci sta un solo spezzone e comincia dove capita.
        return _senza_doppioni(ripieghi)

    finestre = int((ultimo - SALTA_INTRO_SEC) // PASSO_TAGLIO_SEC) + 1
    inizio = SALTA_INTRO_SEC + (salto % finestre) * PASSO_TAGLIO_SEC
    return _senza_doppioni([min(inizio, ultimo)] + ripieghi)


def _senza_doppioni(secondi):
    visti, elenco = set(), []
    for s in secondi:
        if s not in visti:
            visti.add(s)
            elenco.append(s)
    return elenco


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


def _estrai_mp4(url_stream, destinazione, salta=SALTA_INTRO_SEC, durata=None,
                a_1080=False):
    """Usa ffmpeg per trasformare lo stream HLS in un mp4 locale SENZA AUDIO.

    `a_1080` riduce a 1080 righe invece di copiare: i trailer di Rockstar sono
    4K in mpeg4 quasi senza compressione, circa 400 MB ogni 45 secondi, e
    tre cosi' a video peserebbero sul montaggio senza dare niente in piu' a
    uno Short verticale.
    """
    durata = config.SECONDI_TRAILER if durata is None else durata
    comando = [
        _ffmpeg(), "-y", "-loglevel", "error",
        "-ss", str(salta),
        "-i", url_stream,
        "-t", str(durata),
        "-an",                       # audio scartato: azzera il rischio Content ID
        "-c:v", "copy",
        destinazione,
    ]
    if a_1080:
        comando[comando.index("copy")] = "libx264"
        comando[-1:-1] = ["-vf", "scale=-2:1080", "-preset", "veryfast",
                          "-crf", "20", "-pix_fmt", "yuv420p"]
    # I tempi massimi seguono la durata richiesta: con 45 secondi bastavano
    # fissi, ma un trailer intero da quattro minuti si scarica in piu' tempo e
    # un limite fisso lo farebbe fallire sempre.
    try:
        subprocess.run(comando, check=True, timeout=max(180, durata * 3),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as e:
        if a_1080:
            # Era gia' una ricodifica: non c'e' un piano B diverso da provare.
            print(f"[Gameplay] Ricodifica fallita: {e}")
            return False
        print(f"[Gameplay] Remux fallito ({e}), riprovo con ricodifica...")
        comando[comando.index("copy")] = "libx264"
        comando.insert(-1, "-preset")
        comando.insert(-1, "veryfast")
        try:
            subprocess.run(comando, check=True, timeout=max(300, durata * 5),
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
        print("[Gameplay] Nessun trailer ufficiale su Steam per questo gioco.")
        return []

    # I trailer marcati 'highlight' sono quelli principali scelti dall'editore
    # e restano davanti: la rotazione avviene dentro i due gruppi, cosi' il
    # video di ripasso cambia materiale ma non ripiega sugli scarti.
    principali = [m for m in filmati if m.get("highlight", False)]
    altri = [m for m in filmati if not m.get("highlight", False)]
    filmati = ruota(principali, salto) + ruota(altri, salto)

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

        # Il punto di taglio si misura su QUESTO filmato: i trailer di un
        # gioco hanno durate diverse e il piu' lungo ne regala di piu'.
        for salta in punti_di_taglio(url_stream, salto):
            if _estrai_mp4(url_stream, destinazione, salta=salta):
                percorsi.append(destinazione)
                break

    print(f"[Gameplay] {len(percorsi)} trailer ufficiali pronti.")
    return percorsi


# ===========================================================================
# GIOCHI CHE SU STEAM NON CI SONO: LA PAGINA UFFICIALE DELL'EDITORE
# ===========================================================================
# GTA VI e' l'argomento che porta piu' pubblico (8 video sugli ultimi 20 al
# 27 settembre 2026) e su Steam non esiste: finiva sempre su clip Pexels
# generiche. Rockstar pubblica i trailer come mp4 scaricabili nella pagina
# Downloads del sito ufficiale, verificato dai server di GitHub il 27
# settembre 2026. E' materiale dell'editore come i trailer Steam, e come
# quelli si prende senza audio.
PAGINE_UFFICIALI = {
    "gta6": {
        "nome": "Grand Theft Auto VI",
        "pagina": "https://www.rockstargames.com/VI/downloads",
        "schema": r"https://media-rockstargames-com\.akamaized\.net/VI/downloads/videos/[^\"'\s<>\\]+\.mp4",
        # Se la pagina cambia forma, questi restano validi finche' Rockstar
        # non li toglie.
        "riserva": [
            "https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Trailer_2/GTAVI_Trailer_2.mp4",
            "https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Trailer_1/GTAVI_Trailer_1.mp4",
            "https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_An_Extended_Look/GTAVI_An_Extended_Look.mp4",
        ],
    },
}

# La copertina animata e' un'immagine che si muove appena, non gameplay.
_NON_GAMEPLAY = ("cover_art", "coverart", "logo")


def gioco_con_pagina_ufficiale(gioco):
    """La chiave di PAGINE_UFFICIALI per questo gioco, o None.

    Il modello scrive il nome in tanti modi ('GTA 6', 'GTA VI', 'gta6',
    'Grand Theft Auto VI'); GTA V e San Andreas restano fuori.
    """
    nome = _normalizza(gioco or "")
    if re.search(r"\bgta\s*(6|vi)\b", nome):
        return "gta6"
    if "grand theft auto" in nome and _numero_sequel(nome) == 6:
        return "gta6"
    return None


def trailer_dalla_pagina_ufficiale(chiave):
    """Gli mp4 dei trailer elencati nella pagina ufficiale, in ordine."""
    voce = PAGINE_UFFICIALI[chiave]
    trovati = []
    try:
        r = requests.get(voce["pagina"], timeout=20, headers=_UA)
        r.raise_for_status()
        trovati = re.findall(voce["schema"], r.text)
    except Exception as e:
        print(f"[Gameplay] Pagina ufficiale di {voce['nome']} non raggiungibile: {e}")

    elenco = []
    for url in trovati or voce["riserva"]:
        if url not in elenco and not any(p in url.lower() for p in _NON_GAMEPLAY):
            elenco.append(url)
    return elenco


def scarica_mp4_ufficiali(elenco, chiave, quanti=3, salto=0):
    """Scarica i primi mp4 dell'elenco, come scarica_trailer_steam.

    L'indice nel nome del file e' indispensabile: gli mp4 di Epic si chiamano
    tutti 'output.mp4' e senza l'indice il secondo sovrascriverebbe il primo.
    """
    elenco = ruota(elenco, salto)
    percorsi = []
    for indice, url in enumerate(elenco):
        if len(percorsi) >= quanti:
            break
        nome_file = os.path.basename(url.split("?")[0]) or "trailer.mp4"
        destinazione = os.path.join(
            config.DIR_TEMP, f"ufficiale_{chiave}_{indice}_{nome_file}")
        print(f"[Gameplay] Scarico trailer ufficiale dall'editore: {nome_file}")
        # Stesso criterio di Steam: il punto di taglio si misura sul filmato.
        for salta in punti_di_taglio(url, salto):
            if _estrai_mp4(url, destinazione, salta=salta, a_1080=True):
                percorsi.append(destinazione)
                break

    print(f"[Gameplay] {len(percorsi)} trailer ufficiali pronti.")
    return percorsi


def scarica_trailer_ufficiali(chiave, quanti=3, salto=0):
    """Come scarica_trailer_steam, ma dagli mp4 della pagina dell'editore."""
    return scarica_mp4_ufficiali(trailer_dalla_pagina_ufficiale(chiave),
                                 chiave, quanti, salto)


def _scarica_immagine(url, destinazione, minimo=20_000):
    """Salva l'immagine. Un file minuscolo e' un segnaposto, non una
    schermata: si scarta."""
    try:
        contenuto = requests.get(url, timeout=30, headers=_UA).content
        if len(contenuto) < minimo:
            return False
        with open(destinazione, "wb") as f:
            f.write(contenuto)
        return True
    except Exception as e:
        print(f"[Gameplay] Screenshot non scaricato: {e}")
        return False


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
        if _scarica_immagine(url, destinazione):
            percorsi.append(destinazione)

    if percorsi or screenshot:
        print(f"[Gameplay] {len(percorsi)} screenshot ufficiali pronti.")
    return percorsi


# ===========================================================================
# GLI ALTRI NEGOZI UFFICIALI: PLAYSTATION, EPIC, NINTENDO, XBOX
# ===========================================================================
# Steam ha solo i giochi per PC. Le esclusive console non ci sono affatto, e
# sui trenta Short precedenti al 6 ottobre 2026 sei sono usciti con clip
# Pexels generiche per questo motivo: 'Ghost of Yotei' (PlayStation), Pokemon
# (Nintendo), 'Gears of War: E-Day' (Xbox), Fortnite (Epic). Ogni negozio
# pubblica il proprio materiale promozionale, esattamente come Steam, quindi
# si prende da li' con le stesse regole: niente audio, solo roba dell'editore.
#
# Cosa offre ciascuno, verificato dai server di GitHub il 6 ottobre 2026:
#   PlayStation  mp4 veri (2 su Ghost of Yotei, 3 su Spider-Man 2)
#   Epic         mp4 veri (5 su Fortnite)
#   Nintendo     solo immagini, nessun mp4 nelle pagine dei giochi
#   Xbox         solo immagini, la lista 'Videos' del catalogo e' sempre vuota
#
# I negozi si interrogano in quest'ordine e il materiale si somma: prima
# quelli coi filmati, poi quelli con le immagini.
# Quanto si aspetta prima di richiedere la stessa pagina a un negozio che ha
# risposto 'troppe richieste'.
PAUSA_NEGOZIO_SEC = 5


def _scarica_pagina(url, timeout=20, **extra):
    """La pagina, con un secondo tentativo se il negozio ci sta frenando.

    Il 403 e il 429 non vogliono dire 'non esiste' come il 404: vogliono dire
    'troppe richieste'. Il 6 ottobre 2026 la prova ha chiesto venti pagine di
    fila a PlayStation e dalla ventesima ha preso 403 anche sui giochi che un
    minuto prima aveva trovato. In produzione le richieste sono due o tre per
    video, ma una pausa e un secondo tentativo costano poco.
    """
    for tentativo in (1, 2):
        r = requests.get(url, timeout=timeout, headers=_UA, **extra)
        if tentativo == 1 and r.status_code in (403, 429):
            print(f"[Gameplay] Il negozio frena ({r.status_code}), "
                  f"riprovo fra {PAUSA_NEGOZIO_SEC} secondi.")
            time.sleep(PAUSA_NEGOZIO_SEC)
            continue
        r.raise_for_status()
        return r


def _elenco_unico(urls):
    elenco = []
    for url in urls:
        if url not in elenco:
            elenco.append(url)
    return elenco


def _indirizzo_nome(nome):
    """'Marvel's Spider-Man 2' -> 'marvels-spider-man-2'.

    E' il pezzo di indirizzo che PlayStation ed Epic usano per le schede dei
    giochi. Le lettere accentate vanno ridotte alla lettera semplice: il
    titolo vero di Ghost of Yotei ha la o lunga, e un trattino al posto di
    quella lettera darebbe una pagina inesistente.
    """
    testo = unicodedata.normalize("NFD", (nome or "").lower())
    testo = testo.encode("ascii", "ignore").decode("ascii")
    testo = testo.replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", testo).strip("-")


# --------------------------------------------------------------- PlayStation
PLAYSTATION_SCHEDA = "https://www.playstation.com/en-us/games/{}/"
# Due CDN diversi, visti entrambi in produzione: Ghost of Yotei sta su
# gmedia, Ghost of Tsushima su vulcan. Il taglio e' esattamente su '.mp4'
# perche' negli attributi della pagina l'indirizzo continua con altro testo.
_PLAYSTATION_MP4 = re.compile(
    r"https://(?:gmedia\.playstation\.com|vulcan\.dl\.playstation\.net)"
    r"/[^\"'\s<>\\]+?\.mp4")
# In fondo a OGNI scheda c'e' lo stesso spot della console, che non e'
# gameplay del gioco.
_PLAYSTATION_SPOT = ("/hardware/", "ps5-pro", "channel-specific-content")


def materiale_playstation(nome):
    """Gli mp4 della scheda PlayStation del gioco, o None."""
    for variante in _varianti_nome(nome):
        indirizzo = _indirizzo_nome(variante)
        if not indirizzo:
            continue
        try:
            pagina = _scarica_pagina(PLAYSTATION_SCHEDA.format(indirizzo)).text
        except Exception as e:
            print(f"[Gameplay] PlayStation non ha '{indirizzo}': {e}")
            continue
        video = [u for u in _elenco_unico(_PLAYSTATION_MP4.findall(pagina))
                 if not any(p in u.lower() for p in _PLAYSTATION_SPOT)]
        # La scheda di Spider-Man 2 elenca diciannove filmati, perche' in
        # fondo ci sono anche quelli dei giochi consigliati. Quelli del gioco
        # giusto hanno il suo nome nell'indirizzo: vanno davanti.
        video.sort(key=lambda u: indirizzo not in u.lower())
        if video:
            return {"nome": variante, "video": video, "immagini": []}
    return None


# ---------------------------------------------------------------------- Epic
# La pagina del negozio e' tutta JavaScript, ma l'API che la riempie risponde
# in chiaro e senza chiave.
EPIC_SCHEDA = "https://store-content.ak.epicgames.com/api/en-US/content/products/{}"
_EPIC_MP4 = re.compile(r"https://[\w.-]+\.on\.epicgames\.com/[^\"'\s<>\\]+?\.mp4")


def materiale_epic(nome):
    """Gli mp4 della scheda Epic Games Store del gioco, o None."""
    for variante in _varianti_nome(nome):
        indirizzo = _indirizzo_nome(variante)
        if not indirizzo:
            continue
        try:
            scheda = _scarica_pagina(EPIC_SCHEDA.format(indirizzo)).text
        except Exception as e:
            print(f"[Gameplay] Epic non ha '{indirizzo}': {e}")
            continue
        video = _elenco_unico(_EPIC_MP4.findall(scheda))
        if video:
            return {"nome": variante, "video": video, "immagini": []}
    return None


# Fra le immagini di una scheda ci sono anche le fasce decorative e gli
# sfondi del sito: non sono schermate del gioco e in uno Short verticale si
# vedono per quello che sono, grafica di contorno.
_NON_SCHERMATA = ("banner", "background", "logo", "keyart", "boxart",
                  "packshot", "icon")


def _solo_schermate(urls):
    scelte = [u for u in urls if not any(p in u.lower() for p in _NON_SCHERMATA)]
    # Se il filtro svuota tutto, meglio le immagini dubbie che lo stock.
    return scelte or urls


# ------------------------------------------------------------------ Nintendo
NINTENDO_RICERCA = ("https://search.nintendo-europe.com/en/select"
                    "?q={}&fq=type:GAME&wt=json&rows=3")
NINTENDO_SITO = "https://www.nintendo.com"
# Nella pagina di un gioco ci sono fra cento e trecento immagini, e la gran
# parte e' l'arredamento del sito: icone, loghi, bandierine.
_NINTENDO_IMMAGINE = re.compile(
    r"https://[^\"'\s<>\\]+/media/images/[^\"'\s<>\\]+?\.(?:jpg|jpeg|png)")
_NINTENDO_ARREDAMENTO = ("01_website_elements", "02_logos", "/icons/",
                         "favicon", "_logo", "flag")
# Le schede dei giochi piu' vecchi (Wii U, primi anni di Switch) hanno i
# trailer come mp4 sul server video di Nintendo; quelle nuove li incorporano
# da YouTube, e da YouTube non si scarica mai, quindi li' restano le schermate.
_NINTENDO_MP4 = re.compile(r"https://[^\"'\s<>\\]+?\.mp4(?:\?[^\"'\s<>\\]*)?")


_LARGHEZZA_NEL_NOME = re.compile(r"_image(\d+)w(?=\.)")


def _senza_doppioni_di_misura(urls):
    """Lo stesso disegno a misure diverse conta per uno.

    Nelle pagine Nintendo la stessa immagine compare come
    '..._image1280w.jpg', '..._image1600w.jpg' e senza suffisso: sono la
    stessa cosa e si prenderebbero tre dei quattro posti disponibili. Si
    tiene la piu' grande, cioe' quella senza suffisso quando c'e'.
    """
    migliore = {}
    for url in urls:
        misura = _LARGHEZZA_NEL_NOME.search(url)
        base = _LARGHEZZA_NEL_NOME.sub("", url)
        larghezza = int(misura.group(1)) if misura else 10_000
        if base not in migliore or larghezza > migliore[base][0]:
            migliore[base] = (larghezza, url)

    # L'ordine della pagina si conserva: le prime immagini sono le migliori.
    viste, elenco = set(), []
    for url in urls:
        base = _LARGHEZZA_NEL_NOME.sub("", url)
        if base in viste:
            continue
        viste.add(base)
        elenco.append(migliore[base][1])
    return elenco


def _immagini_nintendo(pagina):
    """Le immagini del gioco, le piu' promettenti davanti.

    Le schermate che Nintendo pubblica per la stampa stanno sotto
    '08_content_images', ed e' da li' che si pesca quando la scheda le ha.
    Le pagine nuove di Switch 2 quella cartella non la hanno affatto: Mario
    Kart World ha 323 immagini e nessuna li' dentro, quindi restano le altre
    immagini del gioco, che sono comunque materiale ufficiale. Le icone le
    scarta il controllo sulla dimensione in _scarica_immagine.
    """
    trovate = [u for u in _elenco_unico(_NINTENDO_IMMAGINE.findall(pagina))
               if not any(p in u.lower() for p in _NINTENDO_ARREDAMENTO)]
    trovate.sort(key=lambda u: "08_content_images" not in u)
    return _solo_schermate(_senza_doppioni_di_misura(trovate))


def _video_nintendo(pagina, titolo):
    """Gli mp4 ufficiali della scheda che parlano di QUESTO gioco.

    Il nome del file dice di che gioco e' il trailer
    ('wii-u-mario-kart-8-trailer-release-date-engb.mp4'): si tengono solo
    quelli che contengono una parola del titolo, cosi' un trailer di un altro
    gioco messo in fondo alla pagina non finisce nello Short.
    """
    parole = [p for p in _normalizza(titolo).split() if len(p) >= 4]
    if not parole:
        return []
    video = []
    for url in _elenco_unico(_NINTENDO_MP4.findall(pagina)):
        url = html.unescape(url)
        file = _normalizza(url.split("?", 1)[0].rsplit("/", 1)[-1])
        file = file.replace(" ", "")
        if any(p in file for p in parole) and url not in video:
            video.append(url)
    return video


def materiale_nintendo(nome):
    """Trailer e schermate ufficiali della scheda Nintendo del gioco, o None."""
    for variante in _varianti_nome(nome):
        try:
            risposta = _scarica_pagina(
                NINTENDO_RICERCA.format(quote(variante))).json()
        except Exception as e:
            print(f"[Gameplay] Ricerca Nintendo '{variante}' fallita: {e}")
            continue

        schede = ((risposta or {}).get("response") or {}).get("docs") or []
        for scheda in schede:
            titolo = scheda.get("title") or ""
            # La ricerca Nintendo risponde sempre qualcosa, come quella di
            # Steam: senza questo controllo uno Short su un gioco Sony
            # finirebbe con le schermate di un gioco Nintendo qualunque.
            if _somiglianza(variante, titolo) < SOGLIA_CORRISPONDENZA:
                continue
            percorso = scheda.get("url") or ""
            if not percorso:
                continue
            try:
                pagina = _scarica_pagina(urljoin(NINTENDO_SITO, percorso)).text
            except Exception as e:
                print(f"[Gameplay] Scheda Nintendo di '{titolo}' non letta: {e}")
                continue
            immagini = _immagini_nintendo(pagina)
            video = _video_nintendo(pagina, titolo)
            if immagini or video:
                return {"nome": titolo, "video": video, "immagini": immagini}
    return None


# ---------------------------------------------------------------------- Xbox
# www.xbox.com risponde 404 a chi non e' un browser; queste due API no.
XBOX_SUGGERIMENTI = ("https://www.microsoft.com/msstoreapiprod/api/autosuggest"
                     "?market=en-us&sources=DCatAll-Products&query={}")
XBOX_CATALOGO = ("https://displaycatalog.mp.microsoft.com/v7.0/products"
                 "?bigIds={}&market=US&languages=en-us&MS-CV=samaritan")
XBOX_LARGHEZZA_MINIMA = 1280


def _xbox_suggerimenti(risposta):
    """Le voci suggerite, da entrambe le forme di risposta possibili."""
    voci = list((risposta or {}).get("Suggests") or [])
    for gruppo in (risposta or {}).get("ResultSets") or []:
        voci += list(gruppo.get("Suggests") or [])
    return voci


def materiale_xbox(nome):
    """Le schermate ufficiali del catalogo Microsoft Store, o None."""
    for variante in _varianti_nome(nome):
        try:
            risposta = _scarica_pagina(
                XBOX_SUGGERIMENTI.format(quote(variante))).json()
        except Exception as e:
            print(f"[Gameplay] Ricerca Xbox '{variante}' fallita: {e}")
            continue

        for voce in _xbox_suggerimenti(risposta):
            titolo = voce.get("Title") or ""
            if _somiglianza(variante, titolo) < SOGLIA_CORRISPONDENZA:
                continue
            codice = next((m.get("Value") for m in voce.get("Metas") or []
                           if m.get("Key") == "BigCatalogId"), None)
            if not codice:
                continue
            try:
                catalogo = _scarica_pagina(XBOX_CATALOGO.format(codice)).json()
            except Exception as e:
                print(f"[Gameplay] Catalogo Xbox di '{titolo}' non letto: {e}")
                continue
            immagini = _solo_schermate(_elenco_unico(_immagini_xbox(catalogo)))
            if immagini:
                return {"nome": titolo, "video": [], "immagini": immagini}
    return None


def _immagini_xbox(catalogo):
    for prodotto in (catalogo or {}).get("Products") or []:
        for proprieta in prodotto.get("LocalizedProperties") or []:
            for immagine in proprieta.get("Images") or []:
                if immagine.get("ImagePurpose") != "Screenshot":
                    continue
                if (immagine.get("Width") or 0) < XBOX_LARGHEZZA_MINIMA:
                    continue
                indirizzo = immagine.get("Uri") or ""
                # Microsoft scrive gli indirizzi senza 'https:' davanti.
                if indirizzo.startswith("//"):
                    indirizzo = "https:" + indirizzo
                if indirizzo.startswith("https://"):
                    yield indirizzo


# ----------------------------------------------------------------- App Store
# I giochi per telefono (Pokemon TCG Pocket, Clash Royale, Pokemon GO) non
# stanno su nessuna console. La ricerca pubblica di Apple da' le schermate
# ufficiali della scheda: il 16 ottobre 2026 "Pokemon TCG Pocket" senza
# questo negozio e' finito su clip Pexels.
APPSTORE_RICERCA = ("https://itunes.apple.com/search"
                    "?term={}&entity=software&country=us&limit=5")
# Gli indirizzi chiedono una miniatura ('.../392x696bb.jpg'); 'bb' vuol dire
# "dentro questo riquadro", quindi chiedere un riquadro grande da' la
# schermata alla risoluzione piena senza cambiarne le proporzioni.
_APPSTORE_MISURA = re.compile(r"/\d+x\d+bb(\.\w+)$")


def _appstore_grande(url):
    return _APPSTORE_MISURA.sub(r"/2000x2000bb\1", url)


def materiale_appstore(nome):
    """Le schermate ufficiali della scheda App Store del gioco, o None."""
    for variante in _varianti_nome(nome):
        try:
            risposta = _scarica_pagina(
                APPSTORE_RICERCA.format(quote(variante))).json()
        except Exception as e:
            print(f"[Gameplay] Ricerca App Store '{variante}' fallita: {e}")
            continue

        for app in (risposta or {}).get("results") or []:
            titolo = app.get("trackName") or ""
            if _somiglianza(variante, titolo) < SOGLIA_CORRISPONDENZA:
                continue
            schermate = list(app.get("screenshotUrls") or []) + \
                list(app.get("ipadScreenshotUrls") or [])
            immagini = _elenco_unico(_appstore_grande(u) for u in schermate
                                     if str(u).startswith("https://"))
            if immagini:
                return {"nome": titolo, "video": [], "immagini": immagini}
    return None


def _cercatori_negozi():
    """I negozi nell'ordine in cui si interrogano: prima quelli coi filmati."""
    return (
        ("PlayStation", materiale_playstation),
        ("Epic Games Store", materiale_epic),
        ("Nintendo", materiale_nintendo),
        ("Xbox", materiale_xbox),
        ("App Store", materiale_appstore),
    )


def materiale_dai_negozi(nome, quanti_video=3, quante_immagini=4):
    """Cerca il gioco nei negozi ufficiali diversi da Steam.

    Il materiale dei negozi si somma, perche' nessuno dei cinque ha sempre
    tutto: PlayStation ed Epic danno i filmati, Xbox e App Store soltanto
    schermate e Nintendo i filmati solo per i giochi meno recenti. Si smette appena ce n'e' abbastanza di entrambi. Un negozio
    che non risponde non ferma gli altri e non ferma il video.
    """
    nome = nome_con_alias(nome)
    video, immagini, nome_ufficiale = [], [], None

    for etichetta, cercatore in _cercatori_negozi():
        if len(video) >= quanti_video and len(immagini) >= quante_immagini:
            break
        try:
            trovato = cercatore(nome)
        except Exception as e:
            print(f"[Gameplay] {etichetta} non raggiungibile: {e}")
            continue
        if not trovato:
            continue

        nuovi_video = [u for u in trovato.get("video") or [] if u not in video]
        nuove_immagini = [u for u in trovato.get("immagini") or []
                          if u not in immagini]
        if not nuovi_video and not nuove_immagini:
            continue
        nome_ufficiale = nome_ufficiale or trovato.get("nome")
        video += nuovi_video
        immagini += nuove_immagini
        print(f"[Gameplay] '{nome}' -> {etichetta}: {len(nuovi_video)} filmati "
              f"e {len(nuove_immagini)} schermate ufficiali.")

    if not video and not immagini:
        print(f"[Gameplay] '{nome}' non trovato in nessun negozio ufficiale.")
        return None
    return {"nome": nome_ufficiale or nome, "video": video,
            "immagini": immagini}


def scarica_immagini_dai_negozi(elenco, chiave, quante=4, salto=0):
    """Le schermate dei negozi, scelte come quelle di Steam."""
    elenco = ruota(elenco, salto * quante)
    percorsi = []
    for indice, url in enumerate(elenco[:quante * 3]):
        if len(percorsi) >= quante:
            break
        destinazione = os.path.join(
            config.DIR_TEMP, f"shot_{chiave}_{indice}.jpg")
        if _scarica_immagine(url, destinazione):
            percorsi.append(destinazione)
    if percorsi or elenco:
        print(f"[Gameplay] {len(percorsi)} screenshot ufficiali pronti.")
    return percorsi


# ===========================================================================
# PUNTO DI INGRESSO
# ===========================================================================
def _usa_steam():
    """Si va sugli store dei giochi? Serve il si' di config E del profilo.

    USA_STEAM e' l'interruttore di sempre per spegnere Steam a mano; il
    profilo dice se il canale parla di videogiochi. Un canale di cucina su
    Steam non ci deve andare nemmeno con USA_STEAM acceso.
    """
    return bool(config.USA_STEAM) and profilo.attivo().usa_steam


# Due giochi in un nome: "Super Mario in Elden Ring", "Fortnite x Sonic",
# "Mario vs Sonic". Nessun negozio ha un gioco chiamato cosi'.
_SEPARATORI_NOME = re.compile(r"\s+(?:in|x|vs\.?|versus|meets)\s+", re.IGNORECASE)


def scegli_parte_trovabile(gioco):
    """Per un nome che unisce due giochi, quello che i negozi conoscono.

    Il 12 ottobre 2026 "Super Mario in Elden Ring: il mashup AI" ha cercato
    "Super Mario in Elden Ring", non l'ha trovato da nessuna parte ed e'
    uscito su clip Pexels, mentre Elden Ring su Steam ha trailer e schermate.
    Prima si prova il nome intero; poi le parti, cominciando da quella dopo
    "in", che e' il gioco dove succede la cosa.
    """
    parti = [p.strip() for p in _SEPARATORI_NOME.split(gioco or "") if p.strip()]
    if len(parti) < 2:
        return gioco
    if gioco_con_pagina_ufficiale(gioco) or cerca_gioco_steam(gioco)[0]:
        return gioco
    if re.search(r"\s+in\s+", gioco, re.IGNORECASE):
        parti.reverse()
    for parte in parti:
        if gioco_con_pagina_ufficiale(parte) or cerca_gioco_steam(parte)[0]:
            print(f"[Gameplay] '{gioco}' unisce due giochi: uso '{parte}'.")
            return parte
    return gioco


def procura_materiale(gioco=None, query_pexels="gameplay", minimo=3):
    """Ritorna una lista di sorgenti [{tipo, path, gioco}] per il montaggio.

    tipo = 'video' | 'immagine'
    """
    os.makedirs(config.DIR_TEMP, exist_ok=True)
    sorgenti = []
    nome_ufficiale = None
    dati_gioco = None
    usa_steam = _usa_steam()
    if gioco and usa_steam:
        gioco = scegli_parte_trovabile(gioco)
    salto = video_gia_fatti(gioco)

    pagina_ufficiale = gioco_con_pagina_ufficiale(gioco) if usa_steam else None
    if pagina_ufficiale:
        nome_ufficiale = PAGINE_UFFICIALI[pagina_ufficiale]["nome"]
        if salto:
            print(f"[Gameplay] Short numero {salto + 1} su "
                  f"'{nome_ufficiale}': cambio materiale.")
        for percorso in scarica_trailer_ufficiali(
                pagina_ufficiale, config.STEAM_MAX_TRAILER, salto):
            sorgenti.append({"tipo": "video", "path": percorso,
                             "gioco": nome_ufficiale})
    elif gioco and usa_steam:
        appid, nome_steam = cerca_gioco_steam(gioco)
        if appid:
            nome_ufficiale = nome_steam
            dati = dettagli_gioco(appid)
            dati_gioco = dati
            if dati:
                # Quante volte abbiamo gia' parlato di questo gioco: decide da
                # dove si pesca, cosi' il materiale non si ripete.
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

        # Le esclusive console su Steam non ci sono: si va a chiederle al
        # negozio del loro editore invece di ripiegare sullo stock.
        if not sorgenti and config.USA_ALTRI_NEGOZI:
            trovato = materiale_dai_negozi(
                gioco, config.STEAM_MAX_TRAILER, config.STEAM_MAX_SCREENSHOT)
            if trovato:
                nome_ufficiale = trovato["nome"]
                chiave = _indirizzo_nome(nome_ufficiale) or "negozio"
                if salto:
                    print(f"[Gameplay] Short numero {salto + 1} su "
                          f"'{nome_ufficiale}': cambio materiale.")
                for percorso in scarica_mp4_ufficiali(
                        trovato["video"], chiave,
                        config.STEAM_MAX_TRAILER, salto):
                    sorgenti.append({"tipo": "video", "path": percorso,
                                     "gioco": nome_ufficiale})
                for percorso in scarica_immagini_dai_negozi(
                        trovato["immagini"], chiave,
                        config.STEAM_MAX_SCREENSHOT, salto):
                    sorgenti.append({"tipo": "immagine", "path": percorso,
                                     "gioco": nome_ufficiale})

    # Le clip girate in casa: non sostituiscono il materiale del gioco, ci si
    # aggiungono. 'gioco' resta None perche' non sono di QUEL gioco, e il
    # conteggio del materiale ufficiale nel resoconto deve restare onesto.
    categoria = categoria_clip_mie(gioco, dati_gioco)
    mie = clip_mie(categoria, salto)
    for percorso in mie:
        sorgenti.append({"tipo": "video", "path": percorso,
                         "gioco": None, "mia": True})
    if mie:
        print(f"[Gameplay] {len(mie)} clip girate in casa ('{categoria}').")

    if len(sorgenti) >= minimo:
        print(f"[Gameplay] Materiale UFFICIALE di '{nome_ufficiale}': "
              f"{len(sorgenti) - len(mie)} sorgenti.")
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
