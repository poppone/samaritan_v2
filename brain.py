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

MIN_PAROLE_SCRIPT = 45
MAX_PAROLE_SCRIPT = 95


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
    t = titolo.strip().strip('"').strip("'")
    # "#Shorts" nel titolo non serve piu' dal 2023 e ruba caratteri utili
    t = re.sub(r"#shorts\b", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:100]                        # limite duro YouTube


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


def valida_script(titolo, script):
    """Ritorna (True, "") se lo script e' pubblicabile, altrimenti (False, motivo)."""
    if not titolo or not script:
        return False, "titolo o script vuoti"

    inizio = script.lower().lstrip(" \"'-–—")
    for vietata in APERTURE_VIETATE:
        if inizio.startswith(vietata):
            return False, f"apertura debole vietata: '{vietata}'"

    n_parole = len(script.split())
    if n_parole < MIN_PAROLE_SCRIPT:
        return False, f"script troppo corto ({n_parole} parole)"
    if n_parole > MAX_PAROLE_SCRIPT:
        return False, f"script troppo lungo ({n_parole} parole, lo Short sforerebbe)"

    return True, ""


# ===========================================================================
# GENERAZIONE
# ===========================================================================
def _costruisci_system_prompt(formato, notizie, ultimi_titoli, hook_vincenti):
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
            "(replicane la struttura, NON il contenuto):\n"
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

    return (
        f"Sei il Lead Social Media Manager di '{config.NOME_CANALE}', canale YouTube "
        "Gaming italiano. Scrivi uno script per uno Short ad ALTISSIMA RETENTION "
        "(24-30 secondi, quindi 55-85 parole).\n\n"
        f"FORMATO RICHIESTO: {formato} - {meta['descrizione']}\n\n"
        f"NOTIZIE GAMING REALI DI OGGI:\n{blocco_notizie}\n\n"
        f"{vincolo_fatti}"
        f"{blocco_hook}\n"
        "REGOLE TASSATIVE:\n"
        "1. PRIMA FRASE = HOOK. Deve bloccare lo scroll in 3 secondi. "
        "VIETATO iniziare con saluti ('Ciao', 'Raga', 'Benvenuti', 'Oggi vi parlo'). "
        "Inizia con una contraddizione, un numero shock o un'accusa diretta allo "
        "spettatore (es: 'Stai sbagliando tutto su...', 'Nessuno ti ha detto che...').\n"
        "2. SEAMLESS LOOP: l'ultima frase deve ricollegarsi in modo naturale alla "
        "prima parola dello script, cosi' il video riparte senza stacco percepibile.\n"
        "3. RITMO: frasi corte. Una informazione per frase. Niente subordinate.\n"
        f"4. CTA fluida e breve a '{config.NOME_CANALE}', mai piu' di 6 parole, "
        "mai in apertura.\n"
        "5. TITOLO: massimo 70 caratteri, keyword del gioco all'inizio, UNA sola "
        "emoji, NIENTE '#Shorts'.\n"
        "6. GIOCO: il titolo ESATTO e UFFICIALE del videogioco di cui parla lo "
        "Short, come appare sullo store (es: 'Cyberpunk 2077', 'ELDEN RING', "
        "'Counter-Strike 2'). Serve a scaricare gameplay reale di quel gioco: "
        "niente abbreviazioni, niente nomi di saghe generiche. Se lo Short non "
        "parla di un gioco specifico, metti stringa vuota.\n"
        "7. QUERY VIDEO: in INGLESE, 2-4 parole, usata solo come ripiego se il "
        "gioco non e' reperibile (es: 'cyberpunk gameplay', 'fps shooter action').\n"
        "8. DESCRIZIONE: 2 righe + UNA domanda finale che spinga a commentare.\n"
        "9. NON riusare questi titoli gia' pubblicati:\n"
        f"   {json.dumps(ultimi_titoli, ensure_ascii=False)}\n\n"
        "Rispondi ESCLUSIVAMENTE con un JSON valido con le chiavi: "
        "'titolo', 'script', 'gioco', 'query_video', 'descrizione', "
        "'indice_notizia'."
    )


def genera_script_samaritan(tema=None):
    """Genera il pacchetto contenuto completo.

    Ritorna un dict: titolo, script, query_video, descrizione, fonte, stile.
    """
    notizie = recupera_trend_gaming_online()
    formato = scegli_formato(notizie)

    cronologia = carica_cronologia()
    ultimi_titoli = [_normalizza(i).get("titolo", "") for i in cronologia[-12:]]

    try:
        from analyst import migliori_hook
        hook_vincenti = migliori_hook(n=3)
    except Exception:
        hook_vincenti = []

    system_prompt = _costruisci_system_prompt(
        formato, notizie, ultimi_titoli, hook_vincenti
    )
    prompt_utente = "Scrivi lo Short di oggi."
    if tema:
        prompt_utente += f" Focus specifico richiesto: {tema}"

    modelli = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    for modello in modelli:
        for tentativo in range(1, 3):       # 2 tentativi per modello
            try:
                print(f"[Samaritan Brain] {modello} - tentativo {tentativo} "
                      f"(formato {formato})...")
                response = client.chat.completions.create(
                    model=modello,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_utente},
                    ],
                    temperature=0.9,
                    max_tokens=700,
                    response_format={"type": "json_object"},
                )
                contenuto = response.choices[0].message.content
                if not contenuto:
                    continue

                data = json.loads(contenuto)
                titolo = _pulisci_titolo(str(data.get("titolo", "")))
                script = str(data.get("script", "")).strip()
                query_video = str(data.get("query_video", "gameplay")).strip()
                descrizione = str(data.get("descrizione", "")).strip()
                gioco = _pulisci_nome_gioco(str(data.get("gioco", "")))

                ok, motivo = valida_script(titolo, script)
                if not ok:
                    print(f"[Samaritan Brain] SCARTATO: {motivo}. Rigenero.")
                    continue

                if "gameplay" not in query_video.lower():
                    query_video = f"{query_video} gameplay"

                # Traccia la fonte reale: trasparenza = segnale di qualita'
                fonte = ""
                try:
                    idx = int(data.get("indice_notizia", -1))
                    if 0 <= idx < len(notizie):
                        fonte = f"{notizie[idx]['titolo']} ({notizie[idx]['fonte']})"
                except (TypeError, ValueError):
                    pass

                risultato = {
                    "titolo": titolo,
                    "script": script,
                    "gioco": gioco,
                    "query_video": query_video,
                    "descrizione": descrizione,
                    "fonte": fonte,
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

    # ----------------------------------------------------------- Fallback
    print("[Samaritan Brain] Tutti i modelli hanno fallito: uso il fallback.")
    # Solo giochi presenti su Steam: cosi' anche il fallback ottiene
    # gameplay reale invece di stock generico.
    gioco = random.choice([
        "Cyberpunk 2077", "ELDEN RING", "Counter-Strike 2",
        "Baldur's Gate 3", "Red Dead Redemption 2",
    ])
    risultato = {
        "titolo": f"{gioco}: il dettaglio che il 99% dei giocatori non ha mai notato",
        "script": (
            f"Stai giocando a {gioco} da anni e non hai mai notato questo dettaglio. "
            "Gli sviluppatori lo hanno nascosto talmente bene che serve rigiocare "
            "la prima missione per accorgersene. Una volta che lo vedi, non riesci "
            f"piu' a ignorarlo. Iscriviti a {config.NOME_CANALE} per gli altri. "
            f"E stai giocando a {gioco} da anni senza accorgertene."
        ),
        "gioco": gioco,
        "query_video": f"{gioco.lower()} gameplay",
        "descrizione": (
            f"Un dettaglio di {gioco} che passa inosservato praticamente a tutti.\n"
            f"Altri segreti gaming ogni giorno su {config.NOME_CANALE}.\n\n"
            "Tu l'avevi notato? Scrivilo nei commenti."
        ),
        "fonte": "",
        "stile": formato,
    }
    salva_in_cronologia(risultato)
    return risultato


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
