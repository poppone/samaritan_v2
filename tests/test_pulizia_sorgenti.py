"""Test sulla pulizia dei video prima del montaggio.

Il 2 novembre 2026 le uscite delle 18:00 e delle 21:00 su GTA VI si sono
fermate con "Montaggio fallito": i trailer di Rockstar avevano una traccia di
timecode (tmcd) che il lettore di moviepy non sa interpretare, e tutti e tre
venivano scartati. Ora ogni video si riscrive senza tracce dati prima del
montaggio, e se il materiale ufficiale resta illeggibile si ripiega sulla
riserva invece di saltare l'uscita.
"""
import os
import shutil
import subprocess
import sys
import types

import pytest

import config
import gameplay


@pytest.fixture
def temp(monkeypatch, tmp_path):
    cartella = tmp_path / "temp"
    monkeypatch.setattr(config, "DIR_TEMP", str(cartella))
    return cartella


def _finto_ffmpeg(monkeypatch, esiti):
    """subprocess.run finto: per ogni chiamata il prossimo esito della lista.
    True scrive il file di uscita, False fa fallire ffmpeg."""
    chiamate = []

    def run(comando, **kw):
        chiamate.append(comando)
        if not esiti.pop(0):
            raise subprocess.CalledProcessError(1, comando, stderr=b"rotto")
        with open(comando[-1], "wb") as f:
            f.write(b"video")
        return subprocess.CompletedProcess(comando, 0)

    monkeypatch.setattr(gameplay.subprocess, "run", run)
    return chiamate


class TestComandoDiPulizia:

    def test_tiene_solo_video_e_audio_senza_timecode(self):
        comando = gameplay._comando_pulizia("in.mp4", "out.mp4")
        testo = " ".join(comando)
        assert "-map 0:v:0" in testo
        assert "-map 0:a?" in testo
        assert "-dn" in comando
        assert "-map_metadata -1" in testo
        assert "-c copy" in testo
        assert comando[-1] == "out.mp4"

    def test_la_ricodifica_non_copia(self):
        comando = gameplay._comando_pulizia("in.mp4", "out.mp4", ricodifica=True)
        assert "copy" not in comando
        assert "libx264" in comando
        assert "-dn" in comando


class TestNormalizzaPerMontaggio:

    def test_il_remux_basta(self, monkeypatch, temp):
        chiamate = _finto_ffmpeg(monkeypatch, [True])
        monkeypatch.setattr(gameplay, "_leggibile_dal_montaggio", lambda p: True)
        uscita = gameplay.normalizza_per_montaggio(
            "/x/ufficiale_gta6_0_GTAVI_Trailer_2.mp4")
        assert uscita == str(temp / "pulito_ufficiale_gta6_0_GTAVI_Trailer_2.mp4")
        assert len(chiamate) == 1 and "copy" in chiamate[0]

    def test_se_il_remux_fallisce_si_ricodifica(self, monkeypatch, temp):
        chiamate = _finto_ffmpeg(monkeypatch, [False, True])
        monkeypatch.setattr(gameplay, "_leggibile_dal_montaggio", lambda p: True)
        assert gameplay.normalizza_per_montaggio("/x/a.mp4")
        assert "libx264" in chiamate[1]

    def test_se_il_remux_resta_illeggibile_si_ricodifica(self, monkeypatch, temp):
        chiamate = _finto_ffmpeg(monkeypatch, [True, True])
        letture = iter([False, True])
        monkeypatch.setattr(gameplay, "_leggibile_dal_montaggio",
                            lambda p: next(letture))
        assert gameplay.normalizza_per_montaggio("/x/a.mp4")
        assert len(chiamate) == 2

    def test_illeggibile_anche_dopo_la_ricodifica(self, monkeypatch, temp):
        _finto_ffmpeg(monkeypatch, [True, True])
        monkeypatch.setattr(gameplay, "_leggibile_dal_montaggio", lambda p: False)
        assert gameplay.normalizza_per_montaggio("/x/a.mp4") is None

    def test_ffmpeg_fallisce_sempre(self, monkeypatch, temp):
        _finto_ffmpeg(monkeypatch, [False, False])
        assert gameplay.normalizza_per_montaggio("/x/a.mp4") is None

    def test_le_clip_mie_non_si_sovrascrivono(self, monkeypatch, temp, tmp_path):
        # Le clip girate in casa stanno nel repository: il file pulito va
        # sempre in DIR_TEMP.
        _finto_ffmpeg(monkeypatch, [True])
        monkeypatch.setattr(gameplay, "_leggibile_dal_montaggio", lambda p: True)
        mia = tmp_path / "clip_mie" / "guida" / "volante.mov"
        uscita = gameplay.normalizza_per_montaggio(str(mia))
        assert os.path.dirname(uscita) == str(temp)
        assert uscita.endswith(".mp4")


class TestNormalizzaSorgenti:

    def test_scarta_solo_la_sorgente_illeggibile(self, monkeypatch):
        monkeypatch.setattr(gameplay, "normalizza_per_montaggio",
                            lambda p: None if "rotto" in p else "pulito_" + p)
        sorgenti = [
            {"tipo": "video", "path": "rotto.mp4", "gioco": "GTA"},
            {"tipo": "video", "path": "buono.mp4", "gioco": "GTA"},
            {"tipo": "immagine", "path": "shot.jpg", "gioco": "GTA"},
        ]
        pulite = gameplay.normalizza_sorgenti(sorgenti)
        assert [s["path"] for s in pulite] == ["pulito_buono.mp4", "shot.jpg"]
        assert pulite[0]["gioco"] == "GTA"


class TestRipiegoSeTuttoIlMaterialeUfficialeEScartato:
    """Il caso del 2 novembre: tre trailer di GTA VI scaricati, nessuno
    leggibile. Prima il video saltava, ora si monta con la riserva."""

    def _prepara(self, monkeypatch, tmp_path, leggibili):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "STEAM_MAX_TRAILER", 3)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay, "clip_mie", lambda c, s: [])
        monkeypatch.setattr(gameplay, "trailer_dalla_pagina_ufficiale",
                            lambda chiave: [
                                "https://rockstar/GTAVI_Launch_Trailer.mp4",
                                "https://rockstar/GTAVI_An_Extended_Look.mp4",
                                "https://rockstar/GTAVI_Trailer_2.mp4"])
        monkeypatch.setattr(gameplay, "punti_di_taglio", lambda u, s: [0])

        def finto_mp4(url, destinazione, salta=0, durata=None, a_1080=False):
            open(destinazione, "wb").close()
            return True
        monkeypatch.setattr(gameplay, "_estrai_mp4", finto_mp4)
        monkeypatch.setattr(
            gameplay, "normalizza_per_montaggio",
            lambda p: p if ("bg_" in p or any(n in p for n in leggibili)) else None)

        chiamate = []
        finto = types.ModuleType("stock")

        def per_scene(scene, quante=None, contesto=""):
            chiamate.append(quante)
            return [(f"bg_{i}.mp4", 0) for i in range(quante)]
        finto.scarica_clip_per_scene = per_scene
        monkeypatch.setitem(sys.modules, "stock", finto)
        return chiamate

    def test_tutti_scartati_si_ripiega_su_pexels(self, monkeypatch, tmp_path):
        chiamate = self._prepara(monkeypatch, tmp_path, leggibili=())
        sorgenti, _ = gameplay.procura_materiale("Grand Theft Auto VI", minimo=3)
        assert chiamate, "la riserva non e' stata chiesta"
        assert sorgenti
        assert all(s["gioco"] is None for s in sorgenti)
        assert all(os.path.basename(s["path"]).startswith("bg_") for s in sorgenti)

    def test_tutti_leggibili_niente_riserva(self, monkeypatch, tmp_path):
        chiamate = self._prepara(monkeypatch, tmp_path, leggibili=("GTAVI",))
        sorgenti, nome = gameplay.procura_materiale("Grand Theft Auto VI", minimo=3)
        assert chiamate == []
        assert len(sorgenti) == 3
        assert all(s["gioco"] == nome for s in sorgenti)

    def test_uno_solo_rotto_resta_il_resto(self, monkeypatch, tmp_path):
        chiamate = self._prepara(monkeypatch, tmp_path,
                                 leggibili=("Launch", "Extended"))
        sorgenti, nome = gameplay.procura_materiale("Grand Theft Auto VI", minimo=2)
        assert chiamate == []
        assert len(sorgenti) == 2


class TestIlMontaggioRipiegaSullaRiserva:
    """Se moviepy non apre nemmeno un pezzo del materiale ufficiale, il
    montaggio riprova con la riserva invece di fermarsi."""

    def test_il_sorgente_di_maker_ripiega(self):
        # maker.py non si importa nella CI (moviepy): controllo sul sorgente,
        # come in test_confezionamento.
        radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(radice, "maker.py"), encoding="utf-8") as f:
            maker_py = f.read()
        assert "from gameplay import materiale_di_riserva" in maker_py
        ripiego = maker_py.index("materiale_di_riserva(")
        assert ripiego < maker_py.index('"[Errore Maker] Montaggio fallito')

    def test_montaggio_vero_con_riserva(self, monkeypatch, tmp_path):
        maker = pytest.importorskip("maker")
        ufficiali = [{"tipo": "video", "path": f"u{i}.mp4", "gioco": "GTA VI"}
                     for i in range(3)]
        riserva = [{"tipo": "video", "path": "bg_0.mp4", "gioco": None}]
        monkeypatch.setattr(config, "DIR_OUTPUT", str(tmp_path))
        monkeypatch.setattr(gameplay, "procura_materiale",
                            lambda **kw: (list(ufficiali), "GTA VI"))
        monkeypatch.setattr(gameplay, "materiale_di_riserva",
                            lambda *a, **k: list(riserva))

        class Audio:
            duration = 10.0

            def close(self):
                pass
        monkeypatch.setattr(maker, "AudioFileClip", lambda p: Audio())

        class Montato(Exception):
            pass
        montaggi = []

        def costruisci(sorgenti, durata, stile=None):
            montaggi.append([s["path"] for s in sorgenti])
            if sorgenti[0]["gioco"]:
                return None
            raise Montato()
        monkeypatch.setattr(maker, "costruisci_sfondo_montato", costruisci)

        resoconto = {}
        with pytest.raises(Montato):
            maker.assembla_video_finale(
                testo_per_audio="testo", titolo="GTA 6", gioco="GTA 6",
                resoconto=resoconto, audio_pronto="audio.mp3")
        assert montaggi == [["u0.mp4", "u1.mp4", "u2.mp4"], ["bg_0.mp4"]]
        assert resoconto["sorgenti_ufficiali"] == 0


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="serve ffmpeg")
class TestConFfmpegVero:

    def test_la_traccia_timecode_sparisce(self, temp, tmp_path):
        sorgente = tmp_path / "trailer_con_timecode.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=size=320x240:rate=30", "-t", "1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-timecode", "00:00:00:00", str(sorgente)],
            check=True)

        def tracce(percorso):
            esito = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_type", "-of", "csv=p=0", str(percorso)],
                check=True, stdout=subprocess.PIPE)
            return esito.stdout.decode().split()

        assert "data" in tracce(sorgente)
        uscita = gameplay.normalizza_per_montaggio(str(sorgente))
        assert uscita
        assert tracce(uscita) == ["video"]
