# -*- coding: utf-8 -*-
"""Clip dalle live: scelta dei momenti, avvisi, e cosa si pubblica."""
import json
import os
from datetime import datetime

from taglia_live import punteggio
import clip_live_pubblica as pub


# --- scelta dei momenti -----------------------------------------------------

def test_trova_il_picco_e_ci_mette_attorno_la_clip():
    energia = [1.0] * 1200
    for s in range(700, 706):
        energia[s] = 20.0
    scelti = punteggio.candidati(punteggio.segnale(energia), quante=3)
    inizio, fine, punti, picco = scelti[0]
    assert 695 <= picco <= 710
    assert inizio < picco < fine
    assert punteggio.DURATA_MIN <= fine - inizio <= punteggio.DURATA_MAX
    assert punti > 50


def test_due_clip_non_pescano_dallo_stesso_momento():
    energia = [1.0] * 2000
    for s in (500, 520, 1500):
        energia[s] = 30.0
    scelti = punteggio.candidati(punteggio.segnale(energia), quante=5)
    picchi = sorted(c[3] for c in scelti)
    assert all(b - a >= punteggio.DISTANZA_MINIMA for a, b in zip(picchi, picchi[1:]))


def test_salta_i_saluti_iniziali():
    energia = [1.0] * 3000
    energia[30] = 50.0
    energia[2000] = 10.0
    picchi = [c[3] for c in punteggio.candidati(punteggio.segnale(energia), quante=1)]
    assert picchi and picchi[0] > punteggio.SALTA_INIZIO


def test_live_piatta_non_produce_clip():
    assert punteggio.candidati(punteggio.segnale([5.0] * 1000)) == []


def test_la_chat_viene_anticipata():
    durata = 1000
    energia = [1.0] * durata
    # la chat esplode 7 secondi dopo il momento vero, al secondo 607
    messaggi = [(607, f"utente{i}", "ahahah LUL") for i in range(40)]
    volume, reazioni = punteggio.chat_per_secondo(messaggi, durata)
    valori = punteggio.segnale(energia, volume, reazioni)
    assert abs(valori.index(max(valori)) - 600) <= 2


def test_finestra_resta_nei_limiti_della_live():
    inizio, fine = punteggio.finestra(5, 100)
    assert inizio == 0 and fine - inizio >= punteggio.DURATA_MIN
    inizio, fine = punteggio.finestra(99, 100)
    assert fine == 100 and fine - inizio >= punteggio.DURATA_MIN


# --- avvisi -----------------------------------------------------------------

def test_testo_pulito_nessun_avviso():
    assert punteggio.controlla_testo("che curva ragazzi, guarda che sorpasso") == []


def test_insulti_e_dati_personali():
    assert "insulti" in punteggio.controlla_testo("ma che stronzata ha fatto")
    assert "dati_personali" in punteggio.controlla_testo("scrivimi a mario@gmail.com")
    assert "dati_personali" in punteggio.controlla_testo("chiamami al 333 123 4567")


def test_utente_della_chat_nominato():
    assert punteggio.controlla_testo("grazie Marco_Rossi88 per il follow",
                                     ["Marco_Rossi88"]) == ["utente_chat"]
    # nomi cortissimi non contano
    assert punteggio.controlla_testo("ok gg", ["gg"]) == []


def test_penalita_abbassa_ma_non_va_sotto_zero():
    assert punteggio.applica_penalita(80, ["insulti"]) == 40
    assert punteggio.applica_penalita(30, ["insulti", "dati_personali"]) == 0


# --- pubblicazione ----------------------------------------------------------

def _scrivi(cartella, nome, **campi):
    scheda = {"id": nome, "titolo": "t", "video_url": "https://x/v.mp4",
              "stato": "approvato", "orario": "2026-10-17T16:00:00+02:00",
              "youtube_id": None}
    scheda.update(campi)
    with open(os.path.join(cartella, f"{nome}.json"), "w", encoding="utf-8") as f:
        json.dump(scheda, f)


def test_si_pubblica_solo_l_approvato_con_orario(tmp_path):
    _scrivi(tmp_path, "a")
    _scrivi(tmp_path, "b", stato="da_approvare")
    _scrivi(tmp_path, "c", orario=None, stato="approvato")
    _scrivi(tmp_path, "d", stato="scartato")
    _scrivi(tmp_path, "e", youtube_id="gia_su")
    _scrivi(tmp_path, "f", orario="2026-10-18T16:00:00+02:00", video_url=None)
    pronte, rimandate = pub.da_pubblicare(pub.leggi_schede(str(tmp_path)))
    assert [s["id"] for _o, _p, s in pronte] == ["a"]
    assert rimandate == []


def test_una_clip_al_giorno(tmp_path):
    _scrivi(tmp_path, "presto", orario="2026-10-17T12:00:00+02:00")
    _scrivi(tmp_path, "tardi", orario="2026-10-17T16:00:00+02:00")
    _scrivi(tmp_path, "domani", orario="2026-10-18T16:00:00+02:00")
    _scrivi(tmp_path, "uscita", stato="pubblicato", youtube_id="x",
            orario="2026-10-19T16:00:00+02:00")
    _scrivi(tmp_path, "stesso_giorno_di_uscita", orario="2026-10-19T18:00:00+02:00")
    pronte, rimandate = pub.da_pubblicare(pub.leggi_schede(str(tmp_path)))
    assert [s["id"] for _o, _p, s in pronte] == ["presto", "domani"]
    assert sorted(s["id"] for _p, s in rimandate) == ["stesso_giorno_di_uscita", "tardi"]


def test_orario_senza_fuso_e_ora_italiana():
    orario = pub.leggi_orario("2026-10-17T16:00:00")
    assert orario.utcoffset().total_seconds() == 2 * 3600


def test_clip_live_non_dichiarata_sintetica(tmp_path, monkeypatch):
    _scrivi(tmp_path, "a", orario="2099-01-01T16:00:00+01:00")
    monkeypatch.setattr(pub, "CARTELLA", str(tmp_path))
    monkeypatch.setattr(pub, "scarica", lambda url, dest, token=None: open(dest, "wb").close())
    monkeypatch.setattr(pub, "_avvisa", lambda testo: None)
    chiamate = {}

    import uploader

    def finto(*a, **kw):
        chiamate.update(kw)
        return "VID123"

    monkeypatch.setattr(uploader, "carica_short", finto)
    assert pub.main() == 0
    assert chiamate["contenuto_sintetico"] is False
    assert isinstance(chiamate["pubblica_alle"], datetime)
    salvata = json.load(open(os.path.join(tmp_path, "a.json"), encoding="utf-8"))
    assert salvata["stato"] == "pubblicato" and salvata["youtube_id"] == "VID123"


def test_samaritan_resta_sintetico_di_default():
    import inspect
    import uploader
    firma = inspect.signature(uploader.carica_short)
    assert firma.parameters["contenuto_sintetico"].default is True


def test_salta_i_saluti_finali():
    energia = [1.0] * 9000
    energia[8990] = 80.0      # musica di chiusura negli ultimi secondi
    energia[4000] = 10.0
    picchi = [c[3] for c in punteggio.candidati(punteggio.segnale(energia), quante=1)]
    assert picchi and picchi[0] < 9000 - punteggio.SALTA_FINE


def test_whisper_passa_alla_cpu_se_la_gpu_fallisce(monkeypatch):
    """Su Windows la GPU si carica ma la trascrizione esplode (cublas64_12.dll)."""
    from taglia_live import taglia_live as tl

    class Parola:
        start, end, word = 0.0, 0.5, " ciao"

    class Segmento:
        words = [Parola()]

    class Modello:
        def __init__(self, dispositivo):
            self.dispositivo = dispositivo

        def transcribe(self, audio, **kw):
            def segmenti():
                if self.dispositivo == "cuda":
                    raise RuntimeError("Library cublas64_12.dll is not found")
                yield Segmento()
            return segmenti(), None

    caricati = []

    def carica(dispositivo):
        caricati.append(dispositivo)
        return Modello(dispositivo)

    monkeypatch.setattr(tl, "_audio_16k", lambda p: [0.0])
    monkeypatch.setattr(tl, "_carica_modello", carica)
    monkeypatch.setattr(tl, "_modello", None)
    monkeypatch.setattr(tl, "_dispositivo", None)
    monkeypatch.setattr(tl, "DISPOSITIVO", "")
    assert tl.trascrivi("x.mp4") == [(0.0, 0.5, "ciao")]
    assert caricati == ["cuda", "cpu"]
    # la clip dopo resta sulla CPU, senza riprovare la GPU
    assert tl.trascrivi("y.mp4") == [(0.0, 0.5, "ciao")]
    assert caricati == ["cuda", "cpu"]


# --- impaginazione ----------------------------------------------------------

from taglia_live import impaginazione as imp


def test_webcam_piccola_in_angolo_divide_lo_schermo():
    # volti veri del primo giro di prova (Dirty Business, sorgente 1920x1080)
    volti = [[(162, 66, 53, 68), (1688, 102, 54, 63)]] * 3 + [[(167, 65, 53, 72)]] * 3
    scelta, r = imp.scegli(volti, 1920, 1080)
    assert scelta == "divisa"
    cx, cy, cw, ch = r["cam"]
    assert cx <= 162 and cx + cw >= 162 + 53 and abs(cw / ch - imp.RAPPORTO_CAM) < 0.05
    gx, gy, gw, gh = r["gioco"]
    assert gh == 1080 and gx + gw <= 1920 and gw % 2 == 0


def test_volto_grande_resta_al_centro():
    volti = [[(845, 317, 311, 430)]] * 6          # Contraddittorio
    assert imp.scegli(volti, 1920, 1080) == ("centro", None)


def test_senza_volti_o_volti_sporadici_resta_al_centro():
    assert imp.scegli([], 1920, 1080) == ("centro", None)
    assert imp.scegli([[], [], [], [], [], [(10, 10, 40, 40)]], 1920, 1080)[0] == "centro"


def test_il_gioco_si_sposta_via_dalla_webcam_a_destra():
    _scelta, r = imp.scegli([[(1700, 900, 50, 60)]] * 6, 1920, 1080)
    cx = r["cam"][0]
    gx, _gy, gw, _gh = r["gioco"]
    assert gx + gw <= cx


def test_filtro_ffmpeg_ha_le_due_fasce():
    _s, r = imp.scegli([[(162, 66, 53, 68)]] * 6, 1920, 1080)
    filtro = imp.filtro_ffmpeg("divisa", r, "x.ass")
    assert "vstack" in filtro and "ass=x.ass" in filtro
    assert "boxblur" in imp.filtro_ffmpeg("centro", None, "x.ass")


# --- versione lunga per TikTok ------------------------------------------------

def test_finestra_tiktok_supera_il_minuto():
    for picco in (5, 600, 3599):
        inizio, fine = punteggio.finestra_tiktok(picco, 3600)
        assert punteggio.TIKTOK_MIN <= fine - inizio <= punteggio.TIKTOK_MAX
        assert 0 <= inizio < fine <= 3600
        assert fine - inizio > 60


def test_finestra_tiktok_live_troppo_corta():
    assert punteggio.finestra_tiktok(20, 40) is None


def test_la_versione_tiktok_non_va_su_youtube(tmp_path):
    _scrivi(tmp_path, "yt")
    _scrivi(tmp_path, "tt", piattaforma="tiktok", orario="2026-10-18T16:00:00+02:00")
    pronte, rimandate = pub.da_pubblicare(pub.leggi_schede(str(tmp_path)))
    assert [s["id"] for _o, _p, s in pronte] == ["yt"]
    assert rimandate == []


# --- link al sito -------------------------------------------------------------

def test_la_clip_porta_alla_home_del_sito_con_gli_utm():
    scheda = {"id": "2899935903_01008",
              "descrizione": "Davide spiega.\n\nDalla live su Twitch: x\n\n#shorts"}
    testo = pub.descrizione_con_sito(scheda)
    righe = testo.split("\n\n")
    assert righe[0] == "Davide spiega."
    assert righe[1].startswith("Notizie e approfondimenti: https://www.davidedurazzi.it/?")
    assert "utm_source=youtube" in righe[1] and "utm_medium=short" in righe[1]
    assert "utm_campaign=clip-live-2899935903_01008" in righe[1]
    assert righe[-1] == "#shorts"


def test_la_clip_non_ripete_il_link():
    scheda = {"id": "a", "descrizione": "Vedi davidedurazzi.it"}
    assert pub.descrizione_con_sito(scheda) == "Vedi davidedurazzi.it"
    assert pub.descrizione_con_sito({"id": "a"}).startswith("Notizie e approfondimenti:")


def test_la_clip_caricata_porta_il_link(tmp_path, monkeypatch):
    _scrivi(tmp_path, "a", orario="2099-01-01T16:00:00+01:00", descrizione="Ciao.")
    monkeypatch.setattr(pub, "CARTELLA", str(tmp_path))
    monkeypatch.setattr(pub, "scarica", lambda url, dest, token=None: open(dest, "wb").close())
    monkeypatch.setattr(pub, "_avvisa", lambda testo: None)
    caricate = []

    import uploader
    monkeypatch.setattr(uploader, "carica_short",
                        lambda video, titolo, descrizione, **kw: caricate.append(descrizione) or "V1")
    assert pub.main() == 0
    assert "https://www.davidedurazzi.it/?utm_source=youtube" in caricate[0]
    # La scheda sul disco resta quella scritta da taglia_live.
    salvata = json.load(open(os.path.join(tmp_path, "a.json"), encoding="utf-8"))
    assert salvata["descrizione"] == "Ciao."
