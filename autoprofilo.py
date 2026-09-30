# -*- coding: utf-8 -*-
"""
Il canale che si definisce da solo, e poi si ritara.

Chi installa Samaritan scegliendo "Altro" nella pagina scrive solo di cosa
parla il canale ("di pesca sportiva", "di giardinaggio"). Tutto il resto, cioe'
di cosa parla ogni video, dove cercare le notizie in italiano e in inglese,
quali clip di riserva cercare su Pexels, quali nomi muovono pubblico, tag,
hashtag e categoria YouTube, lo scrive qui il modello, una volta, e lo salva in
`canale_auto.json` accanto a canale.json.

Poi si ritara: ogni GIORNI_RITARATURA giorni lo riscrive guardando i numeri
veri del canale, cioe' cosa cerca davvero il pubblico su YouTube (termini di
ricerca dell'Analytics) e quali titoli sono andati meglio e peggio. Le ricerche
di notizie si spostano cosi' verso quello che funziona.

Tre regole:
  - i campi scritti a mano in canale.json vincono sempre (profilo.py);
  - l'argomento deve essere ammesso da YouTube: il modello lo dice
    ('ammesso'), e un no ferma la pipeline invece di fare un canale che
    verrebbe demonetizzato o chiuso;
  - se il modello non risponde o scrive un profilo che non passa la
    validazione, il canale continua con quello che ha (i ripieghi di
    profilo.py o l'ultima definizione buona): meglio un video generico che
    nessun video.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import config
import profilo

GIORNI_RITARATURA = 14

# I campi che il modello puo' scrivere. Nome, handle, uscite, fuso,
# telegiornale e materiale restano di chi installa.
CAMPI_AUTO = (
    "descrizione_argomento", "descrizione_canale", "soggetto",
    "soggetto_plurale", "genere", "pubblico", "esempi_soggetto",
    "esempi_query_video", "ricerche", "parole_calde", "nomi_grossi",
    "tag_fissi", "tag_fissi_lungo", "hashtag_canale", "query_stock_riserva",
    "categoria_youtube",
)

_LISTA = {"type": "array", "items": {"type": "string"}}
_SCHEMA = {
    "name": "profilo_canale",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "ammesso": {"type": "boolean"},
            "motivo": {"type": "string"},
            "descrizione_argomento": {"type": "string"},
            "descrizione_canale": {"type": "string"},
            "soggetto": {"type": "string"},
            "soggetto_plurale": {"type": "string"},
            "genere": {"type": "string", "enum": ["m", "f"]},
            "pubblico": {"type": "string"},
            "esempi_soggetto": _LISTA,
            "esempi_query_video": _LISTA,
            "ricerche_it": _LISTA,
            "ricerche_en": _LISTA,
            "parole_calde_it": _LISTA,
            "nomi_grossi": _LISTA,
            "tag_fissi": _LISTA,
            "hashtag_canale": {"type": "string"},
            "query_stock_riserva": _LISTA,
            "categoria_youtube": {"type": "string",
                                  "enum": ["1", "2", "10", "15", "17", "19", "22",
                                           "23", "24", "25", "26", "27", "28"]},
        },
        "required": ["ammesso", "motivo", "descrizione_argomento",
                     "descrizione_canale", "soggetto", "soggetto_plurale",
                     "genere", "pubblico", "esempi_soggetto",
                     "esempi_query_video", "ricerche_it", "ricerche_en",
                     "parole_calde_it", "nomi_grossi", "tag_fissi",
                     "hashtag_canale", "query_stock_riserva",
                     "categoria_youtube"],
        "additionalProperties": False,
    },
}


class ArgomentoNonAmmesso(RuntimeError):
    """Il modello dice che YouTube non ammette o non monetizza l'argomento."""


def _adesso():
    return datetime.now(timezone.utc)


def serve_definire(contenuto, auto, adesso=None):
    """Va (ri)scritta la definizione? E perche', in chiaro, o ''."""
    if not isinstance(contenuto, dict) or contenuto.get("autodefinisci") is not True:
        return ""
    if not auto:
        return "prima definizione del canale"
    if auto.get("argomento") != contenuto.get("argomento"):
        return "l'argomento del canale e' cambiato"
    try:
        quando = datetime.fromisoformat(auto.get("aggiornato", ""))
    except (TypeError, ValueError):
        return "data dell'ultima definizione illeggibile"
    if (adesso or _adesso()) - quando >= timedelta(days=GIORNI_RITARATURA):
        return f"sono passati {GIORNI_RITARATURA} giorni: ritaratura sui numeri veri"
    return ""


def _numeri_del_canale():
    """Cosa sa il canale di se', in righe da mettere nel prompt. [] all'inizio."""
    righe = []
    try:
        import analyst
        termini = [t["termine"] for t in analyst.termini_di_ricerca()[:15]]
        if termini:
            righe.append("Cosa cerca il pubblico su YouTube prima di arrivare "
                         "al canale: " + ", ".join(termini) + ".")
        valutati = sorted(analyst._video_valutati(), key=lambda v: v["views"],
                          reverse=True)
        if len(valutati) >= 6:
            migliori = [f"{v['titolo']} ({v['views']} viste)" for v in valutati[:5]]
            peggiori = [f"{v['titolo']} ({v['views']} viste)" for v in valutati[-5:]]
            righe.append("Video andati meglio: " + "; ".join(migliori) + ".")
            righe.append("Video andati peggio: " + "; ".join(peggiori) + ".")
    except Exception as e:
        print(f"[Autoprofilo] Numeri del canale non leggibili ({e}).")
    return righe


def _prompt(contenuto, precedente, numeri):
    argomento = contenuto.get("argomento", "")
    righe = [
        "Configuri un canale YouTube di Shorts automatici che racconta notizie "
        f"vere, trovate su Google News, sull'argomento: \"{argomento}\" "
        f"(canale '{contenuto.get('nome_canale', '')}'). Le immagini sono "
        "clip stock senza diritti di Pexels.",
        "",
        "PRIMA DI TUTTO decidi 'ammesso': false se l'argomento e' sessuale o "
        "per adulti, gioco d'azzardo o scommesse, droghe, armi, pirateria o "
        "hacking, truffe o soldi facili, disinformazione medica o complotti, "
        "odio o violenza, o comunque qualcosa che le norme YouTube non "
        "ammettono o non monetizzano. In 'motivo' scrivi perche', in italiano. "
        "Se non e' ammesso, gli altri campi riempili a caso: non si useranno.",
        "",
        "Se e' ammesso, scrivi in italiano:",
        "- descrizione_argomento: l'argomento come nome, dopo 'canale di' "
        "(es. 'pesca sportiva');",
        "- descrizione_canale: come si presenta, dopo 'canale YouTube' "
        "(es. 'di pesca sportiva italiano');",
        "- soggetto: di cosa parla OGNI video, al singolare, un nome che vuole "
        "l'articolo 'il' o 'la' (es. 'tecnica', 'squadra', 'film'), con "
        "soggetto_plurale e genere ('m' o 'f');",
        "- pubblico: chi guarda, dopo 'per' (es. 'chi pesca in mare');",
        "- esempi_soggetto: 3 nomi reali e famosi di quel soggetto;",
        "- ricerche_it e ricerche_en: 4-5 ricerche per Google News, come le "
        "scriverebbe una persona, dalla piu' generale alla piu' specifica, "
        "anche con OR; devono trovare notizie di OGGI, non guide;",
        "- parole_calde_it: 6-8 parole che nei titoli segnalano una notizia "
        "che la gente cerca (es. 'record', 'ufficiale');",
        "- nomi_grossi: 8-12 nomi (persone pubbliche, marchi, eventi) che "
        "muovono pubblico da soli, in minuscolo;",
        "- tag_fissi: 4 tag YouTube; hashtag_canale: uno, senza #;",
        "- esempi_query_video e query_stock_riserva: in INGLESE, 2-4 parole "
        "che descrivono cosa si VEDE, per cercare clip su Pexels "
        "(2 esempi e 5 di riserva), niente nomi propri;",
        "- categoria_youtube: il numero della categoria (1 Film, 2 Motori, "
        "10 Musica, 15 Animali, 17 Sport, 19 Viaggi, 22 Persone e blog, "
        "23 Comicita', 24 Intrattenimento, 25 Notizie e politica, 26 Stile e "
        "consigli, 27 Istruzione, 28 Scienza e tecnologia).",
    ]
    if precedente:
        righe += ["", "DEFINIZIONE ATTUALE (migliorala, non buttarla):",
                  json.dumps(precedente, ensure_ascii=False)]
    if numeri:
        righe += ["", "NUMERI VERI DEL CANALE: sposta ricerche, nomi grossi e "
                  "tag verso quello che funziona e che il pubblico cerca, "
                  "restando sull'argomento:"] + numeri
    righe += ["", "Rispondi SOLO con il JSON richiesto."]
    return "\n".join(righe)


def _campi_dalla_risposta(dati):
    """Dal JSON del modello ai campi del profilo (nomi di profilo.py)."""
    pulisci = lambda xs, n: [str(x).strip() for x in (xs or []) if str(x).strip()][:n]
    campi = {
        "descrizione_argomento": str(dati["descrizione_argomento"]).strip(),
        "descrizione_canale": str(dati["descrizione_canale"]).strip(),
        "soggetto": str(dati["soggetto"]).strip(),
        "soggetto_plurale": str(dati["soggetto_plurale"]).strip(),
        "genere": dati["genere"],
        "pubblico": str(dati["pubblico"]).strip(),
        "esempi_soggetto": pulisci(dati["esempi_soggetto"], 3),
        "esempi_query_video": pulisci(dati["esempi_query_video"], 2),
        "ricerche": {"it": pulisci(dati["ricerche_it"], 5)},
        "nomi_grossi": [x.lower() for x in pulisci(dati["nomi_grossi"], 12)],
        "tag_fissi": pulisci(dati["tag_fissi"], 5),
        "hashtag_canale": str(dati["hashtag_canale"]).strip().lstrip("#").replace(" ", ""),
        "query_stock_riserva": pulisci(dati["query_stock_riserva"], 6),
        "categoria_youtube": str(dati["categoria_youtube"]),
    }
    en = pulisci(dati["ricerche_en"], 5)
    if en:
        campi["ricerche"]["en"] = en
    calde = pulisci(dati["parole_calde_it"], 8)
    if calde:
        campi["parole_calde"] = {"it": calde}
    # Una lista vuota la validazione la boccerebbe: meglio lasciare il
    # ripiego di profilo.py.
    return {k: v for k, v in campi.items() if v not in ("", [], {})}


def chiedi_al_modello(contenuto, precedente=None, numeri=()):
    """La definizione scritta dal modello: dict di campi del profilo.

    Solleva ArgomentoNonAmmesso se il modello dice che l'argomento non va,
    RuntimeError se nessun modello risponde.
    """
    from brain import client, _estrai_json
    prompt = _prompt(contenuto, precedente, list(numeri))
    ultimo_errore = None
    for modello in config.GROQ_MODELLI:
        try:
            parametri = {
                "model": modello,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 4000,
                "response_format": {"type": "json_schema", "json_schema": _SCHEMA},
            }
            if "gpt-oss" in modello:
                parametri["reasoning_effort"] = "low"
            risposta = client.chat.completions.create(**parametri)
            dati = _estrai_json(risposta.choices[0].message.content)
        except Exception as e:
            ultimo_errore = e
            print(f"[Autoprofilo] {modello}: {e}")
            continue
        if dati.get("ammesso") is not True:
            raise ArgomentoNonAmmesso(
                f"L'argomento '{contenuto.get('argomento')}' non e' adatto a "
                f"YouTube: {dati.get('motivo') or 'nessun motivo dato'}.")
        return _campi_dalla_risposta(dati)
    raise RuntimeError(f"Nessun modello ha scritto la definizione ({ultimo_errore}).")


def aggiorna_se_serve(file=None, adesso=None):
    """Scrive o ritara canale_auto.json se serve. Ritorna True se l'ha fatto.

    Non solleva mai, tranne ArgomentoNonAmmesso: un argomento vietato deve
    fermare la pipeline, tutto il resto no.
    """
    file = file or profilo.percorso()
    contenuto = profilo.contenuto_del_file(file)
    auto = profilo.leggi_autodefinizione(file)
    perche = serve_definire(contenuto, auto, adesso)
    if not perche:
        return False
    print(f"[Autoprofilo] Definisco il canale da solo: {perche}.")

    precedente = (auto or {}).get("campi") if auto and \
        auto.get("argomento") == contenuto.get("argomento") else None
    try:
        campi = chiedi_al_modello(contenuto, precedente, _numeri_del_canale())
    except ArgomentoNonAmmesso:
        raise
    except Exception as e:
        print(f"[Autoprofilo] Definizione non riuscita ({e}): continuo con "
              f"quella che c'e'.")
        return False

    # I campi del file vincono: si prova il profilo cosi' come verra' letto.
    unito = dict(campi)
    unito.update(contenuto)
    try:
        profilo.da_dizionario(unito, "definizione automatica")
    except profilo.ProfiloNonValido as e:
        print(f"[Autoprofilo] La definizione del modello non passa ({e}): "
              f"continuo con quella che c'e'.")
        return False

    nuovo = {
        "_leggimi": ("Scritto da Samaritan (autoprofilo.py) a partire "
                     "dall'argomento di canale.json, e ritarato ogni "
                     f"{GIORNI_RITARATURA} giorni sui numeri del canale. "
                     "I campi scritti in canale.json vincono su questi."),
        "argomento": contenuto.get("argomento"),
        "aggiornato": (adesso or _adesso()).isoformat(timespec="seconds"),
        "campi": campi,
    }
    with open(profilo.file_autodefinizione(file), "w", encoding="utf-8") as f:
        json.dump(nuovo, f, ensure_ascii=False, indent=2)
    profilo.imposta(None)            # si rilegge con i campi nuovi
    p = profilo.attivo()
    print(f"[Autoprofilo] Canale definito: ogni video parla di "
          f"{p.g('un')} {p.soggetto}; ricerche: {', '.join(p.ricerche_per('it'))}.")
    return True
