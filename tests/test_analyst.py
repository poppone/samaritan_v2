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


# ---------------------------------------------------------------------------
# I TERMINI DI RICERCA DEL PUBBLICO
# ---------------------------------------------------------------------------
# popponetv, 21 settembre 2026, alla domanda se Samaritan tenesse conto dei
# trend e della SEO: la risposta onesta era che la classifica delle notizie era
# tutta scritta a mano, quindi un'ipotesi. Questi termini sono l'unico pezzo
# misurato: cosa la gente ha davvero scritto nella ricerca di YouTube per
# finire su un video del canale.
# ---------------------------------------------------------------------------
import json

import config


class _AnalyticsFinto:
    """Finge youtubeAnalytics per la sola richiesta dei termini di ricerca."""

    def __init__(self, righe):
        self.righe = righe
        self.chiamate = []

    def reports(self):
        return self

    def query(self, **kwargs):
        self.chiamate.append(kwargs)
        return self

    def execute(self):
        return {"rows": self.righe}


def _prepara_analytics(monkeypatch, righe, scope=True):
    import googleapiclient.discovery
    import uploader

    finto = _AnalyticsFinto(righe)
    monkeypatch.setattr(uploader, "ottieni_credenziali", lambda: object())
    monkeypatch.setattr(uploader, "ha_scope_analytics", lambda c: scope)
    monkeypatch.setattr(googleapiclient.discovery, "build",
                        lambda *a, **k: finto)
    return finto


class TestScaricaTerminiDiRicerca:

    def test_restituisce_i_termini_con_le_visualizzazioni(self, monkeypatch):
        _prepara_analytics(monkeypatch, [["gta 6 data uscita", 120],
                                         ["fortnite sora", 40]])
        termini = analyst.scarica_termini_di_ricerca()
        assert termini == [{"termine": "gta 6 data uscita", "views": 120},
                           {"termine": "fortnite sora", "views": 40}]

    def test_chiede_solo_il_traffico_dalla_ricerca(self, monkeypatch):
        """Senza il filtro arrivano anche i suggeriti e le pagine del canale,
        che non sono cose che qualcuno ha digitato."""
        finto = _prepara_analytics(monkeypatch, [["gta 6", 10]])
        analyst.scarica_termini_di_ricerca()
        chiamata = finto.chiamate[0]
        assert chiamata["dimensions"] == "insightTrafficSourceDetail"
        assert chiamata["filters"] == "insightTrafficSourceType==YT_SEARCH"

    def test_scarta_i_termini_con_pochissime_visualizzazioni(self, monkeypatch):
        _prepara_analytics(monkeypatch, [["gta 6", 50], ["caso isolato", 1]])
        termini = analyst.scarica_termini_di_ricerca()
        assert [t["termine"] for t in termini] == ["gta 6"]

    def test_senza_scope_analytics_lista_vuota(self, monkeypatch):
        _prepara_analytics(monkeypatch, [["gta 6", 50]], scope=False)
        assert analyst.scarica_termini_di_ricerca() == []

    def test_un_errore_non_ferma_la_pipeline(self, monkeypatch, capsys):
        import uploader
        monkeypatch.setattr(uploader, "ottieni_credenziali",
                            lambda: (_ for _ in ()).throw(RuntimeError("quota")))
        assert analyst.scarica_termini_di_ricerca() == []
        assert "non disponibili" in capsys.readouterr().out


class TestParoleCercate:

    def _con_termini(self, monkeypatch, termini, tmp_path):
        file_finto = tmp_path / "performance.json"
        file_finto.write_text(json.dumps(
            {"video": {}, "ricerche": [{"termine": t, "views": 10}
                                       for t in termini]}), encoding="utf-8")
        monkeypatch.setattr(config, "FILE_PERFORMANCE", str(file_finto))

    def test_scende_alle_parole(self, monkeypatch, tmp_path):
        """Nessuna notizia ripetera' mai la frase intera che qualcuno ha
        digitato, quindi il confronto si fa sulle parole."""
        self._con_termini(monkeypatch, ["gta 6 data uscita"], tmp_path)
        assert "gta" in analyst.parole_cercate()
        assert "uscita" in analyst.parole_cercate()

    def test_butta_le_parole_che_non_dicono_l_argomento(self, monkeypatch, tmp_path):
        self._con_termini(monkeypatch, ["shorts gaming ita"], tmp_path)
        assert analyst.parole_cercate() == frozenset()

    def test_butta_il_nome_del_canale(self, monkeypatch, tmp_path):
        """Chi cerca il canale non sta cercando un argomento."""
        monkeypatch.setattr(config, "NOME_CANALE", "Poppone TV")
        self._con_termini(monkeypatch, ["poppone tv"], tmp_path)
        assert analyst.parole_cercate() == frozenset()

    def test_butta_articoli_e_verbi_ausiliari(self, monkeypatch, tmp_path):
        """29 settembre 2026: 'ha' e 'un' facevano sembrare cercata dal
        pubblico qualunque notizia con 'ha un' nel titolo."""
        self._con_termini(monkeypatch, ["chi è che ha perso un sandalo"], tmp_path)
        assert analyst.parole_cercate() == frozenset({"perso", "sandalo"})

    def test_butta_i_numeri_da_soli(self, monkeypatch, tmp_path):
        self._con_termini(monkeypatch, ["gta 6"], tmp_path)
        assert analyst.parole_cercate() == frozenset({"gta"})

    def test_tiene_le_sigle_corte(self, monkeypatch, tmp_path):
        self._con_termini(monkeypatch, ["f1 25 setup"], tmp_path)
        assert "f1" in analyst.parole_cercate()

    def test_senza_file_nessuna_parola(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_PERFORMANCE",
                            str(tmp_path / "non-esiste.json"))
        assert analyst.parole_cercate() == frozenset()

    def test_un_file_rotto_non_solleva(self, monkeypatch, tmp_path):
        rotto = tmp_path / "performance.json"
        rotto.write_text("{ non json", encoding="utf-8")
        monkeypatch.setattr(config, "FILE_PERFORMANCE", str(rotto))
        assert analyst.parole_cercate() == frozenset()


class TestSalvataggioDeiTermini:

    def test_i_termini_finiscono_nel_file_delle_metriche(self, monkeypatch, tmp_path):
        """Stanno li' perche' performance.json e' uno dei due soli file che il
        workflow ricommitta: un file nuovo non sopravviverebbe alla run."""
        file_finto = tmp_path / "performance.json"
        monkeypatch.setattr(config, "FILE_PERFORMANCE", str(file_finto))
        monkeypatch.setattr(analyst, "scarica_performance",
                            lambda: {"video1": {"views": 10}})
        monkeypatch.setattr(analyst, "scarica_termini_di_ricerca",
                            lambda: [{"termine": "gta 6", "views": 50}])

        analyst.aggiorna_performance()

        salvato = json.loads(file_finto.read_text(encoding="utf-8"))
        assert salvato["ricerche"] == [{"termine": "gta 6", "views": 50}]

    def test_una_lettura_fallita_non_cancella_i_termini_vecchi(
            self, monkeypatch, tmp_path):
        file_finto = tmp_path / "performance.json"
        file_finto.write_text(json.dumps(
            {"video": {}, "ricerche": [{"termine": "gta 6", "views": 50}]}),
            encoding="utf-8")
        monkeypatch.setattr(config, "FILE_PERFORMANCE", str(file_finto))
        monkeypatch.setattr(analyst, "scarica_performance",
                            lambda: {"video1": {"views": 10}})
        monkeypatch.setattr(analyst, "scarica_termini_di_ricerca", lambda: [])

        analyst.aggiorna_performance()

        salvato = json.loads(file_finto.read_text(encoding="utf-8"))
        assert salvato["ricerche"] == [{"termine": "gta 6", "views": 50}]


class TestSorgentiDiTraffico:
    """Da dove arriva davvero il pubblico.

    Il 21 settembre 2026 la lista dei termini di ricerca e' tornata vuota e la
    prima spiegazione che viene in mente e' "su un canale di Short nessuno
    cerca". Puo' darsi, ma e' un'ipotesi: questa ripartizione la trasforma in
    un numero.
    """

    def test_restituisce_le_sorgenti_con_le_visualizzazioni(self, monkeypatch):
        _prepara_analytics(monkeypatch, [["SHORTS", 11000], ["YT_SEARCH", 120]])
        assert analyst.scarica_sorgenti_di_traffico() == [
            {"sorgente": "SHORTS", "views": 11000},
            {"sorgente": "YT_SEARCH", "views": 120},
        ]

    def test_non_chiede_un_numero_massimo_di_righe(self, monkeypatch):
        """Le sorgenti sono un elenco chiuso e corto: chiedere maxResults su
        questi rapporti e' il modo di farsi rispondere 500."""
        finto = _prepara_analytics(monkeypatch, [["SHORTS", 10]])
        analyst.scarica_sorgenti_di_traffico()
        assert "maxResults" not in finto.chiamate[0]

    def test_dice_in_italiano_da_dove_arriva_il_pubblico(self, monkeypatch, capsys):
        _prepara_analytics(monkeypatch, [["SHORTS", 900], ["YT_SEARCH", 100]])
        analyst.scarica_sorgenti_di_traffico()
        uscita = capsys.readouterr().out
        assert "feed Shorts 90%" in uscita
        assert "ricerca YouTube 10%" in uscita

    def test_una_sigla_sconosciuta_non_fa_sparire_la_riga(self, monkeypatch, capsys):
        _prepara_analytics(monkeypatch, [["SIGLA_NUOVA", 10]])
        analyst.scarica_sorgenti_di_traffico()
        assert "SIGLA_NUOVA" in capsys.readouterr().out

    def test_un_errore_non_ferma_la_pipeline(self, monkeypatch, capsys):
        import uploader
        monkeypatch.setattr(uploader, "ottieni_credenziali",
                            lambda: (_ for _ in ()).throw(RuntimeError("500")))
        assert analyst.scarica_sorgenti_di_traffico() == []
        assert "non disponibili" in capsys.readouterr().out

    def test_finiscono_nel_file_delle_metriche(self, monkeypatch, tmp_path):
        file_finto = tmp_path / "performance.json"
        monkeypatch.setattr(config, "FILE_PERFORMANCE", str(file_finto))
        monkeypatch.setattr(analyst, "scarica_performance",
                            lambda: {"video1": {"views": 10}})
        monkeypatch.setattr(analyst, "scarica_termini_di_ricerca", lambda: [])
        monkeypatch.setattr(analyst, "scarica_sorgenti_di_traffico",
                            lambda: [{"sorgente": "SHORTS", "views": 10}])

        analyst.aggiorna_performance()

        salvato = json.loads(file_finto.read_text(encoding="utf-8"))
        assert salvato["sorgenti"] == [{"sorgente": "SHORTS", "views": 10}]


class TestIlLimiteDelleRighe:

    def test_i_termini_di_ricerca_non_superano_il_massimo_dell_api(self):
        """Il 21 settembre 2026 la richiesta chiedeva 40 righe e l'API ha
        risposto 500 con FIELD_UNKNOWN_VALUE su max-results: non e' tornato
        nessun termine, e sembrava che nessuno cercasse."""
        assert analyst.MAX_TERMINI_RICERCA <= 25

    def test_il_massimo_finisce_davvero_nella_richiesta(self, monkeypatch):
        finto = _prepara_analytics(monkeypatch, [["gta 6", 10]])
        analyst.scarica_termini_di_ricerca()
        assert finto.chiamate[0]["maxResults"] == analyst.MAX_TERMINI_RICERCA
