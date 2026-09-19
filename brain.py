"""
Cervello di Samaritan: sceglie il formato, si ancora a notizie reali,
scrive titolo + script + descrizione e valida il risultato.

Differenze chiave rispetto alla versione precedente:
  - Nessuna chiave API hardcoded (tutto da config)
  - Lo script si basa su NOTIZIE VERE scaricate dall'RSS, non su fatti inventati
  - La scelta del formato e' pesata sulla retention reale (vedi analyst.py)
  - Validazione dura: se il modello apre con "Ciao a tutti" lo script viene
    RIFIUTATO e rigenerato. Chiedere al modello di non farlo non basta.
"""
import os
import json
import random
import time
import re
import html
import unicodedata
import xml.etree.ElementTree as ET

import requests
from groq import Groq

import config

client = Groq(api_key=config.GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Formati video. `richiede_fatto` = ha bisogno di una notizia vera per esistere.
# Se non ci sono notizie fresche, Samaritan ripiega su un formato che non ne
# ha bisogno, invece di inventarsi un leak inesistente.
# ---------------------------------------------------------------------------
FORMATI_VIDEO = {
    "VIRAL_HOOK_NEWS": {
        "descrizione": "Notizia vera raccontata con prima frase d'impatto assurdo",
        "richiede_fatto": True,
    },
    "MYTH_BUSTING_VIRAL": {
        "descrizione": "Smentita o conferma di un rumor realmente circolato",
        "richiede_fatto": True,
    },
    "EASTER_EGG_SECRET": {
        "descrizione": "Un segreto storico e verificabile nascosto da uno sviluppatore",
        "richiede_fatto": False,
    },
    "SEAMLESS_LOOP_FACTS": {
        "descrizione": "Curiosita' veloci collegate in loop infinito",
        "richiede_fatto": False,
    },
    "DONT_DO_THIS": {
        "descrizione": "Errore concreto da evitare in un gioco popolare",
        "richiede_fatto": False,
    },
    "TIER_LIST_LAMPO": {
        "descrizione": "Classifica rapidissima e volutamente divisiva (genera commenti)",
        "richiede_fatto": False,
    },
    "DOMANDA_AL_PUBBLICO": {
        "descrizione": "Dilemma gaming che costringe lo spettatore a commentare la sua risposta",
        "richiede_fatto": False,
    },
}

# Aperture vietate: uccidono la retention nei primi 3 secondi
APERTURE_VIETATE = (
    "ciao", "salve", "benvenut", "buongiorno", "buonasera", "ehi ragazzi",
    "oggi vi parlo", "oggi parliamo", "in questo video", "oggi vi mostro",
    "come state", "raga,", "ragazzi,",
)

# Quante voci di cronologia guardare per decidere se qualcosa si sta ripetendo.
# Due video al giorno: tre voci coprono circa un giorno e mezzo, cioe' la
# finestra in cui lo stesso spettatore puo' vedere passare due Short di fila.
MEMORIA_RIPETIZIONI = 3

# Quante parole iniziali confrontare per dire "questo attacco l'abbiamo gia'
# usato". Tre bastano: gli Short scartati si somigliavano proprio li'
# ("Stai sbagliando tutto su X", "Nessuno ti ha detto che Y").
PAROLE_APERTURA = 3

MIN_PAROLE_SCRIPT = 45
MAX_PAROLE_SCRIPT = 95

# Con cosa puo' finire uno script per essere considerato finito. Il tetto
# di token copre anche il ragionamento del modello, quindi ogni tanto la
# risposta si interrompe a meta' parola: nel video si sente, perche' la
# voce legge la chiusura e poi aggiunge una parola a vuoto.
PUNTEGGIATURA_FINALE = ".!?\u2026"

# Oltre i 60 caratteri il titolo viene troncato nel feed Shorts da telefono,
# e la parte tagliata e' sempre la fine, cioe' dove sta l'informazione utile.
MAX_CARATTERI_TITOLO = 60

_CLASSE_EMOJI = (
    "\U0001F000-\U0001FAFF"      # pittogrammi, emoticon, simboli
    "\U00002190-\U000021FF"      # frecce
    "\U00002300-\U000023FF"      # simboli tecnici (orologi, play)
    "\U00002600-\U000027BF"      # simboli vari, dingbats
    "\U00002B00-\U00002BFF"      # simboli e frecce aggiuntivi
    "\U0001F1E6-\U0001F1FF"      # bandiere
    "\u2122\u24C2"
)
# Per TOGLIERE le emoji servono anche i modificatori (selettore di variante e
# keycap), che da soli non sono emoji ma restano appiccicati.
_RE_EMOJI = re.compile(f"[{_CLASSE_EMOJI}\uFE0F\u20E3]+")
# Per CONTARLE serve il carattere singolo: due emoji attaccate sono un solo
# gruppo, e contare i gruppi le farebbe passare entrambe per una sola.
_RE_EMOJI_SINGOLA = re.compile(f"[{_CLASSE_EMOJI}]")

# Parole che non reggono da sole in fondo a una miniatura: tagliare a un numero
# fisso di parole lascia code tipo "L'ERRORE CHE TI FA", che non dice niente.
_PAROLE_DEBOLI = {
    "che", "ti", "fa", "di", "da", "del", "della", "dei", "degli", "delle",
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "e", "ed", "a",
    "al", "allo", "alla", "ai", "in", "nel", "nella", "per", "con", "su",
    "non", "ma", "se", "come", "piu", "ha", "hanno", "ci", "si", "ne", "sul",
    "quasi", "molto", "tanto", "cosi", "ogni", "questo", "questa", "quel",
    "quella", "tra", "fra", "senza", "dal", "dalla", "suo", "sua", "loro",
}

# Tema in hashtag per ogni formato: il primo hashtag della descrizione e'
# l'unico che YouTube mostra sopra al titolo, quindi non va sprecato.
TEMA_PER_FORMATO = {
    "VIRAL_HOOK_NEWS": "newsgaming",
    "MYTH_BUSTING_VIRAL": "rumor",
    "EASTER_EGG_SECRET": "easteregg",
    "SEAMLESS_LOOP_FACTS": "curiosita",
    "DONT_DO_THIS": "consigli",
    "TIER_LIST_LAMPO": "tierlist",
    "DOMANDA_AL_PUBBLICO": "gamingita",
}

# Tag presenti su ogni video. Da soli pesano poco sul ranking, ma cinque tag
# IDENTICI su ogni upload sono una delle impronte che fanno riconoscere un
# canale automatizzato: per questo costruisci_tag() ne aggiunge di variabili.
TAG_FISSI = ["gaming ita", "videogiochi", "shorts ita", "curiosita gaming"]


# ===========================================================================
# MEMORIA
# ===========================================================================
def carica_cronologia():
    """Carica la memoria storica, tollerando il vecchio formato a stringhe."""
    if not os.path.exists(config.FILE_CRONOLOGIA):
        return []
    try:
        with open(config.FILE_CRONOLOGIA, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalizza(item):
    """Converte le vecchie voci-stringa nel formato a dizionario."""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        return {"titolo": item, "stile": "", "estratto_script": "", "video_id": None}
    return {}


def salva_in_cronologia(dati):
    """Aggiunge l'impronta del nuovo video alla memoria."""
    cronologia = carica_cronologia()
    cronologia.append({
        "timestamp": int(time.time()),
        "data": time.strftime("%Y-%m-%d"),
        "titolo": dati["titolo"],
        "estratto_script": dati["script"][:90],
        "stile": dati["stile"],
        "gioco": dati.get("gioco", ""),
        "query_video": dati["query_video"],
        "fonte": dati.get("fonte", ""),
        "fonte_url": dati.get("fonte_url", ""),
        "video_id": None,          # riempito dopo l'upload
    })
    cronologia = cronologia[-200:]
    with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
        json.dump(cronologia, f, ensure_ascii=False, indent=2)


def aggiorna_ultimo_video_id(video_id):
    """Collega l'ultimo record di memoria all'ID YouTube, cosi' analyst.py
    puo' poi incrociare formato <-> retention reale."""
    cronologia = carica_cronologia()
    if not cronologia:
        return
    if isinstance(cronologia[-1], dict):
        cronologia[-1]["video_id"] = video_id
        with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
            json.dump(cronologia, f, ensure_ascii=False, indent=2)


# ===========================================================================
# RICERCA NOTIZIE REALI
# ===========================================================================
def recupera_trend_gaming_online(max_notizie=8):
    """Scarica notizie gaming fresche e scarta quelle gia' sfruttate.

    Ritorna una lista di dict {titolo, fonte, link}: servono strutturate
    perche' lo script deve poter citare la fonte reale.
    """
    print("[Samaritan Search] Ricerca trend gaming reali...")
    url = ("https://news.google.com/rss/search"
           "?q=videogiochi+gaming+quando+esce+aggiornamento&hl=it&gl=IT&ceid=IT:it")

    cronologia = carica_cronologia()
    titoli_passati = " ".join(
        _normalizza(i).get("titolo", "") for i in cronologia
    ).lower()

    notizie = []
    try:
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        for item in root.findall("./channel/item")[:25]:
            nodo_titolo = item.find("title")
            if nodo_titolo is None or not nodo_titolo.text:
                continue

            titolo_completo = html.unescape(nodo_titolo.text)
            # Google News formatta come "Titolo - Testata"
            if " - " in titolo_completo:
                titolo, fonte = titolo_completo.rsplit(" - ", 1)
            else:
                titolo, fonte = titolo_completo, "Google News"

            # Salta le notizie troppo simili a quelle gia' usate
            parole = [w.lower() for w in titolo.split() if len(w) > 4]
            gia_usate = [w for w in parole if w in titoli_passati]
            if parole and len(gia_usate) / len(parole) >= 0.3:
                continue

            nodo_link = item.find("link")
            notizie.append({
                "titolo": titolo.strip(),
                "fonte": fonte.strip(),
                "link": nodo_link.text if nodo_link is not None else "",
            })

            if len(notizie) >= max_notizie:
                break

    except Exception as e:
        print(f"[Warning Search] RSS non raggiungibile ({e}).")

    if notizie:
        random.shuffle(notizie)
        print(f"[Samaritan Search] {len(notizie)} notizie fresche non ancora usate.")
    else:
        print("[Samaritan Search] Nessuna notizia nuova: uso un formato evergreen.")

    return notizie


# ===========================================================================
# SELEZIONE FORMATO (pesata sulla performance reale)
# ===========================================================================
def scegli_formato(notizie_disponibili):
    """Sceglie il formato del video.

    I pesi vengono dalla retention reale misurata da analyst.py: i formati
    che trattengono lo spettatore piu' a lungo escono piu' spesso.
    Se non ci sono ancora dati, la scelta e' uniforme.
    """
    cronologia = carica_cronologia()
    stili_recenti = [_normalizza(i).get("stile", "") for i in cronologia[-4:]]

    try:
        from analyst import pesi_formati
        pesi = pesi_formati()
    except Exception:
        pesi = {}

    candidati, valori = [], []
    for nome, meta in FORMATI_VIDEO.items():
        if meta["richiede_fatto"] and not notizie_disponibili:
            continue                      # niente fatti -> niente formato factual
        if nome in stili_recenti:
            continue                      # evita di ripetere gli ultimi 4
        candidati.append(nome)
        valori.append(max(pesi.get(nome, 1.0), 0.05))

    if not candidati:                     # tutti esclusi: allarga il campo
        candidati = [
            n for n, m in FORMATI_VIDEO.items()
            if not m["richiede_fatto"] or notizie_disponibili
        ]
        valori = [max(pesi.get(n, 1.0), 0.05) for n in candidati]

    scelto = random.choices(candidati, weights=valori, k=1)[0]
    if pesi:
        print(f"[Samaritan Brain] Formato '{scelto}' scelto su dati di retention "
              f"(peso {pesi.get(scelto, 1.0):.2f}).")
    return scelto


# ===========================================================================
# VALIDAZIONE
# ===========================================================================
def _pulisci_titolo(titolo):
    """Normalizza il titolo prima della validazione.

    Sistema meccanicamente quello che si puo' sistemare senza rigenerare:
    l'hashtag inutile, le emoji in eccesso e soprattutto l'emoji in apertura,
    che ruba il posto alla keyword del gioco. Quello che non si puo' aggiustare
    da fuori (titolo troppo lungo, tutto maiuscolo) lo rifiuta valida_titolo().
    """
    t = titolo.strip().strip('"').strip("'")
    # "#Shorts" nel titolo non serve piu' dal 2023 e ruba caratteri utili
    t = re.sub(r"#shorts\b", "", t, flags=re.IGNORECASE).strip()

    # Una sola emoji, e in fondo: in apertura i caratteri piu' preziosi del
    # titolo li deve occupare il nome del gioco, non una faccina.
    prima = _RE_EMOJI_SINGOLA.search(t)
    if prima:
        emoji = prima.group()
        t = _RE_EMOJI.sub(" ", t)
        t = re.sub(r"\s+", " ", t).strip(" -–—:")
        t = f"{t} {emoji}"

    t = re.sub(r"\s+", " ", t).strip()
    return t[:100]                        # limite duro YouTube


def _senza_accenti(testo):
    """'Curiosita\u0300' -> 'Curiosita'. Serve per gli hashtag, che non li accettano."""
    scomposto = unicodedata.normalize("NFKD", testo)
    return "".join(c for c in scomposto if not unicodedata.combining(c))


def _gioco_nel_titolo(titolo, gioco):
    """True se il titolo nomina il gioco, anche con la sigla d'uso comune.

    'GTA 6' e 'Grand Theft Auto VI' sono lo stesso gioco: il modello restituisce
    il nome ufficiale dello store, il titolo usa quello che la gente digita.
    """
    if not gioco:
        return True

    t = _senza_accenti(titolo).lower()
    parole = [p for p in re.split(r"[^0-9a-zA-Z]+", _senza_accenti(gioco).lower()) if p]
    if not parole:
        return True

    if any(len(p) >= 3 and p in t for p in parole):
        return True

    # Sigla: 'Grand Theft Auto VI' -> 'gtavi', che copre anche 'GTA 6'
    sigla = "".join(p[0] for p in parole)
    return len(sigla) >= 3 and (sigla in t or sigla[:3] in t)


def valida_titolo(titolo, gioco=""):
    """Ritorna (True, "") se il titolo e' pubblicabile, altrimenti (False, motivo).

    Le regole non sono di gusto: il troncamento a 60 caratteri e il nome del
    gioco in chiaro decidono se il video e' raggiungibile dalla ricerca, e il
    maiuscolo integrale e' fra gli esempi che YouTube cita come titolo spam.
    """
    if not titolo:
        return False, "titolo vuoto"

    if len(titolo) > MAX_CARATTERI_TITOLO:
        return False, (f"titolo troppo lungo ({len(titolo)} caratteri, "
                       f"max {MAX_CARATTERI_TITOLO}: verrebbe troncato nel feed)")

    if "#short" in titolo.lower():
        return False, "'#Shorts' nel titolo: YouTube riconosce il formato da solo"

    lettere = [c for c in titolo if c.isalpha()]
    if len(lettere) >= 10:
        quota_maiuscole = sum(1 for c in lettere if c.isupper()) / len(lettere)
        if quota_maiuscole > 0.7:
            return False, "titolo quasi tutto in maiuscolo"

    if len(_RE_EMOJI_SINGOLA.findall(titolo)) > 1:
        return False, "piu' di una emoji nel titolo"

    if not _gioco_nel_titolo(titolo, gioco):
        return False, f"il titolo non nomina '{gioco}': invisibile nella ricerca"

    formato = _nome_formato_in_chiaro(titolo)
    if formato:
        return False, f"il titolo contiene il nome interno del formato ({formato})"

    return True, ""


def _pulisci_nome_gioco(gioco):
    """Normalizza il nome del gioco per la ricerca su Steam.

    Scarta i valori generici che il modello a volte restituisce al posto di un
    titolo vero ('videogiochi', 'gaming'): cercarli su Steam darebbe risultati
    casuali, meglio ripiegare direttamente sullo stock.
    """
    g = re.sub(r"[\"'`]", "", gioco).strip()
    g = re.sub(r"\s+", " ", g)
    if len(g) < 3 or len(g) > 60:
        return ""
    if g.lower() in {"videogiochi", "gaming", "gioco", "videogioco",
                     "games", "game", "nessuno", "n/a", "none", "vari"}:
        return ""
    return g


def _nome_formato_in_chiaro(testo):
    """Ritorna il nome interno del formato se e' finito nel testo.

    Visto dal vivo nella prova del 19 settembre 2026: il modello ha scritto
    "Stalker 2: DONT_DO_THIS - non spendere energia sbagliata". Il prompt dice
    "FORMATO RICHIESTO: DONT_DO_THIS" e ogni tanto quella riga viene copiata
    di peso. Su un canale che chiedera' la monetizzazione un titolo con dentro
    una costante di codice e' il segnale piu' chiaro possibile che il video
    l'ha sputato fuori una macchina senza che nessuno lo guardasse.

    Confronta solo la forma esatta con gli underscore: 'TIER LIST LAMPO' con
    gli spazi e' un titolo italiano legittimo, gia' pubblicato, e scartarlo
    sarebbe un falso positivo.
    """
    maiuscolo = (testo or "").upper()
    for nome in FORMATI_VIDEO:
        if nome in maiuscolo:
            return nome
    return ""


def _impronta_apertura(script, n_parole=PAROLE_APERTURA):
    """Le prime parole dello script, ridotte a una forma confrontabile.

    Serve solo a rispondere a "questo attacco l'abbiamo gia' usato?": accenti,
    maiuscole e punteggiatura non contano, contano le parole. Il gioco
    nominato di solito arriva dopo la terza parola, quindi due aperture
    identiche su giochi diversi hanno la stessa impronta, che e' il caso da
    prendere.
    """
    parole = [p for p in re.split(r"[^0-9a-zA-Z]+", _senza_accenti(script or "").lower()) if p]
    return " ".join(parole[:n_parole])


def _ultima_chiusura(script):
    """L'indice dell'ultima punteggiatura di fine frase, -1 se non ce n'e'."""
    return max(script.rfind(segno) for segno in PUNTEGGIATURA_FINALE)


def _senza_decorazioni_finali(script):
    """Lo script senza emoji, virgolette e parentesi in coda.

    Servono a capire dove finisce davvero la frase: un '!' seguito da un
    emoji e' una frase chiusa, una parola seguita da un emoji no.
    """
    nudo = (script or "").rstrip()
    while nudo and nudo[-1] not in PUNTEGGIATURA_FINALE and not nudo[-1].isalnum():
        nudo = nudo[:-1].rstrip()
    return nudo


def _senza_coda_troncata(script):
    """Toglie l'ultima frase quando si interrompe a meta'.

    Si ripara invece di scartare apposta: rigenerare costerebbe uno dei
    quattro tentativi e puo' far saltare la pubblicazione, mentre la coda
    tronca arriva sempre dopo la chiusura vera, quindi togliendola lo script
    resta completo. Se non c'e' nessuna frase chiusa lo script torna intatto e
    a scartarlo ci pensa valida_script().
    """
    testo = (script or "").strip()
    nudo = _senza_decorazioni_finali(testo)
    if not nudo or nudo[-1] in PUNTEGGIATURA_FINALE:
        return testo
    fine = _ultima_chiusura(nudo)
    if fine < 0:
        return testo
    return nudo[:fine + 1].rstrip()


def _script_troncato(script):
    """True se lo script finisce a meta' frase."""
    nudo = _senza_decorazioni_finali(script)
    return not nudo or nudo[-1] not in PUNTEGGIATURA_FINALE


def valida_script(titolo, script, aperture_recenti=()):
    """Ritorna (True, "") se lo script e' pubblicabile, altrimenti (False, motivo)."""
    if not titolo or not script:
        return False, "titolo o script vuoti"

    inizio = script.lower().lstrip(" \"'-–—")
    for vietata in APERTURE_VIETATE:
        if inizio.startswith(vietata):
            return False, f"apertura debole vietata: '{vietata}'"

    # Nove Short di fila aperti con "Stai..." o "Nessuno ti ha detto che..."
    # sono il motivo per cui questo controllo esiste: e' la firma del
    # contenuto prodotto in serie, quello che YouTube guarda quando decide
    # se un canale e' monetizzabile.
    impronta = _impronta_apertura(script)
    if impronta and impronta in set(aperture_recenti):
        return False, f"apre come un video recente ('{impronta}...')"

    formato = _nome_formato_in_chiaro(script)
    if formato:
        return False, f"lo script contiene il nome interno del formato ({formato})"

    n_parole = len(script.split())
    if n_parole < MIN_PAROLE_SCRIPT:
        return False, f"script troppo corto ({n_parole} parole)"
    if n_parole > MAX_PAROLE_SCRIPT:
        return False, f"script troppo lungo ({n_parole} parole, lo Short sforerebbe)"
    if _script_troncato(script):
        return False, "lo script si interrompe a meta' frase"

    return True, ""


# ===========================================================================
# CONFEZIONAMENTO (titolo, descrizione, tag, miniatura)
# ===========================================================================
def _hashtag(testo):
    pulito = "".join(c for c in _senza_accenti(testo) if c.isalnum()).lower()
    return f"#{pulito}" if pulito else ""


def costruisci_hashtag(dati, massimo=3):
    """Gli hashtag della descrizione, in ordine di importanza.

    Conta soprattutto il primo: e' l'unico che YouTube mostra SOPRA al titolo
    del video, quindi ci va il gioco, non '#Shorts'. Tre bastano e avanzano:
    oltre i 15 YouTube li ignora tutti quanti.
    """
    candidati = [
        _hashtag(dati.get("gioco", "")),
        _hashtag(TEMA_PER_FORMATO.get(dati.get("stile", ""), "")),
        "#gamingita",
    ]
    visti, risultato = set(), []
    for h in candidati:
        if h and h not in visti:
            visti.add(h)
            risultato.append(h)
    return risultato[:massimo]


def costruisci_tag(dati, massimo=15, max_caratteri=450):
    """Tag fissi piu' tag che cambiano col video.

    YouTube accetta 500 caratteri di tag in totale e oltre quella soglia
    rifiuta l'upload intero, non i tag in eccesso: qui si taglia a 450.
    """
    tag = list(TAG_FISSI)
    if config.NOME_CANALE:
        tag.append(config.NOME_CANALE.lower())

    gioco = (dati.get("gioco") or "").strip()
    if gioco:
        tag.append(gioco.lower())
        parole = gioco.split()
        if len(parole) > 1:
            tag.append(" ".join(parole[:-1]).lower())   # la saga senza il numero
        tema = TEMA_PER_FORMATO.get(dati.get("stile", ""), "")
        if tema:
            tag.append(f"{gioco.lower()} {tema}")

    visti, risultato, totale = set(), [], 0
    for t in tag:
        t = re.sub(r"\s+", " ", str(t)).strip()
        if not t or t.lower() in visti:
            continue
        if len(risultato) >= massimo or totale + len(t) > max_caratteri:
            break
        visti.add(t.lower())
        risultato.append(t)
        totale += len(t)
    return risultato


def _riga_materiale(dati, materiale):
    """La riga di credito sul materiale video.

    Prima diceva "materiale promozionale ufficiale dei rispettivi editori"
    ogni volta che il modello aveva indicato un gioco. Ma quando Steam non
    trova il gioco, o ne restituisce meno del minimo, `procura_materiale()`
    ripiega su clip d'archivio senza azzerare 'gioco': su quei video la
    descrizione dichiarava il falso proprio nella riga che dovrebbe dare
    credibilita'. Ora la riga la decide chi ha montato davvero il video, e il
    nome usato e' quello ufficiale trovato su Steam, non quello scritto dal
    modello.
    """
    if materiale is None:
        # Chiamante che non sa dire cosa e' finito nel montaggio: meglio una
        # riga generica ma vera che una precisa e falsa.
        return "\nFilmati e immagini a scopo illustrativo."

    nome = (materiale.get("gioco_ufficiale") or dati.get("gioco") or "").strip()
    ufficiali = materiale.get("sorgenti_ufficiali", 0)
    stock = materiale.get("sorgenti_stock", 0)

    if not (ufficiali and nome):
        return "\nFilmati d'archivio a scopo illustrativo."

    if stock:
        return (f"\nFilmati e immagini di {nome}: materiale promozionale "
                "ufficiale dei rispettivi editori, integrato con filmati "
                "d'archivio.")
    return (f"\nFilmati e immagini di {nome}: materiale promozionale "
            "ufficiale dei rispettivi editori.")


def costruisci_descrizione(dati, materiale=None):
    """Descrizione del video.

    Prima solo le prime due righe cambiavano da un video all'altro e tutto il
    resto era identico su ogni upload: e' il pattern che fa riconoscere un
    canale automatizzato. Ora cambiano anche la fonte e gli hashtag finali.

    Nota sul link: viene dal campo <link> del feed Google News, quindi e' un
    indirizzo news.google.com/rss/articles/... che rimanda all'articolo, non
    l'indirizzo della testata. Funziona, ma nella descrizione si legge male.
    """
    parti = [dati.get("descrizione") or dati.get("titolo", "")]

    fonte_url = (dati.get("fonte_url") or "").strip()
    if fonte_url:
        parti.append(f"\nFonte: {fonte_url}")
    elif dati.get("fonte"):
        parti.append(f"\nFonte: {dati['fonte']}")

    parti.append(_riga_materiale(dati, materiale))

    # Dichiararlo qui non cambia nulla per YouTube (la dichiarazione formale la
    # fa gia' uploader.py), ma toglie di mano il commento "e' fatto con l'AI".
    parti.append(
        "\nVideo realizzato con voce sintetica e montaggio automatico, "
        "su fatti e notizie verificabili."
    )
    parti.append(
        f"\nAltri Shorts gaming ogni giorno su {config.NOME_CANALE}: "
        f"youtube.com/{config.HANDLE_CANALE}"
    )
    parti.append("\n" + " ".join(costruisci_hashtag(dati)))
    return "\n".join(parti)


def testo_miniatura(titolo, massimo_parole=4):
    """Le poche parole da stampare grandi sulla miniatura.

    Il nome del gioco sta gia' nel titolo, che YouTube mostra sotto: qui serve
    l'amo, cioe' quello che viene dopo i due punti. Oltre le quattro parole,
    a quella dimensione, nella griglia del canale non si legge piu' niente.
    """
    t = _RE_EMOJI.sub(" ", titolo or "")
    if ":" in t:
        t = t.split(":", 1)[1]
    t = re.sub(r"\s+", " ", t).strip(" -\u2013\u2014:.!?")
    parole = t.split()[:massimo_parole]
    while len(parole) > 1 and parole[-1].lower().strip(".,;:!?'\u2019") in _PAROLE_DEBOLI:
        parole.pop()
    return " ".join(parole).upper()


# ===========================================================================
# GENERAZIONE
# ===========================================================================
def _costruisci_system_prompt(formato, notizie, ultimi_titoli, hook_vincenti,
                              aperture_recenti=(), giochi_recenti=(),
                              notizie_gia_usate=()):
    meta = FORMATI_VIDEO[formato]

    blocco_notizie = "NESSUNA notizia fresca disponibile."
    if notizie:
        righe = [f"  [{i}] {n['titolo']}  (fonte: {n['fonte']})"
                 for i, n in enumerate(notizie)]
        blocco_notizie = "\n".join(righe)

    blocco_hook = ""
    if hook_vincenti:
        blocco_hook = (
            "\nHOOK CHE HANNO FUNZIONATO DAVVERO su questo canale "
            "(replicane il meccanismo, NON le parole: se li ricopi alla "
            "lettera ottieni dieci video che attaccano uguali):\n"
            + "\n".join(f"  - {h}" for h in hook_vincenti) + "\n"
        )

    vincolo_fatti = (
        "VINCOLO DI VERIDICITA' ASSOLUTO: lo script DEVE basarsi su UNA delle notizie "
        "elencate sopra. Non inventare leak, date di uscita o dichiarazioni. "
        "Indica l'indice della notizia usata nel campo 'indice_notizia'.\n"
        if meta["richiede_fatto"] else
        "VINCOLO DI VERIDICITA': usa solo fatti gaming storici e verificabili. "
        "Se non sei certo di un dettaglio, NON inserirlo. Meglio generico che falso. "
        "Imposta 'indice_notizia' a -1.\n"
    )

    # Le regole 11 e 12 compaiono solo quando c'e' davvero qualcosa da evitare:
    # al primo video della vita del canale una lista vuota sarebbe rumore che
    # occupa contesto e non dice niente.
    righe_ripetizioni = []
    if aperture_recenti:
        righe_ripetizioni.append(
            "11. NON aprire lo script come questi video recenti. Cambia proprio "
            "le prime parole, non basta cambiare il gioco nominato:\n"
            + "\n".join(f"   - \"{a}...\"" for a in aperture_recenti)
        )
    if giochi_recenti or notizie_gia_usate:
        vietati = []
        if giochi_recenti:
            vietati.append(f"giochi: {json.dumps(list(giochi_recenti), ensure_ascii=False)}")
        if notizie_gia_usate:
            vietati.append(f"notizie: {json.dumps(list(notizie_gia_usate), ensure_ascii=False)}")
        righe_ripetizioni.append(
            "12. NIENTE DOPPIONI: questi sono gia' usciti, scegli altro.\n   "
            + "\n   ".join(vietati)
        )
    blocco_ripetizioni = "\n".join(righe_ripetizioni)
    if blocco_ripetizioni:
        blocco_ripetizioni += "\n"   # la riga vuota prima di "Rispondi..."

    return (
        f"Sei il Lead Social Media Manager di '{config.NOME_CANALE}', canale YouTube "
        "Gaming italiano. Scrivi uno script per uno Short ad ALTISSIMA RETENTION "
        "(24-30 secondi, quindi 55-85 parole).\n\n"
        f"FORMATO RICHIESTO: {formato} - {meta['descrizione']}\n"
        "(quella sigla e' un'etichetta interna: non deve comparire ne' nel "
        "titolo ne' nello script)\n\n"
        f"NOTIZIE GAMING REALI DI OGGI:\n{blocco_notizie}\n\n"
        f"{vincolo_fatti}"
        f"{blocco_hook}\n"
        "REGOLE TASSATIVE:\n"
        "1. PRIMA FRASE = HOOK. Deve bloccare lo scroll in 3 secondi. "
        "VIETATO iniziare con saluti ('Ciao', 'Raga', 'Benvenuti', 'Oggi vi parlo'). "
        "Attacca con un meccanismo forte, scegliendone uno diverso ogni volta: "
        "una contraddizione, un numero che stona, un'accusa diretta allo "
        "spettatore, una scena raccontata a meta', una domanda secca, un "
        "confronto fra due cose che non c'entrano. Cambia anche le parole, non "
        "solo il gioco nominato: due Short che aprono uguali si leggono come "
        "contenuto prodotto in serie, ed e' cosi' che un canale perde la "
        "monetizzazione.\n"
        "2. SEAMLESS LOOP: l'ultima frase deve ricollegarsi in modo naturale alla "
        "prima parola dello script, cosi' il video riparte senza stacco percepibile.\n"
        "3. RITMO: frasi corte. Una informazione per frase. Niente subordinate.\n"
        f"4. CTA fluida e breve a '{config.NOME_CANALE}', mai piu' di 6 parole, "
        "mai in apertura.\n"
        f"5. TITOLO: massimo {MAX_CARATTERI_TITOLO} caratteri (oltre viene "
        "troncato nel feed), nome del gioco come PRIMA parola, poi i due punti "
        "e l'amo. UNA sola emoji e in FONDO, mai in apertura. Niente '#Shorts'. "
        "Niente maiuscolo integrale: YouTube lo tratta come titolo spam.\n"
        "6. GIOCO: il titolo ESATTO e UFFICIALE del videogioco di cui parla lo "
        "Short, come appare sullo store (es: 'Cyberpunk 2077', 'ELDEN RING', "
        "'Counter-Strike 2'). Serve a scaricare gameplay reale di quel gioco: "
        "niente abbreviazioni, niente nomi di saghe generiche. Se lo Short non "
        "parla di un gioco specifico, metti stringa vuota.\n"
        "7. QUERY VIDEO: in INGLESE, 2-4 parole, usata solo come ripiego se il "
        "gioco non e' reperibile (es: 'cyberpunk gameplay', 'fps shooter action').\n"
        "8. DESCRIZIONE: 2 righe + UNA domanda finale che spinga a commentare.\n"
        "9. NIENTE CRONACA INVENTATA. Se non stai citando una delle notizie "
        "elencate sopra (cioe' se 'indice_notizia' non punta a una di quelle), "
        "lo script NON puo' contenere leak, date di uscita, numeri di vendite, "
        "annunci o conferme attribuite agli sviluppatori: sono fatti verificabili "
        "e inventarli fa danno al canale. In quel caso parla di meccaniche, "
        "segreti di gioco o consigli, che non hanno bisogno di una fonte.\n"
        "10. NON riusare questi titoli gia' pubblicati:\n"
        f"   {json.dumps(ultimi_titoli, ensure_ascii=False)}\n"
        f"{blocco_ripetizioni}\n"
        "Rispondi ESCLUSIVAMENTE con un JSON valido con le chiavi: "
        "'titolo', 'script', 'gioco', 'query_video', 'descrizione', "
        "'indice_notizia'."
    )


# Schema vincolato per la risposta del modello. Con "strict" la decodifica e'
# guidata dallo schema: il JSON non puo' piu' uscire invalido. Supportato dai
# modelli gpt-oss; se un modello non lo accetta, il secondo tentativo ripiega
# sul testo libero. https://console.groq.com/docs/structured-outputs
_SCHEMA_RISPOSTA = {
    "name": "short_samaritan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titolo": {"type": "string"},
            "script": {"type": "string"},
            "gioco": {"type": "string"},
            "query_video": {"type": "string"},
            "descrizione": {"type": "string"},
            "indice_notizia": {"type": "integer"},
        },
        "required": [
            "titolo", "script", "gioco",
            "query_video", "descrizione", "indice_notizia",
        ],
        "additionalProperties": False,
    },
}


# Parole che segnalano un'affermazione di cronaca: qualcosa che o' e' vero e
# allora ha una fonte, o e' inventato. Il modello le usa volentieri perche'
# "bucano" lo scroll, anche quando nessuna notizia gliele ha suggerite.
_SPIE_DI_CRONACA = (
    "trapelat", "leak", "leek", "confermat", "annunciat", "ufficializzat",
    "rumor", "indiscrezion", "data di uscita", "esce il ", "in arrivo il ",
    "hanno dichiarato", "ha dichiarato", "gli sviluppatori hanno",
    "la software house", "secondo il comunicato",
)


def _doppione_recente(gioco, fonte, gioco_precedente, fonti_recenti):
    """Motivo per cui questo video sarebbe un doppione, o stringa vuota.

    Due controlli diversi con due finestre diverse. La notizia non si riusa
    entro MEMORIA_RIPETIZIONI video: e' il caso vero visto il 18 settembre
    2026, due Short usciti dallo stesso articolo su No Man's Sky. Il gioco
    invece si blocca solo sul video immediatamente precedente, perche'
    vietarlo piu' a lungo puo' non lasciare nessuna notizia utilizzabile e
    far saltare la pubblicazione, che e' un danno peggiore della ripetizione.
    """
    f = (fonte or "").strip().lower()
    if f and f in set(fonti_recenti):
        return "riusa la stessa notizia di un video gia' pubblicato"

    g = (gioco or "").strip().lower()
    if g and g == (gioco_precedente or "").strip().lower():
        return f"parla di {gioco} come il video precedente"

    return ""


def _cronaca_senza_fonte(script, fonte):
    """Vero se lo script afferma fatti di cronaca ma non cita nessuna notizia.

    Uno Short che racconta un leak inesistente e' una notizia falsa su un
    prodotto vero, pubblicata in automatico su un canale senza nessuno che la
    rilegga. Meglio rigenerare.
    """
    if fonte:
        return False
    testo = (script or "").lower()
    return any(spia in testo for spia in _SPIE_DI_CRONACA)


def _estrai_json(testo):
    """Ritaglia il primo oggetto JSON da una risposta in testo libero.

    Serve quando lo schema vincolato non e' utilizzabile: il modello a volte
    incornicia il JSON con ```json ... ``` o lo fa precedere da una riga di
    commento.
    """
    testo = (testo or "").strip()
    if testo.startswith("```"):
        testo = re.sub(r"^```[a-zA-Z]*\s*", "", testo)
        testo = re.sub(r"```\s*$", "", testo).strip()
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        raise ValueError("nessun oggetto JSON nella risposta")
    return json.loads(testo[inizio:fine + 1])


def genera_script_samaritan(tema=None):
    """Genera il pacchetto contenuto completo.

    Ritorna un dict: titolo, script, query_video, descrizione, fonte, stile.
    """
    notizie = recupera_trend_gaming_online()
    formato = scegli_formato(notizie)

    cronologia = carica_cronologia()
    ultimi_titoli = [_normalizza(i).get("titolo", "") for i in cronologia[-12:]]

    # Due liste dalla stessa fonte: al modello servono aperture leggibili da
    # evitare, alla validazione serve l'impronta di tre parole da confrontare.
    recenti = [_normalizza(i) for i in cronologia[-MEMORIA_RIPETIZIONI:]]
    estratti = [r.get("estratto_script", "") for r in recenti]
    aperture_da_mostrare = [" ".join(e.split()[:8]) for e in estratti if e.strip()]
    impronte_aperture = {_impronta_apertura(e) for e in estratti}
    impronte_aperture.discard("")

    notizie_gia_usate = sorted({r.get("fonte", "").strip() for r in recenti} - {""})
    fonti_recenti = {f.lower() for f in notizie_gia_usate}

    # Il gioco si blocca solo sull'ultimo video, non su tutta la finestra:
    # vedi _doppione_recente per il perche'.
    gioco_precedente = recenti[-1].get("gioco", "") if recenti else ""
    giochi_recenti = [gioco_precedente] if gioco_precedente.strip() else []

    try:
        from analyst import migliori_hook
        hook_vincenti = migliori_hook(n=3)
    except Exception:
        hook_vincenti = []

    system_prompt = _costruisci_system_prompt(
        formato, notizie, ultimi_titoli, hook_vincenti,
        aperture_da_mostrare, giochi_recenti, notizie_gia_usate
    )
    prompt_base = "Scrivi lo Short di oggi."
    if tema:
        prompt_base += f" Focus specifico richiesto: {tema}"

    # Motivo dell'ultimo scarto: senza questo ogni tentativo riparte dallo
    # stesso identico input e rifa' un tiro di dado. Dicendo al modello cosa
    # non e' andato, i tentativi diventano correzioni.
    motivo_scarto = ""

    modelli = config.GROQ_MODELLI

    for modello in modelli:
        for tentativo in range(1, 3):       # 2 tentativi per modello
            try:
                # Primo tentativo con lo schema vincolato, secondo in testo
                # libero ritagliando il JSON: cosi' anche un modello che non
                # supporta lo schema riesce comunque a rispondere.
                con_schema = tentativo == 1
                prompt_utente = prompt_base
                if motivo_scarto:
                    prompt_utente += (
                        f" Il tentativo precedente e' stato scartato perche' "
                        f"{motivo_scarto}. Correggi quel punto."
                    )
                print(f"[Samaritan Brain] {modello} - tentativo {tentativo} "
                      f"(formato {formato}, "
                      f"{'schema' if con_schema else 'testo libero'})...")
                parametri = {
                    "model": modello,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_utente},
                    ],
                    "temperature": 0.9,
                    # Nei modelli di ragionamento questo tetto copre anche i
                    # token di ragionamento: con 700 il ragionamento si mangiava
                    # tutto il budget e Groq rispondeva 400 json_validate_failed
                    # con generazione vuota.
                    "max_tokens": 2000,
                }
                if con_schema:
                    parametri["response_format"] = {
                        "type": "json_schema",
                        "json_schema": _SCHEMA_RISPOSTA,
                    }
                if "gpt-oss" in modello:
                    # Meno ragionamento, piu' token per la risposta vera.
                    parametri["reasoning_effort"] = "low"

                response = client.chat.completions.create(**parametri)
                contenuto = response.choices[0].message.content
                if not contenuto:
                    print("[Samaritan Brain] Risposta vuota, riprovo.")
                    continue

                data = json.loads(contenuto) if con_schema \
                    else _estrai_json(contenuto)
                titolo = _pulisci_titolo(str(data.get("titolo", "")))
                script = str(data.get("script", "")).strip()
                intero = script
                script = _senza_coda_troncata(script)
                if script != intero:
                    print("[Samaritan Brain] Coda tronca rimossa dallo script.")
                query_video = str(data.get("query_video", "gameplay")).strip()
                descrizione = str(data.get("descrizione", "")).strip()
                gioco = _pulisci_nome_gioco(str(data.get("gioco", "")))

                # La fonte serve gia' in validazione: uno script che parla di
                # leak e conferme senza una notizia dietro va scartato prima di
                # diventare un video.
                fonte, fonte_url = "", ""
                try:
                    idx = int(data.get("indice_notizia", -1))
                    if 0 <= idx < len(notizie):
                        fonte = f"{notizie[idx]['titolo']} ({notizie[idx]['fonte']})"
                        # Il link lo avevamo gia' e lo buttavamo via: in
                        # descrizione e' il segnale di serieta' piu' forte.
                        fonte_url = notizie[idx].get("link", "")
                except (TypeError, ValueError):
                    pass

                ok, motivo = valida_script(titolo, script, impronte_aperture)
                if ok:
                    ok, motivo = valida_titolo(titolo, gioco)
                if ok and _cronaca_senza_fonte(script, fonte):
                    ok = False
                    motivo = "afferma fatti di cronaca senza citare una notizia"
                if ok:
                    doppione = _doppione_recente(
                        gioco, fonte, gioco_precedente, fonti_recenti
                    )
                    if doppione:
                        ok = False
                        motivo = doppione
                if not ok:
                    print(f"[Samaritan Brain] SCARTATO: {motivo}. Rigenero.")
                    motivo_scarto = motivo
                    continue

                motivo_scarto = ""

                if "gameplay" not in query_video.lower():
                    query_video = f"{query_video} gameplay"

                risultato = {
                    "titolo": titolo,
                    "script": script,
                    "gioco": gioco,
                    "query_video": query_video,
                    "descrizione": descrizione,
                    "fonte": fonte,
                    "fonte_url": fonte_url,
                    "stile": formato,
                }
                salva_in_cronologia(risultato)
                print(f"[Samaritan Brain] OK - '{titolo}' "
                      f"({len(script.split())} parole)")
                if gioco:
                    print(f"[Samaritan Brain] Gioco identificato: {gioco}")
                if fonte:
                    print(f"[Samaritan Brain] Ancorato a: {fonte}")
                return risultato

            except Exception as e:
                print(f"[Groq Warning] {modello}: {e}")

    # ------------------------------------------------- Nessun modello risponde
    # Prima qui c'era un testo di ripiego scritto a mano: il video usciva lo
    # stesso, generico e slegato da qualsiasi notizia, e nessuno se ne
    # accorgeva perche' la pipeline chiudeva verde. Meglio saltare il video:
    # l'eccezione fa fallire il workflow, cosi' il problema si vede subito.
    raise RuntimeError(
        "Nessun modello Groq ha risposto: "
        f"provati {', '.join(modelli)}. "
        "Salto il video invece di pubblicare un testo di ripiego. "
        "Controlla il Secret GROQ_API_KEY e l'elenco GROQ_MODELLI "
        "(modelli disponibili: https://console.groq.com/docs/models)."
    )


if __name__ == "__main__":
    dati = genera_script_samaritan()
    print("\n" + "=" * 60)
    print(f"TITOLO      : {dati['titolo']}")
    print(f"FORMATO     : {dati['stile']}")
    print(f"GIOCO       : {dati.get('gioco') or '(non specifico)'}")
    print(f"QUERY VIDEO : {dati['query_video']}")
    print(f"FONTE       : {dati['fonte'] or '(evergreen)'}")
    print("-" * 60)
    print(dati["script"])
    print("-" * 60)
    print(dati["descrizione"])
