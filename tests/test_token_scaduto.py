"""Il token YouTube scaduto si scopre prima di scrivere e montare il video.

Il 4 ottobre 2026 nove lavorazioni hanno scritto, prenotato e montato per
poi cadere al caricamento con invalid_grant.
"""
import os

import notifier
import uploader


def _con_errore(monkeypatch, errore):
    def finta():
        raise errore
    monkeypatch.setattr(uploader, "ottieni_credenziali", finta)


class TestTokenYoutubeScaduto:
    def test_invalid_grant_e_scaduto(self, monkeypatch):
        from google.auth.exceptions import RefreshError
        _con_errore(monkeypatch, RefreshError(
            "invalid_grant: Token has been expired or revoked."))
        assert uploader.token_youtube_scaduto()

    def test_un_errore_di_rete_non_ferma_niente(self, monkeypatch):
        _con_errore(monkeypatch, ConnectionError("timeout"))
        assert not uploader.token_youtube_scaduto()

    def test_credenziali_buone(self, monkeypatch):
        monkeypatch.setattr(uploader, "ottieni_credenziali", lambda: object())
        assert not uploader.token_youtube_scaduto()


class TestAvvisoTokenScaduto:
    def test_dice_cosa_fare_senza_chiedere_il_token(self, monkeypatch):
        inviati = []
        monkeypatch.setattr(notifier, "invia_messaggio",
                            lambda testo: inviati.append(testo) or True)
        notifier.notifica_token_scaduto()
        assert "TOKEN YOUTUBE SCADUTO" in inviati[0]
        assert "setup_secrets.py" in inviati[0]
        assert "non mandarlo in chat" in inviati[0]

    def test_la_pipeline_controlla_prima_di_scrivere(self):
        radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(radice, "main.py"), encoding="utf-8") as f:
            main_py = f.read()
        corpo = main_py[main_py.index("def esegui_pipeline_samaritan"):]
        assert corpo.index("token_youtube_scaduto()") < corpo.index("_scrivi_e_monta(")
