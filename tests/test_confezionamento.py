# -*- coding: utf-8 -*-
"""Test su come il video viene confezionato: titolo, descrizione, tag, miniatura.

Questa e' la parte che decide se un video pubblicato e' RAGGIUNGIBILE. Lo
script puo' essere ottimo, ma se il titolo viene troncato nel feed, non nomina
il gioco e la descrizione e' identica a quella di ieri, il video non lo trova
nessuno e il canale sembra automatico anche a chi ci capita per caso.
"""
import brain


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

    def test_porta_al_canale(self):
        assert "@PopponeTV" in brain.costruisci_descrizione(DATI_GTA)

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

        # Primo titolo: 70 caratteri, viene scartato. Secondo: valido.
        scartato = _json.dumps({
            "titolo": "Elden Ring: il boss segreto che quasi nessun giocatore "
                      "ha mai battuto davvero",
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
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 2
        assert "scartato" not in prompt_visti[0].lower()
        assert "troppo lungo" in prompt_visti[1], prompt_visti[1]
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
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda: [])
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
        assert "costruisci_descrizione(dati, materiale)" in main_py
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
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda: [])
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)

        risultato = brain.genera_script_samaritan()

        assert len(prompt_visti) == 1, "non doveva servire un secondo tentativo"
        assert risultato["script"].endswith("non perderti nulla.")
