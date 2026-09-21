"""
Il pezzo che mancava: la MEMORIA DI CIO' CHE HA FUNZIONATO.

Prima, Samaritan ricordava cosa aveva pubblicato ma non come era andato.
Generava al buio, per sempre, senza imparare nulla.

Questo modulo scarica la retention reale da YouTube Analytics, la incrocia con
il formato usato per ogni video (salvato in cronologia_trend.json) e produce:

  - pesi_formati()  -> quali formati far uscire piu' spesso
  - migliori_hook() -> le prime frasi che hanno davvero trattenuto lo spettatore,
                       reiniettate nel prompt di brain.py come esempi

Se il token OAuth non ha ancora il permesso di lettura statistiche, il modulo
degrada in silenzio (pesi neutri) senza mai bloccare la pipeline.
"""
import os
import json
import datetime

import config

GIORNI_ANALISI = 90
MIN_VIDEO_PER_FORMATO = 2      # sotto questa soglia il dato non e' affidabile
PESO_MIN, PESO_MAX = 0.35, 2.5


# ===========================================================================
# RACCOLTA DATI
# ===========================================================================
def scarica_performance():
    """Scarica le metriche per video dagli ultimi 90 giorni.
    Ritorna {video_id: {metriche}} oppure {} se non disponibile."""
    try:
        from googleapiclient.discovery import build
        from uploader import ottieni_credenziali, ha_scope_analytics

        credenziali = ottieni_credenziali()
        if not ha_scope_analytics(credenziali):
            print("[Samaritan Analyst] Il token non include lo scope Analytics.")
            print("                    Cancella token.pickle e riautentica una volta")
            print("                    per attivare il feedback loop.")
            return {}

        analytics = build("youtubeAnalytics", "v2", credentials=credenziali)
        oggi = datetime.date.today()
        inizio = oggi - datetime.timedelta(days=GIORNI_ANALISI)

        risposta = analytics.reports().query(
            ids="channel==MINE",
            startDate=inizio.isoformat(),
            endDate=oggi.isoformat(),
            metrics=("views,averageViewPercentage,averageViewDuration,"
                     "likes,comments,subscribersGained"),
            dimensions="video",
            sort="-views",
            maxResults=200,
        ).execute()

    except Exception as e:
        print(f"[Samaritan Analyst] Statistiche non disponibili ({e}). "
              f"Uso pesi neutri.")
        return {}

    colonne = [c["name"] for c in risposta.get("columnHeaders", [])]
    performance = {}
    for riga in risposta.get("rows", []):
        record = dict(zip(colonne, riga))
        video_id = record.pop("video", None)
        if video_id:
            performance[video_id] = record

    print(f"[Samaritan Analyst] Metriche raccolte per {len(performance)} video.")
    _controlla_contro_il_canale(analytics, performance, inizio, oggi)
    return performance


def _views_del_canale(analytics, inizio, fine):
    """Visualizzazioni totali del canale nel periodo, SENZA dimensione video.

    E' la stessa cifra che YouTube Studio mostra nella scheda Visualizzazioni,
    quindi serve da metro per capire se il dettaglio per video la rispecchia.
    """
    risposta = analytics.reports().query(
        ids="channel==MINE",
        startDate=inizio.isoformat(),
        endDate=fine.isoformat(),
        metrics="views",
    ).execute()
    righe = risposta.get("rows") or []
    if not righe or not righe[0]:
        return 0
    return righe[0][0]


def _controlla_contro_il_canale(analytics, performance, inizio, fine):
    """Confronta la somma per video col totale di canale e lo dice nel log.

    Il 19 settembre 2026 YouTube Studio segnava 9.843 visualizzazioni in sette
    giorni mentre la somma di questo file ne contava 4.488 in novanta: una delle
    due cifre e' sbagliata, e su quella sbagliata pesi_formati() decide cosa far
    produrre. Finche' non si sa quale, queste righe servono a saperlo dal log
    della prossima run invece che a indovinare.
    """
    somma = sum(m.get("views", 0) for m in performance.values())
    try:
        totale = _views_del_canale(analytics, inizio, fine)
        ieri = fine - datetime.timedelta(days=1)
        ultimi_sette = _views_del_canale(
            analytics, fine - datetime.timedelta(days=7), ieri)
    except Exception as e:
        print(f"[Samaritan Analyst] Confronto col totale di canale non riuscito ({e}).")
        return

    print(f"[Samaritan Analyst] Canale: {totale} views in {GIORNI_ANALISI} giorni, "
          f"{ultimi_sette} negli ultimi 7 (fino a ieri). "
          f"Somma per video: {somma}.")
    if totale and somma < totale * 0.9:
        mancanti = totale - somma
        print(f"[Warning Analyst] Il dettaglio per video copre solo il "
              f"{somma / totale:.0%} del totale: {mancanti} visualizzazioni non "
              f"sono attribuite a nessun video, quindi i pesi dei formati sono "
              f"calcolati su una parte sola del canale.")


def aggiorna_performance():
    """Scarica e salva su disco. Se la chiamata fallisce, mantiene il file vecchio."""
    performance = scarica_performance()
    if not performance:
        return _carica_performance_salvata()

    with open(config.FILE_PERFORMANCE, "w", encoding="utf-8") as f:
        json.dump(
            {"aggiornato": datetime.date.today().isoformat(), "video": performance},
            f, ensure_ascii=False, indent=2,
        )
    return performance


def _carica_performance_salvata():
    if not os.path.exists(config.FILE_PERFORMANCE):
        return {}
    try:
        with open(config.FILE_PERFORMANCE, "r", encoding="utf-8") as f:
            return json.load(f).get("video", {})
    except Exception:
        return {}


# ===========================================================================
# PUNTEGGIO
# ===========================================================================
def _punteggio(metriche):
    """Punteggio unico di un video.

    La retention percentuale e' la metrica regina sugli Shorts: decide se
    l'algoritmo continua a spingere il video. Engagement e iscritti guadagnati
    entrano come bonus, non come protagonisti.
    """
    views = max(metriche.get("views", 0), 1)
    retention = metriche.get("averageViewPercentage", 0.0)      # 0-100
    like_ratio = metriche.get("likes", 0) / views * 100
    commenti_ratio = metriche.get("comments", 0) / views * 100
    iscritti_ratio = metriche.get("subscribersGained", 0) / views * 100

    return (
        retention
        + like_ratio * 4.0
        + commenti_ratio * 10.0        # i commenti sono il segnale piu' pesante
        + iscritti_ratio * 25.0        # obiettivo reale: iscritti per l'YPP
    )


def _video_valutati():
    """Incrocia cronologia (formato + hook) con performance (retention)."""
    from brain import carica_cronologia, _normalizza

    performance = _carica_performance_salvata() or aggiorna_performance()
    if not performance:
        return []

    valutati = []
    for voce in carica_cronologia():
        voce = _normalizza(voce)
        video_id = voce.get("video_id")
        if not video_id or video_id not in performance:
            continue
        valutati.append({
            "stile": voce.get("stile", ""),
            "titolo": voce.get("titolo", ""),
            # Le voci vecchie non hanno la lingua scritta e sono italiane.
            "lingua": (voce.get("lingua") or "it").lower(),
            "hook": voce.get("estratto_script", "").split(".")[0].strip(),
            "punteggio": _punteggio(performance[video_id]),
            "views": performance[video_id].get("views", 0),
        })
    return valutati


# ===========================================================================
# OUTPUT PER IL CERVELLO
# ===========================================================================
def pesi_formati():
    """Peso di selezione per ogni formato, centrato su 1.0.

    I formati senza dati sufficienti restano a 1.0: e' voluto. Serve a
    continuare a esplorare invece di incastrarsi sul primo formato fortunato.
    """
    valutati = _video_valutati()
    if not valutati:
        return {}

    per_formato = {}
    for v in valutati:
        per_formato.setdefault(v["stile"], []).append(v["punteggio"])

    affidabili = {
        stile: sum(p) / len(p)
        for stile, p in per_formato.items()
        if len(p) >= MIN_VIDEO_PER_FORMATO
    }
    if not affidabili:
        return {}

    media = sum(affidabili.values()) / len(affidabili)
    if media <= 0:
        return {}

    return {
        stile: max(PESO_MIN, min(PESO_MAX, punteggio / media))
        for stile, punteggio in affidabili.items()
    }


def migliori_hook(n=3):
    """Le prime frasi dei video andati meglio, da dare in pasto al prompt.

    Solo quelli nella lingua in cui si sta scrivendo adesso: mostrare hook
    italiani a un video inglese non insegna niente e sporca il prompt con
    frasi che non c'entrano.
    """
    import config
    lingua = (config.LINGUA or "it").lower()
    valutati = [v for v in _video_valutati()
                if v["hook"] and v.get("lingua", "it") == lingua]
    valutati.sort(key=lambda v: v["punteggio"], reverse=True)
    return [v["hook"] for v in valutati[:n]]


def stampa_report():
    valutati = _video_valutati()
    if not valutati:
        print("\n[Samaritan Analyst] Nessun dato disponibile.")
        print("Serve almeno un video caricato da Samaritan (con video_id in memoria)")
        print("e un token OAuth con lo scope yt-analytics.readonly.")
        return

    valutati.sort(key=lambda v: v["punteggio"], reverse=True)
    print("\n" + "=" * 70)
    print("REPORT PERFORMANCE SAMARITAN")
    print("=" * 70)
    for v in valutati[:15]:
        print(f"{v['punteggio']:7.1f} | {v['views']:>6} views | "
              f"{v['stile'][:22]:<22} | {v['titolo'][:40]}")

    pesi = pesi_formati()
    if pesi:
        print("\nPESI CALCOLATI (>1 = esce piu' spesso):")
        for stile, peso in sorted(pesi.items(), key=lambda x: -x[1]):
            print(f"  {peso:5.2f}  {stile}")
    else:
        print(f"\nAncora pochi dati: servono {MIN_VIDEO_PER_FORMATO}+ video "
              f"per formato prima di pesare le scelte.")


if __name__ == "__main__":
    aggiorna_performance()
    stampa_report()
