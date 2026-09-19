"""Test sul ciclo di feedback: punteggio dei video e pesi dei formati."""
import analyst


def _metriche(views=1000, retention=50.0, likes=0, commenti=0, iscritti=0):
    return {
        "views": views,
        "averageViewPercentage": retention,
        "likes": likes,
        "comments": commenti,
        "subscribersGained": iscritti,
    }


class TestPunteggio:
    def test_piu_retention_vale_piu_punti(self):
        assert analyst._punteggio(_metriche(retention=80.0)) > \
            analyst._punteggio(_metriche(retention=20.0))

    def test_gli_iscritti_pesano_piu_dei_like(self):
        # A parita' di tutto il resto: un iscritto vale piu' di un like.
        con_iscritto = analyst._punteggio(_metriche(iscritti=10))
        con_like = analyst._punteggio(_metriche(likes=10))
        assert con_iscritto > con_like

    def test_i_commenti_pesano_piu_dei_like(self):
        assert analyst._punteggio(_metriche(commenti=10)) > \
            analyst._punteggio(_metriche(likes=10))

    def test_zero_views_non_divide_per_zero(self):
        assert analyst._punteggio(_metriche(views=0, likes=5)) >= 0

    def test_metriche_mancanti_non_sollevano(self):
        assert analyst._punteggio({}) == 0


class TestPesiFormati:
    """I pesi decidono quale formato esce piu' spesso: e' qui che il
    progetto impara. Sostituiamo la sorgente dati, niente rete."""

    def _finti_video(self, monkeypatch, valutati):
        monkeypatch.setattr(analyst, "_video_valutati", lambda: valutati)

    def test_senza_dati_nessun_peso(self, monkeypatch):
        # Voluto: cosi' la scelta resta uniforme e continua a esplorare.
        self._finti_video(monkeypatch, [])
        assert analyst.pesi_formati() == {}

    def test_ignora_i_formati_con_pochi_video(self, monkeypatch):
        self._finti_video(monkeypatch, [
            {"stile": "SOLO_UNO", "punteggio": 900.0},
            {"stile": "ABBASTANZA", "punteggio": 50.0},
            {"stile": "ABBASTANZA", "punteggio": 50.0},
        ])
        pesi = analyst.pesi_formati()
        assert "SOLO_UNO" not in pesi
        assert "ABBASTANZA" in pesi

    def test_il_formato_migliore_pesa_di_piu(self, monkeypatch):
        self._finti_video(monkeypatch, [
            {"stile": "BUONO", "punteggio": 80.0},
            {"stile": "BUONO", "punteggio": 80.0},
            {"stile": "SCARSO", "punteggio": 20.0},
            {"stile": "SCARSO", "punteggio": 20.0},
        ])
        pesi = analyst.pesi_formati()
        assert pesi["BUONO"] > 1.0 > pesi["SCARSO"]

    def test_i_pesi_restano_nei_limiti(self, monkeypatch):
        # Un solo video virale non deve azzerare tutti gli altri formati.
        self._finti_video(monkeypatch, [
            {"stile": "VIRALE", "punteggio": 100000.0},
            {"stile": "VIRALE", "punteggio": 100000.0},
            {"stile": "NORMALE", "punteggio": 0.01},
            {"stile": "NORMALE", "punteggio": 0.01},
        ])
        for stile, peso in analyst.pesi_formati().items():
            assert analyst.PESO_MIN <= peso <= analyst.PESO_MAX, stile


class TestMiglioriHook:
    def test_restituisce_i_migliori_in_ordine(self, monkeypatch):
        monkeypatch.setattr(analyst, "_video_valutati", lambda: [
            {"hook": "medio", "punteggio": 50.0},
            {"hook": "il migliore", "punteggio": 99.0},
            {"hook": "", "punteggio": 100.0},          # senza hook: escluso
            {"hook": "peggiore", "punteggio": 1.0},
        ])
        assert analyst.migliori_hook(n=2) == ["il migliore", "medio"]

    def test_senza_dati_lista_vuota(self, monkeypatch):
        monkeypatch.setattr(analyst, "_video_valutati", lambda: [])
        assert analyst.migliori_hook() == []


# ---------------------------------------------------------------------------
# Il confronto col totale di canale
#
# Nasce dal 19 settembre 2026: YouTube Studio segnava 9.843 visualizzazioni in
# sette giorni, la somma per video del file ne contava 4.488 in novanta. Questi
# test non dicono quale cifra sia giusta, dicono che il log deve permettere di
# scoprirlo alla prossima run invece di far tirare a indovinare.
# ---------------------------------------------------------------------------
import datetime


class _RispostaFinta:
    def __init__(self, valore):
        self._valore = valore

    def execute(self):
        return {"rows": [[self._valore]]} if self._valore is not None else {}


class _ReportFinto:
    """Finge youtubeAnalytics: risponde con i totali che gli vengono dati.

    Distingue le due richieste dalla lunghezza del periodo: quella lunga e' la
    finestra di analisi, quella corta i sette giorni che si confrontano con
    l'app di YouTube Studio.
    """

    def __init__(self, lungo, breve):
        self.lungo, self.breve = lungo, breve
        self.chiamate = []

    def reports(self):
        return self

    def query(self, **kwargs):
        self.chiamate.append(kwargs)
        giorni = (datetime.date.fromisoformat(kwargs["endDate"])
                  - datetime.date.fromisoformat(kwargs["startDate"])).days
        return _RispostaFinta(self.lungo if giorni > 30 else self.breve)


def _performance(*views):
    return {f"video{i}": {"views": v} for i, v in enumerate(views)}


class TestConfrontoColCanale:

    def _esegui(self, performance, lungo, breve, capsys):
        oggi = datetime.date(2026, 9, 19)
        inizio = oggi - datetime.timedelta(days=analyst.GIORNI_ANALISI)
        finto = _ReportFinto(lungo, breve)
        analyst._controlla_contro_il_canale(finto, performance, inizio, oggi)
        return finto, capsys.readouterr().out

    def test_stampa_sia_il_totale_sia_la_somma(self, capsys):
        _, uscita = self._esegui(_performance(1000, 500), 9000, 4000, capsys)
        assert "9000" in uscita          # totale di canale
        assert "4000" in uscita          # ultimi sette giorni
        assert "1500" in uscita          # somma per video

    def test_avvisa_quando_la_somma_e_molto_piu_bassa(self, capsys):
        _, uscita = self._esegui(_performance(4488), 9843, 9843, capsys)
        assert "Warning Analyst" in uscita
        assert "5355" in uscita          # le visualizzazioni non attribuite

    def test_tace_quando_i_conti_tornano(self, capsys):
        _, uscita = self._esegui(_performance(9000), 9100, 4000, capsys)
        assert "Warning Analyst" not in uscita

    def test_la_finestra_di_sette_giorni_finisce_ieri(self, capsys):
        """Studio mostra i sette giorni fino a ieri: per confrontare le due
        cifre la richiesta deve coprire lo stesso periodo, non includere oggi."""
        finto, _ = self._esegui(_performance(10), 100, 50, capsys)
        breve = [c for c in finto.chiamate if c["startDate"] == "2026-09-12"]
        assert breve, "manca la richiesta sui sette giorni"
        assert breve[0]["endDate"] == "2026-09-18"

    def test_chiede_il_totale_senza_dimensione_video(self, capsys):
        finto, _ = self._esegui(_performance(10), 100, 50, capsys)
        for chiamata in finto.chiamate:
            assert "dimensions" not in chiamata
            assert chiamata["metrics"] == "views"

    def test_un_errore_non_ferma_la_pipeline(self, capsys):
        class Rotto:
            def reports(self):
                return self

            def query(self, **kwargs):
                raise RuntimeError("quota finita")

        oggi = datetime.date(2026, 9, 19)
        analyst._controlla_contro_il_canale(
            Rotto(), _performance(10), oggi - datetime.timedelta(days=90), oggi)
        assert "non riuscito" in capsys.readouterr().out

    def test_risposta_vuota_vale_zero(self, capsys):
        _, uscita = self._esegui(_performance(10), None, None, capsys)
        assert "Warning Analyst" not in uscita
        assert "0 views" in uscita
