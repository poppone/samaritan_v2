# -*- coding: utf-8 -*-
"""La copia pubblica dello Short non deve mai fermare la pipeline."""
from datetime import datetime, timezone

import copia_pubblica


class Risposta:
    def __init__(self, ok=True, j=None, status=200):
        self.ok, self._j, self.status_code, self.text = ok, j or {}, status, ""

    def json(self):
        return self._j


def test_senza_token_non_fa_niente(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    f = tmp_path / "v.mp4"; f.write_bytes(b"x")
    assert copia_pubblica.prepara(str(f), "abc", {}) == {}


def test_carica_e_restituisce_url_e_didascalia(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "t")
    f = tmp_path / "v.mp4"; f.write_bytes(b"x")
    chiamate = []

    def put(url, params=None, data=None, headers=None, timeout=None):
        chiamate.append((params, headers))
        return Risposta(j={"url": "https://x.public.blob.vercel-storage.com/samaritan/abc-r.mp4"})

    monkeypatch.setattr(copia_pubblica.requests, "put", put)
    monkeypatch.setattr(copia_pubblica, "pulisci", lambda token: 0)
    import brain
    monkeypatch.setattr(brain, "costruisci_didascalia_tiktok", lambda d: "didascalia #gaming")
    campi = copia_pubblica.prepara(str(f), "abc", {"titolo": "t"})
    assert campi == {"video_file_url": "https://x.public.blob.vercel-storage.com/samaritan/abc-r.mp4",
                     "didascalia_tiktok": "didascalia #gaming"}
    assert chiamate[0][0] == {"pathname": "samaritan/abc.mp4"}
    assert chiamate[0][1]["authorization"] == "Bearer t"


def test_la_didascalia_salvata_non_ha_backslash_n_ne_spazi_doppi(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "t")
    f = tmp_path / "v.mp4"; f.write_bytes(b"x")
    monkeypatch.setattr(copia_pubblica.requests, "put",
                        lambda *a, **k: Risposta(j={"url": "https://x/abc.mp4"}))
    monkeypatch.setattr(copia_pubblica, "pulisci", lambda token: 0)
    import brain
    monkeypatch.setattr(brain, "costruisci_didascalia_tiktok",
                        lambda d: "Titolo\\nriga  due\n\n#gaming")
    campi = copia_pubblica.prepara(str(f), "abc", {"titolo": "t"})
    assert campi["didascalia_tiktok"] == "Titolo\nriga due\n\n#gaming"


def test_errore_di_rete_non_esce(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "t")
    f = tmp_path / "v.mp4"; f.write_bytes(b"x")

    def put(*a, **k):
        raise ConnectionError("giu'")

    monkeypatch.setattr(copia_pubblica.requests, "put", put)
    assert copia_pubblica.prepara(str(f), "abc", {}) == {}


def test_pulisci_cancella_solo_le_vecchie(monkeypatch):
    elenco = {"blobs": [
        {"url": "u-vecchia", "uploadedAt": "2026-10-01T10:00:00.000Z"},
        {"url": "u-nuova", "uploadedAt": "2026-10-12T10:00:00.000Z"},
    ], "hasMore": False}
    cancellate = []
    monkeypatch.setattr(copia_pubblica.requests, "get", lambda *a, **k: Risposta(j=elenco))
    monkeypatch.setattr(copia_pubblica.requests, "post",
                        lambda url, json=None, **k: cancellate.extend(json["urls"]) or Risposta())
    n = copia_pubblica.pulisci("t", adesso=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert n == 1 and cancellate == ["u-vecchia"]
