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
