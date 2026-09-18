"""Guardie sui due problemi trovati il 18 settembre 2026.

Sono test di regressione: servono a impedire che tornino, non a descrivere
funzionalita' nuove.
"""
import os
import subprocess

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(RADICE, ".github", "workflows", "samaritan.yml")


def _git(*argomenti):
    return subprocess.run(
        ["git", "-C", RADICE, *argomenti],
        capture_output=True, text=True, check=False,
    )


class TestNessunSegretoNelRepository:
    """token.pickle era committato nonostante .gitignore e il README."""

    @pytest.mark.parametrize("segreto", ["token.pickle", "client_secret.json", ".env"])
    def test_i_file_di_credenziali_non_sono_tracciati(self, segreto):
        risultato = _git("ls-files", "--error-unmatch", segreto)
        assert risultato.returncode != 0, (
            f"{segreto} e' tracciato da git: contiene credenziali e non deve "
            f"mai finire in un commit."
        )

    def test_nessun_file_pickle_tracciato(self):
        tracciati = _git("ls-files", "*.pickle").stdout.split()
        assert tracciati == [], f"pickle tracciati: {tracciati}"


class TestWorkflowSalvaLaMemoria:
    """'git add a b' con 'b' inesistente fallisce senza mettere in stage
    nemmeno 'a': per questo la memoria non veniva mai salvata."""

    @pytest.fixture
    def testo(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            return f.read()

    def test_niente_git_add_con_piu_percorsi(self, testo):
        assert "git add cronologia_trend.json performance.json" not in testo

    def test_gli_errori_di_git_non_sono_silenziati(self, testo):
        assert "git add cronologia_trend.json performance.json 2>/dev/null" \
            not in testo

    def test_i_file_di_memoria_sono_aggiunti_uno_per_volta(self, testo):
        assert 'git add -- "$file_memoria"' in testo

    def test_il_push_viene_ritentato_dopo_un_rifiuto(self, testo):
        assert "git pull --rebase origin" in testo


class TestPercorsiAncorati:
    """I percorsi delle credenziali erano relativi alla working directory."""

    def test_uploader_ancora_alla_cartella_di_progetto(self):
        import config
        import uploader

        assert os.path.isabs(uploader.TOKEN_FILE)
        assert os.path.isabs(uploader.CLIENT_SECRET_FILE)
        assert uploader.TOKEN_FILE.startswith(config.DIR_PROGETTO)

    def test_setup_secrets_ancora_alla_cartella_di_progetto(self):
        import setup_secrets

        for percorso in setup_secrets.FILE_SEGRETI.values():
            assert os.path.isabs(percorso)


class TestScopeOAuth:
    def test_lo_scope_analytics_e_richiesto(self):
        # Senza questo scope il ciclo di feedback resta cieco per sempre.
        import uploader

        assert "https://www.googleapis.com/auth/yt-analytics.readonly" \
            in uploader.SCOPES
        assert "https://www.googleapis.com/auth/youtube.upload" in uploader.SCOPES
