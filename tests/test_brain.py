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

    def test_le_console_non_sono_giochi(self):
        for console in ("PS5", "Nintendo Switch 2", "Xbox", "Game Pass"):
            assert brain._pulisci_nome_gioco(console) == ""

    def test_scarta_i_nomi_assurdamente_lunghi(self):
        assert brain._pulisci_nome_gioco("x" * 80) == ""


class TestGiocoDalTitolo:
    """Il 10 ottobre 2026 "Pokémon: ..." e' uscito senza gioco e su Pexels."""

    def test_prende_il_gioco_prima_dei_due_punti(self):
        assert brain._gioco_dal_titolo(
            "Pokémon: Kyle Juszczyk's Viral Football Lineup 🤯") == "Pokémon"
        assert brain._gioco_dal_titolo("Mafia III: Free PS5 upgrade") == "Mafia III"

    def test_senza_due_punti_niente(self):
        assert brain._gioco_dal_titolo("Il gioco piu' atteso dell'anno") == ""

    def test_un_prefisso_lungo_non_e_un_gioco(self):
        assert brain._gioco_dal_titolo(
            "Ecco cosa nessuno ti ha detto oggi: GTA 6") == ""

    def test_i_generici_restano_fuori(self):
        assert brain._gioco_dal_titolo("Gaming: la settimana") == ""


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

    # Con un sommario la notizia regge un secondo tentativo dopo
    # un'invenzione; senza, si cambia subito notizia.
    SOMMARIO = "Two players on Xbox found a way to get the game without paying."

    def _genera(self, monkeypatch, scritti, verdetti, sommario=""):
        prompt_visti, verifiche = [], []
        monkeypatch.setattr(brain, "client", self._finto_client(
            scritti, verdetti, prompt_visti, verifiche))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(self.NOTIZIA, sommario=sommario)])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        return brain.genera_script_samaritan(), prompt_visti, verifiche

    def test_il_prompt_dice_che_della_notizia_si_sa_solo_il_titolo(self):
        prompt = brain._costruisci_system_prompt(
            "VIRAL_HOOK_NEWS", [self.NOTIZIA], [], [])
        assert "SOLO TITOLO E SOMMARIO" in prompt
        assert "senza pagare" in prompt

    def test_senza_notizie_la_regola_non_occupa_spazio(self):
        prompt = brain._costruisci_system_prompt("EASTER_EGG_SECRET", [], [], [])
        assert "SOLO TITOLO E SOMMARIO" not in prompt

    def test_lo_script_che_inventa_viene_rifatto_con_i_dettagli_da_togliere(self, monkeypatch):
        inventato = ('{"dettagli_inventati": ["a glitch skipped the purchase", '
                     '"Microsoft patched it within hours"]}')
        risultato, prompt_visti, verifiche = self._genera(
            monkeypatch, [self._risposta(), self._risposta()],
            [inventato, '{"dettagli_inventati": []}'], sommario=self.SOMMARIO)

        assert len(prompt_visti) == 2
        assert len(verifiche) == 2
        assert self.NOTIZIA["titolo"] in verifiche[0]
        assert "Microsoft patched it within hours" in prompt_visti[1][1]
        assert risultato["fonte"].startswith(self.NOTIZIA["titolo"])

    def test_titolo_con_pretesa_si_corregge_senza_rifare_lo_script(self, monkeypatch):
        """19 ottobre 2026: tre script buoni buttati per "leak" o "shock" nel
        solo titolo."""
        import json as _json
        gonfiato = _json.loads(self._risposta())
        gonfiato["titolo"] = "GTA 6: Xbox players shock Microsoft"
        corretto = '{"titolo": "GTA 6: Xbox players got it the hard way"}'
        risultato, prompt_visti, _ = self._genera(
            monkeypatch, [_json.dumps(gonfiato), corretto],
            ['{"dettagli_inventati": []}'])
        assert len(prompt_visti) == 2
        assert prompt_visti[1][0].startswith("Correggi il TITOLO")
        assert risultato["titolo"] == "GTA 6: Xbox players got it the hard way"
        assert risultato["script"] == self.SCRIPT

    def test_titolo_corretto_ancora_gonfiato_fa_riscrivere(self, monkeypatch):
        import json as _json
        gonfiato = _json.loads(self._risposta())
        gonfiato["titolo"] = "GTA 6: Xbox players shock Microsoft"
        risultato, prompt_visti, _ = self._genera(
            monkeypatch,
            [_json.dumps(gonfiato), '{"titolo": "GTA 6: a shocking trick"}',
             self._risposta()],
            ['{"dettagli_inventati": []}'])
        assert len(prompt_visti) == 3
        assert "parla di shock" in prompt_visti[2][1]
        assert risultato["titolo"] == "GTA 6: Xbox players got it the hard way"

    def test_se_la_verifica_non_risponde_il_video_esce(self, monkeypatch):
        risultato, prompt_visti, _ = self._genera(
            monkeypatch, [self._risposta()],
            [RuntimeError("503 da Groq"), RuntimeError("503 da Groq")])
        assert len(prompt_visti) == 1
        assert risultato["script"] == self.SCRIPT

    def test_se_la_verifica_fallisce_una_volta_riprova(self, monkeypatch):
        """28 settembre 2026: un 400 json_validate_failed della verifica ha
        fatto uscire senza controllo uno script gia' scartato una volta."""
        import json as _json
        pulito = self.SCRIPT.replace("Two Xbox", "Some Xbox")
        risultato, prompt_visti, verifiche = self._genera(
            monkeypatch, [self._risposta(), self._risposta(pulito)],
            [RuntimeError("400 json_validate_failed"),
             _json.dumps({"dettagli_inventati": ["un glitch che salta l'acquisto"]}),
             _json.dumps({"dettagli_inventati": []})], sommario=self.SOMMARIO)
        assert len(verifiche) == 3
        assert len(prompt_visti) == 2
        assert "un glitch che salta l'acquisto" in prompt_visti[1][1]
        assert risultato["script"] == pulito

    def test_dopo_due_invenzioni_sulla_stessa_notizia_si_cambia_notizia(self, monkeypatch):
        """29 settembre 2026: una rassegna su GTA VI ha fatto inventare
        dettagli a tutti e quattro i tentativi e l'uscita e' saltata."""
        import json as _json
        altra = {"titolo": "Hollow Knight Silksong sells a million copies",
                 "fonte": "IGN", "link": "https://news.google.com/y",
                 "apparizioni": 1, "punteggio": 8, "sul_tema": False}
        su_altra = _json.loads(self._risposta(
            "Hollow Knight Silksong just sold a million copies. A million "
            "players waited years for this one, refreshing every trailer and "
            "every rumor along the way. Now the number is here and it is "
            "huge for a small team. Was it worth the wait for you, or did the "
            "hype burn out? Tell me below, and follow Poppone TV for the next "
            "twist in gaming."))
        su_altra.update({"indice_notizia": 1, "gioco": "Hollow Knight Silksong",
                         "titolo": "Silksong: a million players already"})
        inventato = _json.dumps({"dettagli_inventati": ["un glitch"]})
        prompt_visti, verifiche = [], []
        monkeypatch.setattr(brain, "client", self._finto_client(
            [self._risposta(), self._risposta(), self._risposta(),
             _json.dumps(su_altra)],
            [inventato, inventato, _json.dumps({"dettagli_inventati": []})],
            prompt_visti, verifiche))
        con_sommario = dict(self.NOTIZIA, sommario=self.SOMMARIO)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [con_sommario, altra])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        risultato = brain.genera_script_samaritan()
        assert "Non usare le notizie [0]" not in prompt_visti[1][1]
        assert "Non usare le notizie [0]" in prompt_visti[2][1]
        # Il terzo tentativo ripropone la notizia vietata: scartato senza
        # nemmeno chiamare la verifica.
        assert len(verifiche) == 3
        assert risultato["fonte"].startswith("Hollow Knight Silksong")

    def test_una_notizia_senza_sommario_si_cambia_alla_prima_invenzione(self, monkeypatch):
        """1 ottobre 2026: col solo titolo di una patch di No Man's Sky il
        modello ha inventato dettagli a cinque tentativi su due lavorazioni."""
        import json as _json
        altra = {"titolo": "Hollow Knight Silksong sells a million copies",
                 "fonte": "IGN", "link": "https://news.google.com/y",
                 "apparizioni": 1, "punteggio": 8, "sul_tema": False}
        su_altra = _json.loads(self._risposta(
            "Hollow Knight Silksong just sold a million copies. A million "
            "players waited years for this one, refreshing every trailer and "
            "every rumor along the way. Now the number is here and it is "
            "huge for a small team. Was it worth the wait for you, or did the "
            "hype burn out? Tell me below, and follow Poppone TV for the next "
            "twist in gaming."))
        su_altra.update({"indice_notizia": 1, "gioco": "Hollow Knight Silksong",
                         "titolo": "Silksong: a million players already"})
        prompt_visti, verifiche = [], []
        monkeypatch.setattr(brain, "client", self._finto_client(
            [self._risposta(), _json.dumps(su_altra)],
            [_json.dumps({"dettagli_inventati": ["un glitch"]}),
             _json.dumps({"dettagli_inventati": []})],
            prompt_visti, verifiche))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(self.NOTIZIA), altra])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        risultato = brain.genera_script_samaritan()
        assert len(prompt_visti) == 2
        assert "Non usare le notizie [0]" in prompt_visti[1][1]
        assert risultato["fonte"].startswith("Hollow Knight Silksong")

    def test_una_frase_di_colore_si_toglie_senza_riscrivere(self, monkeypatch):
        """30 settembre 2026: sei tentativi su sei scartati per frasi come
        "Nessuno l'aspettava", e l'uscita delle 14:00 e' saltata."""
        colore = "Would you grind for it or just buy it on day one?"
        risultato, prompt_visti, verifiche = self._genera(
            monkeypatch, [self._risposta()],
            ['{"dettagli_inventati": ["Would you grind for it or just buy it on day one"]}'])
        assert len(prompt_visti) == 1
        assert len(verifiche) == 1
        assert colore not in risultato["script"]
        assert risultato["script"].startswith("Two Xbox players got GTA 6")

    def test_la_verifica_vale_anche_all_ultimo_tentativo(self, monkeypatch):
        # Con la verifica spenta sull'ultimo tentativo, nella prova del 28
        # settembre 2026 e' passato uno Short su GTA 6 nato da una notizia su
        # un altro gioco. Meglio un video saltato, che la riserva recupera.
        inventato = '{"dettagli_inventati": ["Microsoft patched it within hours"]}'
        with pytest.raises(RuntimeError):
            self._genera(monkeypatch, [self._risposta()] * 4, [inventato] * 4)

    def test_il_sommario_arriva_al_modello_e_alla_verifica(self, monkeypatch):
        sommario = ("GTA VI could be yours for free, or at least for a big "
                    "discount, using a few tricks that Xbox offers.")
        prompt_visti, verifiche = [], []
        monkeypatch.setattr(brain, "client", self._finto_client(
            [self._risposta()], ['{"dettagli_inventati": []}'],
            prompt_visti, verifiche))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: [dict(self.NOTIZIA, sommario=sommario)])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        brain.genera_script_samaritan()
        assert "Sommario: " + sommario in prompt_visti[0][0]
        assert "SOMMARIO: " + sommario in verifiche[0]

    def test_gli_script_evergreen_non_vengono_verificati(self, monkeypatch):
        import json as _json
        evergreen = _json.loads(self._risposta())
        evergreen["indice_notizia"] = -1
        _, prompt_visti, verifiche = self._genera(
            monkeypatch, [_json.dumps(evergreen)], [])
        assert len(prompt_visti) == 1
        assert verifiche == []


# conftest spegne _sommario_bing in tutti i test perche' va in rete: qui serve
# quello vero, preso all'import del modulo, prima che la fixture lo sostituisca.
_SOMMARIO_BING_VERO = brain._sommario_bing


class TestPretesaInventata:
    """Il 17 ottobre 2026 sono usciti "Urban Food Festival: il glitch che
    rovina l'esperienza" e "Pokémon: Holiday Plush Collection Shocks Fans":
    il fact-check leggeva lo script, non il titolo."""

    def test_glitch_che_la_notizia_non_dice(self):
        notizia = ("Street food, fumetti, Pokémon e videogiochi: a Empoli "
                   "quattro giorni con l'Urban Food Festival")
        assert brain._pretesa_inventata(
            "Urban Food Festival: il glitch che rovina l'esperienza 🍔",
            notizia, "Urban Food Festival") == "glitch o bug"

    def test_shock_che_la_notizia_non_dice(self):
        notizia = "A New Holiday Plush Collection Is Coming to Pokémon Center"
        assert brain._pretesa_inventata(
            "Pokémon: Holiday Plush Collection Shocks Fans 🎁",
            notizia, "Pokémon") == "shock"

    def test_sinonimo_nell_altra_lingua_va_bene(self):
        assert brain._pretesa_inventata(
            "GTA 6: il leak del nuovo trailer",
            "GTA 6 footage leaked ahead of trailer", "GTA 6") == ""
        assert brain._pretesa_inventata(
            "Elden Ring: un bug blocca i salvataggi",
            "Elden Ring glitch wipes save files", "Elden Ring") == ""

    def test_rinvio_detto_dalla_notizia(self):
        assert brain._pretesa_inventata(
            "Grand Theft Auto VI: Release Date Locked",
            "GTA 6 locks in Nov. 19 release date after delays",
            "Grand Theft Auto VI") == ""
        assert brain._pretesa_inventata(
            "GTA 6: di nuovo rinviato",
            "GTA 6 locks in Nov. 19 release date", "GTA 6") == "rinvio"

    def test_nome_del_gioco_non_conta(self):
        assert brain._pretesa_inventata(
            "Hidden Folks: arriva su Switch", "Hidden Folks comes to Switch",
            "Hidden Folks") == ""
        assert brain._pretesa_inventata(
            "Crash Bandicoot: nuovo gioco annunciato",
            "New Crash Bandicoot announced", "Crash Bandicoot") == ""

    def test_all_ultimo_tentativo_passa_solo_l_enfasi(self):
        notizia = "A New Holiday Plush Collection Is Coming to Pokémon Center"
        assert brain._pretesa_inventata(
            "Pokémon: Holiday Plush Collection Shocks Fans", notizia,
            "Pokémon", solo_fatti=True) == ""
        assert brain._pretesa_inventata(
            "Pokémon: un glitch nei peluche", notizia,
            "Pokémon", solo_fatti=True) == "glitch o bug"

    def test_parole_simili_non_scattano(self):
        assert brain._pretesa_inventata(
            "Bandai Namco: nuovo Tekken annunciato",
            "Bandai Namco announces new Tekken", "Tekken") == ""
        assert brain._pretesa_inventata(
            "Fortnite: la nuova banda di Peely",
            "Fortnite adds Peely band skins", "Fortnite") == ""


class TestSommarioBing:
    """Google News da' solo il titolo: il sommario arriva da Bing News."""

    TITOLO = "These Xbox Players Got GTA 6 For Free The Hard Way"

    def _feed(self, *voci):
        items = "".join(
            f"<item><title>{t}</title><description>{d}</description></item>"
            for t, d in voci)
        return f"<rss><channel>{items}</channel></rss>".encode()

    def _con_feed(self, monkeypatch, contenuto, visti=None):
        vero = _SOMMARIO_BING_VERO

        class Risposta:
            content = contenuto

            def raise_for_status(self):
                pass

        def finto_get(url, **kw):
            if visti is not None:
                visti.append(url)
            return Risposta()
        monkeypatch.setattr(brain.requests, "get", finto_get)
        return vero

    def test_prende_il_sommario_della_stessa_notizia(self, monkeypatch):
        visti = []
        sommario = self._con_feed(monkeypatch, self._feed(
            ("Rockstar reveals new GTA 6 artwork", "Jason and Lucia."),
            ("These Xbox players got GTA 6 for free the hard way",
             "GTA VI could be yours for free using a few tricks that Xbox offers."),
        ), visti)(self.TITOLO)
        assert sommario.startswith("GTA VI could be yours for free")
        assert "format=rss" in visti[0]

    def test_non_prende_il_sommario_di_un_altra_notizia(self, monkeypatch):
        sommario = self._con_feed(monkeypatch, self._feed(
            ("Rockstar reveals new GTA 6 artwork of Jason and Lucia",
             "A 14-page feature arrives September 29."),
        ))(self.TITOLO)
        assert sommario == ""

    def test_scarta_il_sommario_che_ripete_il_titolo(self, monkeypatch):
        sommario = self._con_feed(monkeypatch, self._feed(
            (self.TITOLO, self.TITOLO + "."),
        ))(self.TITOLO)
        assert sommario == ""

    def test_taglia_i_sommari_lunghi(self, monkeypatch):
        lungo = "parola " * 200
        sommario = self._con_feed(monkeypatch, self._feed(
            (self.TITOLO, lungo),
        ))(self.TITOLO)
        assert len(sommario) <= brain.MAX_CARATTERI_SOMMARIO + 3
        assert sommario.endswith("...")

    def test_se_bing_non_risponde_la_notizia_resta_senza_sommario(self, monkeypatch):
        def rotto(titolo):
            raise ConnectionError("rete giu'")
        monkeypatch.setattr(brain, "_sommario_bing", rotto)
        notizie = [{"titolo": self.TITOLO}]
        brain._aggiungi_sommari(notizie)
        assert notizie[0]["sommario"] == ""


class TestNotiziaSulGiocoPrecedente:
    """Il 28 settembre 2026 le uscite delle 14:00 e delle 18:00 sono saltate:
    la notizia [0] era su GTA 6 dopo un video su GTA VI, il modello la
    sceglieva perche' il prompt dice di scegliere la [0], e la regola dei
    doppioni la scartava."""

    def test_le_notizie_sul_gioco_precedente_escono_dalla_lista(self, monkeypatch):
        import json as _json
        notizie = [
            {"titolo": "GTA 6, la lista aggiornata delle auto confermate",
             "fonte": "Everyeye.it", "link": "", "sommario": ""},
            {"titolo": "Elden Ring Nightreign ha una nuova modalita'",
             "fonte": "Multiplayer", "link": "", "sommario": ""},
        ]
        visti = []
        risposta = _json.dumps({
            "titolo": "Elden Ring: la modalita' nuova", "script":
            TestDettagliInventati.SCRIPT, "gioco": "Elden Ring",
            "query_video": "elden ring gameplay", "descrizione": "Ci giochi?",
            "indice_notizia": -1})

        class FinteCompletions:
            @staticmethod
            def create(**kw):
                visti.append(kw["messages"][0]["content"])

                class Scelta:
                    class message:
                        content = risposta

                class Risposta:
                    choices = [Scelta()]
                return Risposta()

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        monkeypatch.setattr(brain, "client", FintoClient())
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: notizie)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [{
            "titolo": "Grand Theft Auto VI: la box da 400 euro",
            "gioco": "Grand Theft Auto VI", "lingua": "it"}])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        try:
            brain.genera_script_samaritan()
        except RuntimeError:
            pass
        prompt = visti[0]
        assert "[0] Elden Ring" in prompt
        assert "GTA 6, la lista" not in prompt

    def test_senza_altre_notizie_quella_sul_gioco_precedente_resta(self, monkeypatch):
        notizie = [
            {"titolo": "GTA 6, la lista aggiornata delle auto confermate",
             "fonte": "Everyeye.it", "link": "", "sommario": ""},
        ]
        visti = []

        class FinteCompletions:
            @staticmethod
            def create(**kw):
                visti.append(kw["messages"][0]["content"])
                raise RuntimeError("basta il prompt")

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        monkeypatch.setattr(brain, "client", FintoClient())
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: notizie)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [{
            "titolo": "Grand Theft Auto VI: la box da 400 euro",
            "gioco": "Grand Theft Auto VI", "lingua": "it"}])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        try:
            brain.genera_script_samaritan()
        except RuntimeError:
            pass
        assert "[0] GTA 6" in visti[0]


class TestCorrezioneDelloScript:
    """4 ottobre 2026: due lavorazioni su sei cadute con tutti i tentativi
    scartati, perche' i dettagli inventati stavano in piu' di meta' delle
    frasi e lo script non si poteva ripulire. Ora prima di riscrivere da
    capo si chiede di correggere solo quelle affermazioni."""

    BASE = TestDettagliInventati()
    PULITO = BASE.SCRIPT.replace("Two Xbox", "Some Xbox")

    def _genera(self, monkeypatch, scritti, verdetti, corretto):
        richieste = []

        def finta_correzione(script, dettagli, titolo_notizia, sommario=""):
            richieste.append((script, list(dettagli), titolo_notizia))
            return corretto

        monkeypatch.setattr(brain, "_correggi_script", finta_correzione)
        risultato, prompt_visti, verifiche = self.BASE._genera(
            monkeypatch, scritti, verdetti,
            sommario=TestDettagliInventati.SOMMARIO)
        return risultato, prompt_visti, verifiche, richieste

    def test_lo_script_corretto_esce_senza_riscrivere(self, monkeypatch):
        import json as _json
        risultato, prompt_visti, verifiche, richieste = self._genera(
            monkeypatch, [self.BASE._risposta()],
            [_json.dumps({"dettagli_inventati": ["un glitch"]}),
             _json.dumps({"dettagli_inventati": []})],
            self.PULITO)
        assert len(prompt_visti) == 1
        assert len(verifiche) == 2
        assert richieste[0][1] == ["un glitch"]
        assert richieste[0][2] == TestDettagliInventati.NOTIZIA["titolo"]
        assert risultato["script"] == self.PULITO

    def test_se_anche_la_correzione_inventa_si_riscrive(self, monkeypatch):
        import json as _json
        inventato = _json.dumps({"dettagli_inventati": ["un glitch"]})
        risultato, prompt_visti, verifiche, _ = self._genera(
            monkeypatch, [self.BASE._risposta(), self.BASE._risposta(self.PULITO)],
            [inventato, inventato, _json.dumps({"dettagli_inventati": []})],
            self.BASE.SCRIPT)
        assert len(prompt_visti) == 2
        assert "un glitch" in prompt_visti[1][1]
        assert risultato["script"] == self.PULITO

    def test_una_correzione_troppo_corta_non_passa(self, monkeypatch):
        import json as _json
        risultato, prompt_visti, verifiche, _ = self._genera(
            monkeypatch, [self.BASE._risposta(), self.BASE._risposta(self.PULITO)],
            [_json.dumps({"dettagli_inventati": ["un glitch"]}),
             _json.dumps({"dettagli_inventati": []})],
            "Some Xbox players got GTA 6.")
        # La correzione corta non arriva nemmeno alla verifica.
        assert len(prompt_visti) == 2
        assert len(verifiche) == 2
        assert risultato["script"] == self.PULITO


class TestCorreggiScriptConGroq:
    ORIGINALE = staticmethod(brain._correggi_script)

    def test_legge_lo_script_dalla_risposta(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "client", TestConfrontoCorrezione._client(
            '{"script": "  Lo script corretto.  "}', viste))
        assert self.ORIGINALE("vecchio", ["un prezzo di 30 dollari"],
                              "Black Clover arriva in Fortnite",
                              "Le skin arrivano il 7 ottobre") == "Lo script corretto."
        utente = viste[0]["messages"][1]["content"]
        assert "un prezzo di 30 dollari" in utente
        assert "SOMMARIO: Le skin arrivano il 7 ottobre" in utente
        assert "SCRIPT: vecchio" in utente

    def test_un_errore_di_groq_non_corregge_niente(self, monkeypatch):
        monkeypatch.setattr(brain, "client", TestConfrontoCorrezione._client(
            RuntimeError("500 boom"), []))
        assert self.ORIGINALE("vecchio", ["x"], "titolo") == ""

    def test_senza_dettagli_non_chiama_groq(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "client", TestConfrontoCorrezione._client(
            '{"script": "x"}', viste))
        assert self.ORIGINALE("vecchio", [], "titolo") == ""
        assert viste == []


class TestConfrontoCorrezione:
    @staticmethod
    def _client(esito, viste):
        class Completions:
            @staticmethod
            def create(**kw):
                viste.append(kw)
                if isinstance(esito, Exception):
                    raise esito

                class Scelta:
                    class message:
                        content = esito

                class Risposta:
                    choices = [Scelta()]

                return Risposta()

        class Client:
            class chat:
                completions = Completions()

        return Client()


class TestTestataNellaVerifica:
    def test_la_testata_arriva_alla_verifica(self, monkeypatch):
        visti = []

        class FinteCompletions:
            @staticmethod
            def create(**kw):
                visti.append(kw["messages"][1]["content"])

                class Scelta:
                    class message:
                        content = '{"dettagli_inventati": []}'

                class Risposta:
                    choices = [Scelta()]
                return Risposta()

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        monkeypatch.setattr(brain, "client", FintoClient())
        assert brain._dettagli_inventati(
            "GTA 6, ce ne sono quasi 90", "Everyeye ne ha contate quasi 90.",
            testata="Everyeye.it") == []
        assert "TESTATA: Everyeye.it" in visti[0]


class TestInvitoAlPubblico:
    """1 ottobre 2026: la verifica ha segnalato come fatti gli inviti a
    commentare, e l'uscita delle 21:00 e' saltata."""

    @pytest.mark.parametrize("dettaglio", [
        "Viewers are encouraged to like the video.",
        "Viewers are encouraged to share their opinions on Poppone TV.",
        "Gli spettatori sono invitati a commentare",
        "Subscribe for more updates",
    ])
    def test_gli_inviti_non_sono_fatti(self, dettaglio):
        assert brain._invito_al_pubblico(dettaglio)

    @pytest.mark.parametrize("dettaglio", [
        "Loading times are faster after the update.",
        "The patch eliminates crashes on PlayStation 5 consoles.",
        "Rockstar ha annunciato la data di uscita",
    ])
    def test_i_fatti_restano(self, dettaglio):
        assert not brain._invito_al_pubblico(dettaglio)


class TestTogliFrasiInventate:
    SCRIPT = ("A 78 anni una nonna ha conquistato il Guinness World Record con "
              "Fortnite. Nessuno l'aspettava! Il suo sorriso ha acceso milioni "
              "di chat. Il record dimostra che il controller non ha eta'. "
              "Seguici su Poppone TV.")
    TITOLO = "A 78 anni una nonna conquista il Guinness World Record con Fortnite"

    def test_toglie_le_frasi_citate(self):
        ripulito = brain._togli_frasi_inventate(
            self.SCRIPT, ["Nessuno l’aspettava", "Il suo sorriso ha acceso milioni di chat"],
            self.TITOLO)
        assert "aspettava" not in ripulito
        assert "sorriso" not in ripulito
        assert ripulito.startswith("A 78 anni una nonna")

    def test_riconosce_un_riassunto_della_frase(self):
        ripulito = brain._togli_frasi_inventate(
            self.SCRIPT, ["il record dimostra che il controller"], self.TITOLO)
        assert "controller" not in ripulito

    def test_un_dettaglio_che_la_notizia_dice_non_si_tocca(self):
        # La verifica aveva segnalato "78", l'eta' scritta nel titolo.
        assert brain._togli_frasi_inventate(
            self.SCRIPT, ["78"], self.TITOLO) == self.SCRIPT

    def test_un_dettaglio_che_non_si_trova_obbliga_a_riscrivere(self):
        assert brain._togli_frasi_inventate(
            self.SCRIPT, ["un glitch che salta l'acquisto"], self.TITOLO) == ""

    def test_non_toglie_piu_di_meta_dello_script(self):
        assert brain._togli_frasi_inventate(
            self.SCRIPT, ["Nessuno l'aspettava", "sorriso acceso milioni chat",
                          "record dimostra controller", "Seguici su Poppone TV"],
            self.TITOLO) == ""


class TestLimiteGroq:
    ERRORE = ("Error code: 429 - {'error': {'message': 'Rate limit reached for "
              "model `openai/gpt-oss-20b` on tokens per minute (TPM): Limit "
              "8000, Used 4765, Requested 3390. Please try again in 1.1625s.'}}")

    def _client(self, esiti):
        chiamate = []

        class FinteCompletions:
            @staticmethod
            def create(**kw):
                chiamate.append(kw)
                esito = esiti.pop(0)
                if isinstance(esito, Exception):
                    raise esito
                return esito

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        return FintoClient(), chiamate

    def test_legge_l_attesa(self):
        assert brain._attesa_limite_groq(self.ERRORE) == pytest.approx(1.6625)
        assert brain._attesa_limite_groq("429 try again in 795ms") == pytest.approx(1.295)

    def test_non_aspetta_attese_lunghe_o_altri_errori(self):
        assert brain._attesa_limite_groq("429 Please try again in 12m3.5s") is None
        assert brain._attesa_limite_groq("503 Service Unavailable") is None

    def test_aspetta_e_riprova_una_volta(self, monkeypatch):
        client, chiamate = self._client([RuntimeError(self.ERRORE), "ok"])
        monkeypatch.setattr(brain, "client", client)
        attese = []
        monkeypatch.setattr(brain.time, "sleep", attese.append)
        assert brain._chiedi_a_groq(model="m") == "ok"
        assert len(chiamate) == 2
        assert attese == [pytest.approx(1.6625)]

    def test_un_altro_errore_passa_subito(self, monkeypatch):
        client, chiamate = self._client([RuntimeError("400 json_validate_failed")])
        monkeypatch.setattr(brain, "client", client)
        with pytest.raises(RuntimeError):
            brain._chiedi_a_groq(model="m")
        assert len(chiamate) == 1
