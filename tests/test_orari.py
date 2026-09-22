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

# L'ora in cui parte la riserva di fine giornata, il 21 settembre 2026.
ADESSO = datetime(2026, 9, 21, 22, 30, tzinfo=ROMA)


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
        for cron in ("'30 7 * * *'", "'30 11 * * *'", "'30 14 * * *'"):
            assert cron in testo, cron
        for orario in ("'14:00'", "'18:00'", "'21:00'"):
            assert orario in testo, orario

    def test_il_video_delle_21_esce_in_inglese(self):
        """Il terzo slot e' l'esperimento sull'inglese: se il workflow non
        passa LINGUA, esce un altro video italiano e la prova non esiste."""
        testo = self._workflow()
        assert "LINGUA:" in testo
        riga = [r for r in testo.splitlines() if r.strip().startswith("LINGUA:")][0]
        assert "'30 14 * * *'" in riga and "'en'" in riga, riga

    def test_i_cron_partono_con_almeno_quattro_ore_di_margine(self):
        """Il ritardo peggiore misurato e' tre ore e mezza: se il cron non
        parte con margine, la run finisce dopo l'ora di uscita e il video
        esce in ritardo invece che puntuale."""
        import re
        testo = self._workflow()
        cron = re.findall(r"cron: '(\d+) (\d+) \* \* \*'", testo)
        assert cron, "nessun cron trovato"
        # L'ultimo e' la riserva di fine giornata: non produce un'uscita sua,
        # quindi non ha un margine da rispettare.
        produzione = [c for c in cron if c != (CRON_RISERVA_MIN, CRON_RISERVA_ORA)]
        # 14:00, 18:00 e 21:00 italiane d'estate sono le 12:00, 16:00 e
        # 19:00 UTC.
        assert len(produzione) == 3, cron
        for (minuto, ora), uscita_utc in zip(produzione, (12, 16, 19)):
            partenza = int(ora) + int(minuto) / 60
            assert uscita_utc - partenza >= 4, (ora, minuto, uscita_utc)

    def test_il_workflow_e_l_elenco_delle_uscite_dicono_la_stessa_cosa(self):
        """orari.SLOT_GIORNALIERI e i cron sono due copie della stessa
        informazione: se divergono, la riserva va a cercare un'uscita che non
        esiste, o non si accorge di quella che manca davvero."""
        testo = self._workflow()
        for orario, _ in orari.SLOT_GIORNALIERI:
            assert f"'{orario}'" in testo, orario
        assert len(orari.SLOT_GIORNALIERI) == 3

    def test_la_riserva_di_fine_giornata_e_collegata(self):
        testo = self._workflow()
        assert f"cron: '{CRON_RISERVA_MIN} {CRON_RISERVA_ORA} * * *'" in testo
        riga = [r for r in testo.splitlines() if r.strip().startswith("RECUPERO:")]
        assert riga, "il workflow non passa RECUPERO"
        assert f"'{CRON_RISERVA_MIN} {CRON_RISERVA_ORA} * * *'" in riga[0], riga

    def test_ogni_lavorazione_dichiara_quale_uscita_copre(self):
        """Senza SLOT la cronologia non sa a quale uscita appartiene il video,
        e il controllo anti-doppione non ha su cosa lavorare."""
        testo = self._workflow()
        riga = [r for r in testo.splitlines() if r.strip().startswith("SLOT:")]
        assert riga, "il workflow non passa SLOT"
        for orario, _ in orari.SLOT_GIORNALIERI:
            assert f"'{orario}'" in riga[0], orario

    def test_la_riserva_ha_tutt_e_due_le_voci(self):
        """Sceglie la lingua a lavorazione iniziata, quindi non puo' contare
        su VOCE_TTS deciso dal cron."""
        testo = self._workflow()
        assert "VOCE_TTS_IT:" in testo
        assert "VOCE_TTS_EN:" in testo


# Il cron della riserva, scritto una volta sola perche' i test sopra lo
# citano piu' volte: le 20:30 UTC, cioe' le 22:30 italiane d'estate.
CRON_RISERVA_MIN = "30"
CRON_RISERVA_ORA = "20"


def _voce(slot, quando, video_id="VIDEOFINTO1"):
    """Una riga di cronologia come la scrive brain.salva_in_cronologia."""
    return {
        "slot": slot,
        "timestamp": int(quando.timestamp()),
        "titolo": "Un titolo qualsiasi",
        "video_id": video_id,
    }


class TestUscitaGiaCoperta:
    """Il freno contro i video doppi.

    Il 21 settembre 2026 GitHub ha fatto partire una lavorazione con sette ore
    di ritardo e un'altra non l'ha fatta partire affatto. Da qui la riserva di
    fine giornata, e da qui questo controllo: due lavorazioni che si
    accavallano non devono produrre due video per la stessa uscita.
    """

    def test_senza_cronologia_non_e_coperta_niente(self):
        assert orari.gia_pubblicato("18:00", []) is False
        assert orari.gia_pubblicato("18:00", None) is False

    def test_senza_slot_non_si_controlla_niente(self):
        """E' il caso delle prove lanciate a mano: non coprono un'uscita."""
        assert orari.gia_pubblicato("", [_voce("18:00", ADESSO)]) is False

    def test_un_video_di_oggi_per_quell_uscita_la_copre(self):
        cronologia = [_voce("18:00", ADESSO.replace(hour=19, minute=10))]
        assert orari.gia_pubblicato("18:00", cronologia, ADESSO) is True

    def test_un_video_scritto_in_anticipo_conta_lo_stesso(self):
        """La cronologia registra quando il video viene scritto, non quando
        YouTube lo pubblica: la lavorazione delle 18:00 parte alle 13:30."""
        cronologia = [_voce("18:00", ADESSO.replace(hour=13, minute=40))]
        assert orari.gia_pubblicato("18:00", cronologia, ADESSO) is True

    def test_un_altra_uscita_non_copre_questa(self):
        cronologia = [_voce("14:00", ADESSO.replace(hour=15))]
        assert orari.gia_pubblicato("18:00", cronologia, ADESSO) is False

    def test_il_video_di_ieri_non_copre_quello_di_oggi(self):
        ieri = ADESSO.replace(day=20, hour=18, minute=30)
        assert orari.gia_pubblicato("18:00", [_voce("18:00", ieri)], ADESSO) is False

    def test_una_lavorazione_morta_prima_dell_upload_non_copre(self):
        """Senza video_id il video non e' mai arrivato sul canale: se
        contasse come uscita coperta, la riserva non servirebbe proprio nel
        caso in cui serve."""
        cronologia = [_voce("18:00", ADESSO.replace(hour=19), video_id=None)]
        assert orari.gia_pubblicato("18:00", cronologia, ADESSO) is False

    def test_le_vecchie_righe_a_stringa_non_fanno_saltare_niente(self):
        """cronologia_trend.json contiene ancora voci del primo formato."""
        cronologia = ["Un vecchio titolo", _voce("18:00", ADESSO.replace(hour=19))]
        assert orari.gia_pubblicato("18:00", cronologia, ADESSO) is True

    def test_un_orario_scritto_male_non_blocca_la_pubblicazione(self):
        assert orari.gia_pubblicato("mezzogiorno", [], ADESSO) is False


class TestQualeUscitaRecuperare:

    def test_se_sono_tutte_a_posto_non_si_recupera_niente(self):
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("18:00", ADESSO.replace(hour=19)),
            _voce("21:00", ADESSO.replace(hour=21, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) is None

    def test_recupera_quella_che_manca(self):
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("21:00", ADESSO.replace(hour=21, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) == ("18:00", "it")

    def test_l_uscita_inglese_si_recupera_in_inglese(self):
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("18:00", ADESSO.replace(hour=19)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) == ("21:00", "en")

    def test_se_ne_mancano_due_si_recupera_la_piu_vecchia(self):
        """Una per volta: nel caso peggiore esce un video in piu', mai tre
        tutti insieme."""
        assert orari.slot_da_recuperare([], ADESSO) == ("14:00", "it")

    def test_non_si_recupera_un_uscita_che_deve_ancora_arrivare(self):
        """Altrimenti il video uscirebbe due volte: una adesso e una all'ora
        sua."""
        pomeriggio = ADESSO.replace(hour=16, minute=0)
        assert orari.slot_da_recuperare([], pomeriggio) == ("14:00", "it")

    def test_non_si_recupera_un_uscita_di_ieri(self):
        """Recuperare alle 8 del mattino l'uscita delle 14:00 di ieri vuol
        dire pubblicare una notizia vecchia di un giorno."""
        mattina = ADESSO.replace(day=22, hour=8, minute=0)
        # Alle 8 del 22 nessuna uscita del 22 e' ancora passata, e quelle del
        # 21 sono tutte oltre le dodici ore tranne le 21:00.
        assert orari.slot_da_recuperare([], mattina) == ("21:00", "en")

    def test_a_meta_mattina_non_c_e_piu_niente_da_recuperare(self):
        tardi = ADESSO.replace(day=22, hour=10, minute=0)
        assert orari.slot_da_recuperare([], tardi) is None
