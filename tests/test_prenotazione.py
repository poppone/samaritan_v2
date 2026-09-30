# -*- coding: utf-8 -*-
"""Due lavorazioni partite insieme non devono scegliere la stessa notizia.

Il 30 settembre 2026 sul canale notizie e' successo proprio questo: vedi
prenotazione.py. Qui si simulano con un repository vero, in locale.
"""
import json
import os
import subprocess

import pytest

import brain
import config
import prenotazione


def _git(cartella, *argomenti):
    subprocess.run(["git", *argomenti], cwd=cartella, check=True,
                   capture_output=True, text=True)


def _voce(titolo, fonte, ts, video_id="abc"):
    return {"timestamp": ts, "titolo": titolo, "fonte": fonte, "video_id": video_id}


@pytest.fixture
def due_copie(tmp_path, monkeypatch):
    """Un remoto e due cloni, come due lavorazioni sullo stesso repository."""
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remoto)], check=True)
    seme = tmp_path / "seme"
    subprocess.run(["git", "clone", "-q", str(remoto), str(seme)], check=True)
    (seme / "cronologia_trend.json").write_text(
        json.dumps([_voce("Vecchio video", "Vecchia notizia (ANSA)", 100)]), encoding="utf-8")
    (seme / "performance.json").write_text("{}", encoding="utf-8")
    _git(seme, "add", ".")
    _git(seme, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "inizio")
    _git(seme, "push", "-q", "origin", "HEAD:main")
    copie = []
    for nome in ("prima", "seconda"):
        c = tmp_path / nome
        subprocess.run(["git", "clone", "-q", str(remoto), str(c)], check=True)
        copie.append(c)
    monkeypatch.setenv("SAMARITAN_PRENOTA", "1")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    return remoto, copie


def _in(monkeypatch, cartella):
    monkeypatch.setattr(config, "DIR_PROGETTO", str(cartella))
    monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(cartella / "cronologia_trend.json"))


def _remota(remoto):
    uscita = subprocess.run(["git", "--git-dir", str(remoto), "show", "main:cronologia_trend.json"],
                            capture_output=True, text=True, check=True)
    return json.loads(uscita.stdout)


def test_la_seconda_vede_la_notizia_della_prima(due_copie, monkeypatch):
    remoto, (prima, seconda) = due_copie
    _in(monkeypatch, prima)
    brain.salva_in_cronologia({"titolo": "Sanremo: festival targato De Martino",
                               "script": "x", "stile": "VIRAL_HOOK_NEWS",
                               "query_video": "stage", "fonte": "Sanremo (Adnkronos)"})
    assert prenotazione.prenota("Sanremo")
    assert [v["titolo"] for v in _remota(remoto)][-1] == "Sanremo: festival targato De Martino"

    _in(monkeypatch, seconda)
    assert prenotazione.riallinea_cronologia()
    fonti = [v.get("fonte") for v in brain.carica_cronologia()]
    assert "Sanremo (Adnkronos)" in fonti


def test_la_prenotazione_non_sposta_il_ramo_locale(due_copie, monkeypatch):
    remoto, (prima, _) = due_copie
    _in(monkeypatch, prima)
    prima_di = subprocess.run(["git", "rev-parse", "HEAD"], cwd=prima,
                              capture_output=True, text=True).stdout
    (prima / "performance.json").write_text('{"nostra": 1}', encoding="utf-8")
    brain.salva_in_cronologia({"titolo": "T", "script": "x", "stile": "s",
                               "query_video": "q", "fonte": "F (X)"})
    assert prenotazione.prenota("T")
    dopo = subprocess.run(["git", "rev-parse", "HEAD"], cwd=prima,
                          capture_output=True, text=True).stdout
    assert prima_di == dopo
    # Nel commit di prenotazione c'e' solo la cronologia.
    remota_perf = subprocess.run(["git", "--git-dir", str(remoto), "show", "main:performance.json"],
                                 capture_output=True, text=True).stdout
    assert remota_perf == "{}"


def test_due_prenotazioni_non_si_cancellano(due_copie, monkeypatch):
    remoto, (prima, seconda) = due_copie
    for cartella, titolo in ((prima, "Uno"), (seconda, "Due")):
        _in(monkeypatch, cartella)
        brain.salva_in_cronologia({"titolo": titolo, "script": "x", "stile": "s",
                                   "query_video": "q", "fonte": titolo + " (X)"})
        assert prenotazione.prenota(titolo)
    titoli = [v["titolo"] for v in _remota(remoto)]
    assert "Uno" in titoli and "Due" in titoli


def test_il_video_id_va_sulla_riga_giusta(due_copie, monkeypatch):
    remoto, (prima, seconda) = due_copie
    _in(monkeypatch, prima)
    brain.salva_in_cronologia({"titolo": "Nostra", "script": "x", "stile": "s",
                               "query_video": "q", "fonte": "N (X)"})
    nostra = brain._NOSTRA_VOCE
    # Un'altra lavorazione prenota dopo di noi: la sua riga finisce in fondo.
    cronologia = brain.carica_cronologia()
    cronologia.append(_voce("Altra", "A (X)", nostra[0] + 5, video_id=None))
    with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
        json.dump(cronologia, f)
    brain.aggiorna_ultimo_video_id("VID123")
    per_titolo = {v["titolo"]: v.get("video_id") for v in brain.carica_cronologia()}
    assert per_titolo["Nostra"] == "VID123"
    assert per_titolo["Altra"] is None


def test_spenta_fuori_dal_workflow(tmp_path, monkeypatch):
    monkeypatch.delenv("SAMARITAN_PRENOTA", raising=False)
    _in(monkeypatch, tmp_path)
    assert prenotazione.prenota("x") is False
    assert prenotazione.riallinea_cronologia() is False


def test_il_workflow_la_accende():
    radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(radice, ".github", "workflows", "samaritan.yml"), encoding="utf-8") as f:
        assert "SAMARITAN_PRENOTA: '1'" in f.read()
