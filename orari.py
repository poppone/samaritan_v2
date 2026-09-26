# -*- coding: utf-8 -*-
"""A che ora il video deve comparire sul canale.

GitHub Actions fa partire le run schedulate in ritardo, e il ritardo non e'
prevedibile: fra il 17 e il 19 settembre 2026 e' andato da un'ora e quaranta a
tre ore e mezza. Quindi l'orario di pubblicazione NON si puo' ottenere
scegliendo l'ora del cron.

Si ottiene caricando il video in anticipo e lasciando che sia YouTube a
renderlo pubblico all'istante esatto: e' il campo publishAt dell'API, e vale
al minuto. Il cron serve solo a far partire la pipeline con abbastanza
margine da finire prima.

Effetto collaterale utile: l'orario si calcola in ora italiana vera, quindi
l'ora legale non lo sposta piu'. Prima le ore erano scritte in UTC dentro il
workflow e a fine ottobre andavano corrette a mano.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config


# Le uscite della giornata: orario, lingua e formato di ciascuna. E' l'elenco
# che la run di recupero usa per capire quale manca; il workflow ha la sua
# copia sotto forma di cron, e un test controlla che le due dicano la stessa
# cosa.
#
# Il formato non e' un dettaglio di etichetta: il video lungo esce 16:9 da
# otto minuti e lo Short 9:16 da mezzo minuto, e la lavorazione di recupero
# deve sapere quale dei due sta rifacendo prima di calcolare qualunque misura.
SLOT_GIORNALIERI = (
    ("14:00", "it", "short"),
    ("18:00", "it", "short"),
    ("20:00", "it", "lungo"),
    ("21:00", "en", "short"),
)

# La finestra dentro cui un video "appartiene" a una certa uscita. Non e'
# centrata, e il motivo e' che la cronologia registra il momento in cui il
# video viene SCRITTO, non quello in cui YouTube lo pubblica: la pipeline
# parte in anticipo (al massimo quattro ore e mezza) e puo' invece finire con
# molte ore di ritardo quando GitHub fa partire il cron tardi. Il record e'
# sette ore, il 21 settembre 2026. Le uscite distano 24 ore, quindi la
# finestra piu' larga qui sotto non arriva mai a toccare quella del giorno
# prima.
ANTICIPO_MASSIMO_ORE = 6
RITARDO_MASSIMO_ORE = 12


def _leggi_orario(testo):
    """'18:00' -> (18, 0). Solleva ValueError se non e' un orario."""
    ore, _, minuti = testo.strip().partition(":")
    ora, minuto = int(ore), int(minuti or 0)
    if not (0 <= ora <= 23 and 0 <= minuto <= 59):
        raise ValueError(f"orario fuori scala: {testo!r}")
    return ora, minuto


def uscita_programmata(adesso=None):
    """L'istante in cui il video deve diventare pubblico, o None.

    None vuol dire "pubblica subito", ed e' il caso giusto in tre situazioni:
    nessun orario configurato (le run lanciate a mano), un orario scritto
    male, e soprattutto l'orario di oggi gia' passato. Quest'ultimo e' una
    scelta: se la run e' arrivata in ritardo oltre l'orario, uscire adesso e'
    meglio che aspettare il giorno dopo.
    """
    testo = (config.ORARIO_USCITA or "").strip()
    if not testo:
        return None

    try:
        ora, minuto = _leggi_orario(testo)
    except ValueError:
        print(f"[Orari] '{testo}' non e' un orario: pubblico subito.")
        return None

    try:
        fuso = ZoneInfo(config.FUSO_USCITA)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"[Orari] Fuso '{config.FUSO_USCITA}' sconosciuto: pubblico subito.")
        return None

    adesso = (adesso or datetime.now(fuso)).astimezone(fuso)
    uscita = datetime(adesso.year, adesso.month, adesso.day,
                      ora, minuto, tzinfo=fuso)
    if uscita <= adesso:
        print(f"[Orari] Le {testo} sono gia' passate: pubblico subito.")
        return None
    return uscita


def _fuso():
    try:
        return ZoneInfo(config.FUSO_USCITA)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Rome")


def _ultima_occorrenza(slot, adesso):
    """L'ultima volta che questo orario e' passato: oggi, o ieri."""
    ora, minuto = _leggi_orario(slot)
    quando = adesso.replace(hour=ora, minute=minuto, second=0, microsecond=0)
    if quando > adesso:
        quando -= timedelta(days=1)
    return quando


def _occorrenza_da_coprire(slot, adesso):
    """L'uscita che una lavorazione partita adesso sta coprendo.

    Non e' sempre l'ultima passata. Le lavorazioni partono PRIMA della loro
    uscita (il cron e' quattro ore e mezza prima, di piu' d'inverno), e se
    GitHub e' puntuale l'uscita di oggi non e' ancora arrivata: guardando solo
    all'indietro la lavorazione si confrontava con il video di IERI alla
    stessa ora, lo trovava e si fermava. Cosi' si sono perse le 21:00 del 22 e
    del 24 settembre 2026 e le 18:00 del 25.

    Quindi: se l'uscita di oggi arriva entro ANTICIPO_MASSIMO_ORE e' quella
    che si sta coprendo, altrimenti e' l'ultima passata.
    """
    ultima = _ultima_occorrenza(slot, adesso)
    prossima = ultima + timedelta(days=1)
    if (prossima - adesso).total_seconds() <= ANTICIPO_MASSIMO_ORE * 3600:
        return prossima
    return ultima


def gia_pubblicato(slot, cronologia, adesso=None):
    """Questa uscita e' gia' stata coperta da un video?

    E' il freno contro i doppioni. Una run schedulata che arriva con ore di
    ritardo puo' trovare la sua uscita gia' coperta dalla run di recupero, e
    viceversa: chi arriva secondo si ferma invece di pubblicare un gemello.

    Si ragiona sulla distanza dall'orario dell'uscita e non sulla data del
    calendario, perche' con i ritardi di GitHub una run puo' benissimo partire
    dopo la mezzanotte e trovarsi a fare i conti con un'uscita di 'ieri'.
    """
    slot = (slot or "").strip()
    if not slot:
        return False
    try:
        occorrenza = _occorrenza_da_coprire(slot, adesso or datetime.now(_fuso()))
    except ValueError:
        return False
    return _coperta(slot, occorrenza, cronologia)


def _coperta(slot, occorrenza, cronologia):
    """C'e' in cronologia un video caricato per QUESTA occorrenza dell'uscita?"""
    inizio = occorrenza.timestamp() - ANTICIPO_MASSIMO_ORE * 3600
    fine = occorrenza.timestamp() + RITARDO_MASSIMO_ORE * 3600
    for voce in cronologia or []:
        if not isinstance(voce, dict):
            continue
        if (voce.get("slot") or "").strip() != slot:
            continue
        # Senza video_id il video non e' mai arrivato su YouTube: la riga in
        # cronologia si scrive appena lo script e' pronto, l'identificativo
        # solo a caricamento riuscito. Una lavorazione morta a meta' non deve
        # far passare l'uscita per coperta, altrimenti la rete di sicurezza
        # non servirebbe proprio nel caso in cui serve.
        if not voce.get("video_id"):
            continue
        quando = voce.get("timestamp") or 0
        if inizio <= quando <= fine:
            return True
    return False


def slot_da_recuperare(cronologia, adesso=None):
    """L'uscita saltata da recuperare adesso, come (orario, lingua, formato).

    None se non manca niente.

    Si guardano solo le uscite il cui orario e' passato da poco: recuperare
    un'uscita di ieri vuol dire pubblicare una notizia di ieri, e recuperarne
    una che deve ancora arrivare vuol dire farla uscire due volte.

    Una sola per run, la piu' vecchia fra quelle che mancano: anche nel caso
    peggiore esce un video in piu', mai tre tutti insieme.
    """
    adesso = adesso or datetime.now(_fuso())
    mancanti = []
    for slot, lingua, formato in SLOT_GIORNALIERI:
        try:
            occorrenza = _ultima_occorrenza(slot, adesso)
        except ValueError:
            continue
        if (adesso - occorrenza).total_seconds() > RITARDO_MASSIMO_ORE * 3600:
            continue
        # La riserva ragiona solo su uscite gia' passate, quindi controlla
        # quella precisa occorrenza e non l'uscita "da coprire" adesso.
        if _coperta(slot, occorrenza, cronologia):
            continue
        mancanti.append((occorrenza, slot, lingua, formato))
    if not mancanti:
        return None
    mancanti.sort()
    _, slot, lingua, formato = mancanti[0]
    return slot, lingua, formato
