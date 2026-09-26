"""Test dell'unione della memoria fra due lavorazioni che salvano insieme.

Il 26 settembre 2026 la prova privata e il video lungo hanno salvato a pochi
minuti di distanza: il rebase e' andato in conflitto su cronologia_trend.json
e la riga del video appena caricato e' sparita dalla memoria.
"""
import json
import os
import shutil
import subprocess

import pytest

import unisci_memoria as um

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _voce(ts, titolo, video_id=None):
    return {"timestamp": ts, "titolo": titolo, "video_id": video_id}


def test_le_aggiunte_di_tutte_e_due_restano():
    base = ["vecchia voce di solo testo", _voce(1, "A", "a")]
    loro = base + [_voce(3, "C", "c")]
    nostra = base + [_voce(2, "B", "b")]
    unita = um.unisci_cronologie(loro, nostra)
    assert [v if isinstance(v, str) else v["titolo"] for v in unita] == \
        ["vecchia voce di solo testo", "A", "B", "C"]


def test_il_video_id_arrivato_dopo_non_si_perde():
    loro = [_voce(1, "A", None)]
    nostra = [_voce(1, "A", "id-vero")]
    assert um.unisci_cronologie(loro, nostra)[0]["video_id"] == "id-vero"


def test_un_campo_vuoto_nostro_non_cancella_quello_salvato():
    loro = [_voce(1, "A", "id-vero")]
    nostra = [_voce(1, "A", None)]
    assert um.unisci_cronologie(loro, nostra)[0]["video_id"] == "id-vero"


def test_il_tetto_resta_quello_di_brain():
    loro = [_voce(i, str(i)) for i in range(um.MASSIMO_VOCI)]
    nostra = [_voce(10_000, "nuova")]
    unita = um.unisci_cronologie(loro, nostra)
    assert len(unita) == um.MASSIMO_VOCI
    assert unita[-1]["titolo"] == "nuova"


def test_la_performance_piu_recente_vince():
    vecchia = {"aggiornato": "2026-09-25T10:00", "video": {}}
    nuova = {"aggiornato": "2026-09-26T10:00", "video": {}}
    assert um.performance_piu_recente(vecchia, nuova) is nuova
    assert um.performance_piu_recente(nuova, vecchia) is nuova
    assert um.performance_piu_recente(None, vecchia) is vecchia
    assert um.performance_piu_recente(vecchia, None) is vecchia


@pytest.mark.skipif(shutil.which("git") is None, reason="git non installato")
def test_due_lavorazioni_che_salvano_insieme(tmp_path):
    """La corsa vera, con git: due cloni aggiungono una voce ciascuno."""
    def g(cartella, *argomenti):
        subprocess.run(["git", "-C", str(cartella), *argomenti], check=True,
                       capture_output=True, text=True)

    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remoto)], check=True)
    prima = tmp_path / "prima"
    subprocess.run(["git", "clone", "-q", str(remoto), str(prima)], check=True)
    g(prima, "config", "user.email", "t@t")
    g(prima, "config", "user.name", "t")
    g(prima, "checkout", "-q", "-b", "main")
    (prima / "cronologia_trend.json").write_text(json.dumps([_voce(1, "A", "a")], indent=2))
    g(prima, "add", ".")
    g(prima, "commit", "-q", "-m", "base")
    g(prima, "push", "-q", "origin", "main")

    seconda = tmp_path / "seconda"
    subprocess.run(["git", "clone", "-q", str(remoto), str(seconda)], check=True)
    g(seconda, "config", "user.email", "t@t")
    g(seconda, "config", "user.name", "t")

    # Tutte e due aggiungono in fondo, nello stesso punto del file.
    (prima / "cronologia_trend.json").write_text(json.dumps(
        [_voce(1, "A", "a"), _voce(3, "lungo", None)], indent=2))
    g(prima, "commit", "-qam", "prima")
    g(prima, "push", "-q", "origin", "main")

    (seconda / "cronologia_trend.json").write_text(json.dumps(
        [_voce(1, "A", "a"), _voce(2, "prova", "kf5")], indent=2))
    g(seconda, "commit", "-qam", "seconda")
    rifiutato = subprocess.run(["git", "-C", str(seconda), "push", "-q", "origin", "main"],
                               capture_output=True)
    assert rifiutato.returncode != 0

    # Quello che fa il workflow dopo il rifiuto.
    copia = tmp_path / "copia.json"
    shutil.copy(seconda / "cronologia_trend.json", copia)
    g(seconda, "fetch", "-q", "origin", "main")
    g(seconda, "reset", "-q", "--hard", "origin/main")
    subprocess.run(["python", os.path.join(RADICE, "unisci_memoria.py"), str(copia),
                    str(tmp_path / "manca.json")], cwd=seconda, check=True)
    g(seconda, "commit", "-qam", "unita")
    g(seconda, "push", "-q", "origin", "main")

    titoli = [v["titolo"] for v in json.loads((seconda / "cronologia_trend.json").read_text())]
    assert titoli == ["A", "prova", "lungo"]
    assert not (seconda / "performance.json").exists()


def test_il_workflow_usa_l_unione_e_non_il_rebase():
    with open(os.path.join(RADICE, ".github", "workflows", "samaritan.yml"),
              encoding="utf-8") as f:
        workflow = f.read()
    assert "python unisci_memoria.py" in workflow
    assert "pull --rebase" not in workflow
