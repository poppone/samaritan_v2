"""Il link all'articolo di davidedurazzi.it nei video.

Gli articoli arrivano da una rete finta (monkeypatch su requests.get): i
test non scaricano niente.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import brain
import config


def _giorni_fa(n):
    oggi = datetime.now(ZoneInfo("Europe/Rome")).date()
    return (oggi - timedelta(days=n)).isoformat()


def _articoli():
    return [
        {"slug": "gta-6-rinviato-rockstar-sposta-l-uscita-al-2027",
         "titolo": "GTA 6 rinviato: Rockstar sposta l'uscita al 2027",
         "sezione": "gaming", "data": _giorni_fa(1), "pubblicato": True},
        {"slug": "xbox-apre-il-cloud-gaming-ai-non-abbonati",
         "titolo": "Xbox apre il cloud gaming ai non abbonati: pacchetti da 10 ore",
         "sezione": "gaming", "data": _giorni_fa(2), "pubblicato": True},
        # Stessa notizia ma vecchia, non pubblicata o di un'altra sezione:
        # non si scelgono mai.
        {"slug": "gta-6-rinviato-vecchio",
         "titolo": "GTA 6 rinviato: Rockstar sposta l'uscita",
         "sezione": "gaming", "data": _giorni_fa(9), "pubblicato": True},
        {"slug": "gta-6-rinviato-bozza",
         "titolo": "GTA 6 rinviato: Rockstar sposta l'uscita",
         "sezione": "gaming", "data": _giorni_fa(0), "pubblicato": False},
        {"slug": "gta-6-rinviato-tecnologia",
         "titolo": "GTA 6 rinviato: Rockstar sposta l'uscita",
         "sezione": "tecnologia", "data": _giorni_fa(0), "pubblicato": True},
    ]


class _Risposta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture
def rete(monkeypatch):
    """La rete finta: conta le chiamate e restituisce gli articoli."""
    chiamate = []

    def get(url, timeout=None, **kw):
        chiamate.append((url, timeout))
        return _Risposta(_articoli())

    monkeypatch.setattr(brain, "_articoli_sito", None)
    monkeypatch.setattr(brain.requests, "get", get)
    monkeypatch.setattr(config, "SITO_CANALE", "davidedurazzi.it")
    monkeypatch.setattr(config, "LINGUA", "it")
    monkeypatch.setattr(config, "VIDEO_LUNGO", False)
    return chiamate


GTA = {"titolo": "GTA 6 slitta ancora: nuova data nel 2027",
       "descrizione": "Rockstar rimanda di nuovo.\nE voi?",
       "fonte": "Rockstar rinvia GTA 6 al 2027 (IGN)",
       "gioco": "Grand Theft Auto VI", "stile": ""}
SLUG_GTA = "gta-6-rinviato-rockstar-sposta-l-uscita-al-2027"


class TestArticoloCollegato:
    def test_porta_all_articolo_con_gli_utm(self, rete):
        url = brain.articolo_collegato(GTA)
        assert url.startswith(f"https://www.davidedurazzi.it/articoli/{SLUG_GTA}?")
        assert ".html" not in url
        assert "utm_source=youtube" in url
        assert "utm_medium=short" in url
        assert f"utm_campaign={SLUG_GTA}" in url

    def test_la_rete_cambia_la_sorgente(self, rete):
        assert "utm_source=tiktok" in brain.articolo_collegato(GTA, "tiktok")

    def test_senza_rete_l_indirizzo_e_pulito(self, rete):
        assert brain.articolo_collegato(GTA, rete="") == (
            f"https://www.davidedurazzi.it/articoli/{SLUG_GTA}")

    def test_scarica_una_volta_sola_per_run(self, rete):
        brain.articolo_collegato(GTA)
        brain.articolo_collegato(GTA, "tiktok")
        assert len(rete) == 1
        assert rete[0][0] == "https://www.davidedurazzi.it/content/articoli.json"
        assert rete[0][1] and rete[0][1] <= 10

    def test_niente_di_simile_porta_alla_home(self, rete):
        url = brain.articolo_collegato({"titolo": "Hollow Knight Silksong: patch",
                                        "gioco": "Hollow Knight: Silksong"})
        assert url.startswith("https://www.davidedurazzi.it/?")
        assert "utm_campaign=hollow-knight-silksong-patch" in url

    def test_il_gioco_da_solo_non_basta(self, rete):
        url = brain.articolo_collegato({"titolo": "GTA 6: la mappa in un leak",
                                        "gioco": "Grand Theft Auto VI"})
        assert "/articoli/" not in url

    def test_articoli_vecchi_bozze_e_altre_sezioni_esclusi(self, rete, monkeypatch):
        monkeypatch.setattr(brain, "_articoli_sito", _articoli()[2:])
        assert "/articoli/" not in brain.articolo_collegato(GTA)

    def test_rete_giu_porta_alla_home_senza_errori(self, rete, monkeypatch):
        def esplode(*a, **kw):
            raise brain.requests.ConnectionError("giu'")
        monkeypatch.setattr(brain, "_articoli_sito", None)
        monkeypatch.setattr(brain.requests, "get", esplode)
        assert brain.articolo_collegato(GTA).startswith("https://www.davidedurazzi.it/?")

    def test_json_rotto_porta_alla_home(self, rete, monkeypatch):
        monkeypatch.setattr(brain, "_articoli_sito", None)
        monkeypatch.setattr(brain.requests, "get",
                            lambda *a, **kw: _Risposta({"non": "una lista"}))
        assert "/articoli/" not in brain.articolo_collegato(GTA)

    def test_video_lungo_ha_il_suo_medium(self, rete, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", True)
        assert "utm_medium=lungo" in brain.articolo_collegato(GTA)


class TestNeiTesti:
    def test_descrizione_porta_l_articolo_in_alto(self, rete):
        righe = brain.costruisci_descrizione(GTA).split("\n")
        assert any(r.startswith(f"Articolo completo: https://www.davidedurazzi.it/articoli/{SLUG_GTA}?")
                   for r in righe[:5])
        assert "Approfondimenti su" not in "\n".join(righe)

    def test_descrizione_in_inglese(self, rete, monkeypatch):
        monkeypatch.setattr(config, "LINGUA", "en")
        assert "Full story: https://www.davidedurazzi.it/articoli/" in brain.costruisci_descrizione(GTA)

    def test_senza_sito_niente_link(self, rete, monkeypatch):
        monkeypatch.setattr(config, "SITO_CANALE", "")
        assert "davidedurazzi.it" not in brain.costruisci_descrizione(GTA)
        assert "davidedurazzi.it" not in brain.costruisci_didascalia_tiktok(GTA)

    def test_tiktok_nomina_il_sito_senza_link(self, rete):
        didascalia = brain.costruisci_didascalia_tiktok(GTA)
        assert "https://" not in didascalia
        righe = didascalia.split("\n\n")
        assert righe[-2] == "Articolo completo su davidedurazzi.it"
        assert righe[-1].startswith("#")

    def test_tiktok_senza_articolo_non_lo_promette(self, rete):
        didascalia = brain.costruisci_didascalia_tiktok({"titolo": "Silksong: patch"})
        assert "Articolo completo" not in didascalia
        assert "Altre notizie su davidedurazzi.it" in didascalia

    def test_cronologia_salva_l_articolo(self, rete, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "c.json"))
        brain.salva_in_cronologia(dict(GTA, script="x" * 100, query_video="gta"))
        voce = json.load(open(tmp_path / "c.json", encoding="utf-8"))[-1]
        assert voce["articolo_url"] == f"https://www.davidedurazzi.it/articoli/{SLUG_GTA}"

    def test_cronologia_senza_articolo_niente_campo(self, rete, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "c.json"))
        brain.salva_in_cronologia({"titolo": "Silksong", "script": "x", "stile": "",
                                   "query_video": "q"})
        voce = json.load(open(tmp_path / "c.json", encoding="utf-8"))[-1]
        assert "articolo_url" not in voce
