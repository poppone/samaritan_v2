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
        for cron in ("'17 1 * * *'", "'17 3 * * *'", "'17 5 * * *'", "'17 6 * * *'"):
            assert cron in testo, cron
        for orario in ("'14:00'", "'18:00'", "'21:00'"):
            assert orario in testo, orario

    def test_il_video_delle_21_esce_in_inglese(self):
        """Il terzo slot e' l'esperimento sull'inglese: se il workflow non
        passa LINGUA, esce un altro video italiano e la prova non esiste."""
        testo = self._workflow()
        assert "LINGUA:" in testo
        riga = [r for r in testo.splitlines() if r.strip().startswith("LINGUA:")][0]
        assert "'17 6 * * *'" in riga and "'en'" in riga, riga

    def test_i_cron_partono_con_almeno_dieci_ore_di_margine(self):
        """Il 28 settembre 2026 GitHub ha fatto partire le quattro
        lavorazioni con sei-otto ore di ritardo: se il cron non parte con
        margine, la run finisce dopo l'ora di uscita e il video esce in
        ritardo invece che puntuale. Ma non oltre ANTICIPO_PARTENZA_ORE,
        altrimenti la lavorazione si crede di ieri."""
        import re
        testo = self._workflow()
        cron = re.findall(r"cron: '(\d+) (\d+) \* \* \*'", testo)
        assert cron, "nessun cron trovato"
        # L'ultimo e' la riserva di fine giornata: non produce un'uscita sua,
        # quindi non ha un margine da rispettare.
        produzione = [c for c in cron if c != (CRON_RISERVA_MIN, CRON_RISERVA_ORA)]
        # 14:00, 18:00, 20:00 e 21:00 italiane d'estate sono le 12:00,
        # 16:00, 18:00 e 19:00 UTC.
        assert len(produzione) == 4, cron
        for (minuto, ora), uscita_utc in zip(produzione, (12, 16, 18, 19)):
            partenza = int(ora) + int(minuto) / 60
            assert uscita_utc - partenza >= 10, (ora, minuto, uscita_utc)
            # D'inverno l'uscita e' un'ora piu' tardi in UTC.
            assert uscita_utc + 1 - partenza <= orari.ANTICIPO_PARTENZA_ORE, (
                ora, minuto, uscita_utc)

    def test_il_workflow_e_l_elenco_delle_uscite_dicono_la_stessa_cosa(self):
        """orari.SLOT_GIORNALIERI e i cron sono due copie della stessa
        informazione: se divergono, la riserva va a cercare un'uscita che non
        esiste, o non si accorge di quella che manca davvero."""
        testo = self._workflow()
        for orario, _, _ in orari.SLOT_GIORNALIERI:
            assert f"'{orario}'" in testo, orario
        assert len(orari.SLOT_GIORNALIERI) == 4

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
        for orario, _, _ in orari.SLOT_GIORNALIERI:
            assert f"'{orario}'" in riga[0], orario

    def test_ogni_uscita_in_inglese_ha_lingua_e_voce_inglesi(self):
        """Senza, l'uscita delle 20:00 diventata inglese il 27 settembre 2026
        uscirebbe in italiano, e la memoria anti-ripetizione la metterebbe
        fra quelle italiane."""
        import re
        testo = self._workflow()
        righe = testo.splitlines()
        slot_riga = [r for r in righe if r.strip().startswith("SLOT:")][0]
        lingua = [r for r in righe if r.strip().startswith("LINGUA:")][0]
        voce = [r for r in righe if r.strip().startswith("VOCE_TTS:")][0]
        for orario, lingua_slot, _ in orari.SLOT_GIORNALIERI:
            cron = re.search(
                r"\(github\.event\.schedule == '([^']+)' && '"
                + re.escape(orario) + r"'\)", slot_riga).group(1)
            assert (cron in lingua) == (lingua_slot == "en"), (orario, lingua)
            assert (cron in voce) == (lingua_slot == "en"), (orario, voce)

    def test_nessuna_uscita_programmata_fa_il_video_lungo(self):
        """I tre video lunghi usciti alle 20:00 hanno fatto 6, 0 e 0
        visualizzazioni: il lungo si lancia solo a mano."""
        testo = self._workflow()
        riga = [r for r in testo.splitlines()
                if r.strip().startswith("VIDEO_LUNGO:")][0]
        assert "schedule" not in riga, riga
        assert "inputs.lungo" in riga, riga
        assert all(formato == "short" for _, _, formato in orari.SLOT_GIORNALIERI)

    def test_una_run_a_mano_puo_coprire_un_uscita(self):
        """Per rimpiazzare un cron che non e' partito, pubblicando comunque
        all'ora giusta e nella lingua giusta."""
        righe = self._workflow().splitlines()
        for campo in ("ORARIO_USCITA:", "SLOT:"):
            riga = [r for r in righe if r.strip().startswith(campo)][0]
            assert "inputs.slot" in riga, riga
        for campo in ("LINGUA:", "VOCE_TTS:"):
            riga = [r for r in righe if r.strip().startswith(campo)][0]
            assert "inputs.slot == '20:00'" in riga and "inputs.slot == '21:00'" in riga, riga

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

    def test_partire_prima_della_propria_uscita_non_la_confonde_con_ieri(self):
        """I tre casi veri: una lavorazione partita pochi minuti prima della
        sua uscita trovava il video di ieri alla stessa ora e si fermava.
        Le date e gli orari sono quelli delle lavorazioni perse."""
        casi = [
            # (slot, partenza della lavorazione, video del giorno prima)
            ("21:00", datetime(2026, 9, 22, 20, 12, tzinfo=ROMA),
             datetime(2026, 9, 21, 21, 42, tzinfo=ROMA)),
            ("21:00", datetime(2026, 9, 24, 20, 34, tzinfo=ROMA),
             datetime(2026, 9, 23, 20, 35, tzinfo=ROMA)),
            ("18:00", datetime(2026, 9, 25, 17, 54, tzinfo=ROMA),
             datetime(2026, 9, 24, 17, 56, tzinfo=ROMA)),
        ]
        for slot, partenza, ieri in casi:
            assert orari.gia_pubblicato(slot, [_voce(slot, ieri)], partenza) is False, (
                f"{slot} del {partenza:%d/%m} scambiata per gia' coperta")

    def test_partendo_in_anticipo_il_video_di_oggi_la_copre_ancora(self):
        """Il freno deve restare: se l'uscita di oggi ha gia' il suo video
        (per esempio fatto dalla riserva o da una prova), chi parte prima
        dell'orario si ferma lo stesso."""
        partenza = datetime(2026, 9, 25, 17, 54, tzinfo=ROMA)
        oggi = datetime(2026, 9, 25, 14, 10, tzinfo=ROMA)
        assert orari.gia_pubblicato("18:00", [_voce("18:00", oggi)], partenza) is True

    def test_la_partenza_col_cron_puntuale_guarda_l_uscita_di_oggi(self):
        """Il caso limite: nessun ritardo, la lavorazione parte all'ora del
        cron, quattro ore e mezza prima d'estate e cinque e mezza d'inverno.
        Deve comunque ragionare sull'uscita di oggi."""
        for partenza in (datetime(2026, 9, 25, 13, 30, tzinfo=ROMA),
                         datetime(2026, 12, 15, 12, 30, tzinfo=ROMA)):
            ieri = partenza.replace(day=partenza.day - 1, hour=18, minute=0)
            assert orari.gia_pubblicato("18:00", [_voce("18:00", ieri)], partenza) is False

    def test_partendo_di_notte_guarda_l_uscita_di_oggi(self):
        """Dal 29 settembre 2026 il cron delle 14:00 parte alle 3:17: il
        video delle 14:00 di ieri non deve fermarlo."""
        for partenza in (datetime(2026, 9, 29, 3, 17, tzinfo=ROMA),
                         datetime(2026, 12, 15, 2, 17, tzinfo=ROMA)):
            ieri = partenza.replace(day=partenza.day - 1, hour=17, minute=45)
            voce = _voce("14:00", ieri)
            voce["uscita"] = int(ieri.replace(hour=14, minute=0).timestamp())
            assert orari.gia_pubblicato("14:00", [voce], partenza) is False

    def test_il_video_scritto_di_notte_copre_l_uscita_del_giorno(self):
        """Scritto alle 3:30 per le 14:00: fuori dalla vecchia finestra, ma
        la riga dice quale uscita copre."""
        partenza = datetime(2026, 9, 29, 3, 17, tzinfo=ROMA)
        scritto = partenza.replace(minute=30)
        voce = _voce("14:00", scritto)
        voce["uscita"] = orari.uscita_da_coprire("14:00", partenza)
        assert voce["uscita"] == int(datetime(2026, 9, 29, 14, 0, tzinfo=ROMA).timestamp())
        dopo = datetime(2026, 9, 29, 11, 0, tzinfo=ROMA)
        assert orari.gia_pubblicato("14:00", [voce], dopo) is True
        assert orari.slot_da_recuperare([voce], ADESSO.replace(day=29)) == (
            "18:00", "it", "short")

    def test_la_riserva_scrive_l_uscita_passata(self):
        ora = datetime(2026, 9, 29, 0, 10, tzinfo=ROMA)
        assert orari.uscita_da_coprire("18:00", ora, recupero=True) == int(
            datetime(2026, 9, 28, 18, 0, tzinfo=ROMA).timestamp())
        assert orari.uscita_da_coprire("", ora) is None
        assert orari.uscita_da_coprire("mezzogiorno", ora) is None

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
            _voce("20:00", ADESSO.replace(hour=20, minute=30)),
            _voce("21:00", ADESSO.replace(hour=21, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) is None

    def test_recupera_quella_che_manca(self):
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("20:00", ADESSO.replace(hour=20, minute=30)),
            _voce("21:00", ADESSO.replace(hour=21, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) == (
            "18:00", "it", "short")

    def test_le_20_si_recuperano_in_inglese(self):
        """Lingua e formato viaggiano insieme all'orario: la riserva rifa'
        l'uscita come l'uscita la voleva."""
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("18:00", ADESSO.replace(hour=19)),
            _voce("21:00", ADESSO.replace(hour=21, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) == (
            "20:00", "en", "short")

    def test_l_uscita_inglese_si_recupera_in_inglese(self):
        cronologia = [
            _voce("14:00", ADESSO.replace(hour=15)),
            _voce("18:00", ADESSO.replace(hour=19)),
            _voce("20:00", ADESSO.replace(hour=20, minute=30)),
        ]
        assert orari.slot_da_recuperare(cronologia, ADESSO) == (
            "21:00", "en", "short")

    def test_se_ne_mancano_due_si_recupera_la_piu_vecchia(self):
        """Una per volta: nel caso peggiore esce un video in piu', mai tre
        tutti insieme."""
        assert orari.slot_da_recuperare([], ADESSO) == ("14:00", "it", "short")

    def test_non_si_recupera_un_uscita_che_deve_ancora_arrivare(self):
        """Altrimenti il video uscirebbe due volte: una adesso e una all'ora
        sua."""
        pomeriggio = ADESSO.replace(hour=16, minute=0)
        assert orari.slot_da_recuperare([], pomeriggio) == (
            "14:00", "it", "short")

    def test_non_si_recupera_un_uscita_di_ieri(self):
        """Recuperare alle 8 del mattino l'uscita delle 14:00 di ieri vuol
        dire pubblicare una notizia vecchia di un giorno."""
        mattina = ADESSO.replace(day=22, hour=8, minute=0)
        # Alle 8 del 22 nessuna uscita del 22 e' ancora passata, e quelle del
        # 21 sono tutte oltre le dodici ore tranne le 20:00 e le 21:00: si
        # recupera la piu' vecchia delle due.
        assert orari.slot_da_recuperare([], mattina) == ("20:00", "en", "short")

    def test_la_riserva_non_confonde_un_uscita_di_ieri_con_quella_di_oggi(self):
        """La riserva guarda solo uscite passate. Se parte cosi' tardi che
        l'uscita delle 14:00 di oggi e' vicina, deve comunque giudicare quella
        di ieri sera per quello che e'."""
        mattina = ADESSO.replace(day=22, hour=8, minute=0)
        coperte = [_voce("20:00", ADESSO.replace(hour=19, minute=50)),
                   _voce("21:00", ADESSO.replace(hour=20, minute=40))]
        assert orari.slot_da_recuperare(coperte, mattina) is None

    def test_a_meta_mattina_non_c_e_piu_niente_da_recuperare(self):
        tardi = ADESSO.replace(day=22, hour=10, minute=0)
        assert orari.slot_da_recuperare([], tardi) is None
