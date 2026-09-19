"""
La veste grafica del video: quello che cambia da uno Short all'altro.

Fino a ieri ogni video di Samaritan usciva identico al precedente: stesso
giallo, sottotitoli sempre alla stessa altezza, stessa barra di avanzamento in
cima, stesso banner, stesso zoom nella stessa direzione. Guardati in fila
sembravano lo stesso video con parole diverse, ed e' esattamente il profilo che
le norme YouTube chiamano "contenuti ripetitivi" e non ammettono alla
monetizzazione.

Qui stanno le vesti: ognuna e' un insieme coerente di scelte visive, e
`scegli_veste()` le alterna un video a testa a giro. Le regole che NON si
toccano, perche' sono leggibilita' e non gusto:

  - i sottotitoli restano fra il 58% e il 74% dell'altezza: piu' in basso
    finiscono sotto i comandi dell'app Shorts
  - la barra di avanzamento sta in cima o non c'e': in fondo la sovrascrive
    la barra di YouTube
  - il testo e' sempre con bordo nero, su qualunque colore
"""
import json

import config

# Tutte le vesti, nell'ordine in cui girano.
#
# colore_testo      : sottotitoli normali
# colore_evidenza   : numeri e parole chiave del titolo
# y_sottotitoli     : altezza dei sottotitoli, in frazione dell'altezza video
# corpo_sottotitoli : dimensione del font dei sottotitoli
# y_gameplay        : dove sta il riquadro 16:9 sullo sfondo sfocato
# luminosita_sfondo : quanto resta acceso lo sfondo sfocato (1.0 = intatto)
# banner            : None se il titolo non compare, altrimenti (altezza, secondi)
# barra             : None se non c'e', altrimenti (spessore in pixel, colore RGB)
# zoom              : "dentro", "fuori" o "alternato" (un segmento per verso)
# intensita_zoom    : quanto e' ampio il movimento Ken Burns
# ritmo             : moltiplicatore della durata degli stacchi (<1 = piu' veloce)
VESTI = [
    {
        "nome": "notte",
        "colore_testo": "#FFE600",
        "colore_evidenza": "#00FF9C",
        "y_sottotitoli": 0.68,
        "corpo_sottotitoli": 115,
        "y_gameplay": 0.30,
        "luminosita_sfondo": 0.42,
        "banner": (0.16, 2.5),
        "barra": (12, (255, 230, 0)),
        "zoom": "dentro",
        "intensita_zoom": 0.08,
        "ritmo": 1.0,
    },
    {
        "nome": "ghiaccio",
        "colore_testo": "#FFFFFF",
        "colore_evidenza": "#4FD8FF",
        "y_sottotitoli": 0.72,
        "corpo_sottotitoli": 98,
        "y_gameplay": 0.34,
        "luminosita_sfondo": 0.50,
        "banner": (0.10, 3.5),
        "barra": None,
        "zoom": "fuori",
        "intensita_zoom": 0.10,
        "ritmo": 1.2,
    },
    {
        "nome": "fuoco",
        "colore_testo": "#FF8A00",
        "colore_evidenza": "#FFE600",
        "y_sottotitoli": 0.64,
        "corpo_sottotitoli": 125,
        "y_gameplay": 0.28,
        "luminosita_sfondo": 0.38,
        "banner": (0.20, 2.0),
        "barra": (16, (255, 90, 0)),
        "zoom": "alternato",
        "intensita_zoom": 0.12,
        "ritmo": 0.85,
    },
    {
        "nome": "pulito",
        "colore_testo": "#FFFFFF",
        "colore_evidenza": "#FFE600",
        "y_sottotitoli": 0.70,
        "corpo_sottotitoli": 105,
        "y_gameplay": 0.32,
        "luminosita_sfondo": 0.55,
        "banner": None,
        "barra": None,
        "zoom": "dentro",
        "intensita_zoom": 0.06,
        "ritmo": 1.1,
    },
    {
        "nome": "arena",
        "colore_testo": "#FFE600",
        "colore_evidenza": "#FF4B4B",
        "y_sottotitoli": 0.60,
        "corpo_sottotitoli": 110,
        "y_gameplay": 0.26,
        "luminosita_sfondo": 0.45,
        "banner": (0.06, 2.8),
        "barra": (6, (255, 255, 255)),
        "zoom": "alternato",
        "intensita_zoom": 0.09,
        "ritmo": 0.95,
    },
]

# Limiti di leggibilita', non di gusto: vedi il commento in testa al modulo.
Y_SOTTOTITOLI_MIN = 0.58
Y_SOTTOTITOLI_MAX = 0.74


def _carica_cronologia():
    """La memoria storica, o lista vuota se il file manca o e' illeggibile."""
    try:
        with open(config.FILE_CRONOLOGIA, "r", encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, list) else []
    except Exception:
        return []


def ultima_veste_usata():
    """Il nome della veste dell'ultimo video che l'ha annotata.

    Come per la rotazione delle voci, la posizione nel giro si legge qui e non
    si calcola contando i video: `brain.py` taglia la cronologia a 200
    elementi, quindi un contatore si fermerebbe da solo dopo qualche mese
    senza dire niente a nessuno.
    """
    for elemento in reversed(_carica_cronologia()):
        if isinstance(elemento, dict) and elemento.get("veste"):
            return elemento["veste"]
    return None


def scegli_veste():
    """La veste di questo video: quella dopo l'ultima annotata."""
    nomi = [v["nome"] for v in VESTI]
    precedente = ultima_veste_usata()
    if precedente in nomi:
        indice = (nomi.index(precedente) + 1) % len(VESTI)
    else:
        indice = 0
    return VESTI[indice]


def segna_veste(nome):
    """Annota sulla cronologia la veste con cui il video e' stato montato.

    Si chiama solo a rendering riuscito: un record che dice 'fuoco' su un video
    mai uscito sposterebbe il giro a vuoto, e la veste saltata non tornerebbe.
    Il workflow committa gia' questo file, quindi il prossimo giro lo ritrova.
    """
    cronologia = _carica_cronologia()
    if not cronologia or not isinstance(cronologia[-1], dict):
        return
    cronologia[-1]["veste"] = nome
    try:
        with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
            json.dump(cronologia, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning Veste] Veste non annotata ({e}): "
              f"il prossimo video potrebbe ripetere questa.")
