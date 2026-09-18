"""Test sul motore vocale.

Nessuno di questi test tocca la rete: ElevenLabs e Edge-TTS sono irraggiungibili
dall'ambiente di sviluppo, quindi le risposte sono finte e si verifica solo che
la catena dei ripieghi si comporti come deve. Serve perche' la voce sta nel
percorso che pubblica: se questa parte sbaglia, il video esce muto o robotico.
"""
import importlib
import json

import pytest

import config
import voice


class RispostaFinta:
    def __init__(self, status_code=200, contenuto=b"", dati=None):
        self.status_code = status_code
        self.content = contenuto
        self._dati = dati or {}

    def json(self):
        return self._dati

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


VOCI = {"voices": [
    {"voice_id": "id-primo", "name": "Marco"},
    {"voice_id": "id-secondo", "name": "Giulia"},
]}

# Come ElevenLabs li restituisce davvero: nome piu' descrizione. I tre nomi
# sono quelli veri dell'account di popponetv, con il trattino mediano che
# ElevenLabs usa su uno solo dei tre.
VOCI_CON_DESCRIZIONE = {"voices": [
    {"voice_id": "id-romario", "name": "Romario - Credible, Calm and Balanced"},
    {"voice_id": "id-brando", "name": "Brando Vox – Expressive, Confident, Conversational"},
    {"voice_id": "id-davide", "name": "Davide - Sports Commentator"},
]}


@pytest.fixture(autouse=True)
def azzera_cache():
    voice._voce_risolta = None
    voice._nome_scelto = None
    yield
    voice._voce_risolta = None
    voice._nome_scelto = None


def _chiedi(monkeypatch, valore, precedente=None):
    """Imposta la voce richiesta come farebbe config leggendo la variabile.

    `precedente` e' la voce che risulterebbe usata dal video prima, cioe' il
    punto da cui la rotazione riparte.
    """
    monkeypatch.setattr(config, "ELEVENLABS_VOCE", valore)
    monkeypatch.setattr(
        config, "ELEVENLABS_VOCI", [v.strip() for v in valore.split(",") if v.strip()]
    )
    monkeypatch.setattr(voice, "_ultima_voce_usata", lambda: precedente)
    monkeypatch.setattr(voice, "_segna_voce_usata", lambda nome: None)


class TestSceltaDellaVoce:
    def _con_voci(self, monkeypatch):
        monkeypatch.setattr(
            voice.requests, "get", lambda *a, **k: RispostaFinta(dati=VOCI)
        )

    def test_per_nome_come_si_legge_sul_sito(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "giulia")

        assert voice._risolvi_voce("k") == "id-secondo"

    def test_anche_l_id_diretto_funziona(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "id-primo")

        assert voice._risolvi_voce("k") == "id-primo"

    def test_senza_indicazione_prende_la_prima(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "")

        assert voice._risolvi_voce("k") == "id-primo"

    def test_nome_sbagliato_elenca_quelli_veri(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "Gianni")

        with pytest.raises(RuntimeError) as errore:
            voice._risolvi_voce("k")

        assert "Marco" in str(errore.value) and "Giulia" in str(errore.value)

    def test_la_risoluzione_avviene_una_volta_sola(self, monkeypatch):
        chiamate = []

        def conta(*a, **k):
            chiamate.append(1)
            return RispostaFinta(dati=VOCI)

        monkeypatch.setattr(voice.requests, "get", conta)
        _chiedi(monkeypatch, "Marco")

        voice._risolvi_voce("k")
        voice._risolvi_voce("k")

        assert len(chiamate) == 1


class TestNomeConDescrizione:
    """ElevenLabs aggiunge la descrizione al nome, chi compila scrive il corto."""

    def _con_voci(self, monkeypatch):
        monkeypatch.setattr(
            voice.requests, "get",
            lambda *a, **k: RispostaFinta(dati=VOCI_CON_DESCRIZIONE),
        )

    @pytest.mark.parametrize("scritto,atteso", [
        ("Romario", "id-romario"),
        ("Davide", "id-davide"),
        ("Brando Vox", "id-brando"),          # trattino mediano nel nome vero
        ("brando vox", "id-brando"),          # maiuscole sbagliate
        ("Brando VOx", "id-brando"),          # come l'ha scritto popponetv
        # Nome intero incollato da ElevenLabs: le sue virgole separano le voci,
        # quindi qui arriva solo il primo pezzo. Deve bastare lo stesso.
        ("Romario - Credible", "id-romario"),
    ])
    def test_basta_il_nome_corto(self, monkeypatch, scritto, atteso):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, scritto)

        assert voice._risolvi_voce("k") == atteso

    def test_l_elenco_dell_errore_mostra_i_nomi_corti(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "Gianni")

        with pytest.raises(RuntimeError) as errore:
            voice._risolvi_voce("k")

        # Deve suggerire quello che si scrive, non il nome con la descrizione.
        messaggio = str(errore.value)
        assert "Credible" not in messaggio
        for corto in ("Romario", "Brando Vox", "Davide"):
            assert corto in messaggio

    def test_la_rotazione_funziona_con_i_nomi_veri(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "Romario, Brando VOx, Davide", precedente="Romario")

        assert voice._risolvi_voce("k") == "id-brando"


class TestVociAlternate:
    """Piu' nomi separati da virgola: un video a testa, a turno."""

    def _con_voci(self, monkeypatch):
        monkeypatch.setattr(
            voice.requests, "get", lambda *a, **k: RispostaFinta(dati=VOCI)
        )

    @pytest.mark.parametrize("precedente,atteso", [
        (None, "id-primo"),       # primo video in assoluto
        ("Marco", "id-secondo"),
        ("Giulia", "id-primo"),   # chiuso il giro, si ricomincia
        ("Sconosciuta", "id-primo"),  # lista cambiata: si riparte dall'inizio
    ])
    def test_ogni_video_prende_la_voce_successiva(self, monkeypatch, precedente, atteso):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "Marco, Giulia", precedente=precedente)

        assert voice._risolvi_voce("k") == atteso

    def test_gli_spazi_intorno_ai_nomi_non_contano(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "  Marco ,   Giulia  ", precedente="Marco")

        assert voice._risolvi_voce("k") == "id-secondo"

    def test_un_nome_sbagliato_fa_passare_al_successivo(self, monkeypatch):
        self._con_voci(monkeypatch)
        # Tocca a 'Gianni', che nell'account non esiste: il video esce lo
        # stesso con la voce dopo, invece di ripiegare sulla voce Microsoft.
        _chiedi(monkeypatch, "Marco, Gianni", precedente="Marco")

        assert voice._risolvi_voce("k") == "id-primo"

    def test_sceglie_senza_annotare_subito(self, monkeypatch):
        self._con_voci(monkeypatch)
        annotate = []
        _chiedi(monkeypatch, "Marco, Giulia", precedente="Marco")
        monkeypatch.setattr(voice, "_segna_voce_usata", annotate.append)

        voice._risolvi_voce("k")

        # Scegliere non basta: finche' ElevenLabs non ha prodotto l'audio il
        # turno non e' speso, altrimenti la cronologia direbbe 'Giulia' su un
        # video che parla con la voce Microsoft.
        assert annotate == []
        assert voice._nome_scelto == "Giulia"

    def test_se_nessun_nome_esiste_lo_dice(self, monkeypatch):
        self._con_voci(monkeypatch)
        _chiedi(monkeypatch, "Gianni, Piero")

        with pytest.raises(RuntimeError) as errore:
            voice._risolvi_voce("k")

        assert "Marco" in str(errore.value) and "Giulia" in str(errore.value)


class TestMemoriaDellaRotazione:
    def _storico(self, monkeypatch, tmp_path, contenuto):
        percorso = tmp_path / "cronologia.json"
        percorso.write_text(contenuto, encoding="utf-8")
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(percorso))
        return percorso

    def test_legge_l_ultima_voce_annotata(self, monkeypatch, tmp_path):
        # L'ultimo record e' il video in corso, che la voce non ce l'ha ancora.
        self._storico(monkeypatch, tmp_path, json.dumps([
            {"titolo": "vecchio", "voce": "Marco"},
            {"titolo": "in corso"},
        ]))

        assert voice._ultima_voce_usata() == "Marco"

    def test_vecchie_voci_stringa_non_rompono_niente(self, monkeypatch, tmp_path):
        self._storico(monkeypatch, tmp_path, json.dumps(["titolo vecchio formato"]))

        assert voice._ultima_voce_usata() is None

    @pytest.mark.parametrize("contenuto", ["", "{ non e' json", '{"a": 1}'])
    def test_cronologia_illeggibile_riparte_dall_inizio(self, monkeypatch, tmp_path, contenuto):
        self._storico(monkeypatch, tmp_path, contenuto)

        assert voice._ultima_voce_usata() is None

    def test_cronologia_assente_riparte_dall_inizio(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "manca.json"))

        assert voice._ultima_voce_usata() is None

    def test_annota_sull_ultimo_record(self, monkeypatch, tmp_path):
        percorso = self._storico(monkeypatch, tmp_path, json.dumps([
            {"titolo": "vecchio", "voce": "Marco"},
            {"titolo": "in corso"},
        ]))

        voice._segna_voce_usata("Giulia")

        salvato = json.loads(percorso.read_text(encoding="utf-8"))
        assert salvato[-1]["voce"] == "Giulia"
        assert salvato[-1]["titolo"] == "in corso"   # il resto non si tocca
        assert salvato[0]["voce"] == "Marco"

    def test_senza_cronologia_non_esplode(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "manca.json"))

        voice._segna_voce_usata("Giulia")   # non deve sollevare


class TestSintesiElevenLabs:
    def test_senza_chiave_non_chiama_la_rete(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", None)

        with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
            voice._sintetizza_elevenlabs("ciao", str(tmp_path / "a.mp3"))

    @pytest.mark.parametrize("codice,atteso", [
        (401, "non valida"),
        (402, "piano a pagamento"),
        (429, "credito"),
    ])
    def test_errori_spiegati_in_italiano(self, monkeypatch, tmp_path, codice, atteso):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(voice, "_risolvi_voce", lambda chiave: "id")
        monkeypatch.setattr(
            voice.requests, "post", lambda *a, **k: RispostaFinta(status_code=codice)
        )

        with pytest.raises(RuntimeError, match=atteso):
            voice._sintetizza_elevenlabs("ciao", str(tmp_path / "a.mp3"))

    def test_scrive_l_audio_ricevuto(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(voice, "_risolvi_voce", lambda chiave: "id")
        monkeypatch.setattr(
            voice.requests, "post", lambda *a, **k: RispostaFinta(contenuto=b"mp3" * 400)
        )
        destinazione = tmp_path / "a.mp3"

        voice._sintetizza_elevenlabs("ciao", str(destinazione))

        assert destinazione.read_bytes().startswith(b"mp3")


class TestCatenaDeiRipieghi:
    """Il punto della catena: la pubblicazione non si ferma mai per la voce."""

    def test_elevenlabs_per_primo_quando_c_e_la_chiave(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))

        def finto(testo, destinazione):
            open(destinazione, "wb").write(b"x" * 2048)

        monkeypatch.setattr(voice, "_sintetizza_elevenlabs", finto)
        monkeypatch.setattr(voice, "_sintetizza_edge", lambda *a: pytest.fail(
            "Edge non deve essere chiamato se ElevenLabs riesce"))

        assert voice.genera_voce_samaritan("Ciao a tutti") is not None

    def test_se_elevenlabs_fallisce_si_passa_a_edge(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        usato = []

        def rotto(testo, destinazione):
            raise RuntimeError("credito esaurito")

        async def edge(testo, destinazione):
            usato.append("edge")
            open(destinazione, "wb").write(b"x" * 2048)

        monkeypatch.setattr(voice, "_sintetizza_elevenlabs", rotto)
        monkeypatch.setattr(voice, "_sintetizza_edge", edge)

        assert voice.genera_voce_samaritan("Ciao a tutti") is not None
        assert usato == ["edge"]

    def test_la_voce_si_annota_solo_se_ha_parlato(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        annotate = []
        monkeypatch.setattr(voice, "_segna_voce_usata", annotate.append)

        def finto(testo, destinazione):
            voice._nome_scelto = "Davide"
            open(destinazione, "wb").write(b"x" * 2048)

        monkeypatch.setattr(voice, "_sintetizza_elevenlabs", finto)
        voice.genera_voce_samaritan("Ciao a tutti")

        assert annotate == ["Davide"]

    def test_col_ripiego_non_si_annota_niente(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        annotate = []
        monkeypatch.setattr(voice, "_segna_voce_usata", annotate.append)

        def rifiutato(testo, destinazione):
            # La voce era stata scelta, poi ElevenLabs ha detto no: e' il caso
            # del 402 visto in produzione il 18 settembre 2026.
            voice._nome_scelto = "Davide"
            raise RuntimeError("402 pagamento richiesto")

        async def edge(testo, destinazione):
            open(destinazione, "wb").write(b"x" * 2048)

        monkeypatch.setattr(voice, "_sintetizza_elevenlabs", rifiutato)
        monkeypatch.setattr(voice, "_sintetizza_edge", edge)
        voice.genera_voce_samaritan("Ciao a tutti")

        # Il video parla Microsoft: la cronologia non deve dire 'Davide', e il
        # turno di Davide non e' speso.
        assert annotate == []

    def test_senza_chiave_si_parte_da_edge(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", None)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(voice, "_sintetizza_elevenlabs", lambda *a: pytest.fail(
            "senza chiave ElevenLabs non va nemmeno provato"))

        async def edge(testo, destinazione):
            open(destinazione, "wb").write(b"x" * 2048)

        monkeypatch.setattr(voice, "_sintetizza_edge", edge)

        assert voice.genera_voce_samaritan("Ciao a tutti") is not None


class TestImpostazioni:
    def test_la_chiave_non_e_obbligatoria(self, monkeypatch):
        # Senza ELEVENLABS_API_KEY il progetto deve restare avviabile.
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        importlib.reload(config)

        assert config.ELEVENLABS_API_KEY is None
        assert config.ELEVENLABS_MODELLO == "eleven_multilingual_v2"
