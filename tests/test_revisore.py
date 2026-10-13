# -*- coding: utf-8 -*-
"""Il revisore di qualita': boccia gli script deboli, mai il video intero."""
import brain


def _client(risposte, visti):
    class FinteCompletions:
        def create(self, **parametri):
            visti.append(parametri)
            testo = risposte.pop(0)
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


def test_restituisce_voto_e_consiglio(monkeypatch):
    visti = []
    monkeypatch.setattr(brain, "client", _client(
        ['{"voto": 4, "punto_debole": "apertura lenta", "consiglio": "parti dal dato"}'], visti))
    r = brain._revisione_qualita("Titolo", "Script", "Notizia", "GTA VI")
    assert r == {"voto": 4, "punto_debole": "apertura lenta", "consiglio": "parti dal dato"}
    assert "NOTIZIA: Notizia" in visti[0]["messages"][1]["content"]


def test_errore_o_voto_assurdo_non_bloccano(monkeypatch):
    monkeypatch.setattr(brain, "client", _client([RuntimeError("giu'")], []))
    assert brain._revisione_qualita("T", "S") is None
    monkeypatch.setattr(brain, "client", _client(
        ['{"voto": 42, "punto_debole": "", "consiglio": ""}'], []))
    assert brain._revisione_qualita("T", "S") is None


def test_senza_testo_non_chiama_nessuno(monkeypatch):
    monkeypatch.setattr(brain, "client", None)
    assert brain._revisione_qualita("", "S") is None


def test_lo_script_bocciato_viene_rifatto_col_consiglio(monkeypatch):
    from tests.test_brain import TestDettagliInventati as T
    t = T()
    voti = [{"voto": 4, "punto_debole": "apertura lenta", "consiglio": "parti dal dato"},
            {"voto": 8, "punto_debole": "", "consiglio": ""}]
    monkeypatch.setattr(brain, "_revisione_qualita", lambda *a, **k: voti.pop(0))
    risultato, prompt_visti, _ = t._genera(
        monkeypatch, [t._risposta(), t._risposta()],
        ['{"dettagli_inventati": []}', '{"dettagli_inventati": []}'])
    assert len(prompt_visti) == 2
    assert "parti dal dato" in prompt_visti[1][1]
    assert risultato["voto_revisore"] == 8
