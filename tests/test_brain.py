"""Test sulla validazione dello script e sulla pulizia dei campi.

E' l'ultimo filtro prima che un testo diventi un video pubblicato: se passa
un'apertura debole, la retention dei primi 3 secondi crolla.
"""
import pytest

import brain


SCRIPT_BUONO = (
    "Nessuno ti ha detto che questo boss si puo' battere senza sparare un colpo. "
    "Gli sviluppatori hanno lasciato una porta secondaria dietro la cascata. "
    "Serve solo aspettare che il temporale finisca, poi la strada si apre da sola. "
    "La community ci ha messo sei anni ad accorgersene, e ancora quasi nessuno lo "
    "sa. Iscriviti per gli altri segreti. E nessuno te lo aveva detto."
)


class TestValidaScript:
    def test_accetta_uno_script_buono(self):
        ok, motivo = brain.valida_script("Un titolo qualsiasi", SCRIPT_BUONO)
        assert ok, motivo

    def test_rifiuta_i_saluti(self):
        # Chiedere al modello di non salutare non basta: va rifiutato a valle.
        for apertura in ("Ciao a tutti", "Benvenuti", "Oggi vi parlo",
                         "Raga, ", "Ragazzi, "):
            script = apertura + " " + SCRIPT_BUONO
            ok, motivo = brain.valida_script("Titolo", script)
            assert not ok, f"'{apertura}' doveva essere rifiutato"
            assert "apertura" in motivo

    def test_rifiuta_i_saluti_anche_fra_virgolette(self):
        ok, _ = brain.valida_script("Titolo", '"Ciao a tutti! ' + SCRIPT_BUONO)
        assert not ok

    def test_rifiuta_lo_script_troppo_corto(self):
        ok, motivo = brain.valida_script("Titolo", "Due parole soltanto.")
        assert not ok and "corto" in motivo

    def test_rifiuta_lo_script_troppo_lungo(self):
        lungo = "parola " * (brain.MAX_PAROLE_SCRIPT + 10)
        ok, motivo = brain.valida_script("Titolo", lungo)
        assert not ok and "lungo" in motivo

    def test_rifiuta_i_campi_vuoti(self):
        assert not brain.valida_script("", SCRIPT_BUONO)[0]
        assert not brain.valida_script("Titolo", "")[0]


class TestPulisciTitolo:
    def test_toglie_shorts(self):
        assert "#Shorts" not in brain._pulisci_titolo("GTA 6: il leak #Shorts")
        assert "#shorts" not in brain._pulisci_titolo("GTA 6 #shorts").lower()

    def test_toglie_le_virgolette(self):
        assert brain._pulisci_titolo('"Elden Ring"') == "Elden Ring"

    def test_rispetta_il_limite_youtube(self):
        assert len(brain._pulisci_titolo("x" * 200)) == 100


class TestPulisciNomeGioco:
    def test_accetta_un_titolo_vero(self):
        assert brain._pulisci_nome_gioco("Cyberpunk 2077") == "Cyberpunk 2077"

    def test_toglie_le_virgolette(self):
        assert brain._pulisci_nome_gioco('"ELDEN RING"') == "ELDEN RING"

    def test_scarta_i_generici(self):
        # Cercarli su Steam darebbe un gioco a caso.
        for generico in ("videogiochi", "gaming", "Gioco", "N/A", "vari", ""):
            assert brain._pulisci_nome_gioco(generico) == ""

    def test_scarta_i_nomi_assurdamente_lunghi(self):
        assert brain._pulisci_nome_gioco("x" * 80) == ""


class TestMemoria:
    def test_normalizza_le_voci_vecchie_a_stringa(self):
        # La cronologia storica contiene voci salvate come semplici stringhe.
        voce = brain._normalizza("Un vecchio titolo")
        assert voce["titolo"] == "Un vecchio titolo"
        assert voce["video_id"] is None

    def test_lascia_intatte_le_voci_nuove(self):
        originale = {"titolo": "T", "stile": "TIER_LIST_LAMPO", "video_id": "abc"}
        assert brain._normalizza(originale) is originale

    def test_ogni_formato_dichiara_se_richiede_un_fatto(self):
        # Se manca la chiave, scegli_formato solleva KeyError a runtime.
        for nome, meta in brain.FORMATI_VIDEO.items():
            assert isinstance(meta["richiede_fatto"], bool), nome
            assert meta["descrizione"], nome


class TestEstraiJson:
    """Rete di sicurezza per quando lo schema vincolato non e' utilizzabile."""

    def test_json_nudo(self):
        assert brain._estrai_json('{"titolo": "a"}') == {"titolo": "a"}

    def test_json_dentro_i_backtick(self):
        assert brain._estrai_json('```json\n{"titolo": "a"}\n```') == {"titolo": "a"}
        assert brain._estrai_json('```\n{"titolo": "a"}\n```') == {"titolo": "a"}

    def test_json_preceduto_da_chiacchiere(self):
        risposta = 'Ecco lo Short:\n{"titolo": "a", "indice_notizia": 1}\nfine'
        assert brain._estrai_json(risposta)["indice_notizia"] == 1

    @pytest.mark.parametrize("risposta", ["", "   ", "nessun json qui"])
    def test_senza_json_solleva(self, risposta):
        with pytest.raises(ValueError):
            brain._estrai_json(risposta)


class TestSchemaRisposta:
    def test_lo_schema_copre_le_chiavi_chieste_nel_prompt(self):
        # Se il prompt e lo schema divergono, il modello viene vincolato a una
        # forma diversa da quella che il codice poi rilegge.
        chiavi = set(brain._SCHEMA_RISPOSTA["schema"]["properties"])

        assert chiavi == {
            "titolo", "script", "gioco",
            "query_video", "descrizione", "indice_notizia",
        }
        assert set(brain._SCHEMA_RISPOSTA["schema"]["required"]) == chiavi
        assert brain._SCHEMA_RISPOSTA["strict"] is True
        assert brain._SCHEMA_RISPOSTA["schema"]["additionalProperties"] is False


class TestCronacaSenzaFonte:
    """Il 18 settembre 2026 la pipeline ha prodotto uno Short su un leak di
    Forza Horizon 6 con date, velocita' e conferme degli sviluppatori, e
    `fonte` vuota: notizia inventata su un prodotto vero, pubblicata da sola."""

    SCRIPT_LEAK = (
        "Stai sottovalutando Forza Horizon 6? Un file e' trapelato cinque giorni "
        "prima del lancio. Gli sviluppatori hanno confermato una nuova modalita'."
    )

    def test_scarta_il_leak_senza_fonte(self):
        assert brain._cronaca_senza_fonte(self.SCRIPT_LEAK, "") is True

    def test_lo_stesso_script_passa_se_cita_una_notizia(self):
        fonte = "Forza Horizon 6 annunciato (Eurogamer)"
        assert brain._cronaca_senza_fonte(self.SCRIPT_LEAK, fonte) is False

    @pytest.mark.parametrize("script", [
        "Nessuno ti ha detto che questo boss si batte senza sparare un colpo.",
        "Stai sbagliando tutto sulla guida in curva: molla il gas prima.",
        "",
    ])
    def test_non_scarta_gli_script_senza_cronaca(self, script):
        assert brain._cronaca_senza_fonte(script, "") is False

    @pytest.mark.parametrize("spia", [
        "un leak mostra la mappa", "e' stato annunciato ieri",
        "secondo le indiscrezioni", "la data di uscita e' vicina",
    ])
    def test_riconosce_le_forme_piu_comuni(self, spia):
        assert brain._cronaca_senza_fonte(f"Senti qua: {spia}.", "") is True


class TestDettagliInventati:
    """Il 27 settembre 2026 lo Short inglese delle 20:00 e' nato dal solo
    titolo "These Xbox Players Got GTA 6 For Free The Hard Way" (Engadget) e
    ha raccontato un glitch che saltava l'acquisto e Microsoft che lo
    chiudeva in poche ore: dettagli che la notizia non dava. Nessuna parola
    spia di `_cronaca_senza_fonte`, quindi e' passato."""

    NOTIZIA = {"titolo": "These Xbox Players Got GTA 6 For Free The Hard Way",
               "fonte": "Engadget", "link": "https://news.google.com/x",
               "apparizioni": 1, "punteggio": 10, "sul_tema": False}
    SCRIPT = ("Two Xbox players got GTA 6 without paying a cent, but not the "
              "way you think. The headline says they did it the hard way. "
              "What does the hard way even mean for the biggest game of the "
              "decade? Would you grind for it or just buy it on day one? "
              "Tell me below, and follow Poppone TV for the next twist. "
              "Two Xbox players got it, so what would you do?")

    def _risposta(self, script=None):
        import json as _json
        return _json.dumps({
            "titolo": "GTA 6: Xbox players got it the hard way",
            "script": script or self.SCRIPT, "gioco": "Grand Theft Auto VI",
            "query_video": "gta 6 gameplay", "descrizione": "Would you?",
            "indice_notizia": 0,
        })

    def _finto_client(self, scritti, verdetti, prompt_visti, verifiche):
        """Client finto che distingue lo scrittore dal fact-checker."""
        class FinteCompletions:
            @staticmethod
            def create(**kw):
                sistema, utente = kw["messages"][0]["content"], kw["messages"][1]["content"]
                if sistema.startswith("Sei un fact-checker"):
                    verifiche.append(utente)
                    esito = verdetti.pop(0)
                    if isinstance(esito, Exception):
                        raise esito
                    testo = esito
                else:
                    prompt_visti.append((sistema, utente))
                    testo = scritti.pop(0)

                class Scelta:
                    class message:
                        content = testo

                class Risposta:
                    choices = [Scelta()]

                return Risposta()

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        return FintoClient()

    def _genera(self, monkeypatch, scritti, verdetti):
        prompt_visti, verifiche = [], []
        monkeypatch.setattr(brain, "client", self._finto_client(
            scritti, verdetti, prompt_visti, verifiche))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(self.NOTIZIA)])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        return brain.genera_script_samaritan(), prompt_visti, verifiche

    def test_il_prompt_dice_che_della_notizia_si_sa_solo_il_titolo(self):
        prompt = brain._costruisci_system_prompt(
            "VIRAL_HOOK_NEWS", [self.NOTIZIA], [], [])
        assert "SOLO IL TITOLO" in prompt
        assert "senza pagare" in prompt

    def test_senza_notizie_la_regola_non_occupa_spazio(self):
        prompt = brain._costruisci_system_prompt("EASTER_EGG_SECRET", [], [], [])
        assert "SOLO IL TITOLO" not in prompt

    def test_lo_script_che_inventa_viene_rifatto_con_i_dettagli_da_togliere(self, monkeypatch):
        inventato = ('{"dettagli_inventati": ["a glitch skipped the purchase", '
                     '"Microsoft patched it within hours"]}')
        risultato, prompt_visti, verifiche = self._genera(
            monkeypatch, [self._risposta(), self._risposta()],
            [inventato, '{"dettagli_inventati": []}'])

        assert len(prompt_visti) == 2
        assert len(verifiche) == 2
        assert self.NOTIZIA["titolo"] in verifiche[0]
        assert "Microsoft patched it within hours" in prompt_visti[1][1]
        assert risultato["fonte"].startswith(self.NOTIZIA["titolo"])

    def test_se_la_verifica_non_risponde_il_video_esce(self, monkeypatch):
        risultato, prompt_visti, _ = self._genera(
            monkeypatch, [self._risposta()], [RuntimeError("503 da Groq")])
        assert len(prompt_visti) == 1
        assert risultato["script"] == self.SCRIPT

    def test_all_ultimo_tentativo_la_verifica_si_spegne(self, monkeypatch):
        inventato = '{"dettagli_inventati": ["Microsoft patched it within hours"]}'
        risultato, prompt_visti, verifiche = self._genera(
            monkeypatch, [self._risposta()] * 4, [inventato] * 3)
        assert len(prompt_visti) == 4
        assert len(verifiche) == 3
        assert risultato["script"] == self.SCRIPT

    def test_gli_script_evergreen_non_vengono_verificati(self, monkeypatch):
        import json as _json
        evergreen = _json.loads(self._risposta())
        evergreen["indice_notizia"] = -1
        _, prompt_visti, verifiche = self._genera(
            monkeypatch, [_json.dumps(evergreen)], [])
        assert len(prompt_visti) == 1
        assert verifiche == []
