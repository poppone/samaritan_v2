"""La voce Microsoft nuova, se rifiutata, lascia il posto a quella classica."""
import sys
import types

import config
import voice


def _finto_edge(monkeypatch, rifiutate):
    usate = []

    class Communicate:
        def __init__(self, text, voice, rate, pitch):
            self.voce = voice

        async def save(self, percorso):
            usate.append(self.voce)
            if self.voce in rifiutate:
                raise RuntimeError("voce sconosciuta")
            with open(percorso, "wb") as f:
                f.write(b"x" * 2048)

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    return usate


def test_usa_la_voce_scelta(monkeypatch, tmp_path):
    usate = _finto_edge(monkeypatch, rifiutate=set())
    monkeypatch.setattr(config, "LINGUA", "en")
    monkeypatch.setattr(config, "VOCE_TTS", "en-US-AndrewMultilingualNeural")
    assert voice.genera_voce_samaritan("Ciao a tutti", str(tmp_path / "a.mp3"))
    assert usate == ["en-US-AndrewMultilingualNeural"]


def test_ripiega_sulla_classica_della_stessa_lingua(monkeypatch, tmp_path):
    usate = _finto_edge(monkeypatch, rifiutate={"it-IT-GiuseppeMultilingualNeural"})
    monkeypatch.setattr(config, "LINGUA", "it")
    monkeypatch.setattr(config, "VOCE_TTS", "it-IT-GiuseppeMultilingualNeural")
    percorso = voice.genera_voce_samaritan("Ciao a tutti", str(tmp_path / "a.mp3"))
    assert percorso
    assert usate == ["it-IT-GiuseppeMultilingualNeural", "it-IT-DiegoNeural"]


def test_riserva_per_lingua():
    assert config.VOCE_TTS_RISERVA == {"it": "it-IT-DiegoNeural", "en": "en-US-AndrewNeural"}
