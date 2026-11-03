# -*- coding: utf-8 -*-
"""
Dove sono i momenti buoni di una live, e quali clip vanno tenute basse.

Logica pura, senza rete, ffmpeg o numpy: per questo si testa nella CI insieme
al resto di Samaritan (tests/test_clip_live.py).

Come si trovano i momenti:
  - l'AUDIO dice quando popponetv alza la voce, ride, urla: per ogni secondo
    c'e' un valore di energia;
  - la CHAT dice quando succede qualcosa che la gente nota: messaggi al
    secondo, e quanti sono reazioni ("ahah", "LUL", "KEKW", "clip"...).
    La chat arriva in ritardo sull'evento (il tempo di leggere e scrivere),
    quindi la si anticipa di RITARDO_CHAT secondi.
Ogni segnale viene normalizzato (z-score) e smussato, poi si prendono i picchi
piu' alti lontani fra loro almeno DISTANZA_MINIMA secondi. Attorno a ogni
picco si ritaglia una finestra che parte un po' prima (il contesto) e finisce
poco dopo (la reazione).

Le regole di Finch per le clip da tenere basse: insulti, dati personali,
persone della chat riconoscibili. Lo script non scarta niente da solo: segna
l'avviso e abbassa il punteggio, la decisione e' di Finch.
"""
import math
import re

RITARDO_CHAT = 7          # secondi fra l'evento e la reazione in chat
SMUSSO = 5                # finestra della media mobile, in secondi
DISTANZA_MINIMA = 90      # due clip non pescano dallo stesso momento
PRIMA_DEL_PICCO = 18      # contesto prima del picco (poi si taglia all'hook)
DOPO_IL_PICCO = 14        # reazione dopo il picco
DURATA_MIN = 15
DURATA_MAX = 60
SALTA_INIZIO = 120        # i primi minuti di una live sono "ciao a tutti"
SALTA_FINE = 180          # gli ultimi sono saluti, raid e musica di chiusura

# Versione TikTok: il Creator Rewards Program paga solo video di oltre un
# minuto, quindi attorno ai picchi migliori si taglia anche un pezzo piu' lungo
# con piu' contesto prima (la situazione) e piu' reazione dopo.
TIKTOK_PRIMA = 50
TIKTOK_DOPO = 25
TIKTOK_MIN = 65
TIKTOK_MAX = 90

PAROLE_REAZIONE = (
    "ahah", "ahha", "haha", "lol", "lul", "kekw", "omegalul", "pog", "poggers",
    "clip", "clippa", "noo", "nooo", "madonna", "assurdo", "gg", "wtf", "rip",
    "😂", "🤣", "💀",
)

# Volgarita' e bestemmie: non serve un elenco completo, serve abbassare il
# punteggio quando ce n'e' una. Le radici prendono anche le varianti.
_RADICI_INSULTI = (
    "cazz", "minchi", "stronz", "vaffancul", "fancul", "coglion", "puttan",
    "troi", "merd", "frocio", "froci", "negr", "ritardat", "mongolo",
    "porco dio", "porcodio", "dio cane", "diocane", "porca madonna",
    "dio porco", "madonna puttana", "in culo", "nel culo", "porco due",
)

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TELEFONO = re.compile(r"(?:\+39\s?)?(?:3\d{2}|0\d{1,3})[\s.-]?\d{3}[\s.-]?\d{3,4}")
_RE_INDIRIZZO = re.compile(
    r"\b(?:via|viale|piazza|corso|largo)\s+[a-zà-ù'\s]{3,30}\s+\d{1,4}\b",
    re.IGNORECASE)


def _media(valori):
    return sum(valori) / len(valori) if valori else 0.0


def zscore(valori):
    """Valori normalizzati: 0 = la media della live, 1 = una deviazione sopra."""
    if not valori:
        return []
    media = _media(valori)
    varianza = _media([(v - media) ** 2 for v in valori])
    dev = math.sqrt(varianza)
    if dev == 0:
        return [0.0] * len(valori)
    return [(v - media) / dev for v in valori]


def smussa(valori, finestra=SMUSSO):
    """Media mobile centrata: un urlo di mezzo secondo non e' un momento."""
    if finestra <= 1 or not valori:
        return list(valori)
    meta = finestra // 2
    risultato = []
    for i in range(len(valori)):
        pezzo = valori[max(0, i - meta): i + meta + 1]
        risultato.append(_media(pezzo))
    return risultato


def anticipa(valori, secondi):
    """Sposta un segnale indietro nel tempo (la chat reagisce in ritardo)."""
    if secondi <= 0:
        return list(valori)
    return list(valori[secondi:]) + [0.0] * min(secondi, len(valori))


def chat_per_secondo(messaggi, durata):
    """Da [(secondo, autore, testo), ...] a due serie: volume e reazioni."""
    volume = [0.0] * durata
    reazioni = [0.0] * durata
    for secondo, _autore, testo in messaggi:
        s = int(secondo)
        if not 0 <= s < durata:
            continue
        volume[s] += 1
        basso = (testo or "").lower()
        if any(p in basso for p in PAROLE_REAZIONE):
            reazioni[s] += 1
    return volume, reazioni


def segnale(energia, volume_chat=None, reazioni_chat=None):
    """Il segnale combinato, un valore per secondo.

    Senza chat conta solo l'audio. Con la chat: meta' audio, meta' chat, e
    dentro la chat le reazioni pesano il doppio del semplice volume.
    """
    durata = len(energia)
    audio = smussa(zscore(energia))
    if not volume_chat or not any(volume_chat):
        return audio
    volume = smussa(zscore(anticipa(volume_chat[:durata], RITARDO_CHAT)))
    reaz = smussa(zscore(anticipa((reazioni_chat or [0.0] * durata)[:durata],
                                  RITARDO_CHAT)))
    chat = [(v + 2 * r) / 3 for v, r in zip(volume, reaz)]
    return [0.5 * a + 0.5 * c for a, c in zip(audio, chat)]


def finestra(picco, durata_live):
    """Inizio e fine della clip attorno al picco, dentro i limiti di durata."""
    inizio = max(0, picco - PRIMA_DEL_PICCO)
    fine = min(durata_live, picco + DOPO_IL_PICCO)
    if fine - inizio < DURATA_MIN:
        fine = min(durata_live, inizio + DURATA_MIN)
        inizio = max(0, fine - DURATA_MIN)
    if fine - inizio > DURATA_MAX:
        fine = inizio + DURATA_MAX
    return int(inizio), int(fine)


def finestra_tiktok(picco, durata_live):
    """Come finestra(), ma tra TIKTOK_MIN e TIKTOK_MAX secondi.

    None se la live e' troppo corta per un pezzo cosi' lungo.
    """
    if durata_live < TIKTOK_MIN:
        return None
    inizio = max(0, picco - TIKTOK_PRIMA)
    fine = min(durata_live, picco + TIKTOK_DOPO)
    if fine - inizio < TIKTOK_MIN:
        fine = min(durata_live, inizio + TIKTOK_MIN)
        inizio = max(0, fine - TIKTOK_MIN)
    if fine - inizio > TIKTOK_MAX:
        fine = inizio + TIKTOK_MAX
    return int(inizio), int(fine)


def punteggio_da_z(z):
    """Da z-score a 0-100: la media della live vale 50.

    Sopra la media sale sempre piu' piano verso 100 senza arrivarci: i picchi
    di una live lunga hanno z di 5-15 e con una retta finivano tutti a 100,
    cosi' la classifica non distingueva piu' niente.
    """
    if z <= 0:
        return int(max(0, round(50 + 12 * z)))
    return int(min(99, round(100 - 50 * math.exp(-z / 4))))


# --------------------------------------------------------------------------
# Dopo la trascrizione: hook, voci del gioco, parlato
# --------------------------------------------------------------------------

HOOK_PRIMA = 1.0          # la clip parte un secondo prima della prima frase
CODA_DOPO = 2.0           # e finisce due secondi dopo l'ultima (la reazione)
PAUSA_HOOK = 3.0          # parole isolate da una pausa piu' lunga non aprono la clip
POCO_PARLATO = 6          # sotto queste parole la clip vale meno
PENALITA_MUTA = 15
# Sotto queste parole la clip si scarta: una clip muta non si vende. Le
# TikTok durano piu' di un minuto, quindi devono parlare di piu'.
PAROLE_MIN = {"youtube": 6, "tiktok": 20}


def parole_minime(piattaforma):
    return PAROLE_MIN.get(piattaforma, PAROLE_MIN["youtube"])

_INGLESE = set("""the you your you're can't cannot can our we us is are was were this that
what why how my me i i'm it it's of to and so man anymore will won't don't do does
not no yes he she they them his her with for from be been have has had there here
must shall never ever now fail""".split())
_ITALIANO = set("""il lo la le gli un una di da in con su per che non ma e è ho hai ha
mi ti si ci vi c'è no sì come cosa perché poi qua là questo quello sono sei anche
più già dai vai oh eh ah boh porco madonna dio bravo vieni troppo poco""".split())


def sembra_inglese(parole):
    """True se un pezzo di parlato e' inglese: le voci del gioco, non Davide.

    Whisper gira con language="it", quindi il doppiaggio inglese del gioco
    esce come italiano storpiato. Basta contare le parole piu' comuni delle
    due lingue: "Our sex fist part cannot fail!" non ha niente di italiano.
    """
    basse = [re.sub(r"[^\w'’]", "", p.lower()).replace("’", "'") for p in parole]
    en = sum(1 for p in basse if p in _INGLESE)
    it = sum(1 for p in basse if p in _ITALIANO)
    return en >= 1 and en > it


def taglio_hook(parole, durata, minimo=DURATA_MIN):
    """(inizio, fine) in secondi dentro la clip: niente silenzio prima della
    prima frase e niente coda muta dopo l'ultima.

    parole: [(inizio, fine, testo), ...] gia' filtrate. Non si scende mai sotto
    `minimo` secondi: se tagliando la clip diventerebbe troppo corta, si
    tiene piu' coda e, se non basta, piu' contesto prima.
    """
    if not parole:
        return 0.0, float(durata)
    # Una parola sola seguita da lunghi secondi muti non e' l'inizio del
    # discorso: si parte dalla prima parola che ha un seguito vicino.
    primo = 0
    while (primo < len(parole) - 1
           and parole[primo + 1][0] - parole[primo][1] > PAUSA_HOOK):
        primo += 1
    inizio = max(0.0, parole[primo][0] - HOOK_PRIMA)
    fine = min(float(durata), parole[-1][1] + CODA_DOPO)
    if fine - inizio < minimo:
        fine = min(float(durata), inizio + minimo)
    if fine - inizio < minimo:
        inizio = max(0.0, fine - minimo)
    return round(inizio, 2), round(fine, 2)


def sovrapposte(a, b, margine=0):
    """Due finestre (inizio, fine) che condividono almeno un secondo."""
    return a[0] < b[1] - margine and b[0] < a[1] - margine


def correggi_per_parlato(punti, n_parole):
    """Senza parlato una clip regge poco: scende un po' in classifica."""
    return max(0, punti - PENALITA_MUTA) if n_parole < POCO_PARLATO else punti


def candidati(valori, quante=5, durata_live=None):
    """I momenti migliori: [(inizio, fine, punteggio, picco), ...] per punteggio.

    Greedy: prende il secondo piu' alto, esclude i DISTANZA_MINIMA attorno,
    ripete. I primi SALTA_INIZIO e gli ultimi SALTA_FINE secondi non contano.
    """
    durata_live = durata_live or len(valori)
    ordine = sorted(range(len(valori)), key=lambda i: valori[i], reverse=True)
    presi = []
    for i in ordine:
        if len(presi) >= quante:
            break
        lunga = durata_live > (SALTA_INIZIO + SALTA_FINE) * 3
        if lunga and (i < SALTA_INIZIO or i > durata_live - SALTA_FINE):
            continue
        if valori[i] <= 0:
            break
        if any(abs(i - p) < DISTANZA_MINIMA for p in presi):
            continue
        presi.append(i)
    risultato = []
    for picco in presi:
        inizio, fine = finestra(picco, durata_live)
        if fine - inizio < DURATA_MIN:
            continue
        risultato.append((inizio, fine, punteggio_da_z(valori[picco]), picco))
    return sorted(risultato, key=lambda c: c[2], reverse=True)


def controlla_testo(testo, nomi_chat=()):
    """Avvisi sul parlato della clip: lista di codici, vuota se e' pulita.

    "insulti", "dati_personali", "utente_chat". Un nome della chat conta solo
    se ha almeno quattro caratteri, per non scambiare "ok" o "gg" per persone.
    """
    basso = (testo or "").lower()
    avvisi = []
    if any(r in basso for r in _RADICI_INSULTI):
        avvisi.append("insulti")
    if (_RE_EMAIL.search(testo or "") or _RE_TELEFONO.search(testo or "")
            or _RE_INDIRIZZO.search(testo or "")):
        avvisi.append("dati_personali")
    parole = set(re.findall(r"[\w]+", basso))
    for nome in nomi_chat:
        n = (nome or "").lower().strip("@ ")
        if len(n) >= 4 and (n in parole or ("@" + n) in basso):
            avvisi.append("utente_chat")
            break
    return avvisi


PENALITA = {"insulti": 40, "insulti_coperti": 10, "dati_personali": 50, "utente_chat": 30}


def _pulita(parola):
    return re.sub(r"[^\w']", "", (parola or "").lower())


def parolacce(parole):
    """Indici delle parole da coprire col bip, in [(inizio, fine, testo), ...].

    Le radici di una parola sola ("cazz", "merd"...) si cercano dentro ogni
    parola; quelle di due parole ("porco dio") su ogni coppia vicina.
    """
    singole = [r for r in _RADICI_INSULTI if " " not in r]
    doppie = [r for r in _RADICI_INSULTI if " " in r]
    pulite = [_pulita(p[2]) for p in parole]
    indici = set()
    for i, p in enumerate(pulite):
        if any(r in p for r in singole):
            indici.add(i)
        if i + 1 < len(pulite) and f"{p} {pulite[i + 1]}" in doppie:
            indici.update((i, i + 1))
    return sorted(indici)


def copri_parola(testo):
    """"cazzo" -> "c****": si capisce che c'era, non si legge."""
    lettere = [i for i, c in enumerate(testo) if c.isalpha()]
    if len(lettere) < 2:
        return testo
    return "".join("*" if i in lettere[1:] else c for i, c in enumerate(testo))


def applica_penalita(punteggio, avvisi):
    """Le clip a rischio scendono in fondo: Finch le vede e le scarta."""
    for avviso in avvisi:
        punteggio -= PENALITA.get(avviso, 0)
    return max(0, punteggio)
