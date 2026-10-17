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
import re
import json
import datetime

import config

GIORNI_ANALISI = 90
MIN_VIDEO_PER_FORMATO = 2      # sotto questa soglia il dato non e' affidabile
PESO_MIN, PESO_MAX = 0.35, 2.5

# Quanti termini di ricerca tenere. Sono le parole che la gente ha davvero
# scritto nella ricerca di YouTube per finire su un video del canale: l'unico
# dato vero su cosa cerca questo pubblico, invece di quello che immaginiamo.
# VENTICINQUE E' IL MASSIMO CHE L'API ACCETTA per questo rapporto, e chiederne
# di piu' non fa arrivare meno righe: fa fallire tutta la richiesta con un 500
# e 'FIELD_UNKNOWN_VALUE' su max-results, che non sembra affatto un limite
# superato. Con 40 il 21 settembre 2026 non e' tornato niente.
MAX_TERMINI_RICERCA = 25
# Il rapporto per video ne restituisce al massimo 200 per richiesta: oltre si
# va avanti a pagine (startIndex). Dieci pagine sono duemila video, ben oltre
# quelli che un canale pubblica in novanta giorni.
RIGHE_PER_PAGINA = 200
MAX_PAGINE_VIDEO = 10
# Sotto questa soglia un termine e' un caso isolato, non una domanda ricorrente.
MIN_VIEWS_TERMINE = 2
# Parole che compaiono nei termini ma non dicono di che argomento si tratta.
# Il nome del canale si aggiunge da solo piu' sotto: chi cerca 'poppone tv'
# cerca il canale, non un argomento.
PAROLE_VUOTE_RICERCA = frozenset((
    "shorts", "short", "video", "videos", "youtube", "ita", "italiano",
    "gaming", "game", "games", "gioco", "giochi", "videogiochi", "canale",
    "nuovo", "nuova", "come", "cosa", "quando", "dove", "perche", "with",
    "that", "this", "from", "your", "what", "when", "best", "top",
    # Articoli, preposizioni e verbi ausiliari: il 29 settembre 2026 dalla
    # ricerca "chi e' che ha perso un sandalo" uscivano "ha" e "un", e la
    # notizia piu' grossa del giorno risultava cercata dal pubblico perche'
    # nel titolo c'era "ha un prezzo".
    "il", "lo", "la", "gli", "le", "un", "una", "uno", "di", "da", "in",
    "con", "su", "per", "tra", "fra", "ha", "ho", "hai", "hanno", "che",
    "chi", "non", "si", "mi", "ti", "ci", "del", "della", "dei", "degli",
    "delle", "al", "alla", "ai", "nel", "nella", "sul", "sulla", "ed",
    "the", "an", "of", "to", "on", "for", "and", "is", "it", "how", "why",
    "who", "are", "was", "can", "no", "not",
))


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

        risposte = _scarica_pagine_video(analytics, inizio, oggi)

    except Exception as e:
        print(f"[Samaritan Analyst] Statistiche non disponibili ({e}). "
              f"Uso pesi neutri.")
        return {}

    performance = {}
    for risposta in risposte:
        colonne = [c["name"] for c in risposta.get("columnHeaders", [])]
        for riga in risposta.get("rows", []) or []:
            record = dict(zip(colonne, riga))
            video_id = record.pop("video", None)
            if video_id and video_id not in performance:
                performance[video_id] = record

    print(f"[Samaritan Analyst] Metriche raccolte per {len(performance)} video.")
    _controlla_contro_il_canale(analytics, performance, inizio, oggi)
    return performance


def _scarica_pagine_video(analytics, inizio, fine):
    """Tutte le pagine del rapporto per video, non solo la prima.

    YouTube restituisce al massimo RIGHE_PER_PAGINA video per richiesta,
    ordinati per visualizzazioni. Con quattro Short al giorno, in novanta
    giorni i video sono piu' di duecento: dal 14 ottobre 2026 il file restava
    fermo a 197 video e ogni giorno ne entravano tanti nuovi quanti ne
    uscivano di vecchi, e i video nuovi con poche visualizzazioni rischiavano
    di restare fuori. Si chiede quindi pagina dopo pagina con startIndex.
    La prima pagina che fallisce solleva (come prima); una successiva che
    fallisce non butta quelle gia' arrivate.
    """
    risposte = []
    for numero in range(MAX_PAGINE_VIDEO):
        try:
            risposta = analytics.reports().query(
                ids="channel==MINE",
                startDate=inizio.isoformat(),
                endDate=fine.isoformat(),
                metrics=("views,averageViewPercentage,averageViewDuration,"
                         "likes,comments,subscribersGained"),
                dimensions="video",
                sort="-views",
                maxResults=RIGHE_PER_PAGINA,
                startIndex=1 + numero * RIGHE_PER_PAGINA,
            ).execute()
        except Exception as e:
            if not risposte:
                raise
            print(f"[Warning Analyst] Pagina {numero + 1} delle metriche non "
                  f"arrivata ({e}): tengo le {numero} gia' scaricate.")
            break
        risposte.append(risposta)
        if len(risposta.get("rows") or []) < RIGHE_PER_PAGINA:
            break
    return risposte


def ultimo_giorno_con_dati():
    """L'ultimo giorno per cui YouTube Analytics ha gia' dei numeri.

    YouTube Analytics arriva con due-tre giorni di ritardo: il 13 ottobre
    2026 il file era aggiornato quel giorno stesso ma i video piu' recenti
    con dei numeri erano del 9-10, e da fuori sembrava fermo. Scriverlo nel
    file ('dati_fino_al') distingue il ritardo normale da un aggiornamento
    rotto. None se non si riesce a saperlo.
    """
    try:
        from googleapiclient.discovery import build
        from uploader import ottieni_credenziali, ha_scope_analytics

        credenziali = ottieni_credenziali()
        if not ha_scope_analytics(credenziali):
            return None
        analytics = build("youtubeAnalytics", "v2", credentials=credenziali)
        oggi = datetime.date.today()
        risposta = analytics.reports().query(
            ids="channel==MINE",
            startDate=(oggi - datetime.timedelta(days=14)).isoformat(),
            endDate=oggi.isoformat(),
            metrics="views",
            dimensions="day",
            sort="day",
        ).execute()
    except Exception as e:
        print(f"[Samaritan Analyst] Ultimo giorno con dati non disponibile ({e}).")
        return None
    giorni = [r[0] for r in (risposta.get("rows") or []) if r and r[0]]
    return max(giorni) if giorni else None


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


def scarica_termini_di_ricerca():
    """Cosa la gente ha scritto nella ricerca di YouTube per arrivare qui.

    Ritorna [{"termine": ..., "views": N}] dal piu' visto al meno, o [] se il
    dato non e' disponibile. E' l'unico segnale vero su cosa cerca questo
    pubblico: tutto il resto di come Samaritan sceglie l'argomento e' un
    criterio scritto a mano, quindi un'ipotesi.

    Nota: YouTube non attribuisce tutte le visualizzazioni da ricerca a un
    termine, e i termini rari li nasconde. La lista e' quindi una cima, non un
    censimento, e va letta come "queste sono le domande che tornano".
    """
    try:
        from googleapiclient.discovery import build
        from uploader import ottieni_credenziali, ha_scope_analytics

        credenziali = ottieni_credenziali()
        if not ha_scope_analytics(credenziali):
            return []

        analytics = build("youtubeAnalytics", "v2", credentials=credenziali)
        oggi = datetime.date.today()
        inizio = oggi - datetime.timedelta(days=GIORNI_ANALISI)

        risposta = analytics.reports().query(
            ids="channel==MINE",
            startDate=inizio.isoformat(),
            endDate=oggi.isoformat(),
            metrics="views",
            dimensions="insightTrafficSourceDetail",
            filters="insightTrafficSourceType==YT_SEARCH",
            sort="-views",
            maxResults=MAX_TERMINI_RICERCA,
        ).execute()
    except Exception as e:
        print(f"[Samaritan Analyst] Termini di ricerca non disponibili ({e}).")
        return []

    termini = []
    for riga in risposta.get("rows") or []:
        if len(riga) < 2:
            continue
        termine = (riga[0] or "").strip()
        views = riga[1] or 0
        if termine and views >= MIN_VIEWS_TERMINE:
            termini.append({"termine": termine, "views": views})

    if termini:
        cima = ", ".join(f"{t['termine']} ({t['views']})" for t in termini[:6])
        print(f"[Samaritan Analyst] Il pubblico arriva cercando: {cima}.")
    else:
        print("[Samaritan Analyst] Nessun termine di ricerca con abbastanza "
              "visualizzazioni: la scelta dell'argomento resta come prima.")
    return termini


# Come si chiamano in italiano le sorgenti di traffico che YouTube restituisce
# in sigla. Quelle che mancano si stampano com'e': meglio una sigla che una
# riga persa.
NOMI_SORGENTI = {
    "SHORTS": "feed Shorts",
    "YT_SEARCH": "ricerca YouTube",
    "RELATED_VIDEO": "video suggeriti",
    "SUBSCRIBER": "home e iscrizioni",
    "NOTIFICATION": "notifiche",
    "EXT_URL": "siti esterni",
    "PLAYLIST": "playlist",
    "YT_CHANNEL": "pagina del canale",
    "NO_LINK_EMBEDDED": "player incorporato",
    "NO_LINK_OTHER": "sorgente non dichiarata",
    "ADVERTISING": "pubblicita'",
    "CAMPAIGN_CARD": "schede e campagne",
    "END_SCREEN": "schermata finale",
    "ANNOTATION": "annotazioni",
    "SOUND_PAGE": "pagina dell'audio",
    "HASHTAGS": "hashtag",
}


def scarica_sorgenti_di_traffico():
    """Da dove arrivano davvero le visualizzazioni.

    Ritorna [{"sorgente": ..., "views": N}] dal piu' grosso al piu' piccolo.
    Serve a sapere se ha senso lavorare sulla ricerca: su un canale di soli
    Short il pubblico puo' arrivare quasi tutto dal feed, e in quel caso le
    parole cercate non sono il segnale da inseguire. E' una domanda a cui si
    risponde coi numeri, non a intuito.
    """
    try:
        from googleapiclient.discovery import build
        from uploader import ottieni_credenziali, ha_scope_analytics

        credenziali = ottieni_credenziali()
        if not ha_scope_analytics(credenziali):
            return []

        analytics = build("youtubeAnalytics", "v2", credentials=credenziali)
        oggi = datetime.date.today()
        inizio = oggi - datetime.timedelta(days=GIORNI_ANALISI)

        risposta = analytics.reports().query(
            ids="channel==MINE",
            startDate=inizio.isoformat(),
            endDate=oggi.isoformat(),
            metrics="views",
            dimensions="insightTrafficSourceType",
            sort="-views",
        ).execute()
    except Exception as e:
        print(f"[Samaritan Analyst] Sorgenti di traffico non disponibili ({e}).")
        return []

    sorgenti = []
    for riga in risposta.get("rows") or []:
        if len(riga) < 2:
            continue
        sigla = (riga[0] or "").strip()
        if sigla:
            sorgenti.append({"sorgente": sigla, "views": riga[1] or 0})

    totale = sum(s["views"] for s in sorgenti)
    if totale:
        cima = ", ".join(
            f"{NOMI_SORGENTI.get(s['sorgente'], s['sorgente'])} "
            f"{s['views'] / totale:.0%}"
            for s in sorgenti[:5]
        )
        print(f"[Samaritan Analyst] Il pubblico arriva da: {cima}.")
    return sorgenti


def aggiorna_performance():
    """Scarica e salva su disco. Se la chiamata fallisce, mantiene il file vecchio."""
    performance = scarica_performance()
    if not performance:
        return _carica_performance_salvata()

    # I termini di ricerca stanno nello stesso file delle metriche perche' e'
    # uno dei due soli file che il workflow ricommitta: un file nuovo non
    # sopravviverebbe alla fine della run.
    termini = scarica_termini_di_ricerca() or termini_di_ricerca()
    sorgenti = scarica_sorgenti_di_traffico() or sorgenti_di_traffico()

    # 'aggiornato' e' quando gira lo script, 'dati_fino_al' fin dove arriva
    # YouTube (due-tre giorni prima): chi legge il file vede i due ritardi.
    dati_fino_al = ultimo_giorno_con_dati() or _dati_fino_al_salvato()

    with open(config.FILE_PERFORMANCE, "w", encoding="utf-8") as f:
        json.dump(
            {"aggiornato": datetime.date.today().isoformat(),
             "dati_fino_al": dati_fino_al,
             "video": performance,
             "ricerche": termini,
             "sorgenti": sorgenti},
            f, ensure_ascii=False, indent=2,
        )
    return performance


def termini_di_ricerca():
    """I termini salvati dall'ultima volta, dal piu' visto al meno."""
    if not os.path.exists(config.FILE_PERFORMANCE):
        return []
    try:
        with open(config.FILE_PERFORMANCE, "r", encoding="utf-8") as f:
            salvati = json.load(f).get("ricerche") or []
    except Exception:
        return []
    return [t for t in salvati if isinstance(t, dict) and t.get("termine")]


def sorgenti_di_traffico():
    """La ripartizione salvata dall'ultima volta, dalla piu' grossa in giu'."""
    if not os.path.exists(config.FILE_PERFORMANCE):
        return []
    try:
        with open(config.FILE_PERFORMANCE, "r", encoding="utf-8") as f:
            salvate = json.load(f).get("sorgenti") or []
    except Exception:
        return []
    return [s for s in salvate if isinstance(s, dict) and s.get("sorgente")]


def parole_cercate():
    """Le parole che ricorrono nelle ricerche del pubblico.

    Non i termini interi: chi cerca "gta 6 data uscita" e chi cerca "gta 6
    leak" stanno chiedendo della stessa cosa, e una notizia non ripete mai la
    frase intera. Quindi si scende alle parole e si buttano quelle che non
    dicono di che argomento si parla.
    """
    vuote = set(PAROLE_VUOTE_RICERCA)
    for pezzo in (config.NOME_CANALE or "").split():
        vuote.add(pezzo.strip().lower())
    vuote.add((config.HANDLE_CANALE or "").lstrip("@").lower())

    parole = set()
    for voce in termini_di_ricerca():
        for parola in re.split(r"[^\w]+", (voce.get("termine") or "").lower()):
            # Le sigle corte contano ("gta", "f1"), le paroline no.
            if len(parola) >= 2 and parola not in vuote and not parola.isdigit():
                parole.add(parola)
    return frozenset(parole)


def _dati_fino_al_salvato():
    if not os.path.exists(config.FILE_PERFORMANCE):
        return None
    try:
        with open(config.FILE_PERFORMANCE, "r", encoding="utf-8") as f:
            return json.load(f).get("dati_fino_al")
    except Exception:
        return None


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
