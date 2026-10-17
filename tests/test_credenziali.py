# -*- coding: utf-8 -*-
"""Test sulle credenziali YouTube.

Due strade: token.pickle (setup_secrets.py, il modo di popponetv) e i tre
Secrets YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN
scritti dalla pagina di installazione. Il pickle, quando c'e', vince.
Nessun test tocca la rete: il rinnovo del token e' finto.
"""
import pickle
import types

import pytest
from google.oauth2.credentials import Credentials

import config
import uploader


@pytest.fixture
def rinnovi(monkeypatch, tmp_path):
    """Nessun file sul disco, nessun secret, e un refresh che non va in rete."""
    monkeypatch.setattr(uploader, "TOKEN_FILE", str(tmp_path / "token.pickle"))
    monkeypatch.setattr(uploader, "CLIENT_SECRET_FILE", str(tmp_path / "client_secret.json"))
    for nome in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.setattr(config, nome, None)
    fatti = []

    def refresh_finto(self, richiesta):
        fatti.append(self)
        self.token = "accesso-finto"

    monkeypatch.setattr(Credentials, "refresh", refresh_finto)
    return fatti


def _secret(monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_ID", "id-cliente.apps.googleusercontent.com")
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRET", "segreto-cliente")
    monkeypatch.setattr(config, "YOUTUBE_REFRESH_TOKEN", "1//refresh")


class TestCredenzialiDaSecret:

    def test_bastano_i_tre_secret(self, monkeypatch, rinnovi):
        _secret(monkeypatch)
        credenziali = uploader.ottieni_credenziali()
        assert rinnovi == [credenziali]
        assert credenziali.refresh_token == "1//refresh"
        assert credenziali.client_id == "id-cliente.apps.googleusercontent.com"
        assert credenziali.client_secret == "segreto-cliente"
        assert credenziali.token_uri == "https://oauth2.googleapis.com/token"
        assert list(credenziali.scopes) == uploader.SCOPES
        # analyst legge le statistiche solo se lo scope c'e'.
        assert uploader.ha_scope_analytics(credenziali)

    def test_non_scrive_niente_su_disco(self, monkeypatch, rinnovi, tmp_path):
        _secret(monkeypatch)
        uploader.ottieni_credenziali()
        assert not (tmp_path / "token.pickle").exists()

    def test_ne_manca_uno_e_non_si_usano(self, monkeypatch, rinnovi):
        _secret(monkeypatch)
        monkeypatch.setattr(config, "YOUTUBE_REFRESH_TOKEN", None)
        with pytest.raises(FileNotFoundError):
            uploader.ottieni_credenziali()
        assert rinnovi == []

    def test_il_pickle_vince(self, monkeypatch, rinnovi, tmp_path):
        """popponetv ha token.pickle: anche se un giorno aggiungesse i tre
        secret, il suo canale deve continuare a usare il token di sempre."""
        _secret(monkeypatch)
        valide = types.SimpleNamespace(valid=True)
        with open(tmp_path / "token.pickle", "wb") as f:
            pickle.dump(valide, f)
        credenziali = uploader.ottieni_credenziali()
        assert credenziali.valid is True
        assert not isinstance(credenziali, Credentials)
        assert rinnovi == []
