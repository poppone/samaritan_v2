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
PRIMA_DEL_PICCO = 22      # contesto prima del picco
DOPO_IL_PICCO = 12        # reazione dopo il picco
DURATA_MIN = 15
DURATA_MAX = 60
SALTA_INIZIO = 120        # i primi minuti di una live sono "ciao a tutti"
SALTA_FINE = 180          # gli ultimi sono saluti, raid e musica di chiusura

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


def punteggio_da_z(z):
    """Da z-score a 0-100: la media della live vale 50."""
    return int(max(0, min(100, round(50 + 12 * z))))


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


PENALITA = {"insulti": 40, "dati_personali": 50, "utente_chat": 30}


def applica_penalita(punteggio, avvisi):
    """Le clip a rischio scendono in fondo: Finch le vede e le scarta."""
    for avviso in avvisi:
        punteggio -= PENALITA.get(avviso, 0)
    return max(0, punteggio)
