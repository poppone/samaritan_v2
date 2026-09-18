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
