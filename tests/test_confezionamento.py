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
