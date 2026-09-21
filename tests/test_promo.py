# -*- coding: utf-8 -*-
"""Test sui Reel promozionali di Instagram.

Due cose vanno protette qui, e sono diverse fra loro.

La prima e' che i numeri detti nel Reel siano quelli veri: un video che vende
un servizio e sbaglia le cifre fa un danno peggiore di un video che non esce.

La seconda e' l'isolamento. La regola del progetto e' che Instagram non possa
fare male al canale YouTube, e il punto dove le due cose si toccavano davvero
era la memoria condivisa: la rotazione delle voci annota il proprio turno
sull'ultimo record di `cronologia_trend.json`, che e' un video di YouTube. I
test qui sotto verificano che il Reel non ci scriva mai dentro.
"""
import inspect
import json

import config
import promo
import instagram
import voice


CRONOLOGIA = [
    {"data": "2026-09-20", "titolo": "Uno", "video_id": "aaa"},
    {"data": "2026-09-21", "titolo": "Due", "video_id": "bbb"},
    {"data": "2026-09-21", "titolo": "Tre senza id"},
]

PERFORMANCE = {
    "aggiornato": "2026-09-21",
    "video": {
        "aaa": {"views": 1200, "subscribersGained": 3},
        "bbb": {"views": 330, "subscribersGained": 1},
    },
}


def _prepara(tmp_path, monkeypatch, cronologia=CRONOLOGIA, performance=PERFORMANCE):
    """Punta Samaritan a file finti, cosi' i test non leggono quelli veri."""
    f_cronologia = tmp_path / "cronologia.json"
    f_performance = tmp_path / "performance.json"
    f_diario = tmp_path / "diario.json"
    f_cronologia.write_text(json.dumps(cronologia), encoding="utf-8")
    f_performance.write_text(json.dumps(performance), encoding="utf-8")

    monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(f_cronologia))
    monkeypatch.setattr(config, "FILE_PERFORMANCE", str(f_performance))
    monkeypatch.setattr(promo, "FILE_DIARIO", str(f_diario))
    return f_cronologia, f_diario


# ===========================================================================
# I NUMERI
# ===========================================================================
def test_conta_solo_i_video_davvero_pubblicati(tmp_path, monkeypatch):
    """Un record senza video_id e' un video che non e' mai uscito."""
    _prepara(tmp_path, monkeypatch)
    numeri = promo.raccogli_numeri(oggi="2026-09-21")
    assert numeri["video"] == 2
    assert numeri["video_oggi"] == 2      # i record di oggi sono due
    assert numeri["giorni_attivi"] == 2


def test_somma_views_e_iscritti(tmp_path, monkeypatch):
    _prepara(tmp_path, monkeypatch)
    numeri = promo.raccogli_numeri(oggi="2026-09-21")
    assert numeri["views"] == 1530
    assert numeri["iscritti"] == 4
    assert numeri["migliore_views"] == 1200


def test_numeri_a_zero_senza_file(tmp_path, monkeypatch):
    """Al primo giro i file non ci sono: deve uscire zero, non un errore."""
    monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "manca.json"))
    monkeypatch.setattr(config, "FILE_PERFORMANCE", str(tmp_path / "manca2.json"))
    monkeypatch.setattr(promo, "FILE_DIARIO", str(tmp_path / "manca3.json"))
    numeri = promo.raccogli_numeri()
    assert numeri["video"] == 0 and numeri["views"] == 0


def test_cifre_scritte_all_italiana():
    assert promo._cifra(10330) == "10.330"
    assert promo._cifra(7) == "7"


def test_il_giorno_avanza_con_i_reel_usciti(tmp_path, monkeypatch):
    _, f_diario = _prepara(tmp_path, monkeypatch)
    assert promo.raccogli_numeri()["giorno"] == 1
    promo.salva_nel_diario({"titolo": "primo"})
    assert promo.raccogli_numeri()["giorno"] == 2


# ===========================================================================
# IL TESTO
# ===========================================================================
def test_il_ripiego_sta_nella_misura_e_chiede_il_dm(tmp_path, monkeypatch):
    """Se Groq non risponde il Reel esce lo stesso, e deve chiedere il DM:
    senza quella frase il video non vende niente."""
    _prepara(tmp_path, monkeypatch)
    numeri = promo.raccogli_numeri()
    titolo, script = promo._diario_di_ripiego(numeri)

    assert titolo and len(titolo) <= 60
    assert promo.MIN_PAROLE <= len(script.split()) <= promo.MAX_PAROLE
    assert "dm" in script.lower()
    # I numeri veri devono comparire scritti, non arrotondati a caso.
    assert promo._cifra(numeri["views"]) in script


def test_il_ripiego_cambia_da_un_giorno_all_altro(tmp_path, monkeypatch):
    _prepara(tmp_path, monkeypatch)
    numeri = promo.raccogli_numeri()
    aperture = set()
    for giorno in (1, 2, 3):
        numeri["giorno"] = giorno
        aperture.add(promo._diario_di_ripiego(numeri)[0])
    assert len(aperture) == 3


def test_didascalia_con_numeri_e_chiamata(tmp_path, monkeypatch):
    _prepara(tmp_path, monkeypatch)
    numeri = promo.raccogli_numeri()
    testo = promo.costruisci_didascalia(
        {"titolo": "Il canale va avanti da solo", "script": "..."}, numeri)

    assert "Il canale va avanti da solo" in testo
    assert promo._cifra(numeri["views"]) in testo
    assert config.CONTATTO_PROMO in testo
    assert "#" in testo
    # Instagram taglia la didascalia a 2200 caratteri.
    assert len(testo) <= 2200


# ===========================================================================
# ISOLAMENTO DA YOUTUBE
# ===========================================================================
def test_il_diario_non_tocca_la_memoria_di_youtube(tmp_path, monkeypatch):
    """Il Reel scrive solo sul suo file. Se un giorno scrivesse sull'altro,
    sposterebbe la rotazione delle vesti e delle voci del canale."""
    f_cronologia, _ = _prepara(tmp_path, monkeypatch)
    prima = f_cronologia.read_text(encoding="utf-8")

    promo.salva_nel_diario({"titolo": "Reel di prova", "media_id": "x"})

    assert f_cronologia.read_text(encoding="utf-8") == prima


def test_il_reel_non_usa_la_voce_a_pagamento():
    """ElevenLabs annota il turno della voce sulla cronologia di YouTube:
    il Reel deve chiedere esplicitamente di saltarla."""
    sorgente = inspect.getsource(promo.monta_reel)
    assert "permetti_elevenlabs=False" in sorgente


def test_la_voce_del_canale_resta_com_era():
    """Il parametro nuovo non deve cambiare il comportamento di default:
    i video di YouTube devono continuare a provare ElevenLabs per primo."""
    firma = inspect.signature(voice.genera_voce_samaritan)
    assert firma.parameters["permetti_elevenlabs"].default is True


# ===========================================================================
# PUBBLICAZIONE
# ===========================================================================
def test_senza_token_non_pubblica_e_non_esplode(monkeypatch, tmp_path):
    """Finche' lui non ha messo il token nei secret, la lavorazione deve
    finire bene lasciando il video su disco."""
    monkeypatch.setattr(config, "INSTAGRAM_ATTIVO", False)
    finto = tmp_path / "reel.mp4"
    finto.write_bytes(b"x" * 10)
    assert instagram.pubblica_reel(str(finto), "didascalia") is None


def test_file_mancante_non_esplode(monkeypatch):
    monkeypatch.setattr(config, "INSTAGRAM_ATTIVO", True)
    assert instagram.pubblica_reel("/non/esiste.mp4", "didascalia") is None


def test_pubblicazione_nei_tre_passi_giusti(monkeypatch, tmp_path):
    """Contenitore, caricamento dei byte, attesa, pubblicazione: se un passo
    salta, il Reel resta a meta' e Instagram risponde errore."""
    monkeypatch.setattr(config, "INSTAGRAM_ATTIVO", True)
    monkeypatch.setattr(config, "INSTAGRAM_TOKEN", "tok")
    monkeypatch.setattr(config, "INSTAGRAM_USER_ID", "999")
    monkeypatch.setattr(instagram, "ATTESA_PASSO", 0)

    chiamate = []

    class Risposta:
        def __init__(self, dati):
            self._dati = dati

        def raise_for_status(self):
            return None

        def json(self):
            return self._dati

    def finta_post(url, **kwargs):
        chiamate.append(url)
        if url.endswith("999/media"):
            assert kwargs["data"]["media_type"] == "REELS"
            assert kwargs["data"]["upload_type"] == "resumable"
            return Risposta({"id": "CONT1"})
        if "rupload" in url:
            assert kwargs["headers"]["Authorization"] == "OAuth tok"
            assert kwargs["headers"]["file_size"] == "10"
            return Risposta({"success": True})
        if url.endswith("999/media_publish"):
            assert kwargs["data"]["creation_id"] == "CONT1"
            return Risposta({"id": "MEDIA1"})
        raise AssertionError(f"chiamata inattesa: {url}")

    def finta_get(url, **kwargs):
        chiamate.append(url)
        if kwargs["params"]["fields"].startswith("status_code"):
            return Risposta({"status_code": "FINISHED"})
        return Risposta({"permalink": "https://instagram.com/reel/x"})

    monkeypatch.setattr(instagram.requests, "post", finta_post)
    monkeypatch.setattr(instagram.requests, "get", finta_get)

    finto = tmp_path / "reel.mp4"
    finto.write_bytes(b"x" * 10)

    assert instagram.pubblica_reel(str(finto), "didascalia") == "MEDIA1"
    assert any("rupload" in c for c in chiamate)
    assert any(c.endswith("media_publish") for c in chiamate)


def test_video_rifiutato_non_viene_pubblicato(monkeypatch, tmp_path):
    """Se Instagram scarta il video, non si deve chiamare media_publish."""
    monkeypatch.setattr(config, "INSTAGRAM_ATTIVO", True)
    monkeypatch.setattr(config, "INSTAGRAM_TOKEN", "tok")
    monkeypatch.setattr(config, "INSTAGRAM_USER_ID", "999")
    monkeypatch.setattr(instagram, "ATTESA_PASSO", 0)

    class Risposta:
        def __init__(self, dati):
            self._dati = dati

        def raise_for_status(self):
            return None

        def json(self):
            return self._dati

    def finta_post(url, **kwargs):
        if url.endswith("media_publish"):
            raise AssertionError("non doveva pubblicare un video rifiutato")
        return Risposta({"id": "CONT1"})

    monkeypatch.setattr(instagram.requests, "post", finta_post)
    monkeypatch.setattr(
        instagram.requests, "get",
        lambda url, **k: Risposta({"status_code": "ERROR", "status": "brutto"}))

    finto = tmp_path / "reel.mp4"
    finto.write_bytes(b"x" * 10)
    assert instagram.pubblica_reel(str(finto), "didascalia") is None
