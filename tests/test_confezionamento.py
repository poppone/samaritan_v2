# -*- coding: utf-8 -*-
"""Test su come il video viene confezionato: titolo, descrizione, tag, miniatura.

Questa e' la parte che decide se un video pubblicato e' RAGGIUNGIBILE. Lo
script puo' essere ottimo, ma se il titolo viene troncato nel feed, non nomina
il gioco e la descrizione e' identica a quella di ieri, il video non lo trova
nessuno e il canale sembra automatico anche a chi ci capita per caso.
"""
import brain
import config


DATI_GTA = {
    "titolo": "GTA 6: la mappa che gira online e' falsa",
    "descrizione": "Due righe sul contenuto.\nE la domanda finale?",
    "gioco": "Grand Theft Auto VI",
    "stile": "MYTH_BUSTING_VIRAL",
    "fonte": "Rockstar smentisce la mappa (Everyeye)",
    "fonte_url": "https://news.example.com/gta6-mappa",
}

DATI_EVERGREEN = {
    "titolo": "Portal: il segreto dietro la stanza 19",
    "descrizione": "Un dettaglio che quasi nessuno nota.\nTu lo sapevi?",
    "gioco": "Portal",
    "stile": "EASTER_EGG_SECRET",
    "fonte": "",
    "fonte_url": "",
}


class TestValidaTitolo:
    def test_accetta_un_titolo_a_regola(self):
        ok, motivo = brain.valida_titolo(DATI_GTA["titolo"], DATI_GTA["gioco"])
        assert ok, motivo

    def test_rifiuta_il_titolo_troppo_lungo(self):
        # Oltre i 60 caratteri il feed Shorts taglia proprio la parte utile.
        lungo = "Fortnite: " + "parola " * 12
        assert len(lungo) > brain.MAX_CARATTERI_TITOLO
        ok, motivo = brain.valida_titolo(lungo, "Fortnite")
        assert not ok and "lungo" in motivo

    def test_rifiuta_il_maiuscolo_integrale(self):
        ok, motivo = brain.valida_titolo(
            "FORTNITE: L'ERRORE CHE TI FA PERDERE", "Fortnite")
        assert not ok and "maiuscolo" in motivo

    def test_accetta_le_sigle_in_maiuscolo(self):
        # 'GTA' e 'VI' sono maiuscoli legittimi: non devono far scattare la regola.
        ok, motivo = brain.valida_titolo(
            "GTA 6: la mappa di Vice City e' falsa", "Grand Theft Auto VI")
        assert ok, motivo

    def test_rifiuta_hashtag_shorts(self):
        ok, motivo = brain.valida_titolo("Fortnite: il segreto #Shorts", "Fortnite")
        assert not ok and "Shorts" in motivo

    def test_rifiuta_piu_di_una_emoji(self):
        ok, motivo = brain.valida_titolo("Fortnite: il segreto di Sora \U0001F47E\U0001F525",
                                         "Fortnite")
        assert not ok and "emoji" in motivo

    def test_rifiuta_il_titolo_che_non_nomina_il_gioco(self):
        # E' il caso dei video gia' pubblicati: nessuno cerca '3 segreti nascosti'.
        ok, motivo = brain.valida_titolo(
            "3 segreti nascosti che ti faranno impazzire", "Fortnite")
        assert not ok and "ricerca" in motivo

    def test_riconosce_la_sigla_al_posto_del_nome_ufficiale(self):
        # Il modello restituisce il nome dello store, il titolo usa la sigla.
        assert brain._gioco_nel_titolo("GTA 6: il leak", "Grand Theft Auto VI")
        assert brain._gioco_nel_titolo("Elden Ring: il boss", "ELDEN RING")
        assert not brain._gioco_nel_titolo("Il boss piu' difficile", "ELDEN RING")

    def test_senza_gioco_non_impone_niente(self):
        ok, _ = brain.valida_titolo("Le classifiche piu' divisive del 2026", "")
        assert ok

    def test_rifiuta_il_titolo_vuoto(self):
        assert not brain.valida_titolo("", "Fortnite")[0]


class TestPulisciTitoloEmoji:
    def test_sposta_in_fondo_l_emoji_iniziale(self):
        # In apertura l'emoji ruba il posto alla keyword del gioco.
        pulito = brain._pulisci_titolo("\U0001F6AB GTA 6: la mappa e' falsa")
        assert pulito.startswith("GTA 6")
        assert pulito.endswith("\U0001F6AB")

    def test_tiene_una_sola_emoji(self):
        pulito = brain._pulisci_titolo(
            "⚡ SORA \U0001F525 in Fortnite \U0001F47E")
        assert len(brain._RE_EMOJI_SINGOLA.findall(pulito)) == 1

    def test_non_lascia_due_punti_orfani(self):
        assert ":" not in brain._pulisci_titolo("\U0001F50E Fortnite \U0001F525")[-2:]

    def test_il_titolo_senza_emoji_resta_identico(self):
        assert brain._pulisci_titolo("Portal: la stanza 19") == "Portal: la stanza 19"


class TestHashtag:
    def test_il_primo_hashtag_e_il_gioco(self):
        # E' l'unico che YouTube mostra sopra al titolo del video.
        assert brain.costruisci_hashtag(DATI_GTA)[0] == "#grandtheftautovi"

    def test_al_massimo_tre(self):
        assert len(brain.costruisci_hashtag(DATI_GTA)) == 3

    def test_niente_doppioni(self):
        dati = dict(DATI_EVERGREEN, gioco="gamingita", stile="DOMANDA_AL_PUBBLICO")
        assert len(brain.costruisci_hashtag(dati)) == len(
            set(brain.costruisci_hashtag(dati)))

    def test_toglie_accenti_e_spazi(self):
        assert brain._hashtag("Curiosità Gaming") == "#curiositagaming"

    def test_regge_il_video_senza_gioco(self):
        hashtag = brain.costruisci_hashtag({"gioco": "", "stile": ""})
        assert hashtag == ["#gamingita"]


class TestTag:
    def test_contiene_i_fissi_e_il_gioco(self):
        tag = brain.costruisci_tag(DATI_GTA)
        assert "gaming ita" in tag
        assert "grand theft auto vi" in tag

    def test_aggiunge_la_saga_senza_il_numero(self):
        assert "grand theft auto" in brain.costruisci_tag(DATI_GTA)

    def test_cambia_da_un_video_all_altro(self):
        # Cinque tag identici su ogni upload sono una firma da canale automatico.
        assert brain.costruisci_tag(DATI_GTA) != brain.costruisci_tag(DATI_EVERGREEN)

    def test_niente_doppioni(self):
        tag = brain.costruisci_tag(DATI_GTA)
        assert len(tag) == len({t.lower() for t in tag})

    def test_rispetta_il_limite_di_caratteri_di_youtube(self):
        # Oltre i 500 caratteri YouTube rifiuta l'upload INTERO, non i tag.
        tag = brain.costruisci_tag(dict(DATI_GTA, gioco="g" * 200))
        assert sum(len(t) for t in tag) <= 450
        assert len(tag) <= 15

    def test_regge_il_video_senza_gioco(self):
        tag = brain.costruisci_tag({"gioco": "", "stile": ""})
        assert tag and all(tag)


class TestDescrizione:
    def test_mette_il_link_della_fonte_non_solo_la_testata(self):
        assert DATI_GTA["fonte_url"] in brain.costruisci_descrizione(DATI_GTA)

    def test_ripiega_sulla_testata_se_il_link_manca(self):
        dati = dict(DATI_GTA, fonte_url="")
        descrizione = brain.costruisci_descrizione(dati)
        assert "Everyeye" in descrizione

    def test_non_usa_piu_gli_hashtag_fissi(self):
        # '#Shorts' come primo hashtag sprecava l'unico spazio visibile.
        descrizione = brain.costruisci_descrizione(DATI_GTA)
        assert "#Shorts" not in descrizione
        assert descrizione.rstrip().endswith("#gamingita")

    def test_aggiunge_i_link_della_lingua(self, monkeypatch):
        monkeypatch.setenv("LINK_DESCRIZIONE", '{"it": ["Offerte: https://esempio.it"]}')
        monkeypatch.setattr(brain.config, "LINGUA", "it")
        descrizione = brain.costruisci_descrizione(DATI_GTA)
        assert "Offerte: https://esempio.it" in descrizione
        assert descrizione.rstrip().endswith("#gamingita")

    def test_senza_link_per_la_lingua_non_aggiunge_niente(self, monkeypatch):
        monkeypatch.setenv("LINK_DESCRIZIONE", '{"it": ["Offerte: https://esempio.it"]}')
        monkeypatch.setattr(brain.config, "LINGUA", "en")
        assert "esempio.it" not in brain.costruisci_descrizione(DATI_GTA)

    def test_canale_gaming_porta_instant_gaming(self, monkeypatch):
        monkeypatch.delenv("LINK_DESCRIZIONE", raising=False)
        monkeypatch.setattr(brain.config, "LINGUA", "it")
        assert "igr=poppone" in brain.costruisci_descrizione(DATI_GTA)

    def test_porta_al_canale(self):
        assert "@davidedurazzi" in brain.costruisci_descrizione(DATI_GTA)

    def test_porta_al_sito_subito_sotto_le_prime_righe(self, monkeypatch):
        monkeypatch.setattr(config, "SITO_CANALE", "davidedurazzi.it")
        monkeypatch.setattr(config, "LINGUA", "it")
        righe = brain.costruisci_descrizione(DATI_GTA).split("\n")
        assert "Approfondimenti su https://davidedurazzi.it" in righe[:4]
        monkeypatch.setattr(config, "LINGUA", "en")
        assert "More on https://davidedurazzi.it" in brain.costruisci_descrizione(DATI_GTA)

    def test_senza_sito_nessuna_riga(self, monkeypatch):
        monkeypatch.setattr(config, "SITO_CANALE", "")
        assert "https://davidedurazzi" not in brain.costruisci_descrizione(DATI_GTA)

    def test_cambia_da_un_video_all_altro(self):
        a = brain.costruisci_descrizione(DATI_GTA)
        b = brain.costruisci_descrizione(DATI_EVERGREEN)
        assert a != b
        # e non solo nelle prime due righe: anche fonte, attribuzione e hashtag
        assert a.splitlines()[-1] != b.splitlines()[-1]

    def test_regge_i_campi_mancanti(self):
        assert brain.costruisci_descrizione({"titolo": "Solo un titolo"})


class TestTestoMiniatura:
    def test_prende_l_amo_dopo_i_due_punti(self):
        # Il gioco YouTube lo mostra gia' nel titolo sotto la miniatura.
        assert brain.testo_miniatura(
            "Fortnite: l'errore che ti fa perdere ogni partita"
        ) == "L'ERRORE"

    def test_toglie_le_emoji(self):
        # Il font del montaggio non ha i glifi: resterebbero quadratini vuoti.
        testo = brain.testo_miniatura("GTA 6: la mappa e' falsa \U0001F50E")
        assert "\U0001F50E" not in testo

    def test_funziona_senza_due_punti(self):
        assert brain.testo_miniatura("Tre segreti di Portal") == "TRE SEGRETI DI PORTAL"

    def test_regge_il_titolo_vuoto(self):
        assert brain.testo_miniatura("") == ""

    def test_non_lascia_parole_penzolanti(self):
        # Tagliare a un numero fisso di parole lasciava code come
        # "IL BOSS CHE QUASI", che sulla miniatura non dicono niente.
        assert brain.testo_miniatura(
            "Elden Ring: il boss che quasi nessuno ha mai battuto") == "IL BOSS"
        assert brain.testo_miniatura("Portal: la stanza 19") == "LA STANZA 19"

    def test_non_svuota_mai_del_tutto(self):
        # Anche se sono tutte parole deboli, qualcosa deve restare.
        assert brain.testo_miniatura("Gioco: e che ti fa") != ""


class TestRigenerazioneInformata:
    """Dopo uno scarto il modello deve sapere cosa ha sbagliato.

    Senza questo ogni tentativo riparte dallo stesso identico input: quattro
    tentativi sono quattro tiri di dado invece di quattro correzioni.
    """

    # Uno script che passa valida_script(): abbastanza lungo, apertura non
    # vietata, e chiude riprendendo l'apertura come vuole il formato loop.
    _SCRIPT = (
        "Nessuno lo trova al primo giro in tutta la regione iniziale del gioco. "
        "Dietro la cascata piu' grande c'e' una porta che sembra decorazione. "
        "Si apre soltanto suonando la campana trovata nella cripta a nord, e "
        "dentro ti aspetta un boss che nessuna guida italiana ha mai filmato "
        "per davvero. Ti lascia un'arma che cambia completamente la build. "
        "Provaci stasera prima di andare avanti con la storia principale. "
        "Nessuno lo trova al primo giro."
    )

    def _finto_client(self, risposte, prompt_visti):
        class FinteCompletions:
            @staticmethod
            def create(**kw):
                prompt_visti.append(kw["messages"][1]["content"])

                class Scelta:
                    class message:
                        content = risposte.pop(0)

                class Risposta:
                    choices = [Scelta()]

                return Risposta()

        class FintoClient:
            class chat:
                completions = FinteCompletions()

        return FintoClient()

    def test_il_motivo_dello_scarto_arriva_al_tentativo_dopo(self, monkeypatch):
        import json as _json

        # Primo titolo: tutto maiuscolo, viene scartato. Secondo: valido.
        # (Un titolo troppo lungo non si scarta piu': si accorcia.)
        scartato = _json.dumps({
            "titolo": "ELDEN RING: IL BOSS SEGRETO DELLA CASCATA",
            "script": self._SCRIPT,
            "gioco": "Elden Ring", "query_video": "elden ring gameplay",
            "descrizione": "Un segreto.", "indice_notizia": -1,
        })
        buono = _json.dumps({
            "titolo": "Elden Ring: il boss dietro la cascata",
            "script": self._SCRIPT,
            "gioco": "Elden Ring", "query_video": "elden ring gameplay",
            "descrizione": "Un segreto.", "indice_notizia": -1,
        })

        prompt_visti = []
        monkeypatch.setattr(brain, "client",
                            self._finto_client([scartato, buono], prompt_visti))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 2
        assert "scartato" not in prompt_visti[0].lower()
        assert "maiuscolo" in prompt_visti[1], prompt_visti[1]
        assert risultato["titolo"] == "Elden Ring: il boss dietro la cascata"


class TestAperturaRipetuta:
    """Nove Short di fila aperti nello stesso modo sono il rischio vero.

    Il 18 settembre 2026 tutti e nove gli script della giornata iniziavano
    con "Stai..." oppure "Nessuno ti ha detto che...", perche' erano i due
    esempi scritti dentro il prompt e il modello li ricopiava. E' esattamente
    la firma del contenuto prodotto in serie che YouTube guarda quando decide
    se un canale puo' essere monetizzato.
    """

    def test_l_impronta_ignora_accenti_maiuscole_e_punteggiatura(self):
        assert brain._impronta_apertura("Perche' NON l'hai") == \
            brain._impronta_apertura("perche, non l hai mai visto")

    def test_due_aperture_uguali_su_giochi_diversi_hanno_la_stessa_impronta(self):
        # Il caso vero: cambia solo il gioco dopo le prime tre parole.
        a = brain._impronta_apertura("Stai sbagliando tutto su Fortnite. Primo posto.")
        b = brain._impronta_apertura("Stai sbagliando tutto su Game Pass. Oggi aggiunge due.")
        assert a == b == "stai sbagliando tutto"

    def test_valida_script_scarta_l_apertura_gia_usata(self):
        script = TestRigenerazioneInformata._SCRIPT
        impronta = brain._impronta_apertura(script)
        ok, motivo = brain.valida_script("Portal: la stanza 19", script, {impronta})
        assert not ok
        assert "apre come un video recente" in motivo

    def test_lo_stesso_script_passa_se_non_c_e_niente_da_ripetere(self):
        ok, motivo = brain.valida_script(
            "Portal: la stanza 19", TestRigenerazioneInformata._SCRIPT, set()
        )
        assert ok, motivo

    def test_il_prompt_non_suggerisce_piu_le_due_aperture_fisse(self):
        prompt = brain._costruisci_system_prompt(
            "EASTER_EGG_SECRET", [], [], []
        )
        assert "Stai sbagliando tutto su" not in prompt
        assert "Nessuno ti ha detto che" not in prompt

    def test_il_prompt_elenca_le_aperture_da_evitare(self):
        prompt = brain._costruisci_system_prompt(
            "EASTER_EGG_SECRET", [], [], [],
            aperture_recenti=["Nessuno ti ha detto che il decennio"],
        )
        assert "Nessuno ti ha detto che il decennio" in prompt

    def test_senza_cronologia_la_regola_non_compare(self):
        # Al primo video del canale una lista vuota sarebbe solo rumore.
        prompt = brain._costruisci_system_prompt("EASTER_EGG_SECRET", [], [], [])
        assert "11." not in prompt
        assert "12." not in prompt


class TestDoppioni:
    """Il 18 settembre 2026 sono usciti due Short sullo stesso gioco e dalla
    stessa identica notizia, perche' il controllo guardava solo i titoli."""

    FONTE = "10 anni di No Man's Sky: arriva l'update Cosmos (tomshw.it)"

    def test_scarta_la_notizia_gia_usata(self):
        motivo = brain._doppione_recente(
            "Hollow Knight", self.FONTE, "", {self.FONTE.lower()}
        )
        assert "stessa notizia" in motivo

    def test_scarta_il_gioco_del_video_precedente(self):
        motivo = brain._doppione_recente(
            "No Man's Sky", "", "no man's sky", set()
        )
        assert "come il video precedente" in motivo

    def test_lascia_passare_un_gioco_diverso_con_una_notizia_nuova(self):
        assert brain._doppione_recente(
            "Hollow Knight", "Silksong ha una data (Eurogamer)",
            "no man's sky", {self.FONTE.lower()}
        ) == ""

    def test_il_video_senza_gioco_e_senza_fonte_non_e_mai_un_doppione(self):
        # 'gioco' vuoto e' legittimo: lo Short non parla di un gioco solo.
        assert brain._doppione_recente("", "", "", set()) == ""

    def test_il_prompt_elenca_gioco_e_notizia_da_non_ripetere(self):
        prompt = brain._costruisci_system_prompt(
            "EASTER_EGG_SECRET", [], [], [],
            giochi_recenti=["No Man's Sky"], notizie_gia_usate=[self.FONTE],
        )
        assert "No Man's Sky" in prompt
        assert self.FONTE in prompt


class TestAperturaRipetutaDalVivo:
    """La prova che conta: con un video gia' in cronologia, uno script che
    riapre allo stesso modo viene davvero scartato e rigenerato."""

    _CODA = (
        "La stanza numero diciannove sembra un corridoio qualunque, e invece "
        "nasconde il primo disegno lasciato dagli autori durante le prove "
        "interne. Per vederlo devi appoggiare il cubo sul pulsante sbagliato e "
        "restare fermo una decina di secondi buoni. Poi la parete scorre e resta "
        "aperta finche' non esci dal livello. Provaci stasera prima di dormire."
    )
    RIPETUTO = "Stai sbagliando tutto su Portal. " + _CODA
    NUOVO = "Dietro una parete che sembra decorazione c'e' altro. " + _CODA

    def test_lo_script_che_riapre_uguale_viene_scartato_e_rifatto(self, monkeypatch):
        import json as _json

        def risposta(script):
            return _json.dumps({
                "titolo": "Portal: la stanza che non apre nessuno",
                "script": script, "gioco": "Portal",
                "query_video": "portal gameplay",
                "descrizione": "Un segreto.", "indice_notizia": -1,
            })

        cronologia = [{
            "titolo": "Fortnite: Tier List Lampo",
            "estratto_script": "Stai sbagliando tutto su Fortnite. Primo posto: la skin nuova.",
            "stile": "TIER_LIST_LAMPO", "gioco": "Fortnite",
            "fonte": "", "video_id": "hBMDcRhugbA",
        }]

        prompt_visti = []
        finto = TestRigenerazioneInformata()._finto_client(
            [risposta(self.RIPETUTO), risposta(self.NUOVO)], prompt_visti
        )
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: cronologia)
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 2, "il primo script doveva essere scartato"
        assert "apre come un video recente" in prompt_visti[1]
        assert risultato["script"] == self.NUOVO


class TestRigaMateriale:
    """La descrizione dichiarava "materiale promozionale ufficiale dei
    rispettivi editori" ogni volta che il modello aveva indicato un gioco.
    Ma `procura_materiale()` ripiega su clip d'archivio senza azzerare
    'gioco': su quei video la riga che dovrebbe dare credibilita' diceva il
    falso. Su un canale che chiedera' la monetizzazione e' il dettaglio che
    non conviene avere in giro."""

    SOLO_UFFICIALE = {"gioco_ufficiale": "Grand Theft Auto V",
                      "sorgenti_ufficiali": 5, "sorgenti_stock": 0}
    MISTO = {"gioco_ufficiale": "Grand Theft Auto V",
             "sorgenti_ufficiali": 2, "sorgenti_stock": 2}
    SOLO_ARCHIVIO = {"gioco_ufficiale": None,
                     "sorgenti_ufficiali": 0, "sorgenti_stock": 4}

    def test_dichiara_l_ufficialita_solo_quando_e_vera(self):
        testo = brain.costruisci_descrizione(DATI_GTA, self.SOLO_UFFICIALE)
        assert "materiale promozionale ufficiale" in testo
        assert "d'archivio" not in testo

    def test_usa_il_nome_ufficiale_di_steam_non_quello_del_modello(self):
        # Il credito parla di cosa e' stato scaricato davvero.
        testo = brain.costruisci_descrizione(DATI_GTA, self.SOLO_UFFICIALE)
        assert "Grand Theft Auto V:" in testo

    def test_sul_montaggio_misto_lo_dice(self):
        testo = brain.costruisci_descrizione(DATI_GTA, self.MISTO)
        assert "materiale promozionale ufficiale" in testo
        assert "integrato con filmati d'archivio" in testo

    def test_niente_editori_se_il_video_e_tutto_d_archivio(self):
        # Il caso del bug: 'gioco' e' valorizzato ma Steam non ha dato niente.
        testo = brain.costruisci_descrizione(DATI_GTA, self.SOLO_ARCHIVIO)
        assert "ufficiale dei rispettivi editori" not in testo
        assert "Filmati d'archivio" in testo

    def test_senza_resoconto_non_afferma_niente(self):
        testo = brain.costruisci_descrizione(DATI_GTA)
        assert "ufficiale dei rispettivi editori" not in testo
        assert "a scopo illustrativo" in testo

    def test_la_pipeline_collega_davvero_montaggio_e_descrizione(self):
        """Senza questo collegamento la correzione non serve a niente.

        main.py e maker.py non sono importabili nei test (tirano dentro
        moviepy e le librerie Google), quindi il controllo e' sul sorgente:
        e' sufficiente, perche' l'errore che si vuole impedire e' proprio
        che qualcuno rimuova il passaggio del resoconto.
        """
        import os
        radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(radice, "main.py"), encoding="utf-8") as f:
            main_py = f.read()
        with open(os.path.join(radice, "maker.py"), encoding="utf-8") as f:
            maker_py = f.read()

        assert "resoconto=materiale" in main_py
        assert "costruisci_descrizione(dati, materiale, capitoli)" in main_py
        assert 'resoconto["sorgenti_ufficiali"]' in maker_py


class TestNomeFormatoInChiaro:
    """La prova in privato del 19 settembre 2026 ha prodotto il titolo
    "Stalker 2: DONT_DO_THIS - non spendere energia sbagliata": il modello ha
    ricopiato l'etichetta interna dalla riga FORMATO RICHIESTO del prompt.
    Senza questo controllo quel titolo sarebbe uscito pubblico."""

    TITOLO_SPORCO = "Stalker 2: DONT_DO_THIS - non spendere energia sbagliata"

    def test_riconosce_l_etichetta_nel_titolo(self):
        assert brain._nome_formato_in_chiaro(self.TITOLO_SPORCO) == "DONT_DO_THIS"

    def test_valida_titolo_lo_scarta(self):
        ok, motivo = brain.valida_titolo(self.TITOLO_SPORCO, "Stalker 2")
        assert not ok
        assert "nome interno del formato" in motivo

    def test_valida_script_lo_scarta(self):
        sporco = "VIRAL_HOOK_NEWS. " + TestRigenerazioneInformata._SCRIPT
        ok, motivo = brain.valida_script("Portal: la stanza 19", sporco)
        assert not ok
        assert "nome interno del formato" in motivo

    def test_non_scarta_un_titolo_italiano_legittimo(self):
        # "Fortnite: Tier List Lampo" e' un titolo vero gia' pubblicato: con
        # gli spazi non e' l'etichetta interna e deve passare.
        assert brain._nome_formato_in_chiaro("Fortnite: Tier List Lampo") == ""
        ok, motivo = brain.valida_titolo("Fortnite: Tier List Lampo", "Fortnite")
        assert ok, motivo

    def test_il_prompt_avvisa_che_la_sigla_non_va_scritta(self):
        prompt = brain._costruisci_system_prompt("DONT_DO_THIS", [], [], [])
        assert "etichetta interna" in prompt


class TestCodaTroncata:
    """Il 19 settembre 2026 lo Short su EA Sports FC 26 e' uscito con lo
    script chiuso cosi': '...Iscriviti a Poppone TV e non perderti nulla.
    Hai'. Il tetto di token copre anche il ragionamento del modello, quindi
    ogni tanto la risposta si interrompe a meta' parola, e nel video si sente:
    la voce legge la chiusura e poi aggiunge una parola a vuoto."""

    REALE = (
        "Hai mai creduto che Maradona fosse un mito irraggiungibile? La "
        "verita' e' che EA Sports FC 26 rilascia l'update The World's Game, e "
        "include Maradona e Pele totalmente gratis. Nessuna microtransazione, "
        "solo un download. Il contenuto arriva gia' pronto su Xbox Game Pass "
        "e PC. Vuoi vedere l'azione dal vivo? Iscriviti a Poppone TV e non "
        "perderti nulla. Hai"
    )

    def test_toglie_la_parola_rimasta_a_meta(self):
        riparato = brain._senza_coda_troncata(self.REALE)
        assert riparato.endswith("non perderti nulla.")
        assert not brain._script_troncato(riparato)

    def test_toglie_anche_la_frase_lasciata_a_meta(self):
        testo = "Prima frase chiusa. La seconda invece si ferma qui dopo"
        assert brain._senza_coda_troncata(testo) == "Prima frase chiusa."

    def test_una_virgola_finale_conta_come_frase_tronca(self):
        testo = "Prima frase chiusa. E poi,"
        assert brain._senza_coda_troncata(testo) == "Prima frase chiusa."

    def test_uno_script_gia_finito_non_si_tocca(self):
        for testo in ("Frase una. Frase due!", "Frase una. Frase due! \U0001f3ae",
                      "Boom... ecco la notizia?"):
            assert brain._senza_coda_troncata(testo) == testo
            assert not brain._script_troncato(testo)

    def test_senza_nessuna_frase_chiusa_resta_intatto_e_lo_scarta_il_validatore(self):
        testo = " ".join(["parola"] * 50)
        assert brain._senza_coda_troncata(testo) == testo
        ok, motivo = brain.valida_script("Un titolo qualunque su Portal", testo)
        assert not ok
        assert "meta' frase" in motivo

    def test_il_generatore_ripara_invece_di_bruciare_un_tentativo(self, monkeypatch):
        """La riparazione non deve costare un tentativo: rigenerare puo' far
        saltare la pubblicazione, e la coda tronca arriva sempre dopo la
        chiusura vera."""
        import json as _json

        risposta = _json.dumps({
            "titolo": "EA Sports FC 26: Maradona e Pele gratis?",
            "script": self.REALE, "gioco": "EA Sports FC 26",
            "query_video": "ea sports fc 26 gameplay",
            "descrizione": "L'update The World's Game.", "indice_notizia": -1,
        })

        prompt_visti = []
        finto = TestRigenerazioneInformata()._finto_client([risposta], prompt_visti)
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 1, "non doveva servire un secondo tentativo"
        assert risultato["script"].endswith("non perderti nulla.")


class TestNotiziaGiaUsata:
    """Il 19 settembre 2026 l'update Cosmos di No Man's Sky e' diventato due
    Short a un giorno di distanza. Il filtro delle notizie confrontava le
    parole del titolo della notizia con i TITOLI dei video gia' fatti, che
    pero' il modello riscrive: "No Man's Sky: 10 anni di esplorazione" non
    somiglia abbastanza a "10 anni di No Man's Sky: arriva l'update Cosmos".
    La notizia usata pero' e' scritta per intero in cronologia, quindi il
    confronto si puo' fare esatto."""

    NOTIZIA = "10 anni di No Man's Sky: arriva l'update Cosmos"
    IN_CRONOLOGIA = "10 anni di No Man's Sky: arriva l'update Cosmos (tomshw.it)"

    def _rss(self, titoli):
        voci = "".join(
            f"<item><title>{t} - Testata</title>"
            f"<link>https://example.com/{i}</link></item>"
            for i, t in enumerate(titoli)
        )
        corpo = f"<rss><channel>{voci}</channel></rss>".encode()

        class Risposta:
            content = corpo

            def raise_for_status(self):
                return None

        return lambda *a, **k: Risposta()

    def test_la_testata_in_coda_non_impedisce_il_confronto(self):
        assert (brain._notizia_di_una_voce(self.IN_CRONOLOGIA)
                == brain._impronta_notizia(self.NOTIZIA))

    def test_accenti_e_apostrofi_non_contano(self):
        assert (brain._impronta_notizia("L'update Cosmos è qui!")
                == brain._impronta_notizia("l update cosmos e qui"))

    def test_una_voce_senza_fonte_non_blocca_niente(self):
        assert brain._notizia_di_una_voce("") == ""
        assert brain._notizia_di_una_voce(None) == ""

    def test_la_notizia_gia_diventata_video_viene_scartata(self, monkeypatch):
        cronologia = [{
            "titolo": "No Man's Sky: 10 anni di esplorazione",
            "estratto_script": "Dieci anni dopo, arriva Cosmos.",
            "stile": "SEAMLESS_LOOP_FACTS", "gioco": "No Mans Sky",
            "fonte": self.IN_CRONOLOGIA, "video_id": "KxbKYIyTqIQ",
        }]
        monkeypatch.setattr(brain, "carica_cronologia", lambda: cronologia)
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss([self.NOTIZIA, "Hollow Knight Silksong ha una data"]),
        )

        notizie = brain.recupera_trend_gaming_online()

        titoli = [n["titolo"] for n in notizie]
        assert self.NOTIZIA not in titoli
        assert "Hollow Knight Silksong ha una data" in titoli

    def test_senza_cronologia_la_notizia_passa(self, monkeypatch):
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.requests, "get", self._rss([self.NOTIZIA]))

        assert [n["titolo"] for n in brain.recupera_trend_gaming_online()] == [self.NOTIZIA]

    def test_il_filtro_guarda_oltre_la_finestra_delle_ripetizioni(self, monkeypatch):
        """La notizia era sette voci indietro: la finestra di
        MEMORIA_RIPETIZIONI non la vedeva."""
        vecchia = {
            "titolo": "No Man's Sky: 10 anni di esplorazione", "estratto_script": "",
            "stile": "SEAMLESS_LOOP_FACTS", "gioco": "No Mans Sky",
            "fonte": self.IN_CRONOLOGIA, "video_id": "KxbKYIyTqIQ",
        }
        riempitivo = [{
            "titolo": f"Un altro video {n}", "estratto_script": "", "stile": "TIER_LIST_LAMPO",
            "gioco": f"Gioco {n}", "fonte": f"Una notizia diversa {n} (Testata)",
            "video_id": None,
        } for n in range(7)]
        assert len(riempitivo) > brain.MEMORIA_RIPETIZIONI

        monkeypatch.setattr(brain, "carica_cronologia", lambda: [vecchia] + riempitivo)
        monkeypatch.setattr(brain.requests, "get", self._rss([self.NOTIZIA]))

        assert brain.recupera_trend_gaming_online() == []


class TestCaricamentoFallito:
    """Il 4 ottobre 2026 il token YouTube era scaduto: nove lavorazioni hanno
    scritto righe senza video e ognuna evitava la notizia della precedente,
    che non era mai uscita."""

    ADESSO = 1_791_100_000
    NOTIZIA = TestNotiziaGiaUsata.NOTIZIA
    IN_CRONOLOGIA = TestNotiziaGiaUsata.IN_CRONOLOGIA
    _rss = TestNotiziaGiaUsata._rss

    def _voce(self, video_id, minuti_fa):
        return {"titolo": "No Man's Sky: arriva Cosmos", "estratto_script": "",
                "stile": "SEAMLESS_LOOP_FACTS", "gioco": "No Mans Sky",
                "lingua": "it", "fonte": self.IN_CRONOLOGIA,
                "video_id": video_id, "timestamp": self.ADESSO - minuti_fa * 60}

    def test_tiene_usciti_in_corso_e_vecchio_formato(self):
        uscita = self._voce("abc", 600)
        in_corso = self._voce(None, 10)
        fallita = self._voce(None, 120)
        vecchia = {"titolo": "senza campo video_id"}
        assert brain._uscite_o_in_corso(
            [uscita, in_corso, fallita, vecchia, "stringa"], adesso=self.ADESSO
        ) == [uscita, in_corso, vecchia, "stringa"]

    def test_la_notizia_di_un_caricamento_fallito_si_puo_usare(self, monkeypatch):
        monkeypatch.setattr(brain.time, "time", lambda: self.ADESSO)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [self._voce(None, 120)])
        monkeypatch.setattr(brain.requests, "get", self._rss([self.NOTIZIA]))

        assert [n["titolo"] for n in brain.recupera_trend_gaming_online()] == [self.NOTIZIA]

    def test_la_notizia_di_una_lavorazione_in_corso_resta_presa(self, monkeypatch):
        monkeypatch.setattr(brain.time, "time", lambda: self.ADESSO)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [self._voce(None, 10)])
        monkeypatch.setattr(brain.requests, "get", self._rss([self.NOTIZIA]))

        assert brain.recupera_trend_gaming_online() == []


class TestStoriaGiaRaccontata:
    """Il 27 settembre 2026 "FNAF Fortnite Collab Confirmed" ha fatto 740
    visualizzazioni, il giorno dopo la stessa storia presa da un altro
    articolo ne ha fatte 10. Il confronto esatto sulla notizia non poteva
    vederla: l'articolo era un altro, le parole quasi tutte diverse."""

    ADESSO = 1_790_900_000
    GIA_RACCONTATA = ("FNAF Fortnite Collab Confirmed by Epic Games - Release "
                      "Date, Skins and Mode Revealed (VICE)")
    RIPETUTA = "Fortnite Five Nights at Freddy's Announcement is the Most Liked Reveal Ever"
    NUOVA = "Hollow Knight Silksong ha una data"

    _rss = TestNotiziaGiaUsata._rss

    def _voce(self, giorni_fa, fonte=GIA_RACCONTATA, lingua="it"):
        return {"titolo": "Fortnite: FNAF Collab Confirmed", "estratto_script": "",
                "stile": "MYTH_BUSTING_VIRAL", "gioco": "Fortnite", "lingua": lingua,
                "fonte": fonte, "timestamp": self.ADESSO - giorni_fa * 86400}

    def _prepara(self, monkeypatch, cronologia, titoli, ripetute):
        monkeypatch.setattr(brain.time, "time", lambda: self.ADESSO)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: cronologia)
        monkeypatch.setattr(brain.requests, "get", self._rss(titoli))
        chiamate = []

        def finto(candidate, raccontate):
            chiamate.append((list(candidate), list(raccontate)))
            return {candidate.index(t) for t in ripetute if t in candidate}

        monkeypatch.setattr(brain, "_storie_gia_raccontate", finto)
        return chiamate

    def test_la_stessa_storia_da_un_altro_articolo_viene_saltata(self, monkeypatch):
        chiamate = self._prepara(monkeypatch, [self._voce(1)],
                                 [self.RIPETUTA, self.NUOVA], [self.RIPETUTA])

        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online()]

        assert titoli == [self.NUOVA]
        assert chiamate[0][1] == [self.GIA_RACCONTATA]

    def test_dopo_qualche_giorno_la_storia_si_puo_riprendere(self, monkeypatch):
        chiamate = self._prepara(monkeypatch,
                                 [self._voce(brain.GIORNI_STESSA_STORIA + 1)],
                                 [self.RIPETUTA, self.NUOVA], [self.RIPETUTA])

        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online()]

        assert self.RIPETUTA in titoli
        assert chiamate == [], "senza storie recenti Groq non va chiamato"

    def test_la_storia_raccontata_in_un_altra_lingua_non_conta(self, monkeypatch):
        chiamate = self._prepara(monkeypatch, [self._voce(1, lingua="en")],
                                 [self.RIPETUTA, self.NUOVA], [self.RIPETUTA])

        assert self.RIPETUTA in [n["titolo"] for n in brain.recupera_trend_gaming_online()]
        assert chiamate == []

    def test_se_sono_tutte_ripetute_si_tengono(self, monkeypatch):
        """Meglio una storia ripetuta che un'uscita senza notizie."""
        self._prepara(monkeypatch, [self._voce(1)],
                      [self.RIPETUTA, self.NUOVA], [self.RIPETUTA, self.NUOVA])

        assert len(brain.recupera_trend_gaming_online()) == 2

    def test_il_tema_chiesto_non_viene_saltato(self, monkeypatch):
        self._prepara(monkeypatch, [self._voce(1)],
                      [self.RIPETUTA, self.NUOVA], [self.RIPETUTA])

        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online(tema="fortnite")]

        assert self.RIPETUTA in titoli


class TestConfrontoStorieConGroq:
    """_storie_gia_raccontate legge la risposta del modello senza fidarsi."""

    ORIGINALE = staticmethod(brain._storie_gia_raccontate)

    def _client(self, esito, viste):
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

    def test_tiene_solo_numeri_validi_e_li_porta_a_zero(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "client",
                            self._client('{"ripetute": [2, 9, 0, true, "1"]}', viste))

        assert self.ORIGINALE(["a", "b", "c"], ["storia vecchia (Testata)"]) == {1}
        assert "1. a" in viste[0]["messages"][1]["content"]
        assert "storia vecchia" in viste[0]["messages"][1]["content"]

    def test_un_errore_di_groq_non_scarta_niente(self, monkeypatch):
        monkeypatch.setattr(brain, "client",
                            self._client(RuntimeError("500 boom"), []))

        assert self.ORIGINALE(["a"], ["storia vecchia"]) == set()

    def test_senza_storie_recenti_non_chiama_groq(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "client", self._client('{"ripetute": [1]}', viste))

        assert self.ORIGINALE(["a"], []) == set()
        assert viste == []


class TestSchemaApertura:
    """Quattro Short di fila aperti con una domanda retorica.

    Il 20 settembre 2026 le ultime quattro aperture erano "Pensavi che...?",
    "Scommetti che...?", "Hai mai creduto che...?", "Stai ancora credendo
    che...?". Nessuna ripeteva le parole di un'altra, quindi il controllo
    sulle tre parole iniziali le lasciava passare tutte. Da fuori pero' i
    quattro video si somigliano lo stesso, ed e' la somiglianza che conta
    per la monetizzazione.
    """

    APERTURE_VERE = (
        "Pensavi che i Mondiali fossero solo in TV? EA FC 26 li porta sul campo.",
        "Scommetti che non indovini il prezzo? Starfield cambia tutto.",
        "Hai mai creduto che No Man's Sky fosse finito? Cosmos dice altro.",
        "Stai ancora credendo che i Mondiali siano solo in TV? Guarda qui.",
    )

    def test_le_quattro_aperture_vere_hanno_lo_stesso_schema(self):
        schemi = {brain._schema_apertura(a) for a in self.APERTURE_VERE}
        assert schemi == {brain.SCHEMA_DOMANDA}

    def test_il_controllo_sulle_parole_non_le_prendeva(self):
        # Il motivo per cui serviva un controllo nuovo: quattro impronte
        # diverse, quindi il vecchio confronto non scartava niente.
        impronte = {brain._impronta_apertura(a) for a in self.APERTURE_VERE}
        assert len(impronte) == 4

    def test_conta_solo_la_prima_frase(self):
        # Apre con un'affermazione: la domanda arriva dopo e non e' l'attacco.
        assert brain._schema_apertura("Rockstar ha mentito. Ci credi?") == ""

    def test_una_frase_normale_non_ha_schema(self):
        # Senza questo non resterebbe nessuna apertura consentita.
        assert brain._schema_apertura("Dieci anni dopo, arriva Cosmos.") == ""

    def test_l_apertura_rivolta_allo_spettatore_senza_domanda(self):
        assert brain._schema_apertura(
            "Stai sbagliando tutto su Fortnite. Primo posto: la skin nuova."
        ) == brain.SCHEMA_SECONDA_PERSONA

    def test_le_parole_ambigue_non_fanno_falsi_positivi(self):
        # "sei" e' anche il numero, "dai" anche la preposizione, "vi" anche
        # il VI di GTA VI. Un falso positivo qui costa un tentativo.
        assert brain._schema_apertura(
            "GTA VI slitta al 2027. Sei mesi di attesa in piu'."
        ) == ""
        assert brain._schema_apertura(
            "Dai primi giorni le navi di Starfield erano rotte."
        ) == ""

    def test_valida_script_scarta_lo_schema_gia_usato(self):
        script = self.APERTURE_VERE[0] + " " + TestAperturaRipetutaDalVivo._CODA
        ok, motivo = brain.valida_script(
            "EA FC 26: i Mondiali arrivano", script,
            schemi_recenti=[brain.SCHEMA_DOMANDA],
        )
        assert not ok
        assert "una domanda" in motivo

    def test_valida_script_lascia_passare_una_forma_diversa(self):
        script = ("Dietro una parete che sembra decorazione c'e' altro. "
                  + TestAperturaRipetutaDalVivo._CODA)
        ok, motivo = brain.valida_script(
            "Portal: la stanza che non apre nessuno", script,
            schemi_recenti=[brain.SCHEMA_DOMANDA],
        )
        assert ok, motivo

    def test_la_finestra_degli_schemi_e_piu_corta(self):
        # Le forme riconoscibili sono poche: vietarne troppe in fila
        # vorrebbe dire scartare script buoni.
        assert 0 < brain.MEMORIA_SCHEMI < brain.MEMORIA_RIPETIZIONI

    def test_il_prompt_chiede_di_cambiare_forma(self):
        prompt = brain._costruisci_system_prompt(
            "TIER_LIST_LAMPO", [], [], [],
            schemi_recenti=[brain.SCHEMA_DOMANDA],
        )
        assert "FORMA DELL'ATTACCO" in prompt
        assert brain.SCHEMA_DOMANDA in prompt

    def test_senza_storico_il_prompt_non_dice_niente(self):
        prompt = brain._costruisci_system_prompt("TIER_LIST_LAMPO", [], [], [])
        assert "FORMA DELL'ATTACCO" not in prompt

    def test_lo_script_che_riapre_con_una_domanda_viene_rifatto(self, monkeypatch):
        import json as _json

        ripetuto = ("Pensavi che il segreto fosse finito? "
                    + TestAperturaRipetutaDalVivo._CODA)
        nuovo = ("Dietro una parete che sembra decorazione c'e' altro. "
                 + TestAperturaRipetutaDalVivo._CODA)

        def risposta(script):
            return _json.dumps({
                "titolo": "Portal: la stanza che non apre nessuno",
                "script": script, "gioco": "Portal",
                "query_video": "portal gameplay",
                "descrizione": "Un segreto.", "indice_notizia": -1,
            })

        # Le prime tre parole sono diverse da quelle in cronologia: se lo
        # scarto avviene, avviene per la forma e non per le parole.
        cronologia = [{
            "titolo": "Starfield: il prezzo che non ti aspetti",
            "estratto_script": "Scommetti che non indovini il prezzo? Starfield cambia tutto.",
            "stile": "TIER_LIST_LAMPO", "gioco": "Starfield",
            "fonte": "", "video_id": "hBMDcRhugbA",
        }]

        prompt_visti = []
        finto = TestRigenerazioneInformata()._finto_client(
            [risposta(ripetuto), risposta(nuovo)], prompt_visti
        )
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: cronologia)
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 2, "il primo script doveva essere scartato"
        assert "apre con una domanda" in prompt_visti[1]
        assert risultato["script"] == nuovo


class TestGiocoPuntato:
    """'S.T.A.L.K.E.R. 2' nel titolo veniva letto come assente.

    Il 20 settembre 2026 l'uscita delle 18:00 e' saltata per questo: tre
    tentativi su quattro scartati con "il titolo non nomina
    'S.T.A.L.K.E.R. 2'" mentre il titolo lo scriveva per esteso. Nessuna
    parola del nome arriva a tre lettere e la sigla non si trova, perche' i
    punti stanno in mezzo.
    """

    def test_il_nome_puntato_per_esteso_conta(self):
        assert brain._gioco_nel_titolo(
            "S.T.A.L.K.E.R. 2: il bug che rompe il finale", "S.T.A.L.K.E.R. 2")

    def test_anche_scritto_senza_punti(self):
        assert brain._gioco_nel_titolo(
            "Stalker 2: il bug che rompe il finale", "S.T.A.L.K.E.R. 2")

    def test_il_trattino_non_e_un_ostacolo(self):
        assert brain._gioco_nel_titolo(
            "Counter Strike 2: la skin da mille euro", "Counter-Strike 2")

    def test_un_gioco_diverso_resta_fuori(self):
        # La riparazione non deve far passare tutto.
        assert not brain._gioco_nel_titolo(
            "Fortnite: la skin nuova di oggi", "Elden Ring")

    def test_valida_titolo_accetta_il_nome_puntato(self):
        ok, motivo = brain.valida_titolo(
            "S.T.A.L.K.E.R. 2: il bug che rompe il finale", "S.T.A.L.K.E.R. 2")
        assert ok, motivo


class TestUltimaSpiaggia:
    """All'ultimo tentativo le regole anti-ripetizione si spengono.

    Dicono che un video somiglia a quello di ieri, non che e' sbagliato: un
    video che apre come quello di ieri vale comunque piu' di un buco nella
    pubblicazione.
    """

    _SCRIPT = ("Pensavi che il segreto fosse finito? "
               + TestAperturaRipetutaDalVivo._CODA)

    def _risposta(self):
        import json as _json
        return _json.dumps({
            "titolo": "Portal: la stanza che non apre nessuno",
            "script": self._SCRIPT, "gioco": "Portal",
            "query_video": "portal gameplay",
            "descrizione": "Un segreto.", "indice_notizia": -1,
        })

    def _cronologia(self):
        return [{
            "titolo": "Starfield: il prezzo che non ti aspetti",
            "estratto_script": "Scommetti che non indovini il prezzo? Starfield cambia tutto.",
            "stile": "TIER_LIST_LAMPO", "gioco": "Starfield",
            "fonte": "", "video_id": "hBMDcRhugbA",
        }]

    def test_dopo_uno_scarto_per_la_forma_lo_script_passa(self, monkeypatch):
        prompt_visti = []
        finto = TestRigenerazioneInformata()._finto_client(
            [self._risposta()] * 6, prompt_visti
        )
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", self._cronologia)
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        # Scartato una volta per la forma dell'apertura, accettato al
        # secondo invece di bruciare tentativi e far saltare il video (29
        # settembre 2026, uscita delle 20:00; 3 ottobre, 20:00 e 21:00).
        assert len(prompt_visti) == brain.SCARTI_SCHEMA_MAX + 1
        assert risultato["script"] == self._SCRIPT

    def test_al_primo_tentativo_la_regola_vale(self, monkeypatch):
        # Con un solo modello i tentativi sono tre: il primo scarta e il
        # secondo sa perche'.
        prompt_visti = []
        finto = TestRigenerazioneInformata()._finto_client(
            [self._risposta()] * 3, prompt_visti
        )
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain.config, "GROQ_MODELLI", ["openai/gpt-oss-120b"])
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", self._cronologia)
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        brain.genera_script_samaritan()

        assert len(prompt_visti) == 2
        assert "apre con una domanda" in prompt_visti[1]


class TestTitoloAccorciato:
    """Un titolo troppo lungo si accorcia invece di costare un tentativo: il
    3 ottobre 2026 l'uscita delle 21:00 e' saltata con l'ultimo tentativo
    scartato per un titolo di 73 caratteri."""

    def test_taglia_la_coda_e_tiene_l_emoji(self):
        titolo = ("GTA 6: $400 Collector's Box vs. Creator Bundle and what "
                  "fans think of the 🤔")
        corto = brain._accorcia_titolo(titolo)
        assert corto == "GTA 6: $400 Collector's Box vs. Creator Bundle 🤔"
        assert len(corto) <= brain.MAX_CARATTERI_TITOLO

    def test_non_lascia_parole_deboli_in_fondo(self):
        corto = brain._accorcia_titolo(
            "GTA 6: Lucia e Jason, le nuove immagini svelano molto di più sulla storia")
        assert len(corto) <= brain.MAX_CARATTERI_TITOLO
        ultima = corto.split()[-1].lower()
        assert ultima not in brain._PAROLE_DEBOLI | brain._PAROLE_DEBOLI_EN

    def test_un_titolo_giusto_non_si_tocca(self):
        titolo = "Gears of War: E-Day: Early Access drops Metallica surprise 🎸"
        assert brain._accorcia_titolo(titolo) == titolo

    def test_senza_parole_da_tenere_resta_com_era(self):
        titolo = "Supercalifragilistichespiralidosoelunghissimissimaparolaunica1234 🎮"
        assert brain._accorcia_titolo(titolo) == titolo

    def test_il_titolo_lungo_passa_al_primo_tentativo(self, monkeypatch):
        import json as _json
        risposta = _json.dumps({
            "titolo": "Elden Ring: il boss dietro la cascata che quasi nessun "
                      "giocatore ha mai battuto",
            "script": TestRigenerazioneInformata._SCRIPT,
            "gioco": "Elden Ring", "query_video": "elden ring gameplay",
            "descrizione": "Un segreto.", "indice_notizia": -1,
        })
        prompt_visti = []
        monkeypatch.setattr(brain, "client", TestRigenerazioneInformata()
                            ._finto_client([risposta], prompt_visti))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 1
        assert len(risultato["titolo"]) <= brain.MAX_CARATTERI_TITOLO
        assert risultato["titolo"].startswith("Elden Ring: il boss dietro la cascata")


class TestNotiziaPiuGrossa:
    """L'argomento veniva scelto a caso.

    `recupera_trend_gaming_online()` pescava da una sola ricerca e poi faceva
    `random.shuffle`. Ma sui video veri di questo canale l'argomento e' l'unica
    cosa che separa quelli andati bene (GTA 6, Sora in Fortnite) da quelli
    morti: era l'unica variabile che conta, lasciata al dado.
    """

    def _rss_per_ricerca(self, per_ricerca, viste):
        """Finto Google News che risponde diversamente a ogni ricerca."""
        def get(url, **kw):
            viste.append(url)
            titoli = []
            for marcatore, elenco in per_ricerca.items():
                if marcatore in url:
                    titoli = elenco
                    break
            voci = "".join(
                f"<item><title>{t} - Testata</title>"
                f"<link>https://example.com/{i}</link></item>"
                for i, t in enumerate(titoli)
            )
            corpo = f"<rss><channel>{voci}</channel></rss>".encode()

            class Risposta:
                content = corpo

                def raise_for_status(self):
                    return None

            return Risposta()
        return get

    def test_un_gioco_grosso_vale_piu_di_uno_sconosciuto(self):
        grossa = brain._punteggio_notizia("GTA 6 ha finalmente una data")
        piccola = brain._punteggio_notizia(
            "Un gestionale indie riceve una patch di stabilita'")
        assert grossa > piccola

    def test_le_parole_calde_contano_ma_non_all_infinito(self):
        # Un titolo acchiappaclic non deve superare una notizia vera.
        acchiappa = brain._punteggio_notizia(
            "esce uscita data annuncio gratis leak record remake trailer")
        assert acchiappa <= brain.MAX_PAROLE_CALDE * brain.PUNTI_PAROLA_CALDA

    def test_trovata_da_piu_ricerche_vale_di_piu(self):
        una = brain._punteggio_notizia("Minecraft cambia tutto", apparizioni=1)
        tre = brain._punteggio_notizia("Minecraft cambia tutto", apparizioni=3)
        assert tre == una + 2 * brain.PUNTI_RIPETIZIONE

    def test_una_parola_che_il_pubblico_cerca_vale_di_piu(self):
        """Il resto di questo punteggio e' un criterio scritto a mano; queste
        parole vengono da YouTube Analytics e sono un fatto misurato."""
        senza = brain._punteggio_notizia("Silksong riceve una patch")
        con = brain._punteggio_notizia("Silksong riceve una patch",
                                       cercate=frozenset({"silksong"}))
        assert con == senza + brain.PUNTI_PAROLA_CERCATA

    def test_le_parole_cercate_non_valgono_all_infinito(self):
        """Toccarne tre non vuol dire valere il triplo: vuol dire solo essere
        dello stesso mondo."""
        cercate = frozenset({"silksong", "patch", "riceve", "una"})
        con = brain._punteggio_notizia("Silksong riceve una patch",
                                       cercate=cercate)
        senza = brain._punteggio_notizia("Silksong riceve una patch")
        assert con - senza == brain.MAX_PAROLE_CERCATE * brain.PUNTI_PAROLA_CERCATA

    def test_il_confronto_e_su_parole_intere(self):
        """'gta' dentro 'gtavicecity' non e' qualcuno che cerca GTA."""
        assert brain._punteggio_notizia(
            "Il sito gtavicecity chiude", cercate=frozenset({"gta"})
        ) == brain._punteggio_notizia("Il sito gtavicecity chiude")

    def test_senza_dati_di_ricerca_il_punteggio_resta_quello_di_prima(self):
        """Token senza Analytics, o canale appena nato: il punteggio non deve
        peggiorare, solo restare com'era."""
        assert brain._punteggio_notizia("GTA 6 ha finalmente una data",
                                        cercate=frozenset()) == \
            brain._punteggio_notizia("GTA 6 ha finalmente una data")

    def test_le_ricerche_del_pubblico_arrivano_al_punteggio(self, monkeypatch):
        """Il collegamento vero: se analyst dice che il pubblico cerca una
        cosa, la notizia che la nomina deve salire in cima."""
        import analyst
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(analyst, "parole_cercate",
                            lambda: frozenset({"silksong"}))
        monkeypatch.setattr(brain.requests, "get", self._rss_per_ricerca({
            "videogiochi": ["Un gestionale indie riceve una patch",
                            "Silksong riceve una patch"],
        }, []))

        notizie = brain.recupera_trend_gaming_online()

        assert notizie[0]["titolo"] == "Silksong riceve una patch"

    def test_interroga_tutte_le_ricerche(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.requests, "get",
                            self._rss_per_ricerca({}, viste))

        brain.recupera_trend_gaming_online()

        assert len(viste) == len(brain._lingua()["ricerche"])

    def test_la_notizia_piu_grossa_arriva_per_prima(self, monkeypatch):
        grossa = "GTA 6 ha finalmente una data di uscita"
        piccola = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        # La piccola sta davanti in tutti i feed: se l'ordine non cambia,
        # vuol dire che il punteggio non viene applicato.
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": [piccola, grossa]}, []),
        )

        notizie = brain.recupera_trend_gaming_online()

        assert notizie[0]["titolo"] == grossa
        assert notizie[0]["punteggio"] > notizie[-1]["punteggio"]

    def test_il_gioco_precedente_esce_prima_del_taglio(self, monkeypatch):
        """29 settembre 2026: le otto notizie piu' grosse erano tutte su GTA 6
        dopo un video su GTA VI. Filtrando dopo il taglio non restava niente
        di diverso, e l'uscita delle 18:00 e' saltata quattro volte."""
        gta = [f"GTA 6, novita' numero {i} sul trailer" for i in range(10)]
        altra = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": gta + [altra]}, []),
        )

        notizie = brain.recupera_trend_gaming_online(
            max_notizie=8, gioco_da_evitare="Grand Theft Auto VI")

        assert [n["titolo"] for n in notizie] == [altra]

    def test_se_ci_sono_solo_notizie_sul_gioco_precedente_restano(self, monkeypatch):
        gta = [f"GTA 6, novita' numero {i} sul trailer" for i in range(3)]
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": gta}, []),
        )

        notizie = brain.recupera_trend_gaming_online(
            gioco_da_evitare="Grand Theft Auto VI")

        assert len(notizie) == 3

    def test_una_notizia_fresca_vale_piu_di_una_vecchia(self):
        titolo = "Minecraft annuncia un nuovo aggiornamento"
        fresca = brain._punteggio_notizia(titolo, ore=2)
        normale = brain._punteggio_notizia(titolo, ore=24)
        vecchia = brain._punteggio_notizia(titolo, ore=72)
        senza_data = brain._punteggio_notizia(titolo)
        assert fresca > normale > vecchia
        assert normale == senza_data

    def test_le_ore_arrivano_dalla_data_del_feed(self):
        from datetime import datetime, timezone
        adesso = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
        assert brain._ore_da("Sun, 05 Oct 2026 09:00:00 GMT", adesso) == 3
        assert brain._ore_da(None, adesso) is None
        assert brain._ore_da("non e' una data", adesso) is None

    def test_a_parita_di_gioco_passa_davanti_la_piu_fresca(self, monkeypatch):
        from email.utils import format_datetime
        from datetime import datetime, timedelta, timezone
        adesso = datetime.now(timezone.utc)
        vecchia = ("GTA 6, il trailer di due giorni fa", 60)
        fresca = ("GTA 6, la notizia di stamattina", 1)

        def get(url, **kw):
            voci = "".join(
                f"<item><title>{t} - Testata</title><link>https://x/{i}</link>"
                f"<pubDate>{format_datetime(adesso - timedelta(hours=h))}</pubDate></item>"
                for i, (t, h) in enumerate((vecchia, fresca)))

            class Risposta:
                content = f"<rss><channel>{voci}</channel></rss>".encode()

                def raise_for_status(self):
                    return None
            return Risposta()

        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.requests, "get", get)

        notizie = brain.recupera_trend_gaming_online()

        assert notizie[0]["titolo"] == fresca[0]

    def test_i_giochi_piccoli_escono_se_ci_sono_quelli_grossi(self, monkeypatch):
        """5 ottobre 2026, popponetv: solo giochi giganti. 10 video su 104
        facevano l'85% delle visualizzazioni, tutti su giochi enormi."""
        grosse = ["GTA 6 ha una nuova data di uscita",
                  "Fortnite annuncia la nuova stagione"]
        piccola = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": [piccola] + grosse}, []),
        )

        notizie = brain.recupera_trend_gaming_online()

        assert sorted(n["titolo"] for n in notizie) == sorted(grosse)

    def test_con_una_sola_notizia_grossa_restano_anche_le_piccole(self, monkeypatch):
        grossa = "GTA 6 ha una nuova data di uscita"
        piccola = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": [piccola, grossa]}, []),
        )

        notizie = brain.recupera_trend_gaming_online()

        assert len(notizie) == 2

    def test_il_gioco_precedente_lascia_spazio_agli_altri_grossi(self, monkeypatch):
        gta = [f"GTA 6, novita' numero {i} sul trailer" for i in range(5)]
        altre_grosse = ["Fortnite annuncia la nuova stagione",
                        "Minecraft riceve un aggiornamento enorme"]
        piccola = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca(
                {"videogiochi": gta + [piccola] + altre_grosse}, []),
        )

        notizie = brain.recupera_trend_gaming_online(
            gioco_da_evitare="Grand Theft Auto VI")

        assert sorted(n["titolo"] for n in notizie) == sorted(altre_grosse)

    def test_senza_solo_nomi_grossi_restano_tutte(self, monkeypatch):
        grosse = ["GTA 6 ha una nuova data di uscita",
                  "Fortnite annuncia la nuova stagione"]
        piccola = "Un gestionale indie riceve una patch di stabilita'"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.profilo.attivo(), "solo_nomi_grossi", False)
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"videogiochi": [piccola] + grosse}, []),
        )

        notizie = brain.recupera_trend_gaming_online()

        assert len(notizie) == 3

    def test_la_stessa_notizia_da_due_ricerche_non_si_sdoppia(self, monkeypatch):
        titolo = "Minecraft annuncia un nuovo aggiornamento"
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"": [titolo]}, []),
        )

        notizie = brain.recupera_trend_gaming_online()

        assert len(notizie) == 1
        # Trovata da tutte le ricerche: il conto delle apparizioni lo dice.
        assert notizie[0]["apparizioni"] == len(brain._lingua()["ricerche"])

    def test_una_cronologia_lunga_non_prosciuga_le_notizie(self, monkeypatch):
        """Il filtro sulle PAROLE guardava tutta la cronologia.

        Con cento titoli dentro quasi ogni parola gaming risultava "gia'
        usata" e il filtro si stringeva da solo fino a scartare tutto.
        """
        nuova = "Fortnite Capitolo Sette arriva davvero adesso"
        vecchi = [{"titolo": "Fortnite Capitolo Sei arriva oggi",
                   "estratto_script": "", "stile": "", "gioco": "",
                   "fonte": "", "video_id": None} for _ in range(5)]
        recenti = [{"titolo": f"Starfield: la stazione numero {n}",
                    "estratto_script": "", "stile": "", "gioco": "",
                    "fonte": "", "video_id": None} for n in range(20)]
        monkeypatch.setattr(brain, "carica_cronologia", lambda: vecchi + recenti)
        monkeypatch.setattr(
            brain.requests, "get",
            self._rss_per_ricerca({"": [nuova]}, []),
        )

        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online()]
        assert nuova in titoli

    def test_il_prompt_dice_che_sono_in_ordine(self):
        prompt = brain._costruisci_system_prompt(
            "VIRAL_HOOK_NEWS",
            [{"titolo": "GTA 6 ha una data", "fonte": "IGN", "link": ""}],
            [], [],
        )
        assert "IN ORDINE DI IMPORTANZA" in prompt


class TestLinguaInglese:
    """Il video delle 21:00 esce in inglese sullo stesso canale.

    Non e' una traduzione: e' un secondo pubblico. Quindi tutto quello che
    in `brain.py` era scritto in italiano (saluti vietati, seconda persona,
    ricerche, feed, parole calde) deve avere la sua versione inglese, e le
    regole anti-ripetizione devono valere dentro una lingua sola.
    """

    def _in_inglese(self, monkeypatch):
        monkeypatch.setattr(brain.config, "LINGUA", "en")

    def test_in_inglese_cambiano_le_regole(self, monkeypatch):
        self._in_inglese(monkeypatch)
        assert brain._lingua()["nome"] == "English"
        assert "en-US" in brain._lingua()["rss"]

    def test_una_lingua_sconosciuta_torna_all_italiano(self, monkeypatch):
        monkeypatch.setattr(brain.config, "LINGUA", "klingon")
        assert brain._lingua()["nome"] == "italiano"

    def test_il_saluto_inglese_viene_scartato(self, monkeypatch):
        self._in_inglese(monkeypatch)
        script = ("Hey guys, welcome back to the channel. "
                  + TestAperturaRipetutaDalVivo._CODA)
        ok, motivo = brain.valida_script("Portal: the room nobody opens", script)
        assert not ok
        assert "apertura debole vietata" in motivo

    def test_il_saluto_inglese_non_blocca_un_video_italiano(self):
        # "hello" dentro uno script italiano non e' un saluto in apertura.
        assert not any(
            "Dietro una parete che sembra decorazione c'e' altro.".lower()
            .startswith(v) for v in brain.LINGUE["it"]["aperture_vietate"])

    def test_you_e_la_seconda_persona_in_inglese(self, monkeypatch):
        self._in_inglese(monkeypatch)
        assert brain._schema_apertura(
            "You are playing it wrong. Here is why."
        ) == brain.SCHEMA_SECONDA_PERSONA

    def test_le_parole_calde_inglesi_contano(self, monkeypatch):
        self._in_inglese(monkeypatch)
        grossa = brain._punteggio_notizia("GTA 6 finally has a release date")
        piccola = brain._punteggio_notizia("A small indie sim gets a patch")
        assert grossa > piccola

    def test_il_prompt_chiede_di_scrivere_in_inglese(self, monkeypatch):
        self._in_inglese(monkeypatch)
        prompt = brain._costruisci_system_prompt("TIER_LIST_LAMPO", [], [], [])
        assert "LINGUA DELL'OUTPUT: English" in prompt

    def test_cerca_sul_feed_inglese(self, monkeypatch):
        self._in_inglese(monkeypatch)
        viste = []
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(
            brain.requests, "get",
            TestNotiziaPiuGrossa()._rss_per_ricerca({}, viste),
        )

        brain.recupera_trend_gaming_online()

        assert viste and all("hl=en-US" in u for u in viste)

    def test_la_lingua_finisce_in_cronologia(self, monkeypatch, tmp_path):
        self._in_inglese(monkeypatch)
        percorso = tmp_path / "cronologia.json"
        monkeypatch.setattr(brain.config, "FILE_CRONOLOGIA", str(percorso))
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])

        brain.salva_in_cronologia({
            "titolo": "Portal: the room nobody opens", "script": "A script.",
            "stile": "TIER_LIST_LAMPO", "gioco": "Portal",
            "query_video": "portal gameplay",
        })

        import json as _json
        salvato = _json.loads(percorso.read_text(encoding="utf-8"))
        assert salvato[-1]["lingua"] == "en"

    def test_la_notizia_usata_in_italiano_resta_libera_in_inglese(self, monkeypatch):
        """Il punto dell'esperimento.

        Se le due lingue condividessero la memoria delle notizie, al video
        inglese resterebbero solo gli argomenti scartati da quello italiano,
        cioe' i piu' deboli: la prova nascerebbe truccata contro l'inglese.
        """
        notizia = "GTA 6 finally has a release date"
        cronologia = [{
            "titolo": "GTA 6: la data e' ufficiale", "lingua": "it",
            "estratto_script": "", "stile": "", "gioco": "GTA 6",
            "fonte": f"{notizia} (IGN)", "video_id": "abc",
        }]
        monkeypatch.setattr(brain, "carica_cronologia", lambda: cronologia)
        monkeypatch.setattr(
            brain.requests, "get",
            TestNotiziaPiuGrossa()._rss_per_ricerca({"": [notizia]}, []),
        )

        monkeypatch.setattr(brain.config, "LINGUA", "it")
        assert notizia not in [n["titolo"] for n in brain.recupera_trend_gaming_online()]

        monkeypatch.setattr(brain.config, "LINGUA", "en")
        assert notizia in [n["titolo"] for n in brain.recupera_trend_gaming_online()]


class TestDidascaliaTikTok:
    """La didascalia da incollare a mano su TikTok.

    Il video finito e' gia' buono per TikTok (verticale, MP4, mezzo minuto):
    quello che cambia e' il testo che lo accompagna, perche' su TikTok il link
    al canale non e' cliccabile e le righe di credito non le legge nessuno.
    """

    def test_apre_con_il_titolo(self):
        didascalia = brain.costruisci_didascalia_tiktok(DATI_GTA)
        assert didascalia.startswith(DATI_GTA["titolo"])

    def test_non_porta_dentro_la_roba_di_youtube(self):
        didascalia = brain.costruisci_didascalia_tiktok(DATI_GTA)
        assert "youtube.com" not in didascalia
        assert "@davidedurazzi" not in didascalia
        assert DATI_GTA["fonte_url"] not in didascalia

    def test_finisce_con_gli_hashtag(self):
        didascalia = brain.costruisci_didascalia_tiktok(DATI_GTA)
        ultima = didascalia.splitlines()[-1]
        assert ultima.startswith("#grandtheftautovi")
        assert "#perte" in ultima

    def test_il_per_te_segue_la_lingua_del_video(self, monkeypatch):
        # Il video delle 21:00 esce in inglese: '#perte' li' non lo cerca
        # nessuno, e la lingua si legge a ogni chiamata come nel resto di brain.
        monkeypatch.setattr(brain.config, "LINGUA", "en")
        assert "#fyp" in brain.costruisci_didascalia_tiktok(DATI_GTA)
        monkeypatch.setattr(brain.config, "LINGUA", "it")
        assert "#perte" in brain.costruisci_didascalia_tiktok(DATI_GTA)

    def test_sta_sotto_il_limite_di_tiktok(self):
        # TikTok taglia la didascalia a 2200 caratteri.
        assert len(brain.costruisci_didascalia_tiktok(DATI_GTA)) <= 2200

    def test_regge_il_video_senza_gioco_e_senza_descrizione(self):
        didascalia = brain.costruisci_didascalia_tiktok(
            {"titolo": "Un titolo", "descrizione": "", "gioco": "", "stile": ""})
        assert didascalia.startswith("Un titolo")
        assert "#gamingita" in didascalia

    def test_la_descrizione_youtube_non_e_cambiata(self):
        # Il senso di questa modifica e' aggiungere TikTok senza toccare
        # niente di quello che finisce su YouTube.
        descrizione = brain.costruisci_descrizione(DATI_GTA)
        assert "@davidedurazzi" in descrizione
        assert DATI_GTA["fonte_url"] in descrizione
        assert "#perte" not in descrizione


class TestTemaChiestoAMano:
    """Il 26 settembre 2026 la prova lanciata a mano su "Cyberpunk 2077" e'
    uscita su GTA VI: il video precedente parlava gia' di Cyberpunk, la regola
    anti-ripetizione l'ha scartato e il tema era solo una riga in fondo al
    prompt. Con il comando da Telegram quello che lui chiede deve uscire."""

    def test_le_notizie_sul_tema_passano_davanti(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.requests, "get",
                            TestNotiziaPiuGrossa()._rss_per_ricerca({
                                "Cyberpunk": ["Cyberpunk 2077 riceve la patch 2.3"],
                                "videogiochi": ["GTA 6 ha finalmente una data"],
                            }, viste))

        notizie = brain.recupera_trend_gaming_online(tema="Cyberpunk 2077")

        assert notizie[0]["titolo"] == "Cyberpunk 2077 riceve la patch 2.3"
        assert "Cyberpunk" in viste[0]
        assert len(viste) == len(brain._lingua()["ricerche"]) + 1

    def test_senza_tema_le_ricerche_restano_quelle(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain.requests, "get",
                            TestNotiziaPiuGrossa()._rss_per_ricerca({}, viste))
        brain.recupera_trend_gaming_online(tema="")
        assert len(viste) == len(brain._lingua()["ricerche"])

    def _genera(self, monkeypatch, tema):
        import json as _json
        risposta = _json.dumps({
            "titolo": "Cyberpunk 2077: il segreto dietro la cascata",
            "script": TestRigenerazioneInformata._SCRIPT,
            "gioco": "Cyberpunk 2077", "query_video": "cyberpunk gameplay",
            "descrizione": "Un segreto.", "indice_notizia": -1,
        })
        prompt_visti = []
        monkeypatch.setattr(brain, "client", TestRigenerazioneInformata()._finto_client(
            [risposta] * 8, prompt_visti))
        chiesti = []
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda **k: chiesti.append(k.get("tema")) or [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [
            {"titolo": "Cyberpunk 2077: la patch", "gioco": "Cyberpunk 2077",
             "lingua": "it"}])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        try:
            risultato = brain.genera_script_samaritan(tema)
        except RuntimeError:
            # Senza tema lo stesso gioco viene scartato a ogni tentativo.
            risultato = None
        return risultato, prompt_visti, chiesti

    def test_il_gioco_del_video_prima_non_blocca_il_tema(self, monkeypatch):
        risultato, prompt_visti, chiesti = self._genera(monkeypatch, "Cyberpunk 2077")
        assert risultato["gioco"] == "Cyberpunk 2077"
        assert len(prompt_visti) == 1
        assert "obbligatorio: Cyberpunk 2077" in prompt_visti[0]
        assert chiesti == ["Cyberpunk 2077"]

    def test_senza_tema_la_regola_resta(self, monkeypatch):
        _, prompt_visti, _ = self._genera(monkeypatch, None)
        assert len(prompt_visti) > 1
        assert "come il video precedente" in prompt_visti[1]


class TestCambioAttacco:
    """Fra il 5 e il 6 ottobre 2026 tre lavorazioni su quattro hanno buttato
    un tentativo perche' lo script apriva con una domanda come i video
    recenti. Ora si riscrive solo la prima frase invece di tutto lo script."""

    BASE = TestUltimaSpiaggia()
    NUOVA = "Il segreto di Portal non e' mai finito davvero."

    def _genera(self, monkeypatch, cambio):
        prompt_visti, richieste = [], []
        finto = TestRigenerazioneInformata()._finto_client(
            [self.BASE._risposta()] * 6, prompt_visti)
        monkeypatch.setattr(brain, "client", finto)
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: [])
        monkeypatch.setattr(brain, "carica_cronologia", self.BASE._cronologia)
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        def finto_cambio(script, schema):
            richieste.append((script, schema))
            return cambio(script)

        monkeypatch.setattr(brain, "_cambia_attacco", finto_cambio)
        return brain.genera_script_samaritan(), prompt_visti, richieste

    def test_la_prima_frase_cambiata_evita_la_riscrittura(self, monkeypatch):
        coda = TestAperturaRipetutaDalVivo._CODA
        risultato, prompt_visti, richieste = self._genera(
            monkeypatch, lambda s: f"{self.NUOVA} {coda}")
        assert len(prompt_visti) == 1
        assert richieste[0][1] == brain.SCHEMA_DOMANDA
        assert risultato["script"] == f"{self.NUOVA} {coda}"

    def test_se_il_cambio_fallisce_si_riscrive_come_prima(self, monkeypatch):
        risultato, prompt_visti, _ = self._genera(monkeypatch, lambda s: "")
        assert len(prompt_visti) == brain.SCARTI_SCHEMA_MAX + 1
        assert risultato["script"] == self.BASE._SCRIPT


class TestCambiaAttaccoConGroq:
    from tests.test_brain import TestConfrontoCorrezione as _C
    ORIGINALE = staticmethod(brain._cambia_attacco)
    SCRIPT = "Pensavi fosse finita? Rockstar ha appena mostrato Vice City. Il resto arriva dopo."

    def test_tiene_il_resto_parola_per_parola(self, monkeypatch):
        viste = []
        monkeypatch.setattr(brain, "client", self._C._client(
            '{"script": "Rockstar non ha finito. E questa frase in piu\' sparisce."}',
            viste))
        assert self.ORIGINALE(self.SCRIPT, brain.SCHEMA_DOMANDA) == (
            "Rockstar non ha finito. Rockstar ha appena mostrato Vice City. "
            "Il resto arriva dopo.")
        assert "PRIMA FRASE: Pensavi fosse finita?" in viste[0]["messages"][1]["content"]

    def test_una_frase_che_e_ancora_una_domanda_non_vale(self, monkeypatch):
        monkeypatch.setattr(brain, "client", self._C._client(
            '{"script": "Ci credevi davvero?"}', []))
        assert self.ORIGINALE(self.SCRIPT, brain.SCHEMA_DOMANDA) == ""

    def test_un_errore_di_groq_non_cambia_niente(self, monkeypatch):
        monkeypatch.setattr(brain, "client", self._C._client(RuntimeError("500"), []))
        assert self.ORIGINALE(self.SCRIPT, brain.SCHEMA_DOMANDA) == ""
