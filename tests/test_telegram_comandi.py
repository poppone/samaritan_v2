"""Test del comando da Telegram (telegram/worker.js).

Il Worker e' JavaScript e gira su Cloudflare: le prove vere stanno in
worker_telegram.mjs e le esegue Node, se c'e'. Qui in Python resta solo il
controllo che il workflow non metta i video lanciati a mano nella stessa coda
delle uscite programmate, dove ne cancellerebbero una in attesa.
"""
import os
import shutil
import subprocess

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node non installato")
def test_il_worker_obbedisce_solo_alla_sua_chat():
    esito = subprocess.run(
        ["node", os.path.join(RADICE, "tests", "worker_telegram.mjs")],
        capture_output=True, text=True, timeout=60)
    assert esito.returncode == 0, esito.stderr
    assert "tutto ok" in esito.stdout


def test_i_video_a_mano_hanno_una_coda_propria():
    with open(os.path.join(RADICE, ".github", "workflows", "samaritan.yml"),
              encoding="utf-8") as f:
        righe = f.read().splitlines()
    gruppo = next(r for r in righe if r.strip().startswith("group:"))
    assert "samaritan-manuale-" in gruppo
    assert "github.run_id" in gruppo
    # La riserva lanciata a mano resta invece in coda con le uscite: e' il
    # freno che le impedisce di rifare un video che una run in corso sta
    # ancora caricando.
    assert "!inputs.recupero" in gruppo
