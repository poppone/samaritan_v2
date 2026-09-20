# -*- coding: utf-8 -*-
"""Test sull'ora a cui il video compare sul canale.

popponetv il 20 settembre 2026: "deve pubblicare su youtube alle 14 e alle 18
non piu' tardi, minuto piu' minuto meno". Con il cron da solo non e'
ottenibile: GitHub fa partire le run schedulate in ritardo, fra un'ora e
quaranta e tre ore e mezza nelle run del 17-19 settembre. L'ora esatta la da'
YouTube, a cui si chiede di pubblicare da solo a un istante preciso.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import orari
import uploader


ROMA = ZoneInfo("Europe/Rome")


class TestUscitaProgrammata:

    def test_l_orario_di_oggi_ancora_da_venire(self, monkeypatch):
        monkeypatch.setattr(config, "ORARIO_USCITA", "18:00")
        monkeypatch.setattr(config, "FUSO_USCITA", "Europe/Rome")

        uscita = orari.uscita_programmata(
            datetime(2026, 9, 20, 14, 53, tzinfo=ROMA)
        )

        assert uscita == datetime(2026, 9, 20, 18, 0, tzinfo=ROMA)

    def test_un_orario_gia_passato_pubblica_subito(self, monkeypatch):
        """Se la run arriva in ritardo oltre l'orario, uscire adesso e' meglio
        che aspettare il giorno dopo: "non piu' tardi" vale piu' della
        precisione."""
        monkeypatch.setattr(config, "ORARIO_USCITA", "14:00")
        monkeypatch.setattr(config, "FUSO_USCITA", "Europe/Rome")

        assert orari.uscita_programmata(
            datetime(2026, 9, 20, 14, 1, tzinfo=ROMA)
        ) is None

    def test_senza_orario_configurato_pubblica_subito(self, monkeypatch):
        """E' il caso delle run lanciate a mano dalla tab Actions."""
        monkeypatch.setattr(config, "ORARIO_USCITA", "")
        assert orari.uscita_programmata() is None

    def test_un_orario_scritto_male_non_ferma_la_pubblicazione(self, monkeypatch):
        monkeypatch.setattr(config, "FUSO_USCITA", "Europe/Rome")
        for sbagliato in ("mezzogiorno", "25:00", "14:99", "::"):
            monkeypatch.setattr(config, "ORARIO_USCITA", sbagliato)
            assert orari.uscita_programmata(
                datetime(2026, 9, 20, 9, 0, tzinfo=ROMA)
            ) is None, sbagliato

    def test_un_fuso_inesistente_non_ferma_la_pubblicazione(self, monkeypatch):
        monkeypatch.setattr(config, "ORARIO_USCITA", "18:00")
        monkeypatch.setattr(config, "FUSO_USCITA", "Europa/Nonesiste")
        assert orari.uscita_programmata(
            datetime(2026, 9, 20, 9, 0, tzinfo=ROMA)
        ) is None

    def test_l_ora_legale_non_sposta_piu_l_uscita(self, monkeypatch):
        """Il motivo per cui l'orario sta nel codice e non piu' in UTC dentro
        il workflow: a fine ottobre l'Italia torna all'ora solare e prima
        andavano corrette le ore del cron a mano."""
        monkeypatch.setattr(config, "ORARIO_USCITA", "14:00")
        monkeypatch.setattr(config, "FUSO_USCITA", "Europe/Rome")

        estate = orari.uscita_programmata(datetime(2026, 9, 20, 8, 0, tzinfo=ROMA))
        inverno = orari.uscita_programmata(datetime(2026, 12, 20, 8, 0, tzinfo=ROMA))

        assert estate.hour == inverno.hour == 14
        # Stessa ora italiana, due offset UTC diversi: 12:00 e 13:00 UTC.
        assert estate.utcoffset().total_seconds() == 2 * 3600
        assert inverno.utcoffset().total_seconds() == 1 * 3600


class TestPublishAt:
    """Quello che finisce davvero nella richiesta a YouTube."""

    def _corpo(self, monkeypatch, **kwargs):
        visti = {}

        class FintaRichiesta:
            def next_chunk(self):
                return None, {"id": "VIDEOFINTO1"}

        class FintiVideo:
            def insert(self, part, body, media_body):
                visti["body"] = body
                return FintaRichiesta()

        class FintoYouTube:
            def videos(self):
                return FintiVideo()

        monkeypatch.setattr(uploader, "autentica_youtube", lambda: FintoYouTube())
        monkeypatch.setattr(uploader, "MediaFileUpload", lambda *a, **k: object())
        monkeypatch.setattr(uploader.os.path, "exists", lambda p: True)
        monkeypatch.setattr(uploader, "imposta_miniatura", lambda *a, **k: True)

        uploader.carica_short("/tmp/finto.mp4", "Titolo", "Descrizione", **kwargs)
        return visti["body"]["status"]

    def test_programmato_sale_privato_con_publishAt_in_utc(self, monkeypatch):
        stato = self._corpo(
            monkeypatch, privacy="public",
            pubblica_alle=datetime(2026, 9, 20, 18, 0, tzinfo=ROMA),
        )
        # Privato fino all'ora giusta: e' cosi' che YouTube programma.
        assert stato["privacyStatus"] == "private"
        assert stato["publishAt"] == "2026-09-20T16:00:00Z"

    def test_senza_orario_resta_tutto_come_prima(self, monkeypatch):
        stato = self._corpo(monkeypatch, privacy="public")
        assert stato["privacyStatus"] == "public"
        assert "publishAt" not in stato

    def test_una_prova_privata_non_viene_programmata(self, monkeypatch):
        """Una run lanciata a mano in privato deve restare privata e basta,
        non diventare un video pubblico programmato."""
        stato = self._corpo(
            monkeypatch, privacy="private",
            pubblica_alle=datetime(2026, 9, 20, 18, 0, tzinfo=ROMA),
        )
        assert stato["privacyStatus"] == "private"
        assert "publishAt" not in stato

    def test_la_dichiarazione_di_contenuto_sintetico_resta(self, monkeypatch):
        stato = self._corpo(
            monkeypatch, privacy="public",
            pubblica_alle=datetime(2026, 9, 20, 18, 0, tzinfo=ROMA),
        )
        assert stato["containsSyntheticMedia"] is True
        assert stato["selfDeclaredMadeForKids"] is False


class TestWorkflowCollegato:
    """Il codice sopra non serve a niente se il workflow non passa l'orario."""

    def _workflow(self):
        import os
        qui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(qui, ".github/workflows/samaritan.yml"),
                  encoding="utf-8") as f:
            return f.read()

    def test_ogni_cron_ha_il_suo_orario_di_uscita(self):
        testo = self._workflow()
        assert "ORARIO_USCITA:" in testo
        assert "'30 11 * * *'" in testo and "'30 7 * * *'" in testo
        assert "'18:00'" in testo and "'14:00'" in testo

    def test_i_cron_partono_con_almeno_quattro_ore_di_margine(self):
        """Il ritardo peggiore misurato e' tre ore e mezza: se il cron non
        parte con margine, la run finisce dopo l'ora di uscita e il video
        esce in ritardo invece che puntuale."""
        import re
        testo = self._workflow()
        cron = re.findall(r"cron: '(\d+) (\d+) \* \* \*'", testo)
        assert cron, "nessun cron trovato"
        # 14:00 e 18:00 italiane d'estate sono le 12:00 e le 16:00 UTC.
        for (minuto, ora), uscita_utc in zip(cron, (12, 16)):
            partenza = int(ora) + int(minuto) / 60
            assert uscita_utc - partenza >= 4, (ora, minuto, uscita_utc)
