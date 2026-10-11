# -*- coding: utf-8 -*-
"""Test sul profilo del canale (profilo.py e canale.json).

Due promesse da tenere. La prima: senza canale.json Poppone TV resta
identico, prompt, ricerche, tag e Steam compresi. La seconda: un canale che
non parla di videogiochi non si ritrova a parlare di videogiochi, e su Steam
non ci va mai. Nessun test tocca la rete.
"""
import json
import os
import re
import subprocess
import sys
import types

import pytest

import brain
import config
import gameplay
import lungo
import profilo

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESEMPIO = os.path.join(RADICE, "canale.esempio.json")

NOTIZIA = {"titolo": "Carbonara, il record della porzione piu' grande",
           "fonte": "Gazzetta del Gusto", "link": "https://news.example.com/c",
           "sommario": "Un ristorante romano ha servito dieci chili di carbonara."}

# Le ricerche di Poppone TV com'erano scritte in brain.LINGUE prima che il
# profilo esistesse. Copiate qui a mano apposta: se qualcuno cambia i valori
# predefiniti per sbaglio, questo test se ne accorge.
RICERCHE_DI_SEMPRE = {
    "it": (
        "videogiochi",
        "videogiochi quando esce aggiornamento",
        'GTA 6 OR Fortnite OR "Call of Duty" OR Minecraft OR Roblox',
        'Pokemon OR Zelda OR Mario OR "Elden Ring" OR "EA FC" OR "Brawl Stars"',
        "videogioco annuncio OR uscita OR gratis OR leak",
    ),
    "en": (
        "video games",
        "video game release date OR free OR leak",
        'GTA 6 OR Fortnite OR "Call of Duty" OR Minecraft OR Roblox',
        'Pokemon OR Zelda OR Mario OR "Elden Ring" OR "EA FC" OR "Brawl Stars"',
        "gaming news announcement OR update",
    ),
}


@pytest.fixture
def cucina(monkeypatch):
    """Il profilo d'esempio, quello del canale di cucina."""
    p = profilo.carica(ESEMPIO)
    monkeypatch.setattr(profilo, "_attivo", p)
    monkeypatch.setattr(config, "NOME_CANALE", p.nome_canale)
    monkeypatch.setattr(config, "HANDLE_CANALE", p.handle)
    return p


def _scrivi(tmp_path, contenuto, nome="canale.json"):
    percorso = tmp_path / nome
    percorso.write_text(json.dumps(contenuto) if not isinstance(contenuto, str)
                        else contenuto, encoding="utf-8")
    return str(percorso)


def _minimo_cucina(**altro):
    dati = {"argomento": "di cucina", "soggetto": "ricetta",
            "ricerche": {"it": ["ricette"]}}
    dati.update(altro)
    return dati


class TestSito:
    def test_un_altro_canale_gaming_non_eredita_il_sito(self):
        assert profilo.da_dizionario({"nome_canale": "Altro"}).sito == ""

    def test_un_canale_puo_scrivere_il_suo(self):
        assert profilo.da_dizionario({"sito": "esempio.it"}).sito == "esempio.it"


class TestSenzaCanaleJson:
    """Il canale di popponetv non ha canale.json e non deve accorgersene."""

    def test_senza_file_vale_il_predefinito(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PROFILO_CANALE", raising=False)
        monkeypatch.setattr(profilo, "FILE_PREDEFINITO", str(tmp_path / "canale.json"))
        p = profilo.carica()
        assert p.origine == "predefinito"
        assert p.nome_canale == "Davide Durazzi"
        assert p.sito == "davidedurazzi.it"
        assert p.handle == "@davidedurazzioff"
        assert p.videogiochi and p.usa_steam
        assert p.categoria_youtube == "20"

    def test_le_ricerche_sono_quelle_di_sempre(self, monkeypatch):
        for lingua, attese in RICERCHE_DI_SEMPRE.items():
            monkeypatch.setattr(config, "LINGUA", lingua)
            assert brain._lingua()["ricerche"] == attese

    def test_il_prompt_dello_short_e_quello_di_sempre(self):
        prompt = brain._costruisci_system_prompt(
            "VIRAL_HOOK_NEWS", [NOTIZIA], [], [], giochi_recenti=["Portal"])
        for pezzo in (
            "canale YouTube Gaming italiano. Scrivi uno script",
            "NOTIZIE GAMING REALI DI OGGI, IN ORDINE DI IMPORTANZA",
            "Parla del gioco di cui parla la notizia, non di un altro gioco "
            "nominato solo come paragone.",
            "conta per chi gioca, con quello che e' noto da sempre su quel "
            "gioco e con una domanda al pubblico.",
            "inventando. Esempio di errore da non ripetere: dal titolo 'These "
            "Xbox Players Got GTA 6 For Free The Hard Way'",
            "trucchi per avere giochi o contenuti a pagamento senza pagare",
            "non solo il gioco nominato: due Short",
            "nome del gioco come PRIMA parola",
            "6. GIOCO: il titolo ESATTO e UFFICIALE del videogioco di cui parla "
            "lo Short, come appare sullo store (es: 'Cyberpunk 2077', 'ELDEN "
            "RING', 'Counter-Strike 2'). Serve a scaricare gameplay reale di "
            "quel gioco",
            "gioco non e' reperibile (es: 'cyberpunk gameplay', 'fps shooter "
            "action').\n8. DESCRIZIONE",
            "annunci o conferme attribuite agli sviluppatori",
            "parla di meccaniche, segreti di gioco o consigli, che non hanno "
            "bisogno di una fonte.",
            'giochi: ["Portal"]',
        ):
            assert pezzo in prompt, pezzo

    def test_le_descrizioni_dei_formati_sono_quelle_di_sempre(self):
        prompt = brain._costruisci_system_prompt("DOMANDA_AL_PUBBLICO", [], [], [])
        assert ("DOMANDA_AL_PUBBLICO - Dilemma gaming che costringe lo "
                "spettatore") in prompt
        assert "usa solo fatti gaming storici e verificabili" in prompt
        prompt = brain._costruisci_system_prompt("EASTER_EGG_SECRET", [], [], [])
        assert "nascosto da uno sviluppatore" in prompt

    def test_il_fact_checker_e_quello_di_sempre(self, monkeypatch):
        visti = []

        class Finto:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        visti.append(kw["messages"][0]["content"])
                        raise RuntimeError("niente rete")

        monkeypatch.setattr(brain, "client", Finto)
        brain._dettagli_inventati("titolo", "script")
        assert "il TITOLO di una notizia gaming, a volte" in visti[0]
        assert "a un gioco diverso da quello di cui parla" in visti[0]
        assert ("caratteristiche del gioco (modalita', mappa, prezzo, "
                "contenuti)") in visti[0]
        assert "fatti noti da sempre sul gioco," in visti[0]

    def test_tag_hashtag_e_descrizione_sono_quelli_di_sempre(self, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", False)
        monkeypatch.setattr(config, "NOME_CANALE", "Poppone TV")
        dati = {"titolo": "Portal: x", "gioco": "Portal", "stile": "VIRAL_HOOK_NEWS"}
        assert brain.costruisci_tag(dati)[:4] == [
            "gaming ita", "videogiochi", "shorts ita", "curiosita gaming"]
        assert brain.costruisci_hashtag(dati) == ["#portal", "#newsgaming", "#gamingita"]
        assert "\nAltri Shorts gaming ogni giorno su Poppone TV" in \
            brain.costruisci_descrizione(dati)
        monkeypatch.setattr(config, "VIDEO_LUNGO", True)
        assert brain.costruisci_tag(dati)[:4] == [
            "gaming ita", "videogiochi", "recensione", "guida gaming"]

    def test_la_query_video_prende_ancora_gameplay(self):
        assert brain.completa_query_video("cyberpunk night city") == \
            "cyberpunk night city gameplay"
        assert brain.completa_query_video("fps gameplay") == "fps gameplay"

    def test_il_video_lungo_e_quello_di_sempre(self):
        prompt = lungo._prompt_scaletta([NOTIZIA], [], ["Portal"])
        assert "canale YouTube di videogiochi. Prepara la SCALETTA" in prompt
        assert "su UN SOLO gioco, diviso in" in prompt
        assert "NOTIZIE GAMING DI OGGI" in prompt
        assert "(es: 'Cyberpunk 2077', 'ELDEN RING'). Serve a scaricare i " \
               "trailer ufficiali di QUEL gioco" in prompt
        assert "10. NON riparlare di questi giochi, gia' usati di recente" in prompt

    def test_riserva_stock_e_categoria_di_sempre(self):
        p = profilo.attivo()
        assert p.query_stock_riserva[0] == "video game action"
        assert len(p.query_stock_riserva) == 6
        assert p.categoria_youtube == "20"

    def test_i_nomi_grossi_contano_ancora(self):
        assert brain._punteggio_notizia("GTA 6, nuovo trailer") > \
            brain._punteggio_notizia("Un piccolo gioco indie, nuovo trailer")


class TestElenchiAllineati:
    """profilo.py non importa brain: i due elenchi si tengono in pari qui."""

    def test_formati(self):
        assert set(profilo.FORMATI) == set(brain.FORMATI_VIDEO)

    def test_lingue(self):
        assert set(profilo.LINGUE) == set(brain.LINGUE)


class TestCanaleDiCucina:
    """Il profilo d'esempio: un canale di cucina non parla di videogiochi."""

    # Parole che in un prompt di cucina non devono esserci. 'gioco' resta
    # ammesso solo come nome del campo JSON, che si toglie prima di cercare.
    _GAMING = re.compile(
        r"gaming|videogioc|\bgioc|giochi|steam|store|trailer|gameplay|"
        r"svilupp|\bgta\b|xbox|fortnite|cyberpunk", re.IGNORECASE)

    def _senza_nome_del_campo(self, testo):
        testo = testo.replace("'gioco'", "").replace(
            "GIOCO (il campo si chiama cosi' per ogni canale)", "")
        return testo

    def _nessun_gaming(self, testo):
        trovate = self._GAMING.findall(self._senza_nome_del_campo(testo))
        assert not trovate, trovate

    def test_il_file_d_esempio_e_valido(self, cucina):
        assert cucina.origine == "canale.esempio.json"
        assert not cucina.videogiochi
        assert cucina.materiale == "stock"

    def test_i_prompt_dello_short_non_parlano_di_videogiochi(self, cucina, monkeypatch):
        for lingua in ("it", "en"):
            monkeypatch.setattr(config, "LINGUA", lingua)
            for formato in brain.FORMATI_VIDEO:
                for notizie in ([], [NOTIZIA]):
                    prompt = brain._costruisci_system_prompt(
                        formato, notizie, ["Tiramisu: il segreto"], ["hook"],
                        ["apertura"], ["Carbonara"], ["notizia"], ["una domanda"])
                    self._nessun_gaming(prompt)

    def test_il_prompt_parla_di_ricette(self, cucina):
        prompt = brain._costruisci_system_prompt(
            "VIRAL_HOOK_NEWS", [NOTIZIA], [], [], giochi_recenti=["Carbonara"])
        assert "canale YouTube di cucina italiana." in prompt
        assert "NOTIZIE DI CUCINA REALI DI OGGI" in prompt
        assert ("Parla della ricetta di cui parla la notizia, non di un'altra "
                "ricetta nominata solo come paragone.") in prompt
        assert "conta per chi cucina a casa" in prompt
        assert "nome della ricetta come PRIMA parola" in prompt
        assert "(es: 'Carbonara', 'Tiramisu', 'Pizza napoletana')" in prompt
        assert "clip stock senza diritti" in prompt
        assert 'ricette: ["Carbonara"]' in prompt
        # Le chiavi della risposta restano quelle: la cronologia non cambia.
        assert "'titolo', 'script', 'gioco', 'query_video'" in prompt

    def test_il_fact_checker_non_parla_di_videogiochi(self, cucina, monkeypatch):
        visti = []

        class Finto:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        visti.append(kw["messages"][0]["content"])
                        raise RuntimeError("niente rete")

        monkeypatch.setattr(brain, "client", Finto)
        brain._dettagli_inventati("titolo", "script")
        self._nessun_gaming(visti[0])
        assert "a una ricetta diversa da quella di cui parla" in visti[0]

    def test_il_video_lungo_non_parla_di_videogiochi(self, cucina, monkeypatch):
        self._nessun_gaming(lungo._prompt_scaletta([NOTIZIA], ["t"], ["Carbonara"]))
        scaletta = {"titolo": "T", "gioco": "",
                    "sezioni": [{"titolo": "a", "contenuto": "b"}] * 3}
        for i, fonte in ((0, ""), (1, "F"), (2, "")):
            self._nessun_gaming(lungo._prompt_sezione(
                scaletta, i, scaletta["sezioni"][i], "coda" if i else "", fonte))
        assert "su questa ricetta" in lungo._prompt_sezione(
            scaletta, 0, scaletta["sezioni"][0], "", "")

        visti = []
        monkeypatch.setattr(lungo, "_chiedi",
                            lambda system, utente, **k: visti.append(system)
                            or "parola " * 100)
        lungo._scrivi_sezione(scaletta, 0, scaletta["sezioni"][0], "", "")
        assert visti == ["Scrivi il testo parlato di una sezione di un video "
                         "di cucina."]

    def test_le_ricerche_sono_quelle_del_profilo(self, cucina, monkeypatch):
        monkeypatch.setattr(config, "LINGUA", "it")
        assert brain._lingua()["ricerche"] == tuple(cucina.ricerche["it"])
        monkeypatch.setattr(config, "LINGUA", "en")
        assert brain._lingua()["ricerche"] == tuple(cucina.ricerche["en"])

    def test_confezione(self, cucina, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", False)
        dati = {"titolo": "Carbonara: x", "descrizione": "d",
                "gioco": "Carbonara", "stile": "VIRAL_HOOK_NEWS"}
        tag = brain.costruisci_tag(dati)
        assert tag[:4] == cucina.tag_fissi
        assert not any("gaming" in t for t in tag)
        assert brain.costruisci_hashtag(dati) == [
            "#carbonara", "#notiziecucina", "#cucinaitaliana"]
        descrizione = brain.costruisci_descrizione(dati)
        assert "Altri Shorts di cucina ogni giorno su La Cucina di Esempio: " \
               "youtube.com/@CucinaDiEsempio" in descrizione
        assert "gaming" not in descrizione.lower()

    def test_la_query_video_non_prende_gameplay(self, cucina):
        assert brain.completa_query_video("pasta cooking") == "pasta cooking"
        assert brain.completa_query_video("  ") == cucina.query_stock_riserva[0]

    def test_le_parole_generiche_non_diventano_un_nome(self, cucina):
        for generico in ("ricetta", "Ricette", "cucina"):
            assert brain._pulisci_nome_gioco(generico) == ""
        assert brain._pulisci_nome_gioco("Carbonara") == "Carbonara"

    def test_il_titolo_non_da_un_gioco_fuori_dal_gaming(self, cucina):
        assert brain._gioco_dal_titolo("Carbonara: il segreto") == ""

    def test_i_nomi_grossi_sono_quelli_del_profilo(self, cucina):
        assert brain._punteggio_notizia("Cannavacciuolo apre un ristorante") > \
            brain._punteggio_notizia("GTA 6 apre un ristorante")

    def test_la_generazione_non_aggiunge_gameplay(self, cucina, monkeypatch):
        risposta = json.dumps({
            "titolo": "Carbonara: dieci chili in un piatto",
            "script": ("Dieci chili di carbonara in un solo piatto. Un "
                       "ristorante romano lo ha servito davvero. La domanda e' "
                       "semplice: chi riesce a finirlo? Il guanciale deve "
                       "essere croccante, il pecorino abbondante, l'uovo mai "
                       "cotto. Tu lo divideresti con gli amici o lo "
                       "affronteresti da solo? Scrivilo nei commenti e segui "
                       "La Cucina di Esempio. Perche' dieci chili sono tanti."),
            "gioco": "Carbonara", "query_video": "pasta carbonara cooking",
            "descrizione": "Dieci chili.\nTu ce la faresti?", "indice_notizia": 0,
        })

        class Finto:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        sistema = kw["messages"][0]["content"]
                        testo = ('{"dettagli_inventati": []}'
                                 if sistema.startswith("Sei un fact-checker")
                                 else risposta)

                        class Scelta:
                            class message:
                                content = testo

                        class Risposta:
                            choices = [Scelta()]
                        return Risposta()

        monkeypatch.setattr(brain, "client", Finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(NOTIZIA)])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        salvati = []
        monkeypatch.setattr(brain, "salva_in_cronologia", salvati.append)
        dati = brain.genera_script_samaritan()
        assert dati["query_video"] == "pasta carbonara cooking"
        assert dati["gioco"] == "Carbonara"
        assert salvati and salvati[0]["gioco"] == "Carbonara"


class TestSteamMaiFuoriDalGaming:
    """Su Steam ci sono solo giochi: un canale di cucina non ci va mai."""

    def _vietato(self, *a, **k):
        raise AssertionError("Steam chiamato da un canale che non e' di gaming")

    def _prepara(self, monkeypatch, tmp_path, query_viste):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(tmp_path / "clip_mie"))
        for nome in ("cerca_gioco_steam", "dettagli_gioco", "scarica_trailer_steam",
                     "scarica_screenshot_steam", "gioco_con_pagina_ufficiale",
                     "scarica_trailer_ufficiali"):
            monkeypatch.setattr(gameplay, nome, self._vietato)
        # Il ripiego su Pexels importa maker, che si porta dietro moviepy.
        finto = types.ModuleType("maker")

        def scarica(query, quante=None):
            query_viste.append(query)
            return [str(tmp_path / f"bg_{i}.mp4") for i in range(quante or 3)]

        finto.scarica_clip_sfondo = scarica
        monkeypatch.setitem(sys.modules, "maker", finto)

    def test_la_cucina_usa_solo_stock(self, cucina, monkeypatch, tmp_path):
        query_viste = []
        self._prepara(monkeypatch, tmp_path, query_viste)
        sorgenti, ufficiale = gameplay.procura_materiale(
            "Carbonara", query_pexels="pasta carbonara cooking", minimo=3)
        assert ufficiale is None
        assert sorgenti and all(s["gioco"] is None for s in sorgenti)
        assert query_viste == ["pasta carbonara cooking"]

    def test_anche_un_nome_di_gioco_non_la_porta_su_steam(self, cucina, monkeypatch, tmp_path):
        # Il modello di un canale di cucina che nomina GTA non deve scaricare
        # il trailer di GTA.
        self._prepara(monkeypatch, tmp_path, [])
        sorgenti, _ = gameplay.procura_materiale("Grand Theft Auto VI")
        assert all(s["gioco"] is None for s in sorgenti)

    def test_poppone_tv_su_steam_ci_va_ancora(self, monkeypatch, tmp_path):
        chiamate = []
        self._prepara(monkeypatch, tmp_path, [])
        monkeypatch.setattr(gameplay, "gioco_con_pagina_ufficiale", lambda g: None)
        monkeypatch.setattr(gameplay, "cerca_gioco_steam",
                            lambda nome: chiamate.append(nome) or (None, None))
        gameplay.procura_materiale("Portal 2")
        assert chiamate == ["Portal 2"]

    def test_un_gaming_con_materiale_stock_non_va_su_steam(self, monkeypatch, tmp_path):
        monkeypatch.setattr(profilo, "_attivo",
                            profilo.da_dizionario({"materiale": "stock"}))
        self._prepara(monkeypatch, tmp_path, [])
        sorgenti, _ = gameplay.procura_materiale("Portal 2")
        assert all(s["gioco"] is None for s in sorgenti)


class TestCampiRicavati:
    """Un profilo minimo di cucina deve bastare: il resto si ricava."""

    def test_profilo_minimo(self):
        p = profilo.da_dizionario(_minimo_cucina())
        assert p.genere == "f"
        assert p.soggetto_plurale == "ricette"
        assert p.descrizione_argomento == "cucina"
        assert p.descrizione_canale == "di cucina italiano"
        assert p.pubblico == "gli appassionati di cucina"
        assert p.materiale == "stock"
        assert p.categoria_youtube == "22"
        assert p.tag_fissi == ["cucina", "shorts ita"]
        assert p.hashtag_canale == "cucina"
        assert p.hashtag_formato["DOMANDA_AL_PUBBLICO"] == "cucina"
        assert p.hashtag_formato["VIRAL_HOOK_NEWS"] == "notizie"
        assert p.nomi_grossi == []
        assert "Dilemma di cucina" in p.formati["DOMANDA_AL_PUBBLICO"]
        # Il canale di Poppone TV non si eredita: nome e handle si',
        # ma niente di gaming.
        assert not any("game" in q for q in p.query_stock_riserva)

    def test_plurali_e_generi(self):
        casi = {"squadra": ("squadre", "f"), "film": ("film", "m"),
                "piatto": ("piatti", "m"), "gioco": ("giochi", "m")}
        for soggetto, (plurale, genere) in casi.items():
            p = profilo.da_dizionario(_minimo_cucina(soggetto=soggetto))
            assert (p.soggetto_plurale, p.genere) == (plurale, genere), soggetto

    def test_un_soggetto_di_piu_parole_chiede_il_plurale(self):
        with pytest.raises(profilo.ProfiloNonValido, match="soggetto_plurale"):
            profilo.da_dizionario(_minimo_cucina(soggetto="primo piatto"))
        p = profilo.da_dizionario(_minimo_cucina(
            soggetto="primo piatto", soggetto_plurale="primi piatti"))
        assert p.soggetto_plurale == "primi piatti"

    def test_un_gaming_che_cambia_poco_tiene_il_resto(self):
        p = profilo.da_dizionario({"nome_canale": "Altro Canale",
                                   "ricerche": {"it": ["giochi indie"]},
                                   "hashtag_formato": {"DONT_DO_THIS": "errori"}})
        assert p.videogiochi and p.usa_steam
        assert p.ricerche["it"] == ["giochi indie"]
        assert tuple(p.ricerche["en"]) == RICERCHE_DI_SEMPRE["en"]
        assert p.hashtag_formato["DONT_DO_THIS"] == "errori"
        assert p.hashtag_formato["VIRAL_HOOK_NEWS"] == "newsgaming"
        assert p.tag_fissi[0] == "gaming ita"

    def test_una_lingua_senza_ricerche_usa_quelle_italiane(self, monkeypatch):
        monkeypatch.setattr(profilo, "_attivo", profilo.da_dizionario(_minimo_cucina()))
        monkeypatch.setattr(config, "LINGUA", "en")
        assert brain._lingua()["ricerche"] == ("ricette",)
        # Le parole calde invece restano quelle della lingua del video.
        assert "release" in brain._lingua()["parole_calde"]

    def test_il_predefinito_non_si_sporca(self):
        p = profilo.da_dizionario({"ricerche": {"it": ["x"]}})
        p.tag_fissi.append("sporco")
        assert profilo.PREDEFINITO["ricerche"]["it"][0] == "videogiochi"
        assert "sporco" not in profilo.predefinito().tag_fissi


class TestValidazione:
    """Un file sbagliato si ferma all'avvio con un messaggio in italiano."""

    @pytest.mark.parametrize("modifica, parola", [
        ({"materiale": "youtube"}, "materiale"),
        ({"materiale": "steam"}, "Steam"),
        ({"ricerche": {"it": []}}, "lista vuota"),
        ({"ricerche": {}}, "almeno una lingua"),
        ({"ricerche": {"it": ["ok", ""]}}, "ricerche"),
        ({"ricerche": {"fr": ["cuisine"]}}, "lingua 'fr'"),
        ({"ricerche": ["ricette"]}, "una lista per lingua"),
        ({"genere": "n"}, "genere"),
        ({"handle": "CucinaDiEsempio"}, "@"),
        ({"categoria_youtube": "cucina"}, "categoria_youtube"),
        ({"hashtag_formato": {"NON_ESISTE": "x"}}, "NON_ESISTE"),
        ({"formati": {"DONT_DO_THIS": ""}}, "testo vuoto"),
        ({"tag_fissi": []}, "tag_fissi"),
        ({"soggetto": ""}, "soggetto"),
        ({"materia": "stock"}, "campi sconosciuti: materia"),
    ])
    def test_errori_chiari(self, modifica, parola):
        with pytest.raises(profilo.ProfiloNonValido) as errore:
            profilo.da_dizionario(_minimo_cucina(**modifica))
        assert parola in str(errore.value)
        assert str(errore.value).startswith("Profilo del canale non valido")

    def test_fuori_dal_gaming_servono_ricerche_e_soggetto(self):
        with pytest.raises(profilo.ProfiloNonValido, match="soggetto, ricerche"):
            profilo.da_dizionario({"argomento": "di calcio"})

    def test_la_categoria_scritta_come_numero_va_bene(self):
        assert profilo.da_dizionario(
            _minimo_cucina(categoria_youtube=26)).categoria_youtube == "26"

    def test_i_commenti_si_ignorano(self):
        p = profilo.da_dizionario(_minimo_cucina(_nota="qualsiasi cosa"))
        assert not hasattr(p, "_nota")

    def test_json_rotto(self, tmp_path):
        percorso = _scrivi(tmp_path, '{"argomento": "di cucina",}')
        with pytest.raises(profilo.ProfiloNonValido, match="non e' JSON valido"):
            profilo.carica(percorso)

    def test_non_un_oggetto(self, tmp_path):
        with pytest.raises(profilo.ProfiloNonValido, match="oggetto JSON"):
            profilo.carica(_scrivi(tmp_path, ["argomento"]))

    def test_percorso_indicato_ma_mancante(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PROFILO_CANALE", str(tmp_path / "manca.json"))
        with pytest.raises(profilo.ProfiloNonValido, match="PROFILO_CANALE"):
            profilo.carica()

    def test_percorso_da_variabile(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PROFILO_CANALE", _scrivi(tmp_path, _minimo_cucina(), "altro.json"))
        assert profilo.carica().soggetto == "ricetta"


class TestAvvio:
    """config legge il profilo all'avvio: le variabili d'ambiente vincono,
    un file sbagliato ferma tutto con un messaggio. Gira in un processo a
    parte perche' config si legge una volta sola per processo."""

    def _nome(self, **env):
        ambiente = dict(os.environ, GROQ_API_KEY="x", PEXELS_API_KEY="x")
        ambiente.update(env)
        return subprocess.run(
            [sys.executable, "-c",
             "import config; print(config.NOME_CANALE, config.HANDLE_CANALE)"],
            cwd=RADICE, env=ambiente, capture_output=True, text=True, timeout=60)

    def test_il_file_da_il_nome(self):
        esito = self._nome(PROFILO_CANALE=ESEMPIO, NOME_CANALE="", HANDLE_CANALE="")
        assert esito.returncode == 0, esito.stdout + esito.stderr
        assert esito.stdout.strip() == "La Cucina di Esempio @CucinaDiEsempio"

    def test_le_variabili_vincono_sul_file(self):
        esito = self._nome(PROFILO_CANALE=ESEMPIO, NOME_CANALE="Poppone TV",
                           HANDLE_CANALE="@PopponeTV")
        assert esito.stdout.strip() == "Poppone TV @PopponeTV"

    def test_un_file_sbagliato_ferma_l_avvio(self, tmp_path):
        esito = self._nome(PROFILO_CANALE=_scrivi(
            tmp_path, _minimo_cucina(materiale="youtube")))
        assert esito.returncode == 1
        assert "'materiale' e' 'steam' o 'stock'" in esito.stdout


class TestUscite:
    """Orari e lingue delle uscite stanno nel profilo. Il workflow ha solo
    quattro partenze notturne fisse, e ogni uscita deve cadere abbastanza
    dopo la sua partenza (almeno MARGINE_MINIMO_ORE, contro i ritardi di
    GitHub) ma non troppo (al massimo ANTICIPO_PARTENZA_ORE, se no la
    lavorazione si crede di ieri)."""

    def _uscite(self, *orari, lingua="it"):
        return [{"orario": o, "lingua": lingua} for o in orari]

    def test_le_finestre_di_roma(self):
        assert profilo.finestre("Europe/Rome") == [
            ("11:17", "18:17"), ("13:17", "20:17"),
            ("15:17", "22:17"), ("16:17", "23:17")]

    def test_una_sola_uscita_serale_va_sulla_partenza_giusta(self):
        p = profilo.da_dizionario({"uscite": self._uscite("22:00")})
        assert [profilo.uscita_del_cron(p, n) for n in (1, 2, 3, 4)] == [
            None, None, {"orario": "22:00", "lingua": "it"}, None]

    def test_l_ordine_nel_file_non_conta(self):
        p = profilo.da_dizionario({"uscite": self._uscite("18:00", "12:00")})
        assert profilo.uscita_del_cron(p, 1)["orario"] == "12:00"
        assert profilo.uscita_del_cron(p, 2)["orario"] == "18:00"
        assert profilo.uscita_richiesta(p, "1")["orario"] == "12:00"

    @pytest.mark.parametrize("orari", [
        ("23:30",), ("10:00",), ("11:00", "12:00"),
        ("13:00", "14:00", "15:00", "16:00"),
    ])
    def test_orari_fuori_dalle_partenze(self, orari):
        with pytest.raises(profilo.ProfiloNonValido) as errore:
            profilo.da_dizionario({"uscite": self._uscite(*orari)})
        # Il messaggio dice anche cosa si puo' fare.
        assert "partenza 1 dalle 11:17 alle 18:17" in str(errore.value)

    def test_vale_anche_con_l_ora_legale(self):
        """Le 18:30 a Roma sono 17:30 UTC d'inverno, sedici ore e un quarto
        dopo la prima partenza (01:17 UTC): troppo. D'estate starebbero
        dentro, ma l'uscita deve funzionare tutto l'anno."""
        assert profilo.cron_adatto("18:17", 0, "Europe/Rome")
        assert not profilo.cron_adatto("18:30", 0, "Europe/Rome")

    def test_un_altro_fuso(self):
        p = profilo.da_dizionario({"uscite": self._uscite("09:00"),
                                   "fuso": "America/New_York"})
        assert profilo.uscita_del_cron(p, 1)["orario"] == "09:00"

    @pytest.mark.parametrize("modifica, parola", [
        ({"uscite": []}, "da 1 a 4"),
        ({"uscite": [{"orario": "14:00", "lingua": "it"}] * 5}, "da 1 a 4"),
        ({"uscite": [{"orario": "14", "lingua": "it"}]}, "HH:MM"),
        ({"uscite": [{"orario": "24:00", "lingua": "it"}]}, "HH:MM"),
        ({"uscite": [{"orario": "14:00", "lingua": "fr"}]}, "lingua 'fr'"),
        ({"uscite": [{"orario": "14:00"}]}, "'orario' e 'lingua'"),
        ({"uscite": [{"orario": "14:00", "lingua": "it"},
                     {"orario": "14:00", "lingua": "en"}]}, "due uscite"),
        ({"fuso": "Europa/Roma"}, "fuso orario conosciuto"),
    ])
    def test_errori_chiari(self, modifica, parola):
        with pytest.raises(profilo.ProfiloNonValido) as errore:
            profilo.da_dizionario(_minimo_cucina(**modifica))
        assert parola in str(errore.value)

    def test_l_uscita_richiesta_che_non_c_e(self):
        with pytest.raises(profilo.ProfiloNonValido, match="1\\) 14:00"):
            profilo.uscita_richiesta(profilo.predefinito(), "5")

    def test_un_profilo_di_cucina_ha_due_uscite_nella_sua_lingua(self):
        p = profilo.da_dizionario(_minimo_cucina(ricerche={"en": ["recipes"]}))
        assert p.uscite == self._uscite("14:00", "18:00", lingua="en")
        assert p.fuso == "Europe/Rome"

    def _decidi(self, tmp_path, contenuto, cron):
        percorso = _scrivi(tmp_path, contenuto)
        # -S: senza site-packages, come nel job 'uscita' che non installa
        # niente. profilo.py deve cavarsela con la libreria standard.
        return subprocess.run(
            [sys.executable, "-S", "profilo.py", "decidi"], cwd=RADICE,
            env=dict(os.environ, PROFILO_CANALE=percorso, USCITA_CRON=cron),
            capture_output=True, text=True, timeout=30)

    def test_il_workflow_chiede_al_profilo_da_riga_di_comando(self, tmp_path):
        una = {"uscite": [{"orario": "18:00", "lingua": "it"}]}
        esito = self._decidi(tmp_path, una, "3")
        assert esito.returncode == 0, esito.stderr
        assert esito.stdout.strip() == "attiva=false"
        assert self._decidi(tmp_path, una, "1").stdout.strip() == "attiva=true"

    def test_un_profilo_sbagliato_ferma_la_partenza(self, tmp_path):
        esito = self._decidi(
            tmp_path, {"uscite": [{"orario": "03:00", "lingua": "it"}]}, "1")
        assert esito.returncode == 1
        assert esito.stdout.startswith("::error::Profilo del canale non valido")
