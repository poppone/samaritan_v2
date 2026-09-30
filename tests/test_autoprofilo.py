# -*- coding: utf-8 -*-
"""Test sul canale che si definisce da solo (autoprofilo.py).

Promesse: con il solo argomento il canale parte subito con ripieghi sensati,
il modello scrive il resto una volta e poi lo ritara ogni due settimane, i
campi scritti a mano vincono, un argomento vietato ferma tutto, e un modello
che sbaglia non rompe niente. Nessun test tocca la rete.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import autoprofilo
import brain
import profilo

ADESSO = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)

RISPOSTA_BUONA = {
    "ammesso": True, "motivo": "",
    "descrizione_argomento": "pesca sportiva",
    "descrizione_canale": "di pesca sportiva italiano",
    "soggetto": "tecnica", "soggetto_plurale": "tecniche", "genere": "f",
    "pubblico": "chi pesca", "esempi_soggetto": ["Spinning", "Surfcasting", "Carpfishing"],
    "esempi_query_video": ["fishing rod lake", "fish underwater"],
    "ricerche_it": ["pesca sportiva", "record pesca", "pesca spinning"],
    "ricerche_en": ["fishing record", "sport fishing"],
    "parole_calde_it": ["record", "gigante"],
    "nomi_grossi": ["Tonno", "Siluro"], "tag_fissi": ["pesca", "pesca sportiva"],
    "hashtag_canale": "#pesca sportiva", "query_stock_riserva": ["fishing boat sea", "lake sunrise"],
    "categoria_youtube": "17",
}


def _canale(tmp_path, **altro):
    dati = {"nome_canale": "Pesca Lampo", "handle": "@PescaLampo",
            "argomento": "di pesca sportiva", "autodefinisci": True}
    dati.update(altro)
    file = tmp_path / "canale.json"
    file.write_text(json.dumps(dati), encoding="utf-8")
    return str(file)


def _finto_modello(monkeypatch, risposte):
    """Un Groq finto che risponde in ordine con i dict (o le eccezioni) dati."""
    chiamate = []

    class Completions:
        @staticmethod
        def create(**kw):
            chiamate.append(kw["messages"][0]["content"])
            r = risposte.pop(0)
            if isinstance(r, Exception):
                raise r

            class Scelta:
                class message:
                    content = json.dumps(r)

            class Risposta:
                choices = [Scelta()]
            return Risposta()

    class Client:
        class chat:
            completions = Completions()

    monkeypatch.setattr(brain, "client", Client())
    monkeypatch.setattr(autoprofilo, "_numeri_del_canale", lambda: [])
    return chiamate


class TestProfiloSoloArgomento:
    def test_parte_con_i_ripieghi(self, tmp_path):
        p = profilo.carica(_canale(tmp_path))
        assert p.autodefinisci is True
        assert p.soggetto == "tema"
        assert p.ricerche_per("it") == ("pesca sportiva",)

    def test_senza_autodefinisci_servono_soggetto_e_ricerche(self, tmp_path):
        with pytest.raises(profilo.ProfiloNonValido, match="soggetto"):
            profilo.carica(_canale(tmp_path, autodefinisci=False))

    @pytest.mark.parametrize("argomento", ["di porno", "di scommesse sportive",
                                           "di casinò online", "per adulti"])
    def test_gli_argomenti_vietati_non_passano(self, tmp_path, argomento):
        with pytest.raises(profilo.ProfiloNonValido, match="YouTube"):
            profilo.carica(_canale(tmp_path, argomento=argomento))

    @pytest.mark.parametrize("argomento", ["di cucina", "di hot dog", "di Top Gun",
                                           "di One Piece", "di pesca"])
    def test_gli_argomenti_innocui_passano(self, tmp_path, argomento):
        profilo.carica(_canale(tmp_path, argomento=argomento))


class TestDefinizione:
    def test_scrive_e_poi_si_usa(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA)])
        assert autoprofilo.aggiorna_se_serve(file, ADESSO) is True
        p = profilo.carica(file)
        assert p.soggetto == "tecnica" and p.genere == "f"
        assert p.ricerche_per("en") == ("fishing record", "sport fishing")
        assert p.nomi_grossi == ["tonno", "siluro"]
        assert p.hashtag_canale == "pescasportiva"
        assert p.categoria_youtube == "17"

    def test_i_campi_scritti_a_mano_vincono(self, tmp_path, monkeypatch):
        file = _canale(tmp_path, soggetto="spot", soggetto_plurale="spot")
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA)])
        autoprofilo.aggiorna_se_serve(file, ADESSO)
        p = profilo.carica(file)
        assert p.soggetto == "spot"
        assert p.ricerche_per("it")[0] == "pesca sportiva"

    def test_non_riscrive_prima_di_due_settimane(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        chiamate = _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA), dict(RISPOSTA_BUONA)])
        autoprofilo.aggiorna_se_serve(file, ADESSO)
        assert autoprofilo.aggiorna_se_serve(file, ADESSO + timedelta(days=3)) is False
        assert len(chiamate) == 1
        assert autoprofilo.aggiorna_se_serve(file, ADESSO + timedelta(days=15)) is True
        assert "DEFINIZIONE ATTUALE" in chiamate[1]

    def test_la_ritaratura_usa_i_numeri_del_canale(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        chiamate = _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA)])
        monkeypatch.setattr(autoprofilo, "_numeri_del_canale",
                            lambda: ["Cosa cerca il pubblico su YouTube: siluro gigante."])
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        autoprofilo.aggiorna_se_serve(file, ADESSO)
        assert "siluro gigante" in chiamate[0]

    def test_cambiare_argomento_rifa_la_definizione(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA)])
        autoprofilo.aggiorna_se_serve(file, ADESSO)
        file = _canale(tmp_path, argomento="di giardinaggio")
        p = profilo.carica(file)
        assert p.soggetto == "tema"          # la vecchia definizione non vale
        assert "cambiato" in autoprofilo.serve_definire(
            profilo.contenuto_del_file(file), profilo.leggi_autodefinizione(file), ADESSO)

    def test_argomento_non_ammesso_ferma(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA, ammesso=False,
                                          motivo="contenuti per adulti")])
        with pytest.raises(autoprofilo.ArgomentoNonAmmesso, match="adulti"):
            autoprofilo.aggiorna_se_serve(file, ADESSO)
        assert profilo.leggi_autodefinizione(file) is None

    def test_un_modello_che_sbaglia_non_rompe_niente(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [RuntimeError("429"), RuntimeError("500")])
        assert autoprofilo.aggiorna_se_serve(file, ADESSO) is False
        assert profilo.carica(file).soggetto == "tema"

    def test_una_definizione_non_valida_si_scarta(self, tmp_path, monkeypatch):
        file = _canale(tmp_path)
        monkeypatch.setattr(profilo, "percorso", lambda: file)
        _finto_modello(monkeypatch, [dict(RISPOSTA_BUONA, soggetto="tecnica di lancio",
                                          soggetto_plurale="")])
        assert autoprofilo.aggiorna_se_serve(file, ADESSO) is False
        assert profilo.leggi_autodefinizione(file) is None

    def test_poppone_tv_non_si_definisce(self, tmp_path):
        assert autoprofilo.aggiorna_se_serve(str(tmp_path / "canale.json"), ADESSO) is False
