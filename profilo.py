# -*- coding: utf-8 -*-
"""
Il profilo del canale: come si chiama, di cosa parla, dove cerca le notizie,
che tag e hashtag usa e da dove prende il materiale video.

Samaritan e' nato per Poppone TV, un canale italiano di videogiochi, e per
mesi tutto questo stava scritto dentro il codice. Qui sotto, in PREDEFINITO,
c'e' esattamente quello che il codice faceva prima che il profilo esistesse:
senza `canale.json` il canale di popponetv non cambia di una virgola.

Un altro canale (cucina, calcio, motori...) scrive `canale.json` nella radice
del progetto, oppure indica un altro percorso con la variabile d'ambiente
PROFILO_CANALE. Il file d'esempio completo, con ogni campo spiegato, e'
`canale.esempio.json`.

Due regole che il profilo non puo' cambiare:
  - il materiale video e' SOLO ufficiale dell'editore (Steam, e solo per i
    videogiochi) o stock senza diritti (Pexels) o girato dal proprietario del
    canale. I video degli altri non si usano mai, per nessun argomento;
  - le chiavi interne restano quelle di sempre ('gioco' nella risposta del
    modello e in cronologia): per un canale di cucina 'gioco' contiene il
    nome della ricetta. Cambiarle vorrebbe dire buttare la cronologia.

Questo modulo non importa config ne' nient'altro del progetto: config lo
importa per il nome del canale, e un giro di import li bloccherebbe entrambi.
Per lo stesso motivo usa solo la libreria standard: il workflow lo lancia da
solo (`python3 profilo.py decidi`) per sapere in pochi secondi se una
partenza notturna ha un'uscita da coprire, prima di installare qualunque cosa.
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from itertools import permutations
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Dove si cerca il profilo se PROFILO_CANALE non dice altro.
FILE_PREDEFINITO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "canale.json")
# Quello che Samaritan ha scritto da solo per un canale con 'autodefinisci':
# sta accanto a canale.json e lo scrive autoprofilo.py. E' memoria del
# canale come cronologia_trend.json, e il workflow lo salva con lei.
NOME_FILE_AUTO = "canale_auto.json"

# Le lingue che brain.LINGUE sa gestire. Sono ripetute qui invece di
# importare brain, che si porta dietro Groq: un test controlla che i due
# elenchi restino uguali.
LINGUE = ("it", "en")

# I formati di brain.FORMATI_VIDEO, piu' il video lungo. Stesso discorso: un
# test controlla che coincidano.
FORMATI = (
    "VIRAL_HOOK_NEWS", "MYTH_BUSTING_VIRAL", "EASTER_EGG_SECRET",
    "SEAMLESS_LOOP_FACTS", "DONT_DO_THIS", "TIER_LIST_LAMPO",
    "DOMANDA_AL_PUBBLICO",
)
FORMATI_CON_LUNGO = FORMATI + ("VIDEO_LUNGO",)

MATERIALI = ("steam", "stock")

# Le quattro partenze notturne del workflow (samaritan.yml), in UTC, come
# (ora, minuto). Sono fisse perche' un cron di GitHub si cambia solo toccando
# il workflow, e chi installa Samaritan il workflow non lo tocca: le uscite
# del profilo si abbinano a queste (vedi abbina_cron). Un test controlla che
# il workflow dica la stessa cosa.
CRON_USCITE = ((1, 17), (3, 17), (5, 17), (6, 17))

# Quanto prima della sua uscita deve partire la lavorazione, al minimo e al
# massimo. Il minimo e' il ritardo peggiore visto su GitHub (sei-otto ore il
# 28 settembre 2026): con meno margine una partenza in ritardo pubblica tardi.
# Il massimo non e' una scelta: oltre, orari._occorrenza_da_coprire crede che
# la lavorazione stia coprendo l'uscita di IERI, la trova gia' fatta e si
# ferma senza pubblicare niente (vedi orari.ANTICIPO_PARTENZA_ORE).
MARGINE_MINIMO_ORE = 8
ANTICIPO_PARTENZA_ORE = 16

MAX_USCITE = len(CRON_USCITE)
_RE_ORARIO = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# L'argomento che eredita i valori di Poppone TV. Un profilo con un altro
# argomento NON eredita ricerche, tag e hashtag di gaming: un canale di
# cucina che si dimentica 'ricerche' non deve finire a cercare GTA 6.
ARGOMENTO_GAMING = "gaming"


# ===========================================================================
# IL PROFILO DI POPPONE TV (= il comportamento di sempre)
# ===========================================================================
PREDEFINITO = {
    # Il 9 ottobre 2026 popponetv ha rinominato il canale "Davide Durazzi" e
    # ha chiesto di mandare chi guarda anche sul suo sito. Lo stesso giorno
    # ha cambiato anche l'handle.
    "nome_canale": "Davide Durazzi",
    "handle": "@davidedurazzi",
    # Sito del canale: finisce nella descrizione di ogni video, subito sotto
    # le prime righe. Vuoto = nessuna riga.
    "sito": "davidedurazzi.it",

    # Come si dice l'argomento DOPO un nome: "notizie gaming", "Altri
    # Shorts gaming ogni giorno". Per la cucina sarebbe "di cucina".
    "argomento": ARGOMENTO_GAMING,
    # L'argomento come nome, dopo "di": "canale YouTube di videogiochi".
    "descrizione_argomento": "videogiochi",
    # Dopo "canale YouTube", nella prima riga del prompt dello Short.
    "descrizione_canale": "Gaming italiano",

    # Di cosa parla ogni singolo video. Nella risposta del modello finisce
    # sempre nella chiave 'gioco' (vedi la nota in cima al file).
    "soggetto": "gioco",
    "soggetto_plurale": "giochi",
    "genere": "m",
    # "il perche' la notizia conta per chi gioca"
    "pubblico": "chi gioca",
    "esempi_soggetto": ["Cyberpunk 2077", "ELDEN RING", "Counter-Strike 2"],
    "esempi_query_video": ["cyberpunk gameplay", "fps shooter action"],

    # Dove cercare le notizie. Prima ce n'era una sola, e per giunta stretta
    # ("quando esce aggiornamento"), quindi il pescato era fatto soprattutto
    # di aggiornamenti minori. I video che su questo canale hanno fatto numeri
    # erano invece notizie enormi del giorno: GTA 6, Sora in Fortnite,
    # Fortnite x Kingdom Hearts. Piu' reti in acqua, e poi si sceglie (vedi
    # brain._punteggio_notizia): l'argomento e' l'unica variabile che separa i
    # video andati bene da quelli morti.
    "ricerche": {
        "it": [
            "videogiochi",
            "videogiochi quando esce aggiornamento",
            'GTA 6 OR Fortnite OR "Call of Duty" OR Minecraft OR Roblox',
            'Pokemon OR Zelda OR Mario OR "Elden Ring" OR "EA FC" OR "Brawl Stars"',
            "videogioco annuncio OR uscita OR gratis OR leak",
        ],
        "en": [
            "video games",
            "video game release date OR free OR leak",
            'GTA 6 OR Fortnite OR "Call of Duty" OR Minecraft OR Roblox',
            'Pokemon OR Zelda OR Mario OR "Elden Ring" OR "EA FC" OR "Brawl Stars"',
            "gaming news announcement OR update",
        ],
    },
    # Vuoto = le parole calde di brain.LINGUE, che sono parole da notizia
    # ("annunciato", "rinviato", "record") e valgono per quasi ogni argomento.
    "parole_calde": {},

    # I giochi e le piattaforme che muovono pubblico da soli. E' una lista
    # scritta a mano e va tenuta aggiornata: non esiste un modo di dedurla dai
    # feed, e sbagliarla per difetto costa poco (la notizia resta in lista,
    # solo piu' in basso) mentre un elenco automatico sbagliato per eccesso
    # spingerebbe in cima la roba sbagliata.
    "nomi_grossi": [
        "gta", "grand theft auto", "rockstar", "fortnite", "call of duty",
        "warzone", "minecraft", "roblox", "ea fc", "fifa", "elden ring",
        "zelda", "mario", "pokemon", "the last of us", "god of war",
        "cyberpunk", "assassin", "red dead", "valorant", "league of legends",
        "counter-strike", "counter strike", "overwatch", "apex legends",
        "battlefield", "silksong", "hollow knight", "playstation",
        "xbox", "nintendo switch", "game pass", "brawl stars",
        "clash royale", "clash of clans", "genshin", "marvel rivals",
        "resident evil", "skyrim", "elder scrolls", "sonic", "ea sports fc",
        "nba 2k", "switch 2", "ps5", "ps6",
    ],

    # Vero = si parla SOLO delle notizie che nominano uno dei nomi grossi qui
    # sopra, e le altre si scartano invece di finire solo piu' in basso. Sui
    # numeri di Poppone TV 10 video su 104 facevano l'85% delle
    # visualizzazioni, ed erano tutti su giochi enormi (GTA 6, Fortnite): un
    # video su un gioco piccolo e' un'uscita sprecata. Deciso con popponetv
    # il 5 ottobre 2026. Se i nomi grossi trovano meno di
    # brain.MIN_NOTIZIE_GROSSE notizie si tengono tutte: un video su un gioco
    # piccolo costa meno di un'uscita saltata.
    "solo_nomi_grossi": True,

    # Tag presenti su ogni video. Da soli pesano poco sul ranking, ma cinque
    # tag IDENTICI su ogni upload sono una delle impronte che fanno
    # riconoscere un canale automatizzato: per questo brain.costruisci_tag()
    # ne aggiunge di variabili.
    "tag_fissi": ["gaming ita", "videogiochi", "shorts ita", "curiosita gaming"],
    # Sul video lungo 'shorts ita' e' un tag sbagliato, e i due che lo
    # sostituiscono dicono a YouTube di che tipo di video si tratta.
    "tag_fissi_lungo": ["gaming ita", "videogiochi", "recensione", "guida gaming"],

    # L'ultimo hashtag di ogni descrizione, senza '#'.
    "hashtag_canale": "gamingita",
    # Tema in hashtag per ogni formato: il primo hashtag della descrizione e'
    # l'unico che YouTube mostra sopra al titolo, quindi non va sprecato.
    "hashtag_formato": {
        "VIDEO_LUNGO": "gamingita",
        "VIRAL_HOOK_NEWS": "newsgaming",
        "MYTH_BUSTING_VIRAL": "rumor",
        "EASTER_EGG_SECRET": "easteregg",
        "SEAMLESS_LOOP_FACTS": "curiosita",
        "DONT_DO_THIS": "consigli",
        "TIER_LIST_LAMPO": "tierlist",
        "DOMANDA_AL_PUBBLICO": "gamingita",
    },
    # Descrizioni dei formati da mettere al posto di quelle di
    # brain.FORMATI_VIDEO. Vuoto = quelle, scritte per i videogiochi.
    "formati": {},

    # 'steam' = trailer e screenshot ufficiali dell'editore (gameplay.py),
    # ripiego su Pexels. 'stock' = solo Pexels, cercato con la query del
    # modello.
    "materiale": "steam",
    # Ricerche Pexels di riserva quando quella del modello trova troppo poco.
    "query_stock_riserva": [
        "video game action",
        "fps shooter gameplay",
        "esports tournament",
        "racing game",
        "arcade neon gaming",
        "gamer playing console",
    ],
    # Categoria YouTube dell'upload: 20 = Gaming.
    "categoria_youtube": "20",

    # Le uscite della giornata: a che ora, ora locale del fuso qui sotto, e
    # in che lingua. Per Poppone TV dal 5 ottobre 2026 uno Short italiano e
    # tre inglesi: il pubblico inglese e' molto piu' grande e il primo Short
    # inglese su GTA 6 ha battuto qualunque italiano (deciso con popponetv,
    # "dobbiamo accelerare la crescita"). Le 18:00 italiane sono le 12:00 a
    # New York. Prima c'erano due italiani e, dal 27 settembre, due inglesi
    # (alle 20:00 usciva il video lungo, che resta lanciabile solo a mano).
    # Da una a quattro, una per partenza notturna.
    "uscite": [
        {"orario": "14:00", "lingua": "it"},
        {"orario": "18:00", "lingua": "en"},
        {"orario": "20:00", "lingua": "en"},
        {"orario": "21:00", "lingua": "en"},
    ],
    "fuso": "Europe/Rome",

    # Il canale e' un telegiornale: solo notizie vere con la fonte, tono da
    # conduttore, fonte e "immagini di repertorio" scritte a schermo, e le
    # notizie su morti, crimini e tragedie scartate prima di arrivare al
    # modello (vedi TEMI_DELICATI). Poppone TV non lo e'.
    "telegiornale": False,
    # Parole che, nel titolo o nel sommario di una notizia, la tolgono di
    # mezzo, per lingua. Vuoto = nessun filtro; un telegiornale che non le
    # scrive riceve TEMI_DELICATI.
    "temi_esclusi": {},

    # Samaritan si scrive da solo i campi che mancano (soggetto, ricerche,
    # clip di riserva, nomi grossi, tag...) partendo dal solo argomento, e li
    # rivede ogni tanto sui numeri veri del canale: vedi autoprofilo.py. I
    # campi scritti a mano in canale.json vincono sempre.
    "autodefinisci": False,
}

# Gli argomenti che YouTube non monetizza o non ammette proprio: contenuti
# sessuali, gioco d'azzardo, droghe, armi, pirateria, truffe, disinformazione
# medica. Fuori apposta le parole con un senso innocuo frequente ("hot dog",
# "Top Gun", "Guns N' Roses", "Arma dei Carabinieri", "lotto di produzione").
# Un canale su uno di questi non si installa: la pagina lo rifiuta,
# profilo.py pure, e per un argomento libero anche il modello deve dire che
# e' ammesso (autoprofilo.py). Parole intere, senza accenti, in minuscolo.
ARGOMENTI_VIETATI = (
    "porno", "porn", "pornografia", "sesso", "sex", "sexy", "erotico",
    "erotica", "erotic", "nudo", "nuda", "nudi", "nude", "nudes",
    "escort", "onlyfans", "fetish", "feticismo", "hentai", "xxx",
    "per adulti", "camgirl",
    "scommesse", "betting", "casino", "casinos", "gambling",
    "gioco d azzardo", "azzardo", "slot machine", "poker",
    "droga", "droghe", "drugs", "drug", "cannabis", "marijuana", "weed",
    "cocaina", "cocaine",
    "armi", "weapons", "esplosivi", "explosives",
    "hacking", "hacker", "crack", "cracked", "pirateria", "piracy",
    "pirata", "streaming gratis", "film gratis", "iptv",
    "truffa", "truffe", "scam", "soldi facili", "easy money",
    "schema ponzi", "complotti", "complotto", "conspiracy", "no vax",
    "novax", "cure miracolose", "miracle cure",
)

# Le notizie che un telegiornale automatico non racconta. Non per pudore: su
# morti, crimini, guerre e tragedie YouTube toglie quasi sempre la pubblicita'
# (l'icona gialla), un errore diventa un avvertimento sul canale, e una clip
# stock montata sotto una strage sembra il filmato della strage, cioe'
# contenuto ingannevole. Si confrontano parole intere, senza accenti e in
# minuscolo: "morti" prende "5 morti", non "mortificato". Le parole sono
# scelte a mano, lasciando fuori quelle usate spesso in senso figurato
# ("notizia bomba", "crash di Borsa", "attacca l'avversario"): una che manca
# lascia passare una notizia, una di troppo ne scarta una buona, e una
# notizia buona in piu' c'e' sempre.
TEMI_DELICATI = {
    "it": [
        "morto", "morta", "morti", "morte", "muore", "muoiono", "morire",
        "ucciso", "uccisa", "uccisi", "uccide", "omicidio", "omicida",
        "femminicidio", "strage", "vittima", "vittime", "cadavere", "corpo senza vita",
        "suicidio", "suicida", "stupro", "violenza sessuale",
        "pedofilia", "accoltellato", "accoltellata", "sparatoria", "spari",
        "attentato", "terrorismo", "terrorista", "esplosione",
        "guerra", "bombardamento", "raid", "missili", "ostaggi",
        "incidente mortale", "schianto", "tragedia", "lutto",
        "funerale", "annegato", "annegata", "terremoto", "alluvione",
        "overdose", "rapina", "sequestro", "arrestato", "arrestata",
    ],
    "en": [
        "dead", "dies", "died", "death", "deaths", "killed", "killing",
        "kills", "murder", "murdered", "homicide", "massacre", "victim",
        "victims", "body found", "suicide", "rape", "sexual assault",
        "stabbed", "stabbing", "shooting", "gunman", "terror attack",
        "terror", "terrorist", "bomb", "explosion", "war", "airstrike",
        "missile", "missiles", "hostage", "hostages", "fatal",
        "tragedy", "funeral", "drowned", "earthquake", "flood", "overdose",
        "robbery", "kidnapped", "arrested",
    ],
}

# Campi che un profilo non-gaming ricava dagli altri se il file non li dice.
# Vedi _ricava.
_RICAVATI = (
    "descrizione_argomento", "descrizione_canale", "soggetto_plurale",
    "genere", "pubblico", "tag_fissi", "tag_fissi_lungo", "hashtag_canale",
    "hashtag_formato", "formati", "uscite", "temi_esclusi",
)

# Campi che un profilo non-gaming DEVE scrivere: non c'e' un valore neutro
# che abbia senso. Tutti gli altri hanno un ripiego.
_OBBLIGATORI_FUORI_DAL_GAMING = ("soggetto", "ricerche")

# I ripieghi neutri per un profilo che non parla di videogiochi.
_NEUTRO = {
    "esempi_soggetto": [],
    "esempi_query_video": [],
    "parole_calde": {},
    "nomi_grossi": [],
    "materiale": "stock",
    # In inglese perche' Pexels cerca meglio in inglese. Servono solo quando
    # la query del modello trova meno clip del minimo.
    "query_stock_riserva": [
        "people talking close up",
        "city life timelapse",
        "hands working close up",
        "abstract colorful background",
    ],
    # 22 = Persone e blog, la categoria generica di YouTube.
    "categoria_youtube": "22",
    "fuso": "Europe/Rome",
    "telegiornale": False,
    "temi_esclusi": {},
    "autodefinisci": False,
    "solo_nomi_grossi": False,
    "sito": "",
}

# Articoli e desinenze per i due generi. Servono perche' i prompt parlano
# del soggetto ("del gioco", "della ricetta", "un altro gioco", "un'altra
# ricetta"). Coprono i nomi che vogliono 'il' e 'la': per un nome che vuole
# 'lo' o l'apostrofo conviene scegliere un sinonimo.
_GRAMMATICA = {
    "m": {"il": "il", "del": "del", "sul": "sul", "un": "un",
          "un_altro": "un altro", "quel": "quel", "questo": "questo",
          "quello": "quello", "un_solo": "UN SOLO", "o": "o", "i": "i",
          "questi": "questi"},
    "f": {"il": "la", "del": "della", "sul": "sulla", "un": "una",
          "un_altro": "un'altra", "quel": "quella", "questo": "questa",
          "quello": "quella", "un_solo": "UNA SOLA", "o": "a", "i": "e",
          "questi": "queste"},
}


class ProfiloNonValido(ValueError):
    """Il file del profilo c'e' ma non si puo' usare. Il messaggio dice perche'."""


class Profilo:
    """I valori del profilo come attributi, piu' due aiuti per i prompt."""

    def __init__(self, dati, origine="predefinito"):
        self.__dict__.update(dati)
        self.origine = origine

    @property
    def videogiochi(self):
        """Vero per un canale di videogiochi: i prompt usano le frasi di sempre."""
        return self.argomento.strip().lower() == ARGOMENTO_GAMING

    @property
    def usa_steam(self):
        return self.materiale == "steam"

    @property
    def uscite_in_ordine(self):
        """Le uscite dalla prima della giornata all'ultima."""
        return sorted(self.uscite, key=lambda u: u["orario"])

    def g(self, parola):
        """La parola accordata al genere del soggetto: g('del') -> 'della'."""
        return _GRAMMATICA[self.genere][parola]

    def ricerche_per(self, lingua):
        """Le ricerche di notizie in quella lingua.

        Se il profilo non ne ha per quella lingua si usano quelle italiane, o
        le prime scritte: e' lo stesso ripiego di brain._lingua() per una
        lingua sconosciuta, e cercare nella lingua sbagliata costa meno che
        non cercare affatto.
        """
        if lingua in self.ricerche:
            return tuple(self.ricerche[lingua])
        if "it" in self.ricerche:
            return tuple(self.ricerche["it"])
        return tuple(next(iter(self.ricerche.values())))

    def temi_esclusi_per(self, lingua):
        """Le parole che scartano una notizia in quella lingua, o ()."""
        return tuple(self.temi_esclusi.get(lingua) or ())

    def parole_calde_per(self, lingua):
        """Le parole calde del profilo in quella lingua, o () se non ne ha."""
        return tuple(self.parole_calde.get(lingua) or ())

    @staticmethod
    def elenco(voci):
        """"'a', 'b'" per gli esempi dentro un prompt."""
        return ", ".join(f"'{v}'" for v in voci)


# ===========================================================================
# CARICAMENTO E VALIDAZIONE
# ===========================================================================
def _parole_di(testo):
    """' parola parola ' senza accenti e punteggiatura, per cercare parole intere."""
    scomposto = unicodedata.normalize("NFKD", testo or "")
    pulito = "".join(c for c in scomposto if not unicodedata.combining(c)).lower()
    return " " + " ".join(re.split(r"[^\w]+", pulito)).strip() + " "


def argomento_vietato(testo):
    """La prima parola di ARGOMENTI_VIETATI che compare nel testo, o ''."""
    parole = _parole_di(testo)
    for vietato in ARGOMENTI_VIETATI:
        if _parole_di(vietato) in parole:
            return vietato
    return ""


def _errore(origine, testo):
    return ProfiloNonValido(f"Profilo del canale non valido ({origine}): {testo}")


def _plurale(parola):
    """Il plurale di un nome italiano regolare di una parola sola, o ''."""
    p = parola.strip()
    if not p or " " in p:
        return ""
    for singolare, plurale in (("ca", "che"), ("ga", "ghe"), ("co", "chi"),
                               ("go", "ghi"), ("a", "e"), ("o", "i"),
                               ("e", "i")):
        if p.endswith(singolare):
            return p[:-len(singolare)] + plurale
    return p                                   # 'film', 'sport': invariabili


def _ricava(dati, dal_file):
    """Riempie i campi ricavabili di un profilo non-gaming non scritti nel file."""
    argomento = dati["argomento"].strip()
    if "descrizione_argomento" not in dal_file:
        dati["descrizione_argomento"] = (argomento[3:] if argomento.lower().startswith("di ")
                                         else argomento)
    descrizione = dati["descrizione_argomento"]
    if "descrizione_canale" not in dal_file:
        dati["descrizione_canale"] = f"{argomento} italiano"
    if "soggetto_plurale" not in dal_file:
        dati["soggetto_plurale"] = _plurale(dati["soggetto"])
    if "genere" not in dal_file:
        dati["genere"] = "f" if dati["soggetto"].strip().lower().endswith("a") else "m"
    if "pubblico" not in dal_file:
        dati["pubblico"] = f"gli appassionati di {descrizione}"
    if "tag_fissi" not in dal_file:
        dati["tag_fissi"] = [descrizione, "shorts ita"]
    if "tag_fissi_lungo" not in dal_file:
        dati["tag_fissi_lungo"] = [descrizione]
    if "hashtag_canale" not in dal_file:
        dati["hashtag_canale"] = descrizione
    canale = dati["hashtag_canale"]
    if "uscite" not in dal_file:
        # Due Short al giorno nella lingua delle ricerche: le due uscite
        # inglesi di Poppone TV sono un esperimento suo, non un default.
        ricerche = dati.get("ricerche") if isinstance(dati.get("ricerche"), dict) else {}
        lingua = "it" if "it" in ricerche or not ricerche else next(iter(ricerche))
        dati["uscite"] = [{"orario": "14:00", "lingua": lingua},
                          {"orario": "18:00", "lingua": lingua}]

    if "temi_esclusi" not in dal_file and dati.get("telegiornale") is True:
        dati["temi_esclusi"] = json.loads(json.dumps(TEMI_DELICATI))

    # I temi per formato e le descrizioni dei formati: si parte da quelli
    # neutri e il file puo' cambiarne anche uno solo.
    temi = {
        "VIDEO_LUNGO": canale, "VIRAL_HOOK_NEWS": "notizie",
        "MYTH_BUSTING_VIRAL": "rumor", "EASTER_EGG_SECRET": "segreti",
        "SEAMLESS_LOOP_FACTS": "curiosita", "DONT_DO_THIS": "consigli",
        "TIER_LIST_LAMPO": "classifica", "DOMANDA_AL_PUBBLICO": canale,
    }
    temi.update(dal_file.get("hashtag_formato") or {})
    dati["hashtag_formato"] = temi

    if dati.get("genere") in _GRAMMATICA:
        gr = _GRAMMATICA[dati["genere"]]
        soggetto = dati["soggetto"]
        formati = {
            "EASTER_EGG_SECRET": ("Un segreto storico e verificabile che "
                                  "pochi conoscono"),
            "DONT_DO_THIS": (f"Errore concreto da evitare con {gr['un']} "
                             f"{soggetto} popolare"),
            "DOMANDA_AL_PUBBLICO": (f"Dilemma {argomento} che costringe lo "
                                    "spettatore a commentare la sua risposta"),
        }
        formati.update(dal_file.get("formati") or {})
        dati["formati"] = formati


def _controlla_testo(origine, dati, chiave, vuoto_ammesso=False):
    valore = dati.get(chiave)
    if not isinstance(valore, str) or (not vuoto_ammesso and not valore.strip()):
        raise _errore(origine, f"'{chiave}' deve essere un testo non vuoto.")


def _controlla_lista(origine, dati, chiave, vuota_ammessa=False, nome=None):
    """'nome' e' come chiamare il campo nel messaggio, se non e' la chiave:
    per le ricerche italiane e' "'ricerche' -> 'it'"."""
    valore = dati.get(chiave)
    nome = nome or f"'{chiave}'"
    if (not isinstance(valore, list)
            or not all(isinstance(v, str) and v.strip() for v in valore)):
        raise _errore(origine, f"{nome} deve essere una lista di testi "
                               f"non vuoti.")
    if not valore and not vuota_ammessa:
        raise _errore(origine, f"{nome} non puo' essere una lista vuota.")


def _controlla_per_lingua(origine, dati, chiave, vuoto_ammesso):
    valore = dati.get(chiave)
    if not isinstance(valore, dict):
        raise _errore(origine, f"'{chiave}' deve essere un oggetto con una "
                               f"lista per lingua, per esempio "
                               f'{{"it": ["..."]}}.')
    if not valore and not vuoto_ammesso:
        raise _errore(origine, f"'{chiave}' deve avere almeno una lingua "
                               f"({', '.join(LINGUE)}).")
    for lingua, voci in valore.items():
        if lingua not in LINGUE:
            raise _errore(origine, f"in '{chiave}' la lingua '{lingua}' non "
                                   f"e' gestita: si usa {' o '.join(LINGUE)}.")
        _controlla_lista(origine, valore, lingua,
                         nome=f"'{chiave}' -> '{lingua}'")


def _controlla_per_formato(origine, dati, chiave):
    valore = dati.get(chiave)
    if not isinstance(valore, dict):
        raise _errore(origine, f"'{chiave}' deve essere un oggetto formato -> testo.")
    for formato, testo in valore.items():
        if formato not in FORMATI_CON_LUNGO:
            raise _errore(origine, f"in '{chiave}' il formato '{formato}' non "
                                   f"esiste. Formati: {', '.join(FORMATI_CON_LUNGO)}.")
        if not isinstance(testo, str) or not testo.strip():
            raise _errore(origine, f"in '{chiave}' il formato '{formato}' ha "
                                   f"un testo vuoto.")


def _valida(dati, origine):
    for chiave in ("nome_canale", "handle", "argomento", "descrizione_argomento",
                   "descrizione_canale", "soggetto", "soggetto_plurale",
                   "pubblico", "hashtag_canale"):
        _controlla_testo(origine, dati, chiave)
    if not dati["handle"].startswith("@"):
        raise _errore(origine, f"'handle' e' l'handle YouTube e comincia con "
                               f"'@' (per esempio '@IlMioCanale'), non "
                               f"'{dati['handle']}'.")
    if dati["genere"] not in _GRAMMATICA:
        raise _errore(origine, f"'genere' e' 'm' o 'f', non '{dati['genere']}'.")
    if dati["materiale"] not in MATERIALI:
        raise _errore(origine, f"'materiale' e' 'steam' o 'stock', non "
                               f"'{dati['materiale']}'.")
    if dati["materiale"] == "steam" and dati["argomento"].strip().lower() != ARGOMENTO_GAMING:
        raise _errore(origine, f"'materiale': 'steam' vale solo per i canali "
                               f"di videogiochi (argomento '{ARGOMENTO_GAMING}'): "
                               f"su Steam ci sono solo giochi. Per "
                               f"'{dati['argomento']}' usa 'stock'.")
    _controlla_per_lingua(origine, dati, "ricerche", vuoto_ammesso=False)
    _controlla_per_lingua(origine, dati, "parole_calde", vuoto_ammesso=True)
    _controlla_per_lingua(origine, dati, "temi_esclusi", vuoto_ammesso=True)
    if not isinstance(dati["autodefinisci"], bool):
        raise _errore(origine, f"'autodefinisci' e' true o false, non "
                               f"'{dati['autodefinisci']}'.")
    if not isinstance(dati["solo_nomi_grossi"], bool):
        raise _errore(origine, f"'solo_nomi_grossi' e' true o false, non "
                               f"'{dati['solo_nomi_grossi']}'.")
    if not isinstance(dati["telegiornale"], bool):
        raise _errore(origine, f"'telegiornale' e' true o false, non "
                               f"'{dati['telegiornale']}'.")
    if dati["telegiornale"] and dati["materiale"] != "stock":
        raise _errore(origine, "un telegiornale usa solo clip di repertorio "
                               "senza diritti: 'materiale' deve essere 'stock'.")
    for chiave in ("tag_fissi", "tag_fissi_lungo", "query_stock_riserva"):
        _controlla_lista(origine, dati, chiave)
    for chiave in ("nomi_grossi", "esempi_soggetto", "esempi_query_video"):
        _controlla_lista(origine, dati, chiave, vuota_ammessa=True)
    _controlla_per_formato(origine, dati, "hashtag_formato")
    _controlla_per_formato(origine, dati, "formati")
    _controlla_uscite(origine, dati)
    if not dati["categoria_youtube"].isdigit():
        raise _errore(origine, f"'categoria_youtube' e' il numero della "
                               f"categoria YouTube (20 = Gaming, 26 = Stile e "
                               f"consigli, 17 = Sport...), non "
                               f"'{dati['categoria_youtube']}'.")


# ===========================================================================
# LE USCITE E LE PARTENZE NOTTURNE
# ===========================================================================
def _minuti(orario):
    ora, minuto = orario.split(":")
    return int(ora) * 60 + int(minuto)


def _in_orario(minuti):
    minuti %= 24 * 60
    return f"{minuti // 60:02d}:{minuti % 60:02d}"


def scostamenti(fuso):
    """Gli scostamenti da UTC del fuso nell'anno, in minuti: uno o due.

    Due quando c'e' l'ora legale. Si guardano meta' gennaio e meta' luglio,
    cosi' vale per tutti e due gli emisferi. Solleva ZoneInfoNotFoundError o
    ValueError se il fuso non esiste.
    """
    zona = ZoneInfo(fuso)
    anno = datetime.now().year
    return sorted({int(datetime(anno, mese, 15, 12, tzinfo=zona)
                       .utcoffset().total_seconds() // 60) for mese in (1, 7)})


def cron_adatto(orario, indice, fuso):
    """La partenza numero `indice` (da 0) ha il margine giusto per `orario`?

    Deve valere tutto l'anno: con l'ora legale la stessa uscita locale cade
    un'ora prima in UTC, e il cron resta dov'e'.
    """
    ora, minuto = CRON_USCITE[indice]
    partenza = ora * 60 + minuto
    for scostamento in scostamenti(fuso):
        margine = (_minuti(orario) - scostamento - partenza) % (24 * 60)
        if not (MARGINE_MINIMO_ORE * 60 <= margine <= ANTICIPO_PARTENZA_ORE * 60):
            return False
    return True


def finestre(fuso):
    """Per ogni partenza, fra che ore locali puo' cadere la sua uscita.

    Serve solo a spiegare un profilo sbagliato con parole utili, per esempio
    "prima partenza: dalle 11:17 alle 18:17".
    """
    risultato = []
    offs = scostamenti(fuso)
    for ora, minuto in CRON_USCITE:
        partenza = ora * 60 + minuto
        inizio = partenza + MARGINE_MINIMO_ORE * 60 + max(offs)
        fine = partenza + ANTICIPO_PARTENZA_ORE * 60 + min(offs)
        risultato.append((_in_orario(inizio), _in_orario(fine)))
    return risultato


def abbina_cron(uscite, fuso):
    """A quale partenza notturna va ciascuna uscita, o None se non si puo'.

    Ritorna una lista di indici da 0, nello stesso ordine di `uscite`. Si
    provano gli abbinamenti in ordine, dalle uscite piu' presto alle
    partenze piu' presto, e vince il primo che rispetta i margini: per
    Poppone TV e' 14:00 -> prima, 18:00 -> seconda, 20:00 -> terza, 21:00 ->
    quarta, cioe' i cron di sempre. Quattro partenze danno al massimo 24
    abbinamenti da provare.
    """
    ordine = sorted(range(len(uscite)), key=lambda i: uscite[i]["orario"])
    for scelta in permutations(range(len(CRON_USCITE)), len(uscite)):
        if all(cron_adatto(uscite[i]["orario"], cron, fuso)
               for i, cron in zip(ordine, scelta)):
            abbinamento = [None] * len(uscite)
            for i, cron in zip(ordine, scelta):
                abbinamento[i] = cron
            return abbinamento
    return None


def uscita_del_cron(profilo, numero):
    """L'uscita che copre la partenza numero `numero` (1-4), o None.

    None vuol dire che questa partenza oggi non ha niente da fare: un canale
    con due uscite ne lascia libere due.
    """
    abbinamento = abbina_cron(profilo.uscite, profilo.fuso) or []
    for uscita, cron in zip(profilo.uscite, abbinamento):
        if cron == numero - 1:
            return uscita
    return None


def uscita_richiesta(profilo, testo):
    """L'uscita chiesta a mano: il suo numero nella giornata o il suo orario.

    '2' e' la seconda uscita della giornata, '18:00' e' quella delle 18:00.
    Solleva ProfiloNonValido se nel profilo non c'e'.
    """
    testo = (testo or "").strip()
    in_ordine = profilo.uscite_in_ordine
    if testo.isdigit() and 1 <= int(testo) <= len(in_ordine):
        return in_ordine[int(testo) - 1]
    for uscita in in_ordine:
        if uscita["orario"] == testo:
            return uscita
    elenco = ", ".join(f"{i}) {u['orario']}" for i, u in enumerate(in_ordine, 1))
    raise ProfiloNonValido(
        f"L'uscita richiesta '{testo}' non c'e' nel profilo del canale. "
        f"Le uscite sono: {elenco}.")


def _controlla_uscite(origine, dati):
    fuso = dati.get("fuso")
    if not isinstance(fuso, str) or not fuso.strip():
        raise _errore(origine, "'fuso' deve essere un fuso orario, per "
                               "esempio 'Europe/Rome'.")
    try:
        scostamenti(fuso)
    except (ZoneInfoNotFoundError, ValueError):
        raise _errore(origine, f"'fuso': '{fuso}' non e' un fuso orario "
                               f"conosciuto. Si scrive come 'Europe/Rome' o "
                               f"'America/New_York'.") from None

    uscite = dati.get("uscite")
    if not isinstance(uscite, list) or not 1 <= len(uscite) <= MAX_USCITE:
        raise _errore(origine, f"'uscite' deve essere una lista da 1 a "
                               f"{MAX_USCITE} uscite, per esempio "
                               f'[{{"orario": "18:00", "lingua": "it"}}].')
    visti = set()
    for n, uscita in enumerate(uscite, 1):
        if not isinstance(uscita, dict) or set(uscita) != {"orario", "lingua"}:
            raise _errore(origine, f"l'uscita numero {n} deve avere solo "
                                   f"'orario' e 'lingua'.")
        orario, lingua = uscita["orario"], uscita["lingua"]
        if not isinstance(orario, str) or not _RE_ORARIO.match(orario):
            raise _errore(origine, f"l'uscita numero {n} ha orario "
                                   f"'{orario}': si scrive HH:MM, per esempio "
                                   f"'18:00'.")
        if lingua not in LINGUE:
            raise _errore(origine, f"l'uscita delle {orario} ha lingua "
                                   f"'{lingua}': si usa {' o '.join(LINGUE)}.")
        if orario in visti:
            raise _errore(origine, f"due uscite alle {orario}.")
        visti.add(orario)

    if abbina_cron(uscite, fuso) is None:
        spiegazione = "; ".join(
            f"partenza {n} dalle {da} alle {a}"
            for n, (da, a) in enumerate(finestre(fuso), 1))
        raise _errore(origine, f"gli orari delle uscite non stanno nelle "
                               f"partenze notturne. Ogni uscita deve cadere "
                               f"fra {MARGINE_MINIMO_ORE} e "
                               f"{ANTICIPO_PARTENZA_ORE} ore dopo la sua "
                               f"partenza, e ogni partenza copre una sola "
                               f"uscita. Con il fuso {fuso}: {spiegazione} "
                               f"(ora locale).")


def da_dizionario(dal_file, origine="canale.json"):
    """Costruisce e valida un Profilo a partire dal contenuto del file.

    Solleva ProfiloNonValido con un messaggio in chiaro: meglio fermarsi
    all'avvio che scoprire a meta' pipeline che una ricerca e' vuota.
    """
    if not isinstance(dal_file, dict):
        raise _errore(origine, "il file deve contenere un oggetto JSON { ... }.")
    # Le chiavi che cominciano con '_' sono commenti (JSON non ne ha altri).
    dal_file = {k: v for k, v in dal_file.items() if not k.startswith("_")}
    sconosciute = sorted(set(dal_file) - set(PREDEFINITO))
    if sconosciute:
        raise _errore(origine, f"campi sconosciuti: {', '.join(sconosciute)}. "
                               f"Campi validi: {', '.join(PREDEFINITO)}.")
    # Un numero scritto senza virgolette e' comunque una categoria.
    if isinstance(dal_file.get("categoria_youtube"), int):
        dal_file["categoria_youtube"] = str(dal_file["categoria_youtube"])

    argomento = dal_file.get("argomento", ARGOMENTO_GAMING)
    if not isinstance(argomento, str) or not argomento.strip():
        raise _errore(origine, "'argomento' deve essere un testo non vuoto.")

    if argomento.strip().lower() == ARGOMENTO_GAMING:
        dati = json.loads(json.dumps(PREDEFINITO))     # copia profonda
        # Il sito di popponetv non va a un altro canale di videogiochi.
        dati["sito"] = ""
        for chiave, valore in dal_file.items():
            # Gli oggetti si fondono: chi cambia solo le ricerche italiane
            # tiene quelle inglesi, chi cambia un hashtag tiene gli altri.
            if isinstance(dati[chiave], dict) and isinstance(valore, dict):
                dati[chiave].update(valore)
            else:
                dati[chiave] = valore
    else:
        vietato = argomento_vietato(" ".join(
            str(dal_file.get(c) or "") for c in ("argomento", "descrizione_argomento",
                                                 "soggetto", "descrizione_canale")))
        if vietato:
            raise _errore(origine, f"l'argomento tocca un tema che YouTube non "
                                   f"monetizza o non ammette ('{vietato}'): "
                                   f"Samaritan non fa canali cosi'.")
        if dal_file.get("autodefinisci") is True:
            dal_file = dict(dal_file)
            _ripieghi_autodefinizione(dal_file, argomento)
        mancanti = [c for c in _OBBLIGATORI_FUORI_DAL_GAMING if c not in dal_file]
        if mancanti:
            raise _errore(origine, f"per un canale che non parla di "
                                   f"videogiochi servono anche: "
                                   f"{', '.join(mancanti)}. I valori di "
                                   f"Poppone TV valgono solo con argomento "
                                   f"'{ARGOMENTO_GAMING}'.")
        dati = {c: PREDEFINITO[c] for c in ("nome_canale", "handle")}
        dati.update(json.loads(json.dumps(_NEUTRO)))
        dati.update(dal_file)
        _controlla_testo(origine, dati, "soggetto")
        _ricava(dati, dal_file)
        if not dati["soggetto_plurale"]:
            raise _errore(origine, f"il soggetto '{dati['soggetto']}' e' di "
                                   f"piu' parole: scrivi anche "
                                   f"'soggetto_plurale'.")

    _valida(dati, origine)
    return Profilo(dati, origine)


def _ripieghi_autodefinizione(dal_file, argomento):
    """I valori con cui un canale 'autodefinisci' parte prima che il modello
    abbia scritto i suoi (autoprofilo.py), o se non ci riesce.

    Bastano per fare video veri: si cercano notizie sull'argomento stesso e
    ogni video parla di "un tema". Sono volutamente generici: il primo giro
    della pipeline li sostituisce con quelli scritti dal modello.
    """
    nome = argomento.strip()
    nome = nome[3:] if nome.lower().startswith("di ") else nome
    if "soggetto" not in dal_file:
        dal_file.setdefault("soggetto_plurale", "temi")
        dal_file.setdefault("genere", "m")
        dal_file["soggetto"] = "tema"
    if "ricerche" not in dal_file or not dal_file.get("ricerche"):
        dal_file["ricerche"] = {"it": [nome.strip(" '") or argomento]}


def _con_autodefinizione(contenuto, file):
    """Il contenuto di canale.json con sotto i campi scritti da autoprofilo.py.

    Valgono solo se il file e' 'autodefinisci' e se sono stati scritti per lo
    stesso argomento: chi cambia argomento dalla pagina non deve ritrovarsi
    le ricerche del canale di prima. I campi scritti a mano vincono.
    """
    if not isinstance(contenuto, dict) or contenuto.get("autodefinisci") is not True:
        return contenuto
    auto = leggi_autodefinizione(file)
    if not auto or auto.get("argomento") != contenuto.get("argomento"):
        return contenuto
    unito = dict(contenuto)
    for chiave, valore in (auto.get("campi") or {}).items():
        if chiave in PREDEFINITO and chiave not in unito:
            unito[chiave] = valore
    return unito


def file_autodefinizione(file=None):
    """Dove sta canale_auto.json per il profilo letto da `file`."""
    return os.path.join(os.path.dirname(os.path.abspath(file or percorso())),
                        NOME_FILE_AUTO)


def leggi_autodefinizione(file=None):
    """Il contenuto di canale_auto.json, o None se manca o non si legge."""
    try:
        with open(file_autodefinizione(file), "r", encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def contenuto_del_file(file=None):
    """canale.json cosi' com'e' scritto, senza autodefinizione, o None."""
    file = file or percorso()
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def predefinito():
    """Il profilo di Poppone TV, quello che vale senza canale.json."""
    return Profilo(json.loads(json.dumps(PREDEFINITO)))


def percorso():
    """Dove si legge il profilo: PROFILO_CANALE, oppure canale.json."""
    return (os.getenv("PROFILO_CANALE") or "").strip() or FILE_PREDEFINITO


def carica(file=None):
    """Legge e valida il profilo. Senza file sul disco torna il predefinito.

    Il file mancante e' un errore solo se qualcuno l'ha indicato apposta con
    PROFILO_CANALE: in quel caso un percorso sbagliato farebbe uscire i video
    col profilo di un altro canale, in silenzio.
    """
    indicato = file is not None or bool((os.getenv("PROFILO_CANALE") or "").strip())
    file = file or percorso()
    if not os.path.exists(file):
        if indicato:
            raise ProfiloNonValido(
                f"Profilo del canale non trovato: '{file}' (indicato con "
                f"PROFILO_CANALE) non esiste.")
        return predefinito()
    try:
        with open(file, "r", encoding="utf-8") as f:
            contenuto = json.load(f)
    except json.JSONDecodeError as e:
        raise ProfiloNonValido(
            f"Profilo del canale non valido ({file}): non e' JSON valido "
            f"(riga {e.lineno}, colonna {e.colno}: {e.msg}).") from None
    except OSError as e:
        raise ProfiloNonValido(
            f"Profilo del canale non leggibile ({file}): {e}.") from None
    return da_dizionario(_con_autodefinizione(contenuto, file), os.path.basename(file))


_attivo = None


def attivo():
    """Il profilo in uso. Si legge dal disco una volta sola per processo."""
    global _attivo
    if _attivo is None:
        _attivo = carica()
    return _attivo


def imposta(profilo):
    """Sostituisce il profilo in uso (test, prove a mano). None = rileggi."""
    global _attivo
    _attivo = profilo


def decidi(numero_cron):
    """Per il workflow: questa partenza ha qualcosa da fare? Ritorna le righe
    da scrivere in $GITHUB_OUTPUT.

    Una partenza senza numero (la riserva, le prove a mano) ha sempre da
    fare. Una partenza notturna senza uscita abbinata si ferma qui, prima che
    il workflow installi FFmpeg e tre giga di dipendenze per niente.
    """
    numero = (numero_cron or "").strip()
    if not numero:
        return "attiva=true"
    uscita = uscita_del_cron(attivo(), int(numero))
    if uscita is None:
        print(f"[Profilo] La partenza {numero} non ha un'uscita da coprire: "
              f"non faccio niente.", file=sys.stderr)
        return "attiva=false"
    print(f"[Profilo] La partenza {numero} copre l'uscita delle "
          f"{uscita['orario']} ({uscita['lingua']}).", file=sys.stderr)
    return "attiva=true"


if __name__ == "__main__":
    # python3 profilo.py decidi  -> attiva=true|false, legge USCITA_CRON
    if sys.argv[1:] != ["decidi"]:
        sys.exit("Uso: python3 profilo.py decidi")
    try:
        print(decidi(os.getenv("USCITA_CRON")))
    except ProfiloNonValido as e:
        print(f"::error::{e}")
        sys.exit(1)
