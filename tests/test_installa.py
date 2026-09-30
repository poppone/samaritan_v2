# -*- coding: utf-8 -*-
"""Test sulla pagina di installazione (installa/index.html).

La pagina scrive canale.json dal browser e deve dire di si' e di no negli
stessi casi di profilo.py: se approvasse un profilo che profilo.py rifiuta,
il cliente scoprirebbe l'errore la notte, alla prima partenza fallita.

La pagina gira davvero, in Chromium senza rete (Playwright, gia' installato
sulla macchina). Dove Node o Playwright mancano, questi test si saltano; i
controlli sul testo della pagina girano sempre.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

import pytest

import profilo

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = os.path.join(RADICE, "installa", "index.html")
SCRIPT = os.path.join(RADICE, "tests", "pagina_installa.cjs")


def _modulo(**campi):
    """Un modulo compilato come lo compilerebbe una persona."""
    base = {"nome_canale": "Cucina Lampo", "handle": "@CucinaLampo",
            "tipo": "altro", "argomento": "di cucina", "soggetto": "ricetta",
            "soggetto_plurale": "", "genere": "", "ricerche_it": "ricette\nchef OR ristorante",
            "ricerche_en": "", "uscite": [{"orario": "12:30", "lingua": "it"},
                                          {"orario": "19:00", "lingua": "it"}],
            "fuso": "Europe/Rome", "categoria_youtube": "26",
            "tag_fissi": "cucina, ricette", "hashtag_canale": "#CucinaLampo",
            "esempi_soggetto": "Carbonara, Tiramisu", "query_stock_riserva": "cooking pasta",
            "nomi_grossi": "Cracco, Cannavacciuolo"}
    base.update(campi)
    return base


# Moduli che la pagina puo' produrre: validi e no. Per ognuno pagina e
# profilo.py devono essere d'accordo.
MODULI = [
    _modulo(),
    _modulo(ricerche_it="", ricerche_en="recipes\nfood trend",
            uscite=[{"orario": "18:00", "lingua": "en"}]),
    _modulo(soggetto="ricetta veloce"),                              # manca il plurale
    _modulo(soggetto="ricetta veloce", soggetto_plurale="ricette veloci", genere="f"),
    _modulo(ricerche_it=""),                                         # nessuna ricerca
    _modulo(handle="CucinaLampo"),                                   # senza @
    _modulo(nome_canale=""),
    _modulo(argomento="", soggetto=""),
    _modulo(fuso="Europa/Roma"),
    _modulo(fuso="America/New_York", uscite=[{"orario": "09:00", "lingua": "en"}]),
    _modulo(uscite=[]),
    _modulo(uscite=[{"orario": "23:30", "lingua": "it"}]),
    _modulo(uscite=[{"orario": "10:00", "lingua": "it"}]),
    _modulo(uscite=[{"orario": "11:00", "lingua": "it"}, {"orario": "12:00", "lingua": "it"}]),
    _modulo(uscite=[{"orario": "14:00", "lingua": "it"}, {"orario": "14:00", "lingua": "en"}]),
    _modulo(uscite=[{"orario": "", "lingua": "it"}]),
    _modulo(uscite=[{"orario": o, "lingua": "it"} for o in ("14:00", "16:00", "18:00", "20:00", "22:00")]),
    _modulo(uscite=[{"orario": o, "lingua": l} for o, l in
                    (("14:00", "it"), ("18:00", "it"), ("20:00", "en"), ("21:00", "en"))]),
    _modulo(tipo="gaming", ricerche_it=""),
    _modulo(tipo="gaming", ricerche_it="", ricerche_en="indie games"),
    _modulo(tipo="gaming", handle="", ricerche_it=""),
    _modulo(argomento="di attualita'", soggetto="tema", telegiornale=True,
            ricerche_it="ultime notizie Italia", categoria_youtube="25"),
    _modulo(tipo="gaming", ricerche_it="", telegiornale=True),     # ignorato
    # "Altro" con il solo argomento: il resto lo scrive Samaritan.
    _modulo(tipo="altro", argomento="di pesca sportiva", soggetto="", ricerche_it="",
            nomi_grossi="", tag_fissi="", esempi_soggetto="", query_stock_riserva=""),
    _modulo(tipo="altro", argomento="di scommesse sportive", soggetto="", ricerche_it=""),
    _modulo(tipo="altro", argomento="di video porno", soggetto="", ricerche_it=""),
]
TELEGIORNALE, GAMING_CON_TELEGIORNALE, SOLO_ARGOMENTO = 21, 22, 23
TESTI_VIETATI = ["di cucina", "di porno", "hot dog", "Top Gun", "casinò online",
                 "di One Piece", "per adulti", "Scommesse sul calcio"]

# Lunghezze intorno al blocco di 128 byte di BLAKE2b.
BLAKE = [bytes(range(256))[:n] * 1 for n in (0, 1, 64, 127, 128, 129, 255)] + [
    bytes((i * 7) % 256 for i in range(300))]


def _profilo_python(dati):
    """Gli errori secondo profilo.py: stringa vuota se il profilo va bene."""
    try:
        profilo.da_dizionario(dati)
        return ""
    except profilo.ProfiloNonValido as e:
        return str(e)


def _node():
    node = shutil.which("node")
    if not node:
        return None, None
    try:
        radice = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    if not os.path.isdir(os.path.join(radice, "playwright")):
        return None, None
    return node, radice


@pytest.fixture(scope="module")
def pagina(tmp_path_factory):
    node, moduli_node = _node()
    if not node:
        pytest.skip("Node o Playwright non installati: la pagina non si puo' aprire.")
    casi = tmp_path_factory.mktemp("installa") / "casi.json"
    casi.write_text(json.dumps({"moduli": MODULI, "profili": [], "testi": TESTI_VIETATI,
                                "blake": [b.hex() for b in BLAKE]}), encoding="utf-8")
    ambiente = dict(os.environ, NODE_PATH=moduli_node)
    ambiente.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    esito = subprocess.run([node, SCRIPT, PAGINA, str(casi)], cwd=RADICE,
                           env=ambiente, capture_output=True, text=True, timeout=120)
    if esito.returncode != 0 and "Executable doesn't exist" in esito.stderr:
        pytest.skip("Chromium di Playwright non installato.")
    assert esito.returncode == 0, esito.stderr
    return json.loads(esito.stdout)


class TestPaginaNelBrowser:

    def test_si_apre_senza_errori_e_senza_rete(self, pagina):
        assert pagina["errori_pagina"] == []
        # Nessuna richiesta all'apertura: la libreria di cifratura si scarica
        # solo quando si salvano le chiavi.
        assert pagina["richieste"] == []
        # E niente resta nel browser.
        assert pagina["memoria"] == {"local": 0, "session": 0}

    def test_il_modulo_di_partenza_da_un_canale_json_valido(self, pagina):
        """Chi scrive solo nome e handle e salva ottiene un canale di
        videogiochi con le uscite delle 14:00 e delle 18:00 in italiano."""
        dati = pagina["predefinito"]
        assert json.loads(pagina["anteprima"]) == dati
        p = profilo.da_dizionario(dati)
        assert p.nome_canale == "Il mio canale"
        assert p.handle == "@IlMioCanale"
        assert p.materiale == "steam"
        assert p.uscite == [{"orario": "14:00", "lingua": "it"},
                            {"orario": "18:00", "lingua": "it"}]
        assert p.fuso == "Europe/Rome"
        assert profilo.abbina_cron(p.uscite, p.fuso) == [0, 1]

    def test_un_canale_di_cucina_non_va_su_steam(self, pagina):
        caso = pagina["costruiti"][0]
        assert caso["errori"] == []
        p = profilo.da_dizionario(caso["profilo"])
        assert p.materiale == "stock"
        assert p.ricerche == {"it": ["ricette", "chef OR ristorante"]}
        assert p.hashtag_canale == "CucinaLampo"
        assert p.nomi_grossi == ["cracco", "cannavacciuolo"]
        assert p.categoria_youtube == "26"

    def test_lo_stile_telegiornale_arriva_nel_profilo(self, pagina):
        caso = pagina["costruiti"][TELEGIORNALE]
        assert caso["errori"] == []
        p = profilo.da_dizionario(caso["profilo"])
        assert p.telegiornale is True
        assert p.temi_esclusi == profilo.TEMI_DELICATI
        assert p.categoria_youtube == "25"

    def test_solo_l_argomento_basta(self, pagina):
        caso = pagina["costruiti"][SOLO_ARGOMENTO]
        assert caso["errori"] == []
        assert caso["profilo"]["autodefinisci"] is True
        p = profilo.da_dizionario(caso["profilo"])
        assert p.autodefinisci is True
        assert p.ricerche_per("it") == ("pesca sportiva",)

    def test_ogni_argomento_del_menu_e_un_profilo_valido(self, pagina):
        assert len(pagina["argomenti"]) >= 12
        for caso in pagina["argomenti"]:
            assert caso["errori"] == [], caso["chiave"]
            p = profilo.da_dizionario(caso["profilo"])
            assert p.materiale == "stock", caso["chiave"]
            assert p.ricerche_per("en"), caso["chiave"]
            assert not p.autodefinisci, caso["chiave"]
        tg = [c for c in pagina["argomenti"] if c["chiave"] == "telegiornale"][0]
        assert profilo.da_dizionario(tg["profilo"]).telegiornale is True

    def test_i_temi_vietati_sono_quelli_di_profilo_py(self, pagina):
        assert tuple(pagina["vietati"]) == profilo.ARGOMENTI_VIETATI
        assert pagina["vietato"] == [profilo.argomento_vietato(t) for t in TESTI_VIETATI]

    def test_un_canale_di_videogiochi_non_diventa_telegiornale(self, pagina):
        caso = pagina["costruiti"][GAMING_CON_TELEGIORNALE]
        assert "telegiornale" not in caso["profilo"]

    @pytest.mark.parametrize("indice", range(len(MODULI)))
    def test_pagina_e_profilo_py_sono_d_accordo(self, pagina, indice):
        caso = pagina["costruiti"][indice]
        errore_python = _profilo_python(caso["profilo"])
        assert bool(caso["errori"]) == bool(errore_python), (
            MODULI[indice], caso["errori"], errore_python)

    def test_le_finestre_sono_quelle_di_profilo_py(self, pagina):
        assert [tuple(f) for f in pagina["finestre"]] == profilo.finestre("Europe/Rome")

    def test_le_costanti_sono_quelle_di_profilo_py(self, pagina):
        c = pagina["costanti"]
        assert tuple(tuple(x) for x in c["CRON_USCITE"]) == profilo.CRON_USCITE
        assert c["MARGINE_MINIMO_ORE"] == profilo.MARGINE_MINIMO_ORE
        assert c["ANTICIPO_PARTENZA_ORE"] == profilo.ANTICIPO_PARTENZA_ORE
        assert tuple(c["LINGUE"]) == tuple(profilo.LINGUE)

    def test_blake2b_come_quella_di_python(self, pagina):
        """Il nonce del sealed box: se sbaglia, GitHub non riesce a
        decifrare i Secrets e la pipeline parte senza chiavi."""
        for dato, (corto, lungo) in zip(BLAKE, pagina["blake"]):
            assert corto == hashlib.blake2b(dato, digest_size=24).hexdigest(), len(dato)
            assert lungo == hashlib.blake2b(dato, digest_size=64).hexdigest(), len(dato)

    def test_legge_l_indirizzo_del_repository(self, pagina):
        assert pagina["repository"] == [
            {"owner": "mario", "repo": "samaritan"},
            {"owner": "mario", "repo": "samaritan"}, None]


@pytest.fixture(scope="module")
def testo():
    with open(PAGINA, encoding="utf-8") as f:
        return f.read()


class TestPaginaConGitHubFinto:
    """Il percorso vero dei pulsanti, contro un GitHub finto dentro il
    browser (tests/pagina_installa.cjs): si controlla cosa la pagina manda."""

    def test_nessun_errore_durante_i_passi(self, pagina):
        assert pagina["errori_pagina_github"] == []
        assert pagina["github"]["memoria"] == {"local": 0, "session": 0}

    def test_il_modello_non_si_installa_su_se_stesso(self, pagina):
        g = pagina["github"]
        assert "errore" in g["modello"]["classe"]
        assert "non la tua copia" in g["modello"]["testo"]
        assert "errore" in g["poppone"]["classe"]
        assert g["verifica"]["testo"] == "Collegato a mario/samaritan (privato)."

    def test_ogni_chiamata_porta_il_token(self, pagina):
        g = pagina["github"]
        tutte = g["chiamate_primo"] + g["chiamate_secondo"] + g["chiamate_prova"]
        assert tutte and all(c["auth"] == "Bearer github_pat_finto" for c in tutte)

    def _albero(self, chiamate):
        return next(c["corpo"] for c in chiamate
                    if c["chiave"].endswith("/git/trees"))["tree"]

    def test_il_primo_salvataggio_toglie_la_memoria_del_modello(self, pagina):
        """In un solo commit: canale.json, cronologia vuota, niente
        performance.json e niente clip di chi ha fatto il modello (sono sue:
        Samaritan non usa video di altri). Il LEGGIMI delle clip resta."""
        g = pagina["github"]
        assert "memoria azzerata" in g["primo"]["testo"]
        voci = {v["path"]: v for v in self._albero(g["chiamate_primo"])}
        assert set(voci) == {"canale.json", "cronologia_trend.json",
                             "performance.json", "clip_mie/gol.mp4"}
        assert voci["cronologia_trend.json"]["content"] == "[]\n"
        assert voci["performance.json"]["sha"] is None
        assert voci["clip_mie/gol.mp4"]["sha"] is None
        profilo.da_dizionario(json.loads(voci["canale.json"]["content"]))
        chiavi = [c["chiave"] for c in g["chiamate_primo"]]
        assert chiavi.index("POST /repos/mario/samaritan/git/commits") < chiavi.index(
            "PATCH /repos/mario/samaritan/git/refs/heads/main")
        assert "PUT /repos/mario/samaritan/actions/workflows/promo.yml/disable" in chiavi

    def test_i_salvataggi_dopo_non_toccano_la_memoria(self, pagina):
        """Chi cambia un orario non deve perdere quello che il suo canale ha
        gia' raccontato."""
        g = pagina["github"]
        assert g["secondo"]["testo"] == "canale.json aggiornato."
        assert [v["path"] for v in self._albero(g["chiamate_secondo"])] == ["canale.json"]
        assert not any("promo.yml" in c["chiave"] for c in g["chiamate_secondo"])

    def test_la_prova_e_un_video_privato(self, pagina):
        g = pagina["github"]
        lancio = g["chiamate_prova"][0]
        assert lancio["chiave"].endswith("/actions/workflows/samaritan.yml/dispatches")
        assert lancio["corpo"] == {"ref": "main", "inputs": {"privacy": "private"}}
        assert g["prova"]["testo"].endswith("/actions/runs/1")

    def test_il_workflow_accetta_quello_che_la_pagina_manda(self):
        with open(os.path.join(RADICE, ".github", "workflows", "samaritan.yml"),
                  encoding="utf-8") as f:
            workflow = f.read()
        privacy = re.search(r"\n      privacy:\n(.*?)\n      \w+:\n", workflow, re.S)
        assert privacy, "il workflow non ha piu' l'ingresso 'privacy'"
        assert re.search(r"options: \[[^\]]*\bprivate\b", privacy.group(1))


class TestTestoDellaPagina:
    """Promesse che si leggono nel sorgente, senza browser."""

    def test_script_esterni_solo_da_cdn_ammessi(self, testo):
        for indirizzo in re.findall(r'https://[^"\'\s`)]+', testo):
            dominio = indirizzo.split("/")[2]
            assert dominio in {
                "api.github.com", "github.com", "cdn.jsdelivr.net",
                "accounts.google.com", "oauth2.googleapis.com",
                "www.googleapis.com", "console.cloud.google.com",
                "console.groq.com", "www.pexels.com", "elevenlabs.io",
                "t.me"}, indirizzo
        assert "cdn.jsdelivr.net/npm/tweetnacl@1.0.3/" in testo
        assert "integrity" in testo

    def test_il_token_non_si_salva_nel_browser(self, testo):
        assert "localStorage" not in testo.replace("niente localStorage", "")
        # Il viaggio verso Google salva solo quello che serve al ritorno, e
        # mai il token GitHub.
        salvato = re.search(r'sessionStorage\.setItem\("samaritan-oauth",(.*?)\);', testo, re.S)
        assert salvato, "manca il salvataggio per il ritorno da Google"
        assert "token" not in salvato.group(1)

    def test_google_da_un_refresh_token_che_dura(self, testo):
        assert "access_type" in testo and '"offline"' in testo
        assert "prompt" in testo and '"consent"' in testo
        assert "Pubblica app" in testo          # in Test il token muore in 7 giorni

    def test_non_chiede_password(self, testo):
        assert 'type="password" id="password' not in testo
        assert "non ti chiede mai la password" in testo
