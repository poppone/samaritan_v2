# -*- coding: utf-8 -*-
"""Test sulle clip d'archivio coerenti con la voce.

Davide, 29 ottobre 2026: nei video le immagini di sfondo spesso non c'entrano
con quello che la voce sta dicendo (un'auto elettrica in carica sotto una
notizia di MotoGP). La causa: UNA sola ricerca Pexels per tutto lo Short,
riempita con ricerche di riserva prese a caso e montata mescolata.

Questi test difendono le tre correzioni: una ricerca per scena nell'ordine
dello script, il controllo di pertinenza (una sola chiamata al modello per
video, che se fallisce non blocca niente) e il montaggio nell'ordine delle
scene. Nessun test tocca la rete.
"""
import json
import os

import pytest

import brain
import config
import gameplay
import lungo
import profilo
import stock


ESEMPIO_TG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "canale.telegiornale.esempio.json")


def _motori(monkeypatch, riserva=("car driving highway", "race track aerial")):
    """Un telegiornale di motori con materiale d'archivio, come il canale
    "Motori in 60 secondi"."""
    with open(ESEMPIO_TG, encoding="utf-8") as f:
        dati = json.load(f)
    dati.update(materiale="stock", telegiornale=True,
                query_stock_riserva=list(riserva))
    p = profilo.da_dizionario(dati)
    monkeypatch.setattr(profilo, "_attivo", p)
    return p


# ===========================================================================
# BRAIN: le ricerche di scena
# ===========================================================================
class TestPulisciQueryScene:

    @pytest.fixture
    def motori(self, monkeypatch):
        return _motori(monkeypatch)

    def test_tiene_le_scene_in_ordine(self, motori):
        scene = brain.pulisci_query_scene(
            ["motorcycle racing track", "car factory assembly line",
             "fuel pump gas station"], "race track")
        assert scene == ["motorcycle racing track", "car factory assembly line",
                         "fuel pump gas station"]

    def test_senza_il_campo_ripiega_sulla_query_video(self, motori):
        assert brain.pulisci_query_scene(None, "race track") == ["race track"]
        assert brain.pulisci_query_scene([], "race track") == ["race track"]
        assert brain.pulisci_query_scene(["  ", ""], "race track") == ["race track"]
        assert brain.pulisci_query_scene(42, "race track") == ["race track"]

    def test_una_stringa_sola_diventa_una_scena(self, motori):
        assert brain.pulisci_query_scene("car showroom", "x") == ["car showroom"]

    def test_toglie_i_doppioni_e_rispetta_il_massimo(self, motori):
        scene = brain.pulisci_query_scene(
            ["a b", "A B", "c d", "e f", "g h", "i j", "k l"], "x")
        assert scene == ["a b", "c d", "e f", "g h", "i j"]

    def test_tronca_le_ricerche_troppo_lunghe(self, motori):
        scene = brain.pulisci_query_scene(
            ["one two three four five six seven eight"], "x")
        assert scene == ["one two three four five six"]

    def test_sul_canale_gaming_aggiunge_gameplay_come_alla_query_video(self):
        assert brain.pulisci_query_scene(["sniper aiming"], "fps gameplay") == \
            ["sniper aiming gameplay"]


class TestPromptESchema:

    def test_lo_schema_chiede_la_lista_delle_scene(self):
        proprieta = brain._SCHEMA_RISPOSTA["schema"]["properties"]
        assert proprieta["query_scene"] == {"type": "array",
                                            "items": {"type": "string"}}
        assert "query_scene" in brain._SCHEMA_RISPOSTA["schema"]["required"]

    def test_il_prompt_chiede_una_scena_per_pezzo_di_script(self):
        prompt = brain._costruisci_system_prompt("VIRAL_HOOK_NEWS", [], [], [])
        assert "QUERY SCENE" in prompt
        assert "NELL'ORDINE in cui la voce le dice" in prompt
        assert "'query_scene'" in prompt

    def test_il_telegiornale_chiede_immagini_dell_argomento(self, monkeypatch):
        _motori(monkeypatch)
        prompt = brain._costruisci_system_prompt("VIRAL_HOOK_NEWS", [], [], [])
        assert "QUERY VIDEO e QUERY SCENE" in prompt
        assert "motorcycle racing track" in prompt
        # Il divieto sulle immagini delicate resta.
        assert "Mai violenza, armi, incidenti" in prompt

    def test_lo_schema_del_video_lungo_chiede_le_scene(self):
        schema = lungo._SCHEMA_SCALETTA["schema"]
        assert "query_scene" in schema["properties"]
        assert "query_scene" in schema["required"]


class TestLaGenerazionePassaLeScene:
    NOTIZIA = {"titolo": "These Xbox Players Got GTA 6 For Free The Hard Way",
               "fonte": "Engadget", "link": "https://news.google.com/x",
               "apparizioni": 1, "punteggio": 10, "sul_tema": False}
    SCRIPT = ("Two Xbox players got GTA 6 without paying a cent, but not the "
              "way you think. The headline says they did it the hard way. "
              "What does the hard way even mean for the biggest game of the "
              "decade? Would you grind for it or just buy it on day one? "
              "Tell me below, and follow Poppone TV for the next twist. "
              "Two Xbox players got it, so what would you do?")

    def _genera(self, monkeypatch, risposta):
        class FinteCompletions:
            @staticmethod
            def create(**kw):
                if kw["messages"][0]["content"].startswith("Sei un fact-checker"):
                    testo = json.dumps({"dettagli_inventati": []})
                else:
                    testo = json.dumps(risposta)

                class Scelta:
                    class message:
                        content = testo

                class Risposta:
                    choices = [Scelta()]
                return Risposta()

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        monkeypatch.setattr(brain, "client", FintoClient())
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(self.NOTIZIA)])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        return brain.genera_script_samaritan()

    def _risposta(self, **extra):
        dati = {"titolo": "GTA 6: Xbox players got it the hard way",
                "script": self.SCRIPT, "gioco": "Grand Theft Auto VI",
                "query_video": "open world city", "descrizione": "Would you?",
                "indice_notizia": 0}
        dati.update(extra)
        return dati

    def test_le_scene_arrivano_nel_risultato(self, monkeypatch):
        dati = self._genera(monkeypatch, self._risposta(
            query_scene=["xbox controller hands", "city traffic night"]))
        assert dati["query_scene"] == ["xbox controller hands gameplay",
                                       "city traffic night gameplay"]

    def test_senza_scene_resta_la_query_video(self, monkeypatch):
        dati = self._genera(monkeypatch, self._risposta())
        assert dati["query_scene"] == [dati["query_video"]]


class TestVideoLungo:
    SCALETTA = {
        "titolo": "Hollow Knight Silksong: cosa non torna",
        "gioco": "Hollow Knight: Silksong",
        "query_video": "silksong",
        "descrizione": "Tre righe di descrizione.",
        "indice_notizia": 0,
        "sezioni": [
            {"titolo": "Da dove nasce", "contenuto": "La notizia."},
            {"titolo": "Come si gioca", "contenuto": "Le meccaniche."},
            {"titolo": "Cosa ne penso", "contenuto": "Il giudizio."},
        ],
    }

    def _genera(self, monkeypatch, tmp_path, scaletta):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA",
                            str(tmp_path / "cronologia.json"))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda *a, **k: [])

        def finto_chiedi(system, utente, schema=None, max_tokens=2000):
            if schema is not None:
                return json.dumps(scaletta)
            return " ".join(["parola"] * 120)

        monkeypatch.setattr(lungo, "_chiedi", finto_chiedi)
        return lungo.genera_video_lungo()

    def test_una_scena_per_sezione(self, monkeypatch, tmp_path):
        scaletta = dict(self.SCALETTA,
                        query_scene=["bug insect", "sword fight", "castle ruins"])
        dati = self._genera(monkeypatch, tmp_path, scaletta)
        assert dati["query_scene"] == ["bug insect gameplay",
                                       "sword fight gameplay",
                                       "castle ruins gameplay"]

    def test_senza_scene_ripiega_sulla_query_video(self, monkeypatch, tmp_path):
        dati = self._genera(monkeypatch, tmp_path, dict(self.SCALETTA))
        assert dati["query_scene"] == [dati["query_video"]]


# ===========================================================================
# BRAIN: il giudizio di pertinenza
# ===========================================================================
def _client_che_risponde(testi, chiamate):
    class FinteCompletions:
        @staticmethod
        def create(**kw):
            chiamate.append(kw)
            testo = testi.pop(0)
            if isinstance(testo, Exception):
                raise testo

            class Scelta:
                class message:
                    content = testo

            class Risposta:
                choices = [Scelta()]
            return Risposta()

    class FintoClient:
        class chat:
            completions = FinteCompletions()

    return FintoClient()


class TestScegliClipPertinenti:

    def test_legge_il_giudizio(self, monkeypatch):
        chiamate = []
        monkeypatch.setattr(brain, "client", _client_che_risponde([json.dumps(
            {"scene": [{"scena": 1, "clip": [2]},
                       {"scena": 2, "clip": [2, 1, 9]}]})], chiamate))
        verdetto = brain.scegli_clip_pertinenti(
            ["motorcycle racing track", "fuel pump gas station"],
            [["electric car charging", "motorcycles racing on a track"],
             ["man refueling car at gas station", "fuel nozzle close up"]],
            "La MotoGP torna a Misano. E la benzina sale ancora.")
        # Indici da zero, nell'ordine del giudizio, quelli inesistenti via.
        assert verdetto == {0: [1], 1: [1, 0]}
        assert len(chiamate) == 1
        utente = chiamate[0]["messages"][1]["content"]
        assert "SCENA 1: motorcycle racing track" in utente
        assert "2. motorcycles racing on a track" in utente
        assert "MotoGP torna a Misano" in utente

    def test_se_la_chiamata_fallisce_ritorna_none(self, monkeypatch):
        chiamate = []
        monkeypatch.setattr(brain, "client", _client_che_risponde(
            [RuntimeError("429 rate limit")], chiamate))
        assert brain.scegli_clip_pertinenti(["a b"], [["c d"]]) is None
        # Una sola prova: il controllo non deve mangiarsi la quota.
        assert len(chiamate) == 1

    def test_senza_candidate_non_chiama_il_modello(self, monkeypatch):
        chiamate = []
        monkeypatch.setattr(brain, "client", _client_che_risponde([], chiamate))
        assert brain.scegli_clip_pertinenti(["a b"], [[]]) is None
        assert chiamate == []


# ===========================================================================
# STOCK: descrizioni, riserva, scarico per scena
# ===========================================================================
class TestDescrizioneDaUrl:

    def test_ricava_la_descrizione_dallo_slug(self):
        assert stock.descrizione_da_url(
            "https://www.pexels.com/video/a-red-car-on-a-race-track-123/") == \
            "a red car on a race track"

    def test_senza_slug_e_vuota(self):
        assert stock.descrizione_da_url("https://www.pexels.com/video/123/") == ""
        assert stock.descrizione_da_url("") == ""
        assert stock.descrizione_da_url(None) == ""


class TestRiservaVicina:

    RISERVA = ["car driving highway", "car dashboard night",
               "electric car charging", "race track aerial", "car showroom"]

    def test_sotto_la_motogp_va_la_pista_non_la_colonnina(self):
        ordine = stock.riserva_in_ordine(self.RISERVA,
                                         "motorcycle racing track")
        assert ordine[0] == "race track aerial"
        assert ordine.index("race track aerial") < \
            ordine.index("electric car charging")

    def test_a_parita_resta_l_ordine_del_profilo(self):
        assert stock.riserva_in_ordine(self.RISERVA, "pasta cooking") == \
            self.RISERVA

    def test_non_sorteggia(self, monkeypatch):
        import random
        monkeypatch.setattr(random, "sample",
                            lambda *a, **k: pytest.fail("niente sorteggi"))
        monkeypatch.setattr(random, "shuffle",
                            lambda *a, **k: pytest.fail("niente sorteggi"))
        stock.riserva_in_ordine(self.RISERVA, "fuel pump gas station")


class _FintaRisposta:
    def __init__(self, dati=None, contenuto=b""):
        self._dati = dati
        self.content = contenuto

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture
def pexels(monkeypatch, tmp_path):
    """Pexels finto: `catalogo` dice cosa risponde ogni ricerca, `ricerche` e
    `scaricati` registrano cosa e' stato chiesto."""
    monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
    monkeypatch.setattr(config, "VIDEO_W", 1080)
    monkeypatch.setattr(config, "VIDEO_H", 1920)
    monkeypatch.setattr(config, "NUM_CLIP_SFONDO", 4)
    stato = {"catalogo": {}, "ricerche": [], "scaricati": []}

    def finto_get(url, headers=None, params=None, timeout=None):
        if "api.pexels.com" in url:
            stato["ricerche"].append(params["query"])
            videos = []
            for vid, slug in stato["catalogo"].get(params["query"], []):
                videos.append({
                    "id": vid,
                    "url": f"https://www.pexels.com/video/{slug}-{vid}/",
                    "video_files": [{"width": 1080, "height": 1920,
                                     "link": f"https://cdn/{vid}.mp4"}],
                })
            return _FintaRisposta({"videos": videos})
        stato["scaricati"].append(url)
        return _FintaRisposta(contenuto=b"x" * 60_000)

    monkeypatch.setattr(stock.requests, "get", finto_get)
    return stato


class TestScaricaClipPerScene:

    SCENE = ["motorcycle racing track", "fuel pump gas station"]

    def _catalogo(self, pexels):
        pexels["catalogo"] = {
            "motorcycle racing track": [(1, "electric-car-charging"),
                                        (2, "motorcycles-racing-on-a-track"),
                                        (3, "motorbike-rider-on-circuit")],
            "fuel pump gas station": [(4, "woman-in-an-office"),
                                      (5, "man-refueling-car-at-gas-station")],
        }

    def test_scarta_le_clip_fuori_tema_con_una_sola_chiamata(self, pexels,
                                                             monkeypatch):
        self._catalogo(pexels)
        giudizi = []

        def giudice(scene, descrizioni, contesto=""):
            giudizi.append((scene, descrizioni, contesto))
            return {0: [1, 2], 1: [1]}

        monkeypatch.setattr(brain, "scegli_clip_pertinenti", giudice)
        clip = stock.scarica_clip_per_scene(self.SCENE, quante=4,
                                            contesto="MotoGP e benzina")
        assert len(giudizi) == 1
        assert giudizi[0][1][0] == ["electric car charging",
                                    "motorcycles racing on a track",
                                    "motorbike rider on circuit"]
        # Due per scena, nell'ordine delle scene; l'auto in carica e
        # l'ufficio non si scaricano nemmeno.
        assert [s for _, s in clip] == [0, 0, 1]
        assert pexels["scaricati"] == ["https://cdn/2.mp4", "https://cdn/3.mp4",
                                       "https://cdn/5.mp4"]
        # La riserva non serve: le scene hanno trovato abbastanza.
        assert pexels["ricerche"] == self.SCENE

    def test_se_il_giudizio_fallisce_usa_le_candidate_in_ordine(self, pexels,
                                                                monkeypatch):
        self._catalogo(pexels)
        monkeypatch.setattr(brain, "scegli_clip_pertinenti",
                            lambda *a, **k: None)
        clip = stock.scarica_clip_per_scene(self.SCENE, quante=2)
        assert [s for _, s in clip] == [0, 1]
        assert pexels["scaricati"] == ["https://cdn/1.mp4", "https://cdn/4.mp4"]

    def test_il_giudizio_vero_che_fallisce_non_blocca(self, pexels, monkeypatch):
        # Il client di brain alza un'eccezione: il video si fa lo stesso.
        self._catalogo(pexels)
        monkeypatch.setattr(brain, "client", _client_che_risponde(
            [RuntimeError("503")], []))
        clip = stock.scarica_clip_per_scene(self.SCENE, quante=2)
        assert len(clip) == 2

    def test_la_riserva_e_l_ultimo_ripiego_e_la_piu_vicina(self, pexels,
                                                           monkeypatch):
        _motori(monkeypatch, ["electric car charging", "car showroom",
                              "race track aerial"])
        pexels["catalogo"] = {
            "motorcycle racing track": [(1, "woman-in-an-office")],
            "race track aerial": [(7, "aerial-view-of-a-race-track"),
                                  (8, "race-track-from-above")],
            "electric car charging": [(9, "electric-car-charging")],
        }
        monkeypatch.setattr(brain, "scegli_clip_pertinenti",
                            lambda scene, d, c="": {0: []})
        clip = stock.scarica_clip_per_scene(["motorcycle racing track"],
                                            quante=3)
        assert pexels["ricerche"] == ["motorcycle racing track",
                                      "race track aerial"]
        assert pexels["scaricati"] == ["https://cdn/7.mp4", "https://cdn/8.mp4"]
        assert [s for _, s in clip] == [0, 0]

    def test_meglio_una_clip_scartata_che_nessun_video(self, pexels,
                                                       monkeypatch):
        _motori(monkeypatch, ["car showroom"])
        pexels["catalogo"] = {"motorcycle racing track":
                              [(1, "woman-in-an-office")]}
        monkeypatch.setattr(brain, "scegli_clip_pertinenti",
                            lambda scene, d, c="": {0: []})
        clip = stock.scarica_clip_per_scene(["motorcycle racing track"])
        assert pexels["scaricati"] == ["https://cdn/1.mp4"]
        assert [s for _, s in clip] == [0]

    def test_la_vecchia_funzione_resta(self, pexels, monkeypatch):
        pexels["catalogo"] = {"car showroom": [(1, "a-car-showroom")]}
        monkeypatch.setattr(brain, "scegli_clip_pertinenti",
                            lambda scene, d, c="": {0: [0]})
        percorsi = stock.scarica_clip_sfondo("car showroom", quante=1)
        assert len(percorsi) == 1 and percorsi[0].endswith("bg_1.mp4")


# ===========================================================================
# MONTAGGIO: le clip seguono l'ordine delle scene
# ===========================================================================
class TestOrdineDelMontaggio:

    def _sorgenti(self, scene):
        return [{"tipo": "video", "path": f"bg_{i}.mp4", "gioco": None,
                 "scena": s, "scene_totali": 3} for i, s in enumerate(scene)]

    def _scaletta(self, sorgenti, durata=30.0, passo=2.5):
        usi, scelte, t = {}, [], 0.0
        while t < durata:
            scelte.append(stock.scegli_sorgente(sorgenti, t, durata, usi))
            t += passo
        return scelte

    def test_ogni_scena_nella_sua_finestra(self):
        sorgenti = self._sorgenti([0, 1, 2])
        scelte = self._scaletta(sorgenti)
        assert [s["scena"] for s in scelte] == [0] * 4 + [1] * 4 + [2] * 4

    def test_due_clip_della_stessa_scena_si_alternano(self):
        sorgenti = self._sorgenti([0, 0, 1, 2])
        scelte = self._scaletta(sorgenti)
        assert [s["path"] for s in scelte[:4]] == \
            ["bg_0.mp4", "bg_1.mp4", "bg_0.mp4", "bg_1.mp4"]

    def test_una_scena_senza_clip_la_copre_la_vicina(self):
        # La scena 1 non ha trovato niente: la sua finestra la copre la 0,
        # e la 2 resta al suo posto in fondo.
        sorgenti = self._sorgenti([0, 2])
        scelte = self._scaletta(sorgenti)
        assert [s["scena"] for s in scelte] == [0] * 8 + [2] * 4

    def test_il_materiale_ufficiale_si_alterna_con_la_scena(self):
        sorgenti = self._sorgenti([0, 1, 2]) + [
            {"tipo": "video", "path": "trailer.mp4", "gioco": "X"}]
        scelte = self._scaletta(sorgenti)
        assert scelte[0]["path"] == "bg_0.mp4"
        assert scelte[1]["path"] == "trailer.mp4"
        assert all(s.get("scena") in (0, None) for s in scelte[:4])

    def test_il_montaggio_usa_l_ordine_per_scena(self):
        """maker.py non si importa nei test della CI (moviepy): il controllo
        e' sul sorgente, come in test_confezionamento."""
        import os
        radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(radice, "maker.py"), encoding="utf-8") as f:
            maker_py = f.read()
        assert "scegli_sorgente(utilizzabili, coperto, durata_totale, usi)" \
            in maker_py
        assert "query_scene=query_scene, contesto=testo_per_audio" in maker_py
        with open(os.path.join(radice, "main.py"), encoding="utf-8") as f:
            main_py = f.read()
        # Short e video lungo.
        assert main_py.count('query_scene=dati.get("query_scene")') == 2


# ===========================================================================
# GAMEPLAY: il ripiego su Pexels porta le scene
# ===========================================================================
class TestProcuraMateriale:

    def test_le_clip_d_archivio_portano_la_loro_scena(self, monkeypatch,
                                                      tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", False)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "x.json"))
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(tmp_path / "mie"))
        chiamate = []

        def finto(scene, quante=None, contesto=""):
            chiamate.append((list(scene), quante, contesto))
            return [(f"bg_{i}.mp4", i) for i in range(len(scene))]

        monkeypatch.setattr(stock, "scarica_clip_per_scene", finto)
        sorgenti, _ = gameplay.procura_materiale(
            "", query_pexels="race track", minimo=3,
            query_scene=["a b", "c d", "e f", "g h"], contesto="voce")
        # Due clip per scena, cosi' gli stacchi veloci non ripetono le stesse.
        assert chiamate == [(["a b", "c d", "e f", "g h"], 8, "voce")]
        assert [(s["scena"], s["scene_totali"]) for s in sorgenti] == \
            [(0, 4), (1, 4), (2, 4), (3, 4)]

    def test_senza_scene_usa_la_query_video(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", False)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "x.json"))
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(tmp_path / "mie"))
        chiamate = []
        monkeypatch.setattr(stock, "scarica_clip_per_scene",
                            lambda scene, quante=None, contesto="":
                            chiamate.append(list(scene)) or [])
        gameplay.procura_materiale("", query_pexels="race track", minimo=3)
        assert chiamate == [["race track"]]


# ---------------------------------------------------------------------------
# Persone che parlano in pubblico (29/10/2026: un ragazzo a un leggio sotto
# una notizia su Salvini sembrava Salvini)
# ---------------------------------------------------------------------------
class TestPersoneCheParlano:
    def test_leggio_e_comizio_sono_vietati(self):
        assert stock.vietata("man reading a speech at a podium")
        assert stock.vietata("politician speaking at a rally")
        assert stock.vietata("woman with microphone at press conference")

    def test_loghi_e_social_sono_vietati(self):
        assert stock.vietata("youtube logo painted on a stone")
        assert stock.vietata("hand holding phone with tiktok app")

    def test_auto_e_strade_vanno_bene(self):
        assert not stock.vietata("a red car on a race track")
        assert not stock.vietata("traffic on a highway in the rain")
        assert not stock.vietata("")

    def test_cerca_candidate_le_scarta(self, monkeypatch):
        class Risposta:
            def raise_for_status(self):
                pass

            def json(self):
                file_ok = [{"width": 1080, "height": 1920, "link": "x"}]
                return {"videos": [
                    {"id": 1, "url": "https://www.pexels.com/video/"
                     "man-reading-speech-at-podium-1/", "video_files": file_ok},
                    {"id": 2, "url": "https://www.pexels.com/video/"
                     "electric-car-on-the-road-2/", "video_files": file_ok},
                ]}

        monkeypatch.setattr(stock.requests, "get", lambda *a, **k: Risposta())
        trovate = stock.cerca_candidate("self driving car", set())
        assert [c["id"] for c in trovate] == [2]

    def test_il_giudizio_chiede_di_scartarle(self, monkeypatch):
        mandati = []

        class Completamenti:
            def create(self, **k):
                mandati.append(k["messages"][0]["content"])
                raise RuntimeError("niente rete")

        class Client:
            chat = type("C", (), {"completions": Completamenti()})()

        monkeypatch.setattr(brain, "client", Client())
        brain.scegli_clip_pertinenti(["car factory"], [["a car factory"]])
        assert mandati and "leggio" in mandati[0]
