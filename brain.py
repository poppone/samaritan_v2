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
from urllib.parse import quote

import requests
from groq import Groq

import config
import prenotazione
import profilo

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

# Le notizie invece si ricordano per tutta la cronologia. Il 19 settembre
# 2026 lo stesso update Cosmos di No Man's Sky e' diventato due Short a un
# giorno di distanza: la notizia era sette voci indietro, fuori dalla
# finestra qui sopra. Ricordarle tutte non costa niente e non puo' far
# saltare una pubblicazione, perche' scarta una notizia prima di sceglierla
# invece di scartare uno script gia' scritto.
MEMORIA_NOTIZIE = 0          # 0 = tutta la cronologia

# Quante parole iniziali confrontare per dire "questo attacco l'abbiamo gia'
# usato". Tre bastano: gli Short scartati si somigliavano proprio li'
# ("Stai sbagliando tutto su X", "Nessuno ti ha detto che Y").
PAROLE_APERTURA = 3

# Quante voci guardare per la FORMA dell'attacco (non le parole: la forma).
# Il 20 settembre 2026 quattro Short di fila hanno aperto con una domanda
# retorica: "Pensavi che...?", "Scommetti che...?", "Hai mai creduto che...?",
# "Stai ancora credendo che...?". Nessuna ripeteva le parole dell'altra,
# quindi il controllo sulle tre parole iniziali le lasciava passare tutte,
# ma da fuori i quattro video si somigliano lo stesso ed e' esattamente la
# somiglianza che YouTube guarda. La finestra qui e' piu' corta di
# MEMORIA_RIPETIZIONI perche' le forme riconoscibili sono poche: vietarne
# troppe in fila vorrebbe dire scartare script buoni, e ogni scarto costa
# uno dei quattro tentativi.
MEMORIA_SCHEMI = 2

SCHEMA_DOMANDA = "una domanda"
SCHEMA_SECONDA_PERSONA = "una frase rivolta allo spettatore"

# Parole che rivelano che la frase parla in faccia a chi guarda. E' un elenco
# corto e scelto a mano invece di una regola sulle desinenze: in italiano la
# seconda persona finisce in -i come mezza lingua ("giochi", "ricordi",
# "aspetti" sono anche sostantivi) e un falso positivo qui costa un
# tentativo di generazione, mentre una parola che manca non costa niente.
# Fuori di proposito: "sei" (anche il numero), "dai" (anche la preposizione)
# e "vi" (anche il VI di 'GTA VI'). Le aperture in seconda persona piu'
# comuni sono comunque domande, e quelle le prende il punto interrogativo.
SECONDA_PERSONA = frozenset((
    "tu", "ti", "te", "tuo", "tua", "tuoi", "tue", "vostro", "vostra",
    "hai", "stai", "vai", "fai", "sai", "puoi", "vuoi", "devi",
    "credi", "pensi", "scommetti", "smetti", "senti", "provi", "conosci",
    "eri", "avevi", "stavi", "pensavi", "credevi", "sapevi", "volevi",
    "dovevi", "facevi", "dicevi", "giocavi",
    "immagina", "dimmi", "fidati", "preparati", "smettila",
))

# Dove cercare le notizie lo dice il profilo del canale (profilo.py, voce
# 'ricerche'), perche' cambia con l'argomento del canale.
# Quante voci leggere da ogni ricerca prima di filtrare.
VOCI_PER_RICERCA = 15

# Il sommario di una notizia arriva da Bing News, che nel feed RSS scrive una
# o due frasi dell'articolo. Google News invece da' solo il titolo, e con il
# solo titolo il modello riempiva 25 secondi di dettagli inventati (vedi
# _costruisci_system_prompt). Il titolo trovato su Bing deve somigliare a
# quello di Google almeno per questa quota di parole, se no il sommario e' di
# un'altra notizia.
SOGLIA_STESSA_NOTIZIA = 0.5
# Quante notizie su altri giochi devono restare per togliere dalla lista
# quelle sul gioco del video precedente invece di metterle solo in fondo.
# Una basta: il 29 settembre 2026, con la soglia a 3, su 8 notizie quasi tutte
# su GTA 6 la lista e' rimasta intera e l'uscita delle 18:00 e' saltata la
# terza volta. Una notizia minore su un altro gioco vale piu' di un buco.
MIN_NOTIZIE_ALTRO_GIOCO = 1
MAX_CARATTERI_SOMMARIO = 400

# I nomi che muovono pubblico da soli (per Poppone TV: GTA, Fortnite, le
# console) stanno nel profilo del canale, voce 'nomi_grossi'.

# Parole che dicono "questa notizia la gente la sta gia' cercando". Non sono
# parole a effetto da mettere nel titolo: servono solo a mettere in ordine le
# notizie in entrata.
# Tutto quello che cambia quando il video non e' in italiano. Sta qui in un
# posto solo apposta: aggiungere una lingua deve voler dire aggiungere una
# voce a questo dizionario, non andare a caccia di stringhe italiane sparse
# per il file.
LINGUE = {
    "it": {
        "nome": "italiano",
        "aperture_vietate": APERTURE_VIETATE,
        "seconda_persona": SECONDA_PERSONA,
        "rss": "hl=it&gl=IT&ceid=IT:it",
        "bing": "setlang=it-IT&cc=IT",
        # Le ricerche di notizie le aggiunge _lingua() dal profilo del canale.
        "parole_calde": (
            "esce", "uscita", "data", "annuncio", "annunciato", "svelato",
            "confermato", "gratis", "gratuito", "leak", "trapelato",
            "rinviato", "cancellato", "chiude", "record", "remake",
            "remaster", "trailer", "nuovo capitolo", "sequel", "crossover",
        ),
    },
    "en": {
        "nome": "English",
        # Gli stessi saluti che uccidono la retention, in inglese.
        "aperture_vietate": (
            "hi ", "hey", "hello", "yo ", "welcome", "what's up", "whats up",
            "in this video", "today we", "today i", "guys,", "let's talk",
            "lets talk",
        ),
        # In inglese la seconda persona e' una parola sola e non si confonde
        # con nient'altro: niente elenco lungo come in italiano.
        "seconda_persona": frozenset((
            "you", "your", "youre", "youve", "yours", "yourself",
        )),
        "rss": "hl=en-US&gl=US&ceid=US:en",
        "bing": "setlang=en-US&cc=US",
        "parole_calde": (
            "release", "releases", "launch", "date", "announced",
            "announcement", "revealed", "confirmed", "free", "leak",
            "leaked", "delayed", "cancelled", "canceled", "shutting down",
            "record", "remake", "remaster", "trailer", "sequel", "crossover",
        ),
    },
}


def _lingua():
    """Le regole della lingua in cui esce questo video.

    Si legge da config a ogni chiamata e non una volta all'avvio: la lingua
    cambia da una run all'altra (il video delle 21:00 e' in inglese) e i
    test la cambiano sotto i piedi.

    Le ricerche di notizie arrivano dal profilo del canale, perche' dipendono
    da cosa parla il canale oltre che dalla lingua; le parole calde pure, se
    il profilo ne ha di sue.
    """
    codice = (config.LINGUA or "it").lower()
    if codice not in LINGUE:
        codice = "it"
    p = profilo.attivo()
    regole = dict(LINGUE[codice])
    regole["ricerche"] = p.ricerche_per(codice)
    regole["parole_calde"] = p.parole_calde_per(codice) or regole["parole_calde"]
    regole["temi_esclusi"] = p.temi_esclusi_per(codice)
    return regole


def _tema_escluso(testo, temi=None):
    """La prima parola del profilo ('temi_esclusi') che compare nel testo, o ''.

    Parole intere, senza accenti e in minuscolo: "morti" prende "cinque
    morti" ma non "mortificato". Per un telegiornale sono le notizie su
    morti, crimini e tragedie (profilo.TEMI_DELICATI).
    """
    temi = _lingua()["temi_esclusi"] if temi is None else temi
    if not temi or not testo:
        return ""
    pulito = " " + " ".join(re.split(r"[^\w]+", _senza_accenti(testo).lower())) + " "
    for tema in temi:
        chiave = " ".join(re.split(r"[^\w]+", _senza_accenti(tema).lower())).strip()
        if chiave and f" {chiave} " in pulito:
            return tema
    return ""


def _lingua_di(voce):
    """La lingua di una voce di cronologia. Le voci vecchie non ce l'hanno
    scritta e sono tutte italiane."""
    return (voce.get("lingua") or "it").lower()


def _stessa_lingua(voci):
    """Solo i video usciti nella lingua di adesso.

    Le regole anti-ripetizione valgono dentro una lingua, non fra lingue: il
    video inglese delle 21:00 puo' e deve poter raccontare la stessa notizia
    grossa di quello italiano delle 14:00, perche' parla a gente diversa.
    Mescolare le due memorie vorrebbe dire lasciare all'inglese solo gli
    argomenti che l'italiano ha scartato.
    """
    attuale = (config.LINGUA or "it").lower()
    return [v for v in voci if _lingua_di(v) == attuale]


def _formato_di(voce):
    """Il formato di una voce di cronologia. Le voci scritte prima del 22
    settembre 2026 non ce l'hanno e sono tutte Short."""
    return (voce.get("formato") or "short").lower()


def _stesso_formato(voci):
    """Solo i video usciti nello stesso formato di adesso.

    Stesso ragionamento di _stessa_lingua: le regole anti-ripetizione valgono
    dentro un formato. Un video lungo da otto minuti su un gioco non deve
    impedire allo Short della sera di parlarne, sono due cose diverse per due
    modi diversi di guardare; e l'apertura di una sezione di otto minuti non
    dice niente su come deve attaccare uno Short.
    """
    attuale = "lungo" if config.VIDEO_LUNGO else "short"
    return [v for v in voci if _formato_di(v) == attuale]


PUNTI_GIOCO_GROSSO = 4
PUNTI_PAROLA_CALDA = 1
MAX_PAROLE_CALDE = 3      # oltre, e' un titolo acchiappaclic, non una notizia
PUNTI_RIPETIZIONE = 2     # la stessa notizia trovata da piu' di una ricerca

# Le parole che il pubblico di QUESTO canale scrive davvero nella ricerca di
# YouTube, prese da Analytics (analyst.parole_cercate). Pesano piu' di tutto il
# resto messo qui a mano: GIOCHI_GROSSI e le parole calde sono una mia ipotesi
# su cosa interessa, queste sono un fatto misurato. Il tetto serve perche' una
# notizia che tocca tre parole cercate non vale il triplo di una che ne tocca
# una: vuol dire solo che e' dello stesso mondo.
PUNTI_PAROLA_CERCATA = 3
MAX_PAROLE_CERCATE = 2

# Con quante voci di cronologia confrontare le PAROLE di una notizia. E' un
# confronto sfumato, quindi la finestra deve restare corta: `titoli_passati`
# prendeva tutta la cronologia, e con cento titoli dentro quasi ogni parola
# gaming risultava "gia' usata", cosi' il filtro si stringeva da solo fino a
# scartare tutto. Il confronto esatto sulla notizia (MEMORIA_NOTIZIE) continua
# a guardare tutto: quello non puo' sbagliare bersaglio.
MEMORIA_PAROLE_TITOLI = 10

MIN_PAROLE_SCRIPT = 45

# Tentativi di scrittura per ogni modello Groq: dispari lo schema vincolato,
# pari il testo libero. Erano due: con due modelli, quattro tentativi in
# tutto, e il 29 settembre 2026 sono saltate tre uscite su quattro con tutti
# i tentativi bruciati. Il modello piccolo scrive spesso script troppo corti,
# quindi il tentativo in piu' conviene darlo a entrambi.
TENTATIVI_PER_MODELLO = 3
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

# Il tema in hashtag di ogni formato e i tag fissi di ogni video stanno nel
# profilo del canale (voci 'hashtag_formato', 'tag_fissi', 'tag_fissi_lungo'):
# per un canale di cucina '#newsgaming' sarebbe un hashtag sbagliato.


def _descrizione_formato(formato):
    """Come si descrive il formato al modello: quella del profilo se ce l'ha.

    Le descrizioni di FORMATI_VIDEO sono scritte per i videogiochi ("nascosto
    da uno sviluppatore"); un profilo di un altro argomento le sostituisce.
    """
    return (profilo.attivo().formati.get(formato)
            or FORMATI_VIDEO[formato]["descrizione"])


def _tema_formato(stile):
    """Il tema in hashtag del formato, senza '#', o stringa vuota."""
    return profilo.attivo().hashtag_formato.get(stile or "", "")


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


# La riga di questa lavorazione, (timestamp, titolo): con la prenotazione la
# cronologia si unisce a quella di altre lavorazioni e l'ultima riga del file
# puo' non essere la nostra.
_NOSTRA_VOCE = None


def salva_in_cronologia(dati):
    """Aggiunge l'impronta del nuovo video alla memoria."""
    global _NOSTRA_VOCE
    cronologia = carica_cronologia()
    adesso = int(time.time())
    _NOSTRA_VOCE = (adesso, dati["titolo"])
    cronologia.append({
        "timestamp": adesso,
        "data": time.strftime("%Y-%m-%d"),
        "titolo": dati["titolo"],
        "lingua": (config.LINGUA or "it").lower(),
        # Quale uscita della giornata sta coprendo questo video ('14:00',
        # '18:00', '21:00'). Vuoto per le prove lanciate a mano, che non
        # coprono niente. Serve a orari.gia_pubblicato() per non far uscire
        # due video sulla stessa uscita quando una run arriva in ritardo.
        "slot": (config.SLOT or "").strip(),
        # L'istante di quella uscita: con i cron che partono di notte, l'ora
        # in cui il video e' scritto non basta a dire di che giorno e'.
        "uscita": config.USCITA,
        # 'short' oppure 'lungo'. Serve alla lavorazione di recupero, che deve
        # sapere che formato rifare, e ai conti sulle performance, dove un
        # video da otto minuti e uno da trenta secondi non si sommano.
        "formato": "lungo" if config.VIDEO_LUNGO else "short",
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
    voce = cronologia[-1]
    if _NOSTRA_VOCE:
        for candidata in reversed(cronologia):
            if (isinstance(candidata, dict)
                    and (candidata.get("timestamp"), candidata.get("titolo")) == _NOSTRA_VOCE):
                voce = candidata
                break
    if isinstance(voce, dict):
        voce["video_id"] = video_id
        with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
            json.dump(cronologia, f, ensure_ascii=False, indent=2)


# ===========================================================================
# RICERCA NOTIZIE REALI
# ===========================================================================
def _impronta_notizia(titolo):
    """Forma confrontabile del titolo di una notizia.

    Accenti, maiuscole e punteggiatura non contano: la stessa notizia
    ripresa due giorni dopo puo' avere un apostrofo diverso e resta la
    stessa notizia.
    """
    parole = [p for p in re.split(r"[^0-9a-zA-Z]+", _senza_accenti(titolo or "").lower()) if p]
    return " ".join(parole)


def _notizia_di_una_voce(fonte):
    """L'impronta della notizia usata da un video gia' pubblicato.

    In cronologia la fonte e' scritta come "Titolo della notizia (Testata)",
    mentre l'RSS da' il titolo da solo: la testata in coda va tolta prima di
    confrontare.
    """
    testo = (fonte or "").strip()
    if testo.endswith(")") and "(" in testo:
        testo = testo[:testo.rfind("(")]
    return _impronta_notizia(testo)


def _punteggio_notizia(titolo, apparizioni=1, cercate=frozenset()):
    """Quanto vale una notizia in entrata. Piu' alto = piu' gente la cerca.

    Non giudica come e' scritta la notizia, giudica di cosa parla. Sui video
    veri di questo canale l'argomento e' l'unica cosa che separa i video
    andati bene da quelli morti, e finora l'argomento veniva scelto a caso.

    'cercate' sono le parole che il pubblico scrive nella ricerca di YouTube
    per arrivare su questo canale: l'unico pezzo di questo punteggio che non
    e' un'ipotesi. Quando mancano (token senza Analytics, canale nuovo) il
    punteggio resta quello di prima, non peggiore.
    """
    testo = _senza_accenti(titolo or "").lower()
    punti = 0
    if any(g in testo for g in profilo.attivo().nomi_grossi):
        punti += PUNTI_GIOCO_GROSSO
    calde = sum(1 for parola in _lingua()["parole_calde"] if parola in testo)
    punti += min(calde, MAX_PAROLE_CALDE) * PUNTI_PAROLA_CALDA
    # Trovata da piu' di una ricerca: non e' un giudizio nostro, e' il segno
    # che la notizia sta girando.
    punti += (apparizioni - 1) * PUNTI_RIPETIZIONE
    # Le parole si confrontano intere: 'gta' non deve accendersi dentro
    # 'gtavicecity', e soprattutto una sigla di due lettere non deve
    # accendersi dentro mezzo vocabolario.
    if cercate:
        parole_titolo = set(re.split(r"[^\w]+", testo))
        trovate = len(parole_titolo & cercate)
        punti += min(trovate, MAX_PAROLE_CERCATE) * PUNTI_PAROLA_CERCATA
    return punti


def _voci_rss(ricerca):
    """Le voci grezze di una ricerca su Google News: (titolo, fonte, link)."""
    url = ("https://news.google.com/rss/search?q="
           + quote(ricerca)
           + "&" + _lingua()["rss"])
    risposta = requests.get(url, timeout=8)
    risposta.raise_for_status()
    radice = ET.fromstring(risposta.content)

    voci = []
    for item in radice.findall("./channel/item")[:VOCI_PER_RICERCA]:
        nodo_titolo = item.find("title")
        if nodo_titolo is None or not nodo_titolo.text:
            continue
        titolo_completo = html.unescape(nodo_titolo.text)
        # Google News formatta come "Titolo - Testata"
        if " - " in titolo_completo:
            titolo, fonte = titolo_completo.rsplit(" - ", 1)
        else:
            titolo, fonte = titolo_completo, "Google News"
        nodo_link = item.find("link")
        voci.append((titolo.strip(), fonte.strip(),
                     nodo_link.text if nodo_link is not None else ""))
    return voci


def _parole_significative(testo):
    return {p for p in _impronta_notizia(testo).split() if len(p) > 3}


def _stessa_notizia(a, b):
    """Vero se due titoli parlano della stessa notizia.

    Non si confrontano per intero: Bing e Google riprendono la stessa
    notizia da testate diverse, con parole appena diverse.
    """
    pa, pb = _parole_significative(a), _parole_significative(b)
    if not pa or not pb:
        return False
    return len(pa & pb) / len(pa | pb) >= SOGLIA_STESSA_NOTIZIA


def _sommario_bing(titolo):
    """Una o due frasi dell'articolo, cercate su Bing News. Vuoto se non c'e'.

    Il 28 settembre 2026, per la notizia da cui era nato il video inventato
    del giorno prima, Bing dava: "GTA VI could be yours for free, or at
    least for a big discount, using a few tricks that Xbox offers". Col solo
    titolo il modello aveva raccontato un glitch.
    """
    url = ("https://www.bing.com/news/search?q=" + quote(titolo)
           + "&format=rss&" + _lingua()["bing"])
    risposta = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    risposta.raise_for_status()
    radice = ET.fromstring(risposta.content)
    for item in radice.findall("./channel/item")[:5]:
        if not _stessa_notizia(html.unescape(item.findtext("title") or ""), titolo):
            continue
        testo = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        testo = " ".join(html.unescape(testo).split())
        # Un sommario che ripete il titolo non aggiunge niente.
        if testo and _impronta_notizia(testo) != _impronta_notizia(titolo):
            if len(testo) > MAX_CARATTERI_SOMMARIO:
                testo = testo[:MAX_CARATTERI_SOMMARIO].rsplit(" ", 1)[0] + "..."
            return testo
    return ""


def _aggiungi_sommari(notizie):
    """Mette a ogni notizia il campo 'sommario', vuoto se non si trova."""
    for notizia in notizie:
        try:
            notizia["sommario"] = _sommario_bing(notizia["titolo"])
        except Exception as e:
            print(f"[Warning Search] Sommario non trovato per "
                  f"'{notizia['titolo']}' ({e}).")
            notizia["sommario"] = ""
    if notizie:
        print(f"[Samaritan Search] Sommario dell'articolo trovato per "
              f"{sum(1 for n in notizie if n['sommario'])} notizie su "
              f"{len(notizie)}.")


def recupera_trend_gaming_online(max_notizie=8, tema=None, gioco_da_evitare=""):
    """Scarica notizie gaming fresche e scarta quelle gia' sfruttate.

    Ritorna una lista di dict {titolo, fonte, link}: servono strutturate
    perche' lo script deve poter citare la fonte reale.

    Con un tema (un video chiesto a mano, per esempio da Telegram) si cerca
    prima proprio quello, e le notizie trovate cosi' passano davanti a tutte
    le altre: senza, il modello riceveva le notizie del giorno e il tema come
    una riga in fondo, e sceglieva la notizia piu' grossa.

    Con gioco_da_evitare (il gioco del video precedente) le notizie su quel
    gioco escono prima del taglio a max_notizie, se ne resta almeno una su un
    altro: il 29 settembre 2026 le otto piu' grosse erano tutte su GTA 6
    dopo un video su GTA VI, e filtrare dopo il taglio non lasciava niente.
    """
    print(f"[Samaritan Search] Ricerca trend {profilo.attivo().argomento} reali...")

    # Cosa cerca davvero il pubblico di questo canale. Importato qui dentro e
    # non in cima al file: analyst importa brain, e in cima si avviterebbero.
    try:
        from analyst import parole_cercate
        cercate = parole_cercate()
    except Exception as e:
        print(f"[Samaritan Search] Ricerche del pubblico non leggibili ({e}).")
        cercate = frozenset()

    cronologia = carica_cronologia()
    voci = _stessa_lingua([_normalizza(i) for i in cronologia])
    # Solo gli ultimi titoli: vedi MEMORIA_PAROLE_TITOLI.
    titoli_passati = " ".join(
        v.get("titolo", "") for v in voci[-MEMORIA_PAROLE_TITOLI:]
    ).lower()
    # Le notizie gia' sfruttate, confrontate per intero e non per parole: il
    # filtro sulle parole qui sotto guarda i TITOLI dei video, che sono
    # riscritti dal modello e possono non somigliare alla notizia da cui
    # nascono.
    da_guardare = voci[-MEMORIA_NOTIZIE:] if MEMORIA_NOTIZIE else voci
    notizie_passate = {_notizia_di_una_voce(v.get("fonte", "")) for v in da_guardare}
    notizie_passate.discard("")

    # Le ricerche si sovrappongono apposta: la stessa notizia trovata da piu'
    # di una e' una notizia che sta girando, e quel conto finisce nel
    # punteggio. Chiave: l'impronta della notizia, non il titolo, perche'
    # testate diverse la scrivono con parole appena diverse.
    trovate = {}
    scartate_per_tema = 0
    tema = (tema or "").strip()
    ricerche = ((tema,) if tema else ()) + tuple(_lingua()["ricerche"])
    for ricerca in ricerche:
        try:
            voci_rss = _voci_rss(ricerca)
        except Exception as e:
            print(f"[Warning Search] Ricerca '{ricerca}' non riuscita ({e}).")
            continue

        for titolo, fonte, link in voci_rss:
            impronta = _impronta_notizia(titolo)
            if not impronta:
                continue
            if impronta in trovate:
                trovate[impronta]["apparizioni"] += 1
                continue

            # Questa notizia e' gia' diventata un video: saltala.
            if impronta in notizie_passate:
                continue

            # Un tema che il canale non tratta (per un telegiornale: morti,
            # crimini, tragedie). Si scarta qui e non dopo: la notizia non
            # arriva nemmeno al modello.
            escluso = _tema_escluso(titolo)
            if escluso:
                scartate_per_tema += 1
                continue

            # Salta le notizie troppo simili a quelle gia' usate di recente.
            parole = [w.lower() for w in titolo.split() if len(w) > 4]
            gia_usate = [w for w in parole if w in titoli_passati]
            if parole and len(gia_usate) / len(parole) >= 0.3:
                continue

            trovate[impronta] = {
                "titolo": titolo, "fonte": fonte, "link": link,
                "apparizioni": 1,
                "sul_tema": bool(tema) and ricerca == tema,
            }

    for voce in trovate.values():
        voce["punteggio"] = _punteggio_notizia(
            voce["titolo"], voce["apparizioni"], cercate
        )

    # In ordine di importanza, non a caso: la piu' grossa arriva al modello
    # per prima. A parita' di punteggio l'ordine e' quello di arrivo.
    notizie = sorted(trovate.values(),
                     key=lambda v: (not v["sul_tema"], -v["punteggio"]))
    if gioco_da_evitare.strip():
        altre = [n for n in notizie
                 if not _gioco_nel_titolo(n["titolo"], gioco_da_evitare)]
        if len(altre) >= MIN_NOTIZIE_ALTRO_GIOCO:
            print(f"[Samaritan Search] Tolte {len(notizie) - len(altre)} "
                  f"notizie su {gioco_da_evitare}, il gioco del video precedente.")
            notizie = altre
    notizie = notizie[:max_notizie]

    _aggiungi_sommari(notizie)
    # Il titolo puo' tacere quello che il sommario dice ("Lutto nel mondo
    # della musica" -> "e' morto a 80 anni"): si guarda anche quello.
    prima = len(notizie)
    notizie = [n for n in notizie if not _tema_escluso(n.get("sommario", ""))]
    scartate_per_tema += prima - len(notizie)
    # Un telegiornale senza sommario ha solo il titolo per riempire un minuto,
    # e il modello lo riempie inventando: il 30 settembre 2026 statistiche su
    # "Serie A", il 1 ottobre le date dei "Pagamenti Inps ottobre", e due
    # uscite sono saltate con tutti i tentativi scartati dal fact-check. Le
    # notizie con sommario passano davanti; fra loro l'ordine resta quello
    # per importanza.
    if profilo.attivo().telegiornale:
        notizie.sort(key=lambda n: not n.get("sommario"))
    if scartate_per_tema:
        print(f"[Samaritan Search] Scartate {scartate_per_tema} notizie su "
              f"temi che il canale non tratta (profilo, 'temi_esclusi').")

    if notizie:
        print(f"[Samaritan Search] {len(notizie)} notizie fresche non ancora "
              f"usate, la piu' grossa vale {notizie[0]['punteggio']} punti: "
              f"{notizie[0]['titolo']}")
        if cercate:
            testo = _senza_accenti(notizie[0]["titolo"]).lower()
            toccate = sorted(set(re.split(r"[^\w]+", testo)) & cercate)
            if toccate:
                print(f"[Samaritan Search] Parole che il pubblico cerca "
                      f"davvero e che questa notizia tocca: "
                      f"{', '.join(toccate)}.")
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

    # Un telegiornale racconta solo notizie: niente curiosita', classifiche o
    # dilemmi. Senza notizie non c'e' telegiornale, e l'uscita la recupera la
    # riserva invece di riempirla con un video che non c'entra.
    if profilo.attivo().telegiornale:
        if not notizie_disponibili:
            raise RuntimeError(
                "Nessuna notizia utilizzabile per il telegiornale: salto il "
                "video invece di fare un contenuto senza fonte.")
        formati = {n: m for n, m in FORMATI_VIDEO.items() if m["richiede_fatto"]}
    else:
        formati = FORMATI_VIDEO

    candidati, valori = [], []
    for nome, meta in formati.items():
        if meta["richiede_fatto"] and not notizie_disponibili:
            continue                      # niente fatti -> niente formato factual
        if nome in stili_recenti:
            continue                      # evita di ripetere gli ultimi 4
        candidati.append(nome)
        valori.append(max(pesi.get(nome, 1.0), 0.05))

    if not candidati:                     # tutti esclusi: allarga il campo
        candidati = [
            n for n, m in formati.items()
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
    if prima and profilo.attivo().telegiornale:
        # Un telegiornale non mette faccine nei titoli.
        t = re.sub(r"\s+", " ", _RE_EMOJI.sub(" ", t)).strip(" -–—:")
    elif prima:
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


def _compatto(testo):
    """Solo lettere e cifre: 'S.T.A.L.K.E.R. 2' -> 'stalker2'."""
    return re.sub(r"[^0-9a-z]", "", _senza_accenti(testo or "").lower())


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

    # Nomi puntati. 'S.T.A.L.K.E.R. 2' non ha nessuna parola di tre lettere e
    # nemmeno la sigla si trova, perche' i punti stanno in mezzo: il 20
    # settembre 2026 il titolo lo scriveva per esteso e questo controllo lo
    # scartava lo stesso, tre tentativi di fila, finche' il video e' saltato.
    # Tolta la punteggiatura da entrambe le parti il confronto torna a dire
    # la verita'.
    compatto_gioco = _compatto(gioco)
    if len(compatto_gioco) >= 3 and compatto_gioco in _compatto(titolo):
        return True

    # Sigla: 'Grand Theft Auto VI' -> 'gtavi', che copre anche 'GTA 6'
    sigla = "".join(p[0] for p in parole)
    return len(sigla) >= 3 and (sigla in t or sigla[:3] in t)


def _fuori_stile_tg(titolo, script):
    """Il motivo per cui titolo o apertura non sono da telegiornale, o "".

    La prima prova vera del canale di notizie (30 settembre 2026) e' uscita
    come "Inter: assenza contro il Parma? 🤔", con lo script che apriva
    "Inter assente contro il Parma? E' vero.": il tono di uno Short gaming,
    non di un TG.
    """
    if "?" in titolo:
        return ("il titolo e' una domanda: un telegiornale titola con "
                "un'affermazione, senza punto di domanda")
    prima = re.split(r"(?<=[.!?])\s", script.strip(), maxsplit=1)[0]
    if prima.endswith("?"):
        return ("lo script apre con una domanda: un telegiornale apre "
                "dicendo il fatto")
    di_parte = _parola_di_parte(titolo + " " + script)
    if di_parte:
        return (f"usa '{di_parte}', una parola che prende posizione: un "
                "telegiornale riferisce i fatti con parole neutre")
    return ""


# Parole che in un titolo o in uno script prendono posizione invece di
# riferire: un telegiornale le lascia ai commentatori. Servono soprattutto
# sulla politica, che il canale notizie tratta dal 1 ottobre 2026 a patto di
# restare neutro. Solo parole che un TG serio non userebbe mai a voce sua:
# "attacca" o "critica" restano, perche' riferiscono cosa ha fatto qualcuno.
PAROLE_DI_PARTE = {
    "it": [
        "vergogna", "vergognoso", "vergognosa", "scandaloso", "scandalosa",
        "schiaffo", "batosta", "asfalta", "asfaltato", "asfaltata", "umilia",
        "umiliato", "umiliata", "umiliazione", "disastroso", "disastrosa",
        "flop", "trionfo", "trionfale", "stravince", "demolisce", "distrugge",
        "massacra", "follia", "incredibile", "assurdo", "assurda", "shock",
        "choc", "regime", "vergognarsi", "fa a pezzi", "zittisce", "gela",
    ],
    "en": [
        "slams", "destroys", "humiliates", "humiliating", "disastrous",
        "shameful", "outrageous", "crushing", "epic", "meltdown", "shock",
        "shocking", "insane", "owns", "eviscerates", "obliterates",
    ],
}


def _parola_di_parte(testo):
    """La prima parola di parte che compare nel testo, o ""."""
    lingua = (config.LINGUA or "it").lower()
    return _tema_escluso(testo, PAROLE_DI_PARTE.get(lingua, []))


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
    casuali, meglio ripiegare direttamente sullo stock. Per un canale di un
    altro argomento vale lo stesso con le sue parole ('ricetta', 'cucina'):
    finirebbero come nome nel titolo e nei tag.
    """
    g = re.sub(r"[\"'`]", "", gioco).strip()
    g = re.sub(r"\s+", " ", g)
    if len(g) < 3 or len(g) > 60:
        return ""
    p = profilo.attivo()
    generici = {"videogiochi", "gaming", "gioco", "videogioco",
                "games", "game", "nessuno", "n/a", "none", "vari"}
    generici |= {v.strip().lower() for v in (
        p.argomento, p.descrizione_argomento, p.soggetto, p.soggetto_plurale)}
    if g.lower() in generici:
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


def _prima_frase(script):
    """Solo l'attacco: il testo fino alla prima punteggiatura di fine frase.

    Il resto dello script non c'entra. "Rockstar ha mentito. Ci credi?" apre
    con un'affermazione, non con una domanda, e va contato per quello.
    """
    testo = (script or "").strip()
    fine = min((i for i, c in enumerate(testo) if c in PUNTEGGIATURA_FINALE),
               default=-1)
    return testo if fine < 0 else testo[:fine + 1]


def _schema_apertura(script):
    """Che FORMA ha l'attacco, indipendentemente dalle parole usate.

    Ritorna stringa vuota quando l'attacco e' una frase normale: quella non
    si blocca mai, altrimenti non resterebbe nessuna apertura consentita.
    Si riconoscono solo le due forme che si ripetevano davvero.

    Lavora anche sull'estratto di 90 caratteri salvato in cronologia. Se il
    taglio cade prima del punto interrogativo la domanda non viene vista e
    il video passa: e' il verso giusto in cui sbagliare, perche' un mancato
    riconoscimento non costa niente e un riconoscimento sbagliato costa un
    tentativo.
    """
    frase = _prima_frase(script)
    if not frase:
        return ""
    if frase.endswith("?"):
        return SCHEMA_DOMANDA
    parole = set(re.split(r"[^0-9a-zA-Z]+", _senza_accenti(frase).lower()))
    if parole & _lingua()["seconda_persona"]:
        return SCHEMA_SECONDA_PERSONA
    return ""


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


def valida_script(titolo, script, aperture_recenti=(), schemi_recenti=()):
    """Ritorna (True, "") se lo script e' pubblicabile, altrimenti (False, motivo)."""
    if not titolo or not script:
        return False, "titolo o script vuoti"

    inizio = script.lower().lstrip(" \"'-–—")
    for vietata in _lingua()["aperture_vietate"]:
        if inizio.startswith(vietata):
            return False, f"apertura debole vietata: '{vietata}'"

    # Nove Short di fila aperti con "Stai..." o "Nessuno ti ha detto che..."
    # sono il motivo per cui questo controllo esiste: e' la firma del
    # contenuto prodotto in serie, quello che YouTube guarda quando decide
    # se un canale e' monetizzabile.
    impronta = _impronta_apertura(script)
    if impronta and impronta in set(aperture_recenti):
        return False, f"apre come un video recente ('{impronta}...')"

    # Il controllo qui sopra guarda le parole, questo guarda la forma: quattro
    # domande retoriche di fila hanno quattro impronte diverse e un solo
    # schema. Vedi MEMORIA_SCHEMI.
    schema = _schema_apertura(script)
    if schema and schema in set(schemi_recenti):
        return False, f"apre con {schema}, come i video recenti"

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
        _hashtag(_tema_formato(dati.get("stile", ""))),
        _hashtag(profilo.attivo().hashtag_canale),
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
    p = profilo.attivo()
    tag = list(p.tag_fissi_lungo if config.VIDEO_LUNGO else p.tag_fissi)
    if config.NOME_CANALE:
        tag.append(config.NOME_CANALE.lower())

    gioco = (dati.get("gioco") or "").strip()
    if gioco:
        tag.append(gioco.lower())
        parole = gioco.split()
        if len(parole) > 1:
            tag.append(" ".join(parole[:-1]).lower())   # la saga senza il numero
        tema = _tema_formato(dati.get("stile", ""))
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
        if profilo.attivo().telegiornale:
            return ("\nImmagini di repertorio a scopo illustrativo: non "
                    "ritraggono i fatti raccontati.")
        return "\nFilmati d'archivio a scopo illustrativo."

    if stock:
        return (f"\nFilmati e immagini di {nome}: materiale promozionale "
                "ufficiale dei rispettivi editori, integrato con filmati "
                "d'archivio.")
    return (f"\nFilmati e immagini di {nome}: materiale promozionale "
            "ufficiale dei rispettivi editori.")


def costruisci_descrizione(dati, materiale=None, capitoli=""):
    """Descrizione del video.

    Prima solo le prime due righe cambiavano da un video all'altro e tutto il
    resto era identico su ogni upload: e' il pattern che fa riconoscere un
    canale automatizzato. Ora cambiano anche la fonte e gli hashtag finali.

    Nota sul link: viene dal campo <link> del feed Google News, quindi e' un
    indirizzo news.google.com/rss/articles/... che rimanda all'articolo, non
    l'indirizzo della testata. Funziona, ma nella descrizione si legge male.
    """
    parti = [dati.get("descrizione") or dati.get("titolo", "")]

    # I capitoli vanno IN ALTO, subito sotto le prime righe: YouTube li legge
    # ovunque siano nella descrizione, ma chi guarda li cerca li'. Li ha solo
    # il video lungo, dove sono la ragione principale per cui uno spettatore
    # resta invece di chiudere al primo minuto.
    if capitoli:
        parti.append("\nCapitoli:\n" + capitoli)

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
    cosa = "Altri video" if config.VIDEO_LUNGO else "Altri Shorts"
    parti.append(
        f"\n{cosa} {profilo.attivo().argomento} ogni giorno su "
        f"{config.NOME_CANALE}: "
        f"youtube.com/{config.HANDLE_CANALE}"
    )
    parti.append("\n" + " ".join(costruisci_hashtag(dati)))
    return "\n".join(parti)


# Il 'for you' di TikTok, lingua per lingua: il video delle 21:00 esce in
# inglese e '#perte' la' non lo cerca nessuno.
HASHTAG_PER_TE = {"it": "#perte", "en": "#fyp"}


def costruisci_didascalia_tiktok(dati, massimo_hashtag=4):
    """La didascalia pronta da incollare su TikTok.

    Non e' la descrizione di YouTube e non deve diventarlo: li' servono la
    fonte, il credito al materiale e il link al canale, qui no. Su TikTok i
    link non sono cliccabili e le prime due righe sono le uniche che si
    leggono prima di 'altro', quindi resta il titolo, un rigo di contenuto e
    gli hashtag.
    """
    titolo = (dati.get("titolo") or "").strip()

    # Della descrizione tengo solo la prima riga: la seconda e' la domanda
    # finale, che nel video la voce la dice gia'.
    descrizione = (dati.get("descrizione") or "").strip()
    prima_riga = descrizione.splitlines()[0].strip() if descrizione else ""

    hashtag = costruisci_hashtag(dati, massimo=massimo_hashtag)
    # L'hashtag del 'per te' e' una convenzione di TikTok e cambia con la
    # lingua del video: su YouTube sarebbe solo rumore, per questo sta qui e
    # non in costruisci_hashtag.
    per_te = HASHTAG_PER_TE.get((config.LINGUA or "it").lower(), "#perte")
    if len(hashtag) < massimo_hashtag and per_te not in hashtag:
        hashtag.append(per_te)

    parti = [p for p in (titolo, prima_riga, " ".join(hashtag)) if p]
    return "\n\n".join(parti)


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
def _esempi(voci):
    """" (es: 'a', 'b')" da mettere in un prompt, vuoto se non ci sono esempi."""
    return f" (es: {profilo.Profilo.elenco(voci)})" if voci else ""


def completa_query_video(query):
    """La ricerca delle clip stock, pronta per Pexels.

    Per i videogiochi si aggiunge 'gameplay', come si e' sempre fatto: senza,
    Pexels risponde con gente seduta davanti a uno schermo. Per ogni altro
    argomento la parola sbaglierebbe la ricerca, e una query vuota ripiega
    sulla prima ricerca di riserva del profilo.
    """
    p = profilo.attivo()
    if not p.videogiochi:
        return query.strip() or p.query_stock_riserva[0]
    if "gameplay" not in query.lower():
        query = f"{query} gameplay"
    return query


def _costruisci_system_prompt(formato, notizie, ultimi_titoli, hook_vincenti,
                              aperture_recenti=(), giochi_recenti=(),
                              notizie_gia_usate=(), schemi_recenti=()):
    meta = FORMATI_VIDEO[formato]
    # Di cosa parla il canale. Senza canale.json sono i videogiochi e il
    # prompt esce identico, parola per parola, a quello di sempre.
    p = profilo.attivo()
    s = p.soggetto

    blocco_notizie = "NESSUNA notizia fresca disponibile."
    if notizie:
        righe = []
        for i, n in enumerate(notizie):
            righe.append(f"  [{i}] {n['titolo']}  (fonte: {n['fonte']})")
            if n.get("sommario"):
                righe.append(f"      Sommario: {n['sommario']}")
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
        f"VINCOLO DI VERIDICITA': usa solo fatti {p.argomento} storici e verificabili. "
        "Se non sei certo di un dettaglio, NON inserirlo. Meglio generico che falso. "
        "Imposta 'indice_notizia' a -1.\n"
    )

    # Della notizia il modello riceve il titolo di Google News e, quando Bing
    # lo ha, un sommario di una o due frasi. Col solo titolo il modello
    # completava la storia di fantasia. Il 27 settembre 2026 da "These Xbox Players Got GTA 6 For
    # Free The Hard Way" (Engadget) e' uscito uno Short su un glitch che
    # saltava l'acquisto, chiuso da Microsoft in poche ore: niente di tutto
    # questo stava nel titolo. Vale per ogni formato, perche' anche quelli
    # che non richiedono una notizia a volte se ne prendono una.
    # L'esempio e' un caso vero di questo canale e parla di GTA 6: a un
    # canale di cucina insegnerebbe solo che esiste GTA 6.
    esempio_invenzione = (
        " Esempio di errore da non "
        "ripetere: dal titolo 'These Xbox Players Got GTA 6 For Free The Hard "
        "Way' uno script si e' inventato un glitch che saltava l'acquisto e "
        "Microsoft che lo chiudeva in poche ore."
        if p.videogiochi else ""
    )
    vincolo_titolo = (
        "SOLO TITOLO E SOMMARIO: di ogni notizia conosci SOLO il titolo e, "
        "quando c'e', il sommario scritti qui sopra. Se lo Short usa una "
        "notizia, puo' affermare come fatto solo cio' che titolo e sommario "
        f"dicono. Parla {p.g('del')} {s} di cui parla la notizia, non di "
        f"{p.g('un_altro')} {s} nominat{p.g('o')} solo come paragone. Come "
        "e' successo, quando, quante persone, "
        "quanto e' durato, chi ha reagito e come e' andata a finire NON li "
        "sai: non scriverli, nemmeno per rendere la storia piu' forte. Il "
        "resto dei secondi riempilo con il perche' la notizia conta per "
        f"{p.pubblico}, con quello che e' noto da sempre su {p.g('quel')} {s} "
        "e con una "
        "domanda al pubblico. Se il titolo lascia un dubbio, trasformalo in "
        "domanda invece di risolverlo inventando."
        f"{esempio_invenzione}\n"
        "MAI suggerire glitch, hack o trucchi per avere "
        f"{p.soggetto_plurale} o contenuti a "
        "pagamento senza pagare: e' contenuto ingannevole per YouTube.\n"
        if notizie else ""
    )

    # Le regole 11 e 12 compaiono solo quando c'e' davvero qualcosa da evitare:
    # al primo video della vita del canale una lista vuota sarebbe rumore che
    # occupa contesto e non dice niente.
    righe_ripetizioni = []
    if aperture_recenti:
        righe_ripetizioni.append(
            "11. NON aprire lo script come questi video recenti. Cambia proprio "
            f"le prime parole, non basta cambiare {p.g('il')} {s} "
            f"nominat{p.g('o')}:\n"
            + "\n".join(f"   - \"{a}...\"" for a in aperture_recenti)
        )
    if schemi_recenti:
        righe_ripetizioni.append(
            "12. CAMBIA LA FORMA DELL'ATTACCO, non solo le parole. Gli ultimi "
            "video hanno aperto con " + " e con ".join(schemi_recenti)
            + ". Questo Short deve attaccare in un modo diverso: un numero "
            "che stona, una scena raccontata a meta', un confronto fra due "
            "cose che non c'entrano, una contraddizione secca. Una domanda "
            "diversa resta una domanda: non basta."
        )
    if giochi_recenti or notizie_gia_usate:
        vietati = []
        if giochi_recenti:
            vietati.append(f"{p.soggetto_plurale}: "
                           f"{json.dumps(list(giochi_recenti), ensure_ascii=False)}")
        if notizie_gia_usate:
            vietati.append(f"notizie: {json.dumps(list(notizie_gia_usate), ensure_ascii=False)}")
        righe_ripetizioni.append(
            "13. NIENTE DOPPIONI: questi sono gia' usciti, scegli altro.\n   "
            + "\n   ".join(vietati)
        )
    blocco_ripetizioni = "\n".join(righe_ripetizioni)
    if blocco_ripetizioni:
        blocco_ripetizioni += "\n"   # la riga vuota prima di "Rispondi..."

    # Il campo 'gioco' ha due mestieri diversi a seconda del materiale. Con
    # Steam e' la chiave per scaricare i trailer ufficiali, quindi deve essere
    # il nome esatto dello store; con lo stock serve solo a titolo, tag e
    # hashtag, e la query video diventa l'unica cosa che decide le immagini.
    if p.usa_steam:
        regole_materiale = (
            "6. GIOCO: il titolo ESATTO e UFFICIALE del videogioco di cui parla lo "
            f"Short, come appare sullo store{_esempi(p.esempi_soggetto)}. "
            "Serve a scaricare gameplay reale di quel gioco: "
            "niente abbreviazioni, niente nomi di saghe generiche. Se lo Short non "
            "parla di un gioco specifico, metti stringa vuota.\n"
            "7. QUERY VIDEO: in INGLESE, 2-4 parole, usata solo come ripiego se il "
            f"gioco non e' reperibile{_esempi(p.esempi_query_video)}.\n"
        )
    else:
        regole_materiale = (
            f"6. GIOCO (il campo si chiama cosi' per ogni canale): il nome "
            f"{p.g('del')} {s} di cui parla lo Short, scritto come lo cerca "
            f"il pubblico{_esempi(p.esempi_soggetto)}. Finisce nel titolo, "
            "nei tag e nel primo hashtag: niente sigle inventate. Se lo "
            f"Short non parla di {p.g('un')} {s} precis{p.g('o')}, metti "
            "stringa vuota.\n"
            "7. QUERY VIDEO: in INGLESE, 2-4 parole concrete che descrivono "
            "cosa si deve VEDERE mentre la voce parla"
            f"{_esempi(p.esempi_query_video)}. Serve a cercare clip stock "
            "senza diritti: niente nomi propri, niente marchi.\n"
        )

    # Di cosa si puo' parlare senza una fonte, e a chi non si possono
    # attribuire annunci inventati.
    if p.videogiochi:
        chi_annuncia = "agli sviluppatori"
        senza_fonte = "meccaniche, segreti di gioco o consigli"
    else:
        chi_annuncia = "ai diretti interessati"
        senza_fonte = "curiosita', storia o consigli pratici"

    blocco_tg = ""
    if p.telegiornale:
        blocco_tg = (
            "STILE TELEGIORNALE (quando contraddice le regole qui sotto, vince "
            "questo):\n"
            "- Sei il conduttore di un telegiornale, non un creator: tono "
            "neutro e asciutto, niente iperboli, niente 'incredibile', "
            "'shock' o 'assurdo', niente accuse o domande provocatorie allo "
            "spettatore.\n"
            "- La prima frase e' il fatto principale della notizia, detto in "
            "modo netto e AFFERMATIVO, mai come domanda: e' quello l'hook.\n"
            "- TITOLO da telegiornale: un'affermazione, senza punto di domanda "
            "e senza emoji (per esempio 'Inter: contro il Parma mancano tre "
            "titolari').\n"
            "- Nomina a voce la testata che riporta la notizia (per esempio "
            "'Lo riporta ANSA' / 'according to Reuters').\n"
            "- POLITICA, NEUTRALITA' ASSOLUTA: nessuna opinione su partiti, "
            "politici, governi o religioni. Riferisci cosa e' successo e chi "
            "l'ha detto, con il suo ruolo ('secondo il ministro...', 'ha "
            "dichiarato la segretaria del partito...'). Ogni giudizio e' "
            "attribuito a chi lo ha espresso, mai detto con la tua voce. "
            "Niente aggettivi di valore ('storico', 'vergognoso', "
            "'disastroso'), niente previsioni, niente sondaggi presentati come "
            "risultati. In uno scontro fra due parti non dai ragione a "
            "nessuno: dici le posizioni che la fonte riporta.\n"
            "- Il loop della regola 2 non serve: chiudi con la CTA.\n"
            "- QUERY VIDEO: immagini di repertorio NEUTRE che non mostrino il "
            "fatto e non sembrino il suo filmato (per esempio 'city skyline "
            "aerial', 'newspaper printing press', 'stock market screen', "
            "'world map globe'). Mai violenza, armi, incidenti, ospedali, "
            "polizia, bandiere o persone riconoscibili.\n"
            "- Il campo 'gioco' contiene il protagonista della notizia "
            "(un'azienda, un paese, un'istituzione), mai una persona "
            "privata.\n\n"
        )

    return (
        f"Sei il Lead Social Media Manager di '{config.NOME_CANALE}', canale YouTube "
        f"{p.descrizione_canale}. Scrivi uno script per uno Short ad ALTISSIMA RETENTION "
        "(24-30 secondi, quindi 55-85 parole).\n\n"
        f"LINGUA DELL'OUTPUT: {_lingua()['nome']}. Titolo, script e "
        f"descrizione vanno scritti INTERAMENTE in {_lingua()['nome']}. "
        "Le regole qui sotto sono scritte in italiano perche' parlano a te, "
        "ma dicono come scrivere, non in che lingua.\n\n"
        f"FORMATO RICHIESTO: {formato} - {_descrizione_formato(formato)}\n"
        "(quella sigla e' un'etichetta interna: non deve comparire ne' nel "
        "titolo ne' nello script)\n\n"
        f"NOTIZIE {p.argomento.upper()} REALI DI OGGI, IN ORDINE DI IMPORTANZA "
        f"(la [0] e' quella che piu' gente sta cercando in questo momento: "
        f"scegli quella, e passa a una successiva solo se con la [0] non si "
        f"riesce a scrivere niente di sensato):\n{blocco_notizie}\n\n"
        f"{vincolo_fatti}"
        f"{vincolo_titolo}"
        f"{blocco_hook}\n"
        f"{blocco_tg}"
        "REGOLE TASSATIVE:\n"
        "1. PRIMA FRASE = HOOK. Deve bloccare lo scroll in 3 secondi. "
        "VIETATO iniziare con saluti ('Ciao', 'Raga', 'Benvenuti', 'Oggi vi parlo'). "
        "Attacca con un meccanismo forte, scegliendone uno diverso ogni volta: "
        "una contraddizione, un numero che stona, un'accusa diretta allo "
        "spettatore, una scena raccontata a meta', una domanda secca, un "
        "confronto fra due cose che non c'entrano. Cambia anche le parole, non "
        f"solo {p.g('il')} {s} nominat{p.g('o')}: due Short che aprono uguali si leggono come "
        "contenuto prodotto in serie, ed e' cosi' che un canale perde la "
        "monetizzazione.\n"
        "2. SEAMLESS LOOP: l'ultima frase deve ricollegarsi in modo naturale alla "
        "prima parola dello script, cosi' il video riparte senza stacco percepibile.\n"
        "3. RITMO: frasi corte. Una informazione per frase. Niente subordinate.\n"
        f"4. CTA fluida e breve a '{config.NOME_CANALE}', mai piu' di 6 parole, "
        "mai in apertura.\n"
        f"5. TITOLO: massimo {MAX_CARATTERI_TITOLO} caratteri (oltre viene "
        f"troncato nel feed), nome {p.g('del')} {s} come PRIMA parola, poi i due punti "
        "e l'amo. UNA sola emoji e in FONDO, mai in apertura. Niente '#Shorts'. "
        "Niente maiuscolo integrale: YouTube lo tratta come titolo spam.\n"
        f"{regole_materiale}"
        "8. DESCRIZIONE: 2 righe + UNA domanda finale che spinga a commentare.\n"
        "9. NIENTE CRONACA INVENTATA. Se non stai citando una delle notizie "
        "elencate sopra (cioe' se 'indice_notizia' non punta a una di quelle), "
        "lo script NON puo' contenere leak, date di uscita, numeri di vendite, "
        f"annunci o conferme attribuite {chi_annuncia}: sono fatti verificabili "
        f"e inventarli fa danno al canale. In quel caso parla di {senza_fonte}, "
        "che non hanno bisogno di una fonte.\n"
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


# Quanto si aspetta, al massimo, quando Groq dice di riprovare fra poco.
ATTESA_MAX_LIMITE_GROQ = 20


def _attesa_limite_groq(errore):
    """Secondi da aspettare per un 429 sui token al minuto, o None.

    Il 30 settembre 2026 l'ultimo tentativo delle 21:00 e' andato perso per
    un 429 che chiedeva di riprovare fra 1,2 secondi. Un limite giornaliero
    o un'attesa lunga invece non si aspettano: None.
    """
    testo = str(errore)
    if "429" not in testo and "rate_limit" not in testo:
        return None
    trovato = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", testo)
    if not trovato:
        return None
    minuti, valore, unita = trovato.groups()
    secondi = float(valore) / (1000 if unita == "ms" else 1) + 60 * int(minuti or 0)
    if secondi > ATTESA_MAX_LIMITE_GROQ:
        return None
    return secondi + 0.5


def _chiedi_a_groq(**parametri):
    """client.chat.completions.create, che aspetta e riprova una volta se
    Groq chiede solo qualche secondo di pazienza."""
    try:
        return client.chat.completions.create(**parametri)
    except Exception as e:
        attesa = _attesa_limite_groq(e)
        if attesa is None:
            raise
        print(f"[Samaritan Brain] Limite di Groq al minuto: aspetto "
              f"{attesa:.1f} secondi e riprovo.")
        time.sleep(attesa)
        return client.chat.completions.create(**parametri)


_SCHEMA_VERIFICA = {
    "name": "verifica_fatti",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "dettagli_inventati": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["dettagli_inventati"],
        "additionalProperties": False,
    },
}


def _dettagli_inventati(titolo_notizia, script, sommario="", testata=""):
    """I dettagli di cronaca che lo script aggiunge al titolo della notizia.

    Una seconda lettura, fatta da un modello che non ha scritto lo script e
    ha davanti solo il titolo: e' il controllo che mancava il 27 settembre
    2026, quando uno Short su GTA 6 ha raccontato un glitch e una chiusura in
    poche ore che la notizia non diceva. Le parole spia di
    `_cronaca_senza_fonte` qui non servono: il testo inventato non usava
    nessuna di quelle parole.

    Gira sull'ultimo modello dell'elenco, non sul primo: il primo e' quello
    che scrive, e il 28 settembre 2026 scrittura e verifica sullo stesso
    modello hanno sforato il limite di token al minuto di Groq.

    Lista vuota se non trova niente o se la verifica non riesce: un errore di
    Groq qui non deve costare il video.
    """
    if not titolo_notizia or not script:
        return []
    p = profilo.attivo()
    s = p.soggetto
    caratteristiche = ("(modalita', mappa, prezzo, contenuti)" if p.videogiochi
                       else "(prezzo, quantita', contenuti)")
    istruzioni = (
        f"Sei un fact-checker. Ricevi il TITOLO di una notizia {p.argomento}, a "
        "volte il suo SOMMARIO, e lo SCRIPT di uno Short che la racconta. "
        "Della notizia si conosce SOLO cio' che dicono titolo e sommario. "
        "Elenca i dettagli sull'EVENTO della notizia che lo script afferma "
        "come fatti ma che titolo e sommario non dicono, compreso "
        f"attribuire la notizia a {p.g('un')} {s} divers{p.g('o')} da "
        f"{p.g('quello')} di cui parla: "
        "come e' "
        "successo, quando, quanti, quanto e' durato, chi ha reagito, come e' "
        f"finita, citazioni, numeri, caratteristiche {p.g('del')} {s} "
        f"{caratteristiche}. NON elencare: il nome della TESTATA che "
        "ha dato la notizia (dire che l'ha scritto o contato lei e' "
        "corretto), opinioni, domande al "
        "pubblico, inviti a immaginare o a pensare ('immagina di...', "
        "'pensa se...'), inviti a iscriversi, frasi generiche su fan e community, "
        f"fatti noti da sempre {p.g('sul')} {s}, e riformulazioni o deduzioni "
        "ovvie del titolo (per esempio 'appena annunciato' per una notizia "
        "di oggi, 'enorme' o 'spettacolare' per un titolo che dice che il "
        "mondo 'looks wild'). Nel dubbio non elencare. Rispondi in JSON con "
        "la chiave 'dettagli_inventati' (una lista di frasi brevi, vuota se "
        "non c'e' niente)."
    )
    modello = config.GROQ_MODELLI[-1]
    notizia = f"TITOLO: {titolo_notizia}"
    if testata:
        notizia += f"\nTESTATA: {testata}"
    if sommario:
        notizia += f"\nSOMMARIO: {sommario}"
    # Due prove: il 28 settembre 2026 la prima e' tornata 400
    # json_validate_failed con failed_generation vuota, cioe' il
    # ragionamento aveva mangiato tutto max_tokens, e uno script gia'
    # scartato una volta per dettagli inventati e' uscito senza verifica.
    # La seconda ragiona meno e lascia piu' spazio alla risposta.
    for ragionamento in ("medium", "low"):
        try:
            risposta = _chiedi_a_groq(
                model=modello,
                messages=[
                    {"role": "system", "content": istruzioni},
                    {"role": "user", "content": f"{notizia}\n\nSCRIPT: {script}"},
                ],
                temperature=0,
                max_tokens=3000,
                response_format={"type": "json_schema",
                                 "json_schema": _SCHEMA_VERIFICA},
                **({"reasoning_effort": ragionamento} if "gpt-oss" in modello else {}),
            )
            dati = _estrai_json(risposta.choices[0].message.content)
            dettagli = dati.get("dettagli_inventati", [])
            if not isinstance(dettagli, list):
                return []
            return [str(d).strip() for d in dettagli if str(d).strip()][:4]
        except Exception as e:
            print(f"[Samaritan Brain] Verifica dei fatti non riuscita "
                  f"(ragionamento {ragionamento}): {e}")
    print("[Samaritan Brain] Verifica dei fatti non disponibile: lo script "
          "passa senza.")
    return []


def _togli_frasi_inventate(script, dettagli, notizia=""):
    """Lo script senza le frasi che contengono i dettagli inventati.

    Il 30 settembre 2026 l'uscita delle 14:00 e' saltata: sei tentativi su
    sei scartati, quasi sempre per una frase di colore ("Nessuno
    l'aspettava", "Seguici su Poppone TV") che la verifica prende per un
    fatto. Riscrivere tutto da capo rifa' lo stesso errore da un'altra parte;
    togliere le frasi indicate invece non puo' aggiungere niente di falso.

    Un "dettaglio" che sta tutto nel titolo o nel sommario della notizia non
    e' inventato (il 30 settembre la verifica ha segnalato "78", l'eta' che
    il titolo diceva): si ignora, altrimenti si toglierebbe proprio la frase
    con la notizia.

    Stringa vuota quando non si puo': un dettaglio che non corrisponde a
    nessuna frase, o piu' di meta' delle frasi da togliere. Il risultato va
    comunque ripassato da valida_script (lunghezza, apertura).
    """
    frasi = [f for f in re.split(r"(?<=[.!?…])\s+", (script or "").strip()) if f]
    if len(frasi) < 2 or not dettagli:
        return ""

    def parole(testo):
        return [w for w in re.split(r"[^0-9a-z]+", _senza_accenti(testo).lower()) if w]

    parole_notizia = set(parole(notizia))
    parole_frasi = [set(parole(f)) for f in frasi]
    compatte = [" ".join(parole(f)) for f in frasi]
    da_togliere = set()
    for dettaglio in dettagli:
        cercate = parole(dettaglio)
        if not cercate:
            return ""
        if set(cercate) <= parole_notizia:
            continue
        compatto = " ".join(cercate)
        trovata = next((i for i, c in enumerate(compatte)
                        if f" {compatto} " in f" {c} "), None)
        if trovata is None:
            # Il fact-checker a volte riassume invece di citare: basta che
            # quasi tutte le parole piene del dettaglio stiano nella frase.
            piene = [w for w in cercate if len(w) > 3]
            if len(piene) < 2:
                return ""
            quote = [len(set(piene) & pf) / len(set(piene)) for pf in parole_frasi]
            migliore = max(range(len(frasi)), key=lambda i: quote[i])
            if quote[migliore] < 0.7:
                return ""
            trovata = migliore
        da_togliere.add(trovata)
    if len(da_togliere) * 2 > len(frasi):
        return ""
    return " ".join(f for i, f in enumerate(frasi) if i not in da_togliere)


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
    tema = (tema or "").strip()
    # Le notizie scelte da lavorazioni partite insieme a questa: vedi
    # prenotazione.py.
    prenotazione.riallinea_cronologia()
    cronologia = _stesso_formato(
        _stessa_lingua([_normalizza(i) for i in carica_cronologia()])
    )
    # Il gioco si blocca solo sull'ultimo video, non su tutta la finestra:
    # vedi _doppione_recente per il perche'.
    # Un tema chiesto a mano vince: se chiede Cyberpunk subito dopo un video
    # su Cyberpunk, vuole un altro video su Cyberpunk. Il 26 settembre 2026 la
    # prova su "Cyberpunk 2077" e' stata scartata per questo ed e' uscito GTA VI.
    ultima_voce = cronologia[-1] if cronologia else {}
    gioco_precedente = "" if tema else ultima_voce.get("gioco", "")

    notizie = recupera_trend_gaming_online(tema=tema, gioco_da_evitare=gioco_precedente)
    formato = scegli_formato(notizie)
    ultimi_titoli = [v.get("titolo", "") for v in cronologia[-12:]]

    # Due liste dalla stessa fonte: al modello servono aperture leggibili da
    # evitare, alla validazione serve l'impronta di tre parole da confrontare.
    recenti = [_normalizza(i) for i in cronologia[-MEMORIA_RIPETIZIONI:]]
    estratti = [r.get("estratto_script", "") for r in recenti]
    aperture_da_mostrare = [" ".join(e.split()[:8]) for e in estratti if e.strip()]
    impronte_aperture = {_impronta_apertura(e) for e in estratti}
    impronte_aperture.discard("")

    # La forma dell'attacco si guarda su una finestra piu' corta delle parole:
    # vedi MEMORIA_SCHEMI.
    schemi_recenti = {_schema_apertura(e) for e in estratti[-MEMORIA_SCHEMI:]}
    schemi_recenti.discard("")
    schemi_recenti = sorted(schemi_recenti)

    notizie_gia_usate = sorted({r.get("fonte", "").strip() for r in recenti} - {""})
    fonti_recenti = {f.lower() for f in notizie_gia_usate}

    giochi_recenti = [gioco_precedente] if gioco_precedente.strip() else []

    # Le notizie sul gioco del video precedente vanno in fondo alla lista.
    # Il prompt dice di scegliere la [0], la regola dei doppioni la scarta:
    # il 28 settembre 2026 la [0] era su GTA 6 dopo un video su GTA VI, e le
    # uscite delle 14:00 e delle 18:00 sono saltate con tre tentativi su
    # quattro bruciati cosi'. L'ordine resta stabile per tutto il resto.
    # Il 29 settembre 2026 non e' bastato: il modello andava a prendersi la
    # notizia su GTA 6 anche in fondo alla lista, e l'uscita delle 18:00 e'
    # saltata due volte. Se resta almeno una notizia su un altro gioco,
    # quelle sul gioco precedente si tolgono.
    if gioco_precedente.strip():
        altre = [n for n in notizie
                 if not _gioco_nel_titolo(n["titolo"], gioco_precedente)]
        if len(altre) >= MIN_NOTIZIE_ALTRO_GIOCO:
            notizie = altre
        else:
            notizie = sorted(
                notizie, key=lambda n: _gioco_nel_titolo(n["titolo"], gioco_precedente))

    try:
        from analyst import migliori_hook
        hook_vincenti = migliori_hook(n=3)
    except Exception:
        hook_vincenti = []

    system_prompt = _costruisci_system_prompt(
        formato, notizie, ultimi_titoli, hook_vincenti,
        aperture_da_mostrare, giochi_recenti, notizie_gia_usate,
        schemi_recenti
    )
    prompt_base = "Scrivi lo Short di oggi."
    if tema:
        prompt_base += (
            f" Il proprietario del canale ha chiesto un video su questo "
            f"argomento, ed e' obbligatorio: {tema}. Se tra le notizie ce n'e' "
            f"una su questo argomento, usa quella."
        )

    # Motivo dell'ultimo scarto: senza questo ogni tentativo riparte dallo
    # stesso identico input e rifa' un tiro di dado. Dicendo al modello cosa
    # non e' andato, i tentativi diventano correzioni.
    motivo_scarto = ""
    # Le notizie su cui lo script ha inventato dettagli due volte (una, se
    # la notizia non ha sommario). Il 29
    # settembre 2026 una rassegna ("GTA VI, tutte le novita' che ridefiniscono
    # la serie") ha fatto inventare funzioni del gioco a tutti e quattro i
    # tentativi e l'uscita e' saltata: su una notizia cosi' il modello non
    # smette di riempire, conviene cambiarla.
    invenzioni_per_notizia = {}
    notizie_vietate = set()

    modelli = config.GROQ_MODELLI
    # Quante volte uno script e' stato scartato per la forma dell'apertura.
    # Il 29 settembre 2026 l'uscita delle 20:00 e' saltata con tre tentativi
    # su quattro scartati perche' aprivano con una domanda come i video
    # recenti: il modello non riesce a uscirne, e un'apertura gia' vista vale
    # piu' di un buco. Dopo due scarti cosi' la regola si spegne.
    scarti_per_schema = 0

    for n_modello, modello in enumerate(modelli):
        for tentativo in range(1, TENTATIVI_PER_MODELLO + 1):
            # Sull'ultimo tentativo le regole anti-ripetizione si spengono.
            # Dicono che un video somiglia a quello di ieri, non che e'
            # sbagliato, e un video che apre come quello di ieri vale
            # comunque piu' di un buco nella pubblicazione. Il 20 settembre
            # 2026 l'uscita delle 18:00 e' saltata proprio cosi': tre
            # tentativi bruciati da un titolo che non passava, il quarto
            # scartato per la forma dell'apertura.
            ultima_spiaggia = (n_modello == len(modelli) - 1
                               and tentativo == TENTATIVI_PER_MODELLO)
            try:
                # Primo tentativo con lo schema vincolato, secondo in testo
                # libero ritagliando il JSON: cosi' anche un modello che non
                # supporta lo schema riesce comunque a rispondere.
                con_schema = tentativo % 2 == 1
                prompt_utente = prompt_base
                if motivo_scarto:
                    prompt_utente += (
                        f" Il tentativo precedente e' stato scartato perche' "
                        f"{motivo_scarto}. Correggi quel punto."
                    )
                if notizie_vietate:
                    elenco = ", ".join(f"[{i}]" for i in sorted(notizie_vietate))
                    prompt_utente += (
                        f" Non usare le notizie {elenco}: scegline un'altra "
                        f"dall'elenco."
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

                response = _chiedi_a_groq(**parametri)
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

                ok, motivo = valida_script(
                    titolo, script,
                    () if ultima_spiaggia else impronte_aperture,
                    () if ultima_spiaggia or scarti_per_schema >= 2
                    else schemi_recenti,
                )
                if not ok and motivo.startswith("apre con ") \
                        and motivo.endswith(", come i video recenti"):
                    scarti_per_schema += 1
                if ok:
                    ok, motivo = valida_titolo(titolo, gioco)
                if ok and fonte and idx in notizie_vietate:
                    ok = False
                    motivo = (f"usa la notizia [{idx}], che non si puo' piu' "
                              f"usare. Scegline un'altra")
                if ok and profilo.attivo().telegiornale:
                    motivo = _fuori_stile_tg(titolo, script)
                    ok = not motivo
                if ok and profilo.attivo().telegiornale and not fonte:
                    ok = False
                    motivo = ("non racconta nessuna delle notizie elencate, e "
                              "un telegiornale racconta solo quelle: metti in "
                              "'indice_notizia' la notizia usata")
                if ok and _cronaca_senza_fonte(script, fonte):
                    ok = False
                    motivo = "afferma fatti di cronaca senza citare una notizia"
                # Vale anche all'ultimo tentativo, a differenza delle regole
                # anti-ripetizione: nella prova del 28 settembre 2026, con la
                # verifica spenta sull'ultimo tentativo, e' passato uno Short
                # su "GTA 6" nato da una notizia su un altro gioco. Un video
                # saltato lo recupera la riserva, una notizia falsa resta.
                if ok and fonte:
                    inventati = _dettagli_inventati(
                        notizie[idx]["titolo"], script,
                        notizie[idx].get("sommario", ""),
                        notizie[idx].get("fonte", ""))
                    ripulito = _togli_frasi_inventate(
                        script, inventati,
                        notizie[idx]["titolo"] + " "
                        + notizie[idx].get("sommario", "")) if inventati else ""
                    if ripulito and valida_script(
                            titolo, ripulito,
                            () if ultima_spiaggia else impronte_aperture,
                            () if ultima_spiaggia or scarti_per_schema >= 2
                            else schemi_recenti)[0]:
                        if ripulito == script:
                            print("[Samaritan Brain] La verifica segnala solo "
                                  "cose che la notizia dice gia' ("
                                  + "; ".join(inventati) + "): lo script va bene.")
                        else:
                            print("[Samaritan Brain] Tolte dallo script le frasi "
                                  "con dettagli che la notizia non dice ("
                                  + "; ".join(inventati) + ").")
                        script = ripulito
                        inventati = []
                    if inventati:
                        print("[Samaritan Brain] Le frasi segnalate non si "
                              "possono togliere senza rovinare lo script: "
                              "riscrivo.")
                        ok = False
                        invenzioni_per_notizia[idx] = invenzioni_per_notizia.get(idx, 0) + 1
                        # Una notizia senza sommario si cambia alla prima
                        # invenzione: il 1 ottobre 2026 un titolo sull'update
                        # di No Man's Sky ("critical bugs fixed and game
                        # optimized for PlayStation 5") ha fatto inventare
                        # dettagli della patch a cinque tentativi su due
                        # lavorazioni, e l'uscita delle 21:00 e' saltata. Col
                        # solo titolo il modello non ha altro con cui riempire.
                        if invenzioni_per_notizia[idx] >= (
                                2 if notizie[idx].get("sommario") else 1):
                            notizie_vietate.add(idx)
                        motivo = ("aggiunge alla notizia dettagli che il titolo "
                                  "non dice (" + "; ".join(inventati) + "). "
                                  "Racconta solo quello che dice il titolo")
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

                query_video = completa_query_video(query_video)

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
                prenotazione.prenota(titolo)
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
    if motivo_scarto:
        raise RuntimeError(
            "Tutti i tentativi sono stati scartati, l'ultimo perche' "
            f"{motivo_scarto}. Salto il video: lo recupera la riserva.")
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
