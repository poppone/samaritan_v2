"""Preparazione comune ai test.

I moduli di Samaritan importano `config`, che esce con errore se mancano le
chiavi obbligatorie. Qui mettiamo valori finti PRIMA che i test importino
qualsiasi cosa: i test non toccano la rete, quindi non servono chiavi vere.
"""
import os
import sys

os.environ.setdefault("GROQ_API_KEY", "test-non-usata")
os.environ.setdefault("PEXELS_API_KEY", "test-non-usata")

# La radice del progetto deve stare nel path: i moduli sono a livello singolo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pytest


@pytest.fixture(autouse=True)
def _profilo_predefinito(monkeypatch):
    """Ogni test parte dal profilo di Poppone TV, anche se sul disco c'e' un
    canale.json: i test dicono come si comporta il codice, non il canale di
    chi li lancia. I test sui profili se ne impostano uno loro."""
    import config
    import profilo
    predefinito = profilo.predefinito()
    monkeypatch.setattr(profilo, "_attivo", predefinito)
    # config legge nome e handle dal canale.json una volta sola, all'import:
    # nella copia di un cliente sarebbero i suoi, e i test fallirebbero a ogni
    # salvataggio del canale.
    monkeypatch.setattr(config, "PROFILO", predefinito)
    monkeypatch.setattr(config, "NOME_CANALE", predefinito.nome_canale)
    monkeypatch.setattr(config, "HANDLE_CANALE", predefinito.handle)
    monkeypatch.setattr(config, "FUSO_USCITA", predefinito.fuso)


@pytest.fixture(autouse=True)
def _niente_sommari_dalla_rete(monkeypatch):
    """Il sommario delle notizie si cerca su Bing: nei test niente rete."""
    import brain
    monkeypatch.setattr(brain, "_sommario_bing", lambda titolo: "")


@pytest.fixture(autouse=True)
def _niente_confronto_storie_dalla_rete(monkeypatch):
    """Il confronto con le storie gia' raccontate chiede a Groq: nei test
    niente rete. I test su quel confronto ne mettono uno loro."""
    import brain
    monkeypatch.setattr(brain, "_storie_gia_raccontate",
                        lambda candidate, raccontate: set())


@pytest.fixture(autouse=True)
def _niente_correzione_dalla_rete(monkeypatch):
    """La correzione dello script chiede a Groq: nei test niente rete. I test
    su quella correzione ne mettono una loro."""
    import brain
    monkeypatch.setattr(brain, "_correggi_script",
                        lambda script, dettagli, titolo_notizia, sommario="": "")
    monkeypatch.setattr(brain, "_cambia_attacco", lambda script, schema: "")
