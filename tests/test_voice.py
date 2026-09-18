"""Test sul motore vocale.

Nessuno di questi test tocca la rete: ElevenLabs e Edge-TTS sono irraggiungibili
dall'ambiente di sviluppo, quindi le risposte sono finte e si verifica solo che
la catena dei ripieghi si comporti come deve. Serve perche' la voce sta nel
percorso che pubblica: se questa parte sbaglia, il video esce muto o robotico.
"""
import importlib

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


@pytest.fixture(autouse=True)
def azzera_cache():
    voice._voce_risolta = None
    yield
    voice._voce_risolta = None


class TestSceltaDellaVoce:
    def _con_voci(self, monkeypatch):
        monkeypatch.setattr(
            voice.requests, "get", lambda *a, **k: RispostaFinta(dati=VOCI)
        )

    def test_per_nome_come_si_legge_sul_sito(self, monkeypatch):
        self._con_voci(monkeypatch)
        monkeypatch.setattr(config, "ELEVENLABS_VOCE", "giulia")

        assert voice._risolvi_voce("k") == "id-secondo"

    def test_anche_l_id_diretto_funziona(self, monkeypatch):
        self._con_voci(monkeypatch)
        monkeypatch.setattr(config, "ELEVENLABS_VOCE", "id-primo")

        assert voice._risolvi_voce("k") == "id-primo"

    def test_senza_indicazione_prende_la_prima(self, monkeypatch):
        self._con_voci(monkeypatch)
        monkeypatch.setattr(config, "ELEVENLABS_VOCE", "")

        assert voice._risolvi_voce("k") == "id-primo"

    def test_nome_sbagliato_elenca_quelli_veri(self, monkeypatch):
        self._con_voci(monkeypatch)
        monkeypatch.setattr(config, "ELEVENLABS_VOCE", "Gianni")

        with pytest.raises(RuntimeError) as errore:
            voice._risolvi_voce("k")

        assert "Marco" in str(errore.value) and "Giulia" in str(errore.value)

    def test_la_risoluzione_avviene_una_volta_sola(self, monkeypatch):
        chiamate = []

        def conta(*a, **k):
            chiamate.append(1)
            return RispostaFinta(dati=VOCI)

        monkeypatch.setattr(voice.requests, "get", conta)
        monkeypatch.setattr(config, "ELEVENLABS_VOCE", "Marco")

        voice._risolvi_voce("k")
        voice._risolvi_voce("k")

        assert len(chiamate) == 1


class TestSintesiElevenLabs:
    def test_senza_chiave_non_chiama_la_rete(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", None)

        with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
            voice._sintetizza_elevenlabs("ciao", str(tmp_path / "a.mp3"))

    @pytest.mark.parametrize("codice,atteso", [
        (401, "non valida"),
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
