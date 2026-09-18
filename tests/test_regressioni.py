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


class TestModelliGroq:
    """I due modelli llama erano scritti nel codice; Groq li ha spostati sul
    piano Enterprise il 18 settembre 2026 e hanno iniziato a rispondere 404."""

    def test_i_modelli_non_sono_scritti_nel_codice(self):
        testo = open(
            os.path.join(RADICE, "brain.py"), encoding="utf-8"
        ).read()

        assert "llama-3.3-70b-versatile" not in testo
        assert "llama-3.1-8b-instant" not in testo
        assert "modelli = config.GROQ_MODELLI" in testo

    def _ricarica(self, monkeypatch, valore):
        import importlib

        import config

        if valore is None:
            monkeypatch.delenv("GROQ_MODELLI", raising=False)
        else:
            monkeypatch.setenv("GROQ_MODELLI", valore)
        importlib.reload(config)
        return config.GROQ_MODELLI

    def test_l_elenco_si_cambia_da_variabile_d_ambiente(self, monkeypatch):
        try:
            assert self._ricarica(monkeypatch, "primo/modello, secondo/modello ") == [
                "primo/modello",
                "secondo/modello",
            ]
        finally:
            self._ricarica(monkeypatch, None)

    def test_una_variabile_vuota_non_svuota_l_elenco(self, monkeypatch):
        # Su GitHub Actions ${{ vars.GROQ_MODELLI }} non impostata arriva come
        # stringa vuota: se vincesse sul default, nessun modello verrebbe
        # provato e - tolto il ripiego - non uscirebbe alcun video.
        try:
            for vuota in ("", "   ", " , , "):
                assert self._ricarica(monkeypatch, vuota) == [
                    "openai/gpt-oss-120b",
                    "openai/gpt-oss-20b",
                ]
        finally:
            self._ricarica(monkeypatch, None)

    def test_il_workflow_passa_la_variabile_al_job(self):
        # Senza questa riga la variabile del repository non arriva mai a
        # config.py, e cambiarla da GitHub non avrebbe alcun effetto.
        testo = open(
            os.path.join(RADICE, ".github", "workflows", "samaritan.yml"),
            encoding="utf-8",
        ).read()

        assert "GROQ_MODELLI: ${{ vars.GROQ_MODELLI }}" in testo


class TestNienteTestoDiRipiego:
    """Scelta di popponetv del 18 settembre 2026: se l'intelligenza non
    risponde, meglio saltare il video che pubblicarne uno finto."""

    def test_il_ripiego_e_stato_rimosso(self):
        testo = open(
            os.path.join(RADICE, "brain.py"), encoding="utf-8"
        ).read()

        assert "uso il fallback" not in testo
        assert "il dettaglio che quasi nessuno nota" not in testo
        assert "Nessun modello Groq ha risposto" in testo
