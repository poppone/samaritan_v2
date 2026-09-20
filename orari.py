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
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config


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
