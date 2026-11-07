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


def _modello_finto(caricati, gpu_rotta):
    class Parola:
        start, end, word = 0.0, 0.5, " ciao"

    class Segmento:
        words = [Parola()]

    class Modello:
        def __init__(self, dispositivo):
            self.dispositivo = dispositivo

        def transcribe(self, audio, **kw):
            def segmenti():
                if self.dispositivo == "cuda" and gpu_rotta:
                    raise RuntimeError("Library cublas64_12.dll is not found")
                yield Segmento()
            return segmenti(), None

    def carica(dispositivo):
        caricati.append(dispositivo)
        return Modello(dispositivo)
    return carica


def test_whisper_si_ferma_se_la_gpu_non_va(monkeypatch):
    """Su Windows la GPU si carica ma la trascrizione esplode (cublas64_12.dll):
    niente ripiego sulla CPU (sottotitoli confusi), errore chiaro."""
    import pytest
    from taglia_live import taglia_live as tl
    caricati = []
    monkeypatch.setattr(tl, "_carica_modello", _modello_finto(caricati, gpu_rotta=True))
    monkeypatch.setattr(tl, "librerie_cuda", lambda: [])
    monkeypatch.setattr(tl, "_silenzio_di_prova", lambda: [0.0] * 16000)
    monkeypatch.setattr(tl, "_modello", None)
    monkeypatch.setattr(tl, "DISPOSITIVO", "")
    with pytest.raises(tl.GpuNonDisponibile, match="nvidia-cublas-cu12"):
        tl.controlla_gpu()
    assert caricati == ["cuda"]
    assert tl._modello is None


def test_whisper_usa_la_gpu_controllata(monkeypatch):
    from taglia_live import taglia_live as tl
    caricati = []
    monkeypatch.setattr(tl, "_carica_modello", _modello_finto(caricati, gpu_rotta=False))
    monkeypatch.setattr(tl, "librerie_cuda", lambda: [])
    monkeypatch.setattr(tl, "_silenzio_di_prova", lambda: [0.0] * 16000)
    monkeypatch.setattr(tl, "_audio_16k", lambda p: [0.0])
    monkeypatch.setattr(tl, "_modello", None)
    monkeypatch.setattr(tl, "_dispositivo", None)
    monkeypatch.setattr(tl, "DISPOSITIVO", "")
    tl.controlla_gpu()
    assert tl.trascrivi("x.mp4") == [(0.0, 0.5, "ciao")]
    assert caricati == ["cuda"] and tl._dispositivo == "cuda"


def test_whisper_cpu_solo_se_chiesta(monkeypatch):
    from taglia_live import taglia_live as tl
    caricati = []
    monkeypatch.setattr(tl, "_carica_modello", _modello_finto(caricati, gpu_rotta=True))
    monkeypatch.setattr(tl, "_audio_16k", lambda p: [0.0])
    monkeypatch.setattr(tl, "_modello", None)
    monkeypatch.setattr(tl, "DISPOSITIVO", "cpu")
    tl.controlla_gpu()
    assert tl.trascrivi("x.mp4") == [(0.0, 0.5, "ciao")]
    assert caricati == ["cpu"]


# --- momenti sparsi per la live, non solo l'inizio -------------------------

def test_i_saluti_della_chat_non_contano():
    assert punteggio.e_saluto("ciao a tutti!")
    assert punteggio.e_saluto("Buonasera Hay")
    assert not punteggio.e_saluto("ciao ahahahah")
    assert not punteggio.e_saluto("ma che ha fatto")
    volume, _ = punteggio.chat_per_secondo([(5, "a", "ciao"), (5, "b", "noo")], 10)
    assert volume[5] == 1


def test_bot_e_abbonamenti_regalati_non_sono_reazioni():
    """haytano 5/11: i picchi di chat erano sub regalate e StreamElements."""
    assert punteggio.e_avviso("tano92m", "tano92m gifted a Tier 1 sub to roxyyy93!")
    assert punteggio.e_avviso("StreamElements", "roxyyy93 just subscribed PogChamp")
    assert punteggio.e_avviso("france881", "Cheer1 Cheer1 Cheer1")
    assert punteggio.e_avviso("x", "!discord")
    assert not punteggio.e_avviso("walter_98_", "Porcoooooooo ahahah")
    volume, _ = punteggio.chat_per_secondo(
        [(1, "StreamElements", "a just cheered 5 bits"), (1, "b", "LUL")], 3)
    assert volume[1] == 1


def test_un_ora_di_chat_fitta_all_inizio_non_si_prende_tutte_le_clip():
    """haytano 4/11: chat fitta per la prima ora, picchi veri piu' avanti."""
    durata = 4 * 3600
    energia = [1.0] * durata
    volume = [0.0] * durata
    for s in range(600, 3600):
        volume[s] = 3.0 + (s % 97 == 0) * 2       # chat fitta e un po' mossa
    for picco in (6000, 9000, 12000):
        for s in range(picco, picco + 8):
            volume[s] = 12.0
            energia[s] = 6.0
    valori = punteggio.segnale(energia, volume, [0.0] * durata)
    picchi = sorted(c[3] for c in punteggio.candidati(valori, quante=5))
    assert sum(1 for p in picchi if p < 3600) <= 2
    for picco in (6000, 9000, 12000):
        assert any(abs(p - picco) < 30 for p in picchi)


def test_live_lunga_salta_dieci_minuti_e_si_sparge():
    durata = 4 * 3600
    energia = [1.0] * durata
    for s in (200, 400) + tuple(range(1000, 1700, 100)):
        energia[s] = 40.0
    energia[10000] = 20.0
    picchi = [c[3] for c in punteggio.candidati(punteggio.segnale(energia), quante=4)]
    assert all(p >= punteggio.SALTA_INIZIO_LUNGA for p in picchi)
    assert any(abs(p - 10000) < 5 for p in picchi)


# --- ascolto ------------------------------------------------------------------

def test_ascolto_accordo_e_note():
    from taglia_live import ascolta
    assert ascolta.accordo("CHE CURVA RAGAZZI C****", "che curva ragazzi cazzo") == 1.0
    assert ascolta.accordo("PAROLE INVENTATE QUI", "tutt'altro discorso") == 0.0
    assert ascolta.accordo("", "x") is None
    stacco, muto = ascolta.stacco_e_silenzio([-30, -30, -30, -10, -60])
    assert stacco == 20 and muto == 0.2
    m = {"prima_parola": 4.0, "parole_al_secondo": 0.5, "accordo_sottotitoli": 0.3,
         "stacco_db": 3, "silenzio": 0.0}
    testo = " ".join(ascolta.note(m))
    assert "parte muta" in testo and "poco" in testo and "sottotitoli" in testo


# --- impaginazione ----------------------------------------------------------

from taglia_live import impaginazione as imp


def test_webcam_piccola_in_angolo_divide_lo_schermo():
    # volti veri del primo giro di prova (Dirty Business, sorgente 1920x1080)
    volti = [[(162 + i, 66 + 2 * i, 53, 68), (1688, 102, 54, 63)] for i in range(3)] + [[(167 - i, 65 + i, 53, 72)] for i in range(3)]
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


def test_senza_webcam_il_gioco_si_ingrandisce():
    """alexdieci gioca senza facecam: non la scena intera alta 607 pixel."""
    scelta, r = imp.scegli([[], [], [], [], [], []], 1920, 1080, senza_webcam="gioco")
    assert scelta == "gioco"
    gx, gy, gw, gh = r["gioco"]
    assert gh == 1080 and gw == 810 and gx == 554
    filtro = imp.filtro_ffmpeg("gioco", r, "x.ass")
    assert "crop=810:1080:554:0" in filtro and "ass=x.ass" in filtro
    # OpenCV non ha guardato (nessun fotogramma): resta al centro
    assert imp.scegli([], 1920, 1080, senza_webcam="gioco")[0] == "centro"


def test_il_gioco_si_sposta_via_dalla_webcam_a_destra():
    _scelta, r = imp.scegli([[(1700 + 2 * i, 900 - i, 50, 60)] for i in range(6)], 1920, 1080)
    cx = r["cam"][0]
    gx, _gy, gw, _gh = r["gioco"]
    assert gx + gw <= cx


def test_filtro_ffmpeg_ha_le_due_fasce():
    _s, r = imp.scegli([[(162 + i, 66 + i, 53, 68)] for i in range(6)], 1920, 1080)
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


# --- qualita' per gli streamer (prova del 3/11) --------------------------------

def test_i_picchi_alti_non_finiscono_tutti_a_cento():
    punti = [punteggio.punteggio_da_z(z) for z in (2, 5, 9, 15)]
    assert punti == sorted(punti) and len(set(punti)) == 4 and max(punti) < 100
    assert punteggio.punteggio_da_z(0) == 50


def test_le_voci_inglesi_del_gioco_si_riconoscono():
    assert punteggio.sembra_inglese("Our sex fist part cannot fail!".split())
    assert punteggio.sembra_inglese("So man, you can't control your bloodlust".split())
    assert not punteggio.sembra_inglese("ma non ha più stamina, perché non è stordito".split())
    assert not punteggio.sembra_inglese("Ah, why smetti un secondo di menare le mani".split())


def test_hook_taglia_il_silenzio_iniziale_senza_scendere_sotto_il_minimo():
    parole = [(19.8, 20.5, "ma"), (20.5, 21.7, "stamina"), (24.0, 24.4, "dio")]
    inizio, fine = punteggio.taglio_hook(parole, 34, minimo=15)
    assert inizio == 18.8 and fine - inizio >= 14.99 and fine <= 34
    assert punteggio.taglio_hook([], 34) == (0.0, 34.0)


def test_finestre_sovrapposte():
    assert punteggio.sovrapposte((100, 160), (150, 180))
    assert not punteggio.sovrapposte((100, 160), (160, 200))


def test_sottotitoli_brevi_e_senza_righe_ferme():
    from taglia_live import taglia_live as tl
    parole = [(0.0, 0.4, "attimo"), (0.4, 12.9, "come"), (13.0, 13.4, "fatto"),
              (13.4, 13.8, "c'è")]
    gruppi = tl.gruppi_sottotitoli(parole)
    assert all(f - i <= tl.RIGA_MAX_SECONDI for i, f, _t in gruppi)
    assert all(len(t) <= tl.RIGA_MAX_CARATTERI for _i, _f, t in gruppi)
    assert "c'è" in " ".join(t for _i, _f, t in gruppi)


def test_titolo_di_ripiego_usa_il_parlato():
    from taglia_live import taglia_live as tl
    titolo = tl.titolo_di_ripiego("ok vai. Ma non ha più stamina, perché non è stordito? poi", "Phantom Blade Zero")
    assert titolo.startswith("Ma non ha più stamina") and titolo.endswith("| Phantom Blade Zero")
    assert tl.titolo_di_ripiego("", "X") == "X - dalla live"


def test_la_webcam_e_il_volto_fermo_non_il_piu_grande():
    # webcam piccola sempre a destra, volti del gioco piu' grandi che si spostano
    webcam = (1732, 507, 24, 34)
    volti = [[webcam, (300 + 150 * i, 400, 80, 100)] for i in range(6)]
    volto, quota = imp.volto_tipico(volti)
    assert volto == webcam and quota == 1.0


def test_parola_isolata_non_apre_la_clip():
    parole = [(1.0, 1.6, "ma"), (45.8, 46.5, "non"), (46.5, 47.0, "ha"), (47.0, 48.3, "stamina")]
    inizio, _fine = punteggio.taglio_hook(parole, 75, minimo=15)
    assert inizio == 44.8


def test_le_tiktok_devono_parlare_piu_delle_short():
    assert punteggio.parole_minime("tiktok") > punteggio.parole_minime("youtube") >= 6
    assert punteggio.parole_minime("altro") == punteggio.parole_minime("youtube")


# --- clienti: webcam, nomi, parolacce (prova StrayDog del 3/11) ----------------

# Volti veri di Pax Dei: sei ritratti dell'interfaccia fermi a sinistra e la
# webcam a destra che si muove di qualche pixel.
_HUD = [(23, 266, 29, 39), (23, 180, 29, 42), (20, 428, 29, 43), (22, 512, 27, 37)]
_PAX = [_HUD + [(1713 + (i * 3) % 9, 500 + i % 3, 33 + i % 2, 48)] for i in range(10)]


def test_i_ritratti_fermi_dell_hud_non_sono_la_webcam():
    scelta, r = imp.scegli(_PAX, 1920, 1080)
    assert scelta == "divisa" and r["cam"][0] > 1400


def test_la_zona_della_webcam_si_puo_imporre():
    assert imp.zona_webcam("alto-destra", 1920, 1080) == (960, 0, 1920, 540)
    assert imp.zona_webcam("0.5,0.25,0.5,0.5", 1920, 1080) == (960, 270, 1920, 810)
    assert imp.zona_webcam("boh", 1920, 1080) is None
    ritratti_fermi = [_HUD + [(1715, 500, 33, 48)] for _ in range(10)]
    scelta, r = imp.scegli(ritratti_fermi, 1920, 1080, imp.zona_webcam("destra", 1920, 1080))
    assert scelta == "divisa" and r["cam"][0] > 1400


def test_parolacce_coperte():
    parole = [(0, 1, "ma"), (1, 2, "che"), (2, 3, "cazzo"), (3, 4, "vuoi,"), (4, 5, "porco"), (5, 6, "dio!")]
    assert punteggio.parolacce(parole) == [2, 4, 5]
    assert punteggio.copri_parola("cazzo") == "c****"
    assert punteggio.copri_parola("dio!") == "d**!"
    assert punteggio.applica_penalita(70, ["insulti_coperti"]) == 60


def test_sulle_clip_dei_clienti_non_compare_davide(monkeypatch):
    from taglia_live import taglia_live as tl
    monkeypatch.setattr(tl, "CANALE", "straydogtv")
    assert tl.e_cliente() and tl.censura_attiva()
    assert tl.senza_nomi_sbagliati("Davide Durazzi: devi andare a sentimento") == "Devi andare a sentimento"
    assert "Davide" not in tl.senza_nomi_sbagliati("Davide commenta il monitor")
    monkeypatch.setattr(tl, "CANALE", "davidedurazzi")
    assert not tl.e_cliente() and not tl.censura_attiva()
    assert tl.senza_nomi_sbagliati("Davide commenta") == "Davide commenta"
