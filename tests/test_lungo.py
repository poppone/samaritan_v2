# -*- coding: utf-8 -*-
"""Test sul video lungo.

popponetv, 22 settembre 2026: "preparati anche a fare video piu' lunghi
ampliamo samaritan anche 1 solo al giorno ma magari entrare nel dettaglio dei
giochi reperire spezzoni online di gameplay vero lasciando spazio all'audio
del gioco se necessario", e subito dopo "si prepara ma cerca i trailer
ufficiali anche lunghi, si non rischiamo che youtube ci blocchi quando faremo
domanda".

Le due cose che questi test difendono sono quelle: che il video lungo esca
davvero lungo e orizzontale, e che i capitoli siano timestamp veri. Un
capitolo sbagliato di venti secondi e' peggio di nessun capitolo.
"""
import json

import pytest

import config
import brain
import lungo


class TestMisureDelFormato:

    def test_lo_short_resta_verticale(self):
        config.applica_formato(False)
        assert (config.VIDEO_W, config.VIDEO_H) == (1080, 1920)

    def test_il_video_lungo_e_orizzontale(self):
        config.applica_formato(True)
        try:
            assert config.VIDEO_W > config.VIDEO_H
            assert (config.VIDEO_W, config.VIDEO_H) == (1920, 1080)
        finally:
            config.applica_formato(False)

    def test_il_video_lungo_prende_i_trailer_interi(self):
        """E' la richiesta esplicita di popponetv: trailer ufficiali anche
        lunghi. Con 45 secondi a testa le stesse inquadrature tornerebbero
        sei o sette volte dentro lo stesso video."""
        config.applica_formato(False)
        corto = config.SECONDI_TRAILER
        config.applica_formato(True)
        try:
            assert config.SECONDI_TRAILER >= 180
            assert config.SECONDI_TRAILER > corto
        finally:
            config.applica_formato(False)

    def test_il_video_lungo_ha_piu_materiale_e_piu_clip_di_casa(self):
        config.applica_formato(False)
        prima = (config.STEAM_MAX_TRAILER, config.STEAM_MAX_SCREENSHOT,
                 config.MAX_CLIP_MIE)
        config.applica_formato(True)
        try:
            dopo = (config.STEAM_MAX_TRAILER, config.STEAM_MAX_SCREENSHOT,
                    config.MAX_CLIP_MIE)
            assert all(d > p for d, p in zip(dopo, prima)), (prima, dopo)
        finally:
            config.applica_formato(False)

    def test_gli_stacchi_del_video_lungo_respirano(self):
        """Il ritmo dello Short su otto minuti darebbe piu' di duecento
        stacchi: stanca e basta."""
        config.applica_formato(True)
        try:
            assert config.STACCO_MIN >= 3.5
        finally:
            config.applica_formato(False)

    def test_una_variabile_d_ambiente_vince_sul_formato(self, monkeypatch):
        monkeypatch.setenv("VIDEO_W", "1280")
        config.applica_formato(True)
        try:
            assert config.VIDEO_W == 1280
        finally:
            monkeypatch.delenv("VIDEO_W")
            config.applica_formato(False)


class TestCapitoli:

    def test_i_capitoli_escono_nel_formato_che_youtube_riconosce(self):
        testo = lungo.formatta_capitoli([
            (0.0, "Cosa e' successo"),
            (95.4, "Il gioco vero"),
            (240.0, "Cosa ne penso"),
        ])
        assert testo.splitlines() == [
            "0:00 Cosa e' successo",
            "1:35 Il gioco vero",
            "4:00 Cosa ne penso",
        ]

    def test_oltre_l_ora_compaiono_le_ore(self):
        testo = lungo.formatta_capitoli([
            (0.0, "Uno"), (30.0, "Due"), (3725.0, "Tre"),
        ])
        assert testo.splitlines()[-1] == "1:02:05 Tre"

    def test_meno_di_tre_capitoli_non_sono_capitoli(self):
        """YouTube in quel caso li ignora tutti: meglio non scriverli."""
        assert lungo.formatta_capitoli([(0.0, "Uno"), (60.0, "Due")]) == ""

    def test_il_primo_capitolo_deve_stare_a_zero(self):
        assert lungo.formatta_capitoli([
            (12.0, "Uno"), (60.0, "Due"), (120.0, "Tre"),
        ]) == ""

    def test_due_capitoli_troppo_vicini_invalidano_tutto(self):
        assert lungo.formatta_capitoli([
            (0.0, "Uno"), (4.0, "Due"), (120.0, "Tre"),
        ]) == ""


class TestAudioASezioni:

    def _prepara(self, monkeypatch, durate):
        """Finge voce, ffprobe e concat: qui si controllano i conti, non ffmpeg."""
        prodotti = []

        def finta_voce(testo, destinazione=None):
            prodotti.append(destinazione)
            return destinazione

        durate_per_file = dict(zip(
            [f"sezione_{i:02d}.mp3" for i in range(len(durate))], durate))

        def finta_durata(percorso):
            import os
            nome = os.path.basename(percorso)
            if nome == "pausa.mp3":
                return lungo.PAUSA_FRA_SEZIONI
            return durate_per_file[nome]

        monkeypatch.setattr(lungo, "genera_voce_samaritan", finta_voce)
        monkeypatch.setattr(lungo, "_durata_audio", finta_durata)
        monkeypatch.setattr(lungo, "_silenzio",
                            lambda p, secondi=None: p)
        monkeypatch.setattr(lungo, "_unisci_audio",
                            lambda pezzi: "/tmp/audio.mp3")
        return prodotti

    def test_i_capitoli_seguono_le_durate_vere(self, monkeypatch):
        """I secondi sono misurati sui file, non stimati sulle parole."""
        self._prepara(monkeypatch, [90.0, 75.0, 120.0])
        sezioni = [{"titolo": f"Parte {i}", "testo": "..."} for i in (1, 2, 3)]

        audio, capitoli = lungo.produci_audio_e_capitoli(sezioni)

        pausa = lungo.PAUSA_FRA_SEZIONI
        assert audio == "/tmp/audio.mp3"
        assert capitoli[0] == (0.0, "Parte 1")
        assert capitoli[1] == (90.0 + pausa, "Parte 2")
        assert capitoli[2] == (90.0 + 75.0 + 2 * pausa, "Parte 3")

    def test_una_sezione_senza_voce_ferma_tutto(self, monkeypatch):
        """Meglio saltare il video che pubblicarne uno mutilato a meta'."""
        self._prepara(monkeypatch, [90.0, 75.0])
        monkeypatch.setattr(lungo, "genera_voce_samaritan",
                            lambda testo, destinazione=None: None)

        with pytest.raises(RuntimeError, match="Voce non generata"):
            lungo.produci_audio_e_capitoli(
                [{"titolo": "Parte 1", "testo": "..."}])


class TestPuliziaDelParlato:

    def test_toglie_titoli_e_asterischi(self):
        """Sono residui di markdown: la voce non li legge, ma finirebbero
        nei sottotitoli e in cronologia."""
        assert lungo._pulisci_sezione("## Il gioco\n**Ecco** il punto.") == \
            "Il gioco Ecco il punto."

    def test_toglie_l_etichetta_della_sezione(self):
        assert lungo._pulisci_sezione(
            "Sezione 2: il gioco e' uscito.") == "il gioco e' uscito."

    def test_la_coda_sono_le_ultime_parole(self):
        assert lungo._coda("uno due tre quattro", parole=2) == "tre quattro"


class TestScritturaDelVideoLungo:

    SCALETTA = {
        "titolo": "Hollow Knight Silksong: cosa non torna",
        "gioco": "Hollow Knight: Silksong",
        "query_video": "silksong",
        "descrizione": "Tre righe di descrizione.",
        "indice_notizia": 0,
        "sezioni": [
            {"titolo": "Da dove nasce", "contenuto": "La notizia."},
            {"titolo": "Come si gioca", "contenuto": "Le meccaniche."},
            {"titolo": "Cosa ne penso", "contenuto": "Il giudizio."},
        ],
    }

    def _prepara(self, monkeypatch, tmp_path, testo_sezione=None):
        testo_sezione = testo_sezione or " ".join(["parola"] * 120)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA",
                            str(tmp_path / "cronologia.json"))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda *a, **k: [
            {"titolo": "Silksong ha una data", "fonte": "Eurogamer",
             "link": "https://esempio/1"},
        ])

        chiamate = []

        def finto_chiedi(system, utente, schema=None, max_tokens=2000):
            chiamate.append(utente)
            if schema is not None:
                return json.dumps(self.SCALETTA)
            return testo_sezione

        monkeypatch.setattr(lungo, "_chiedi", finto_chiedi)
        return chiamate

    def test_scrive_una_sezione_per_capitolo(self, monkeypatch, tmp_path):
        chiamate = self._prepara(monkeypatch, tmp_path)

        dati = lungo.genera_video_lungo()

        assert len(dati["sezioni"]) == 3
        assert [s["titolo"] for s in dati["sezioni"]] == [
            "Da dove nasce", "Come si gioca", "Cosa ne penso"]
        # Una chiamata per la scaletta piu' una per sezione.
        assert len(chiamate) == 4

    def test_lo_script_completo_e_l_unione_delle_sezioni(self, monkeypatch, tmp_path):
        self._prepara(monkeypatch, tmp_path)
        dati = lungo.genera_video_lungo()
        for sezione in dati["sezioni"]:
            assert sezione["testo"] in dati["script"]

    def test_si_ancora_alla_notizia_scelta(self, monkeypatch, tmp_path):
        self._prepara(monkeypatch, tmp_path)
        dati = lungo.genera_video_lungo()
        assert "Silksong ha una data" in dati["fonte"]
        assert dati["fonte_url"] == "https://esempio/1"

    def test_ogni_sezione_sa_come_finiva_la_precedente(self, monkeypatch, tmp_path):
        """Senza, le sezioni si ripetono a vicenda: e' il difetto piu'
        evidente di un video lungo scritto a pezzi."""
        chiamate = self._prepara(monkeypatch, tmp_path,
                                 testo_sezione=" ".join(["fine"] * 100))
        lungo.genera_video_lungo()
        assert "La sezione precedente finiva" in chiamate[-1]
        assert "La sezione precedente finiva" not in chiamate[1]

    def test_una_scaletta_con_due_sezioni_viene_rifiutata(self, monkeypatch, tmp_path):
        magra = dict(self.SCALETTA, sezioni=self.SCALETTA["sezioni"][:2])
        monkeypatch.setattr(config, "FILE_CRONOLOGIA",
                            str(tmp_path / "cronologia.json"))
        monkeypatch.setattr(brain, "recupera_trend_gaming_online",
                            lambda *a, **k: [])
        monkeypatch.setattr(
            lungo, "_chiedi",
            lambda s, u, schema=None, max_tokens=2000:
                json.dumps(magra) if schema else "testo")

        with pytest.raises(RuntimeError, match="capitoli"):
            lungo.genera_video_lungo()

    def test_una_sezione_troppo_lunga_viene_tagliata(self, monkeypatch, tmp_path):
        self._prepara(monkeypatch, tmp_path,
                      testo_sezione=" ".join(["parola"] * 900))
        dati = lungo.genera_video_lungo()
        for sezione in dati["sezioni"]:
            assert len(sezione["testo"].split()) <= lungo.MAX_PAROLE_SEZIONE

    def test_il_video_finisce_in_cronologia_come_lungo(self, monkeypatch, tmp_path):
        self._prepara(monkeypatch, tmp_path)
        monkeypatch.setattr(config, "VIDEO_LUNGO", True)

        lungo.genera_video_lungo()

        voci = brain.carica_cronologia()
        assert voci[-1]["formato"] == "lungo"
        assert voci[-1]["stile"] == "VIDEO_LUNGO"


class TestConfezionamentoDelVideoLungo:

    DATI = {
        "titolo": "Silksong: cosa non torna",
        "descrizione": "Due righe.",
        "gioco": "Hollow Knight: Silksong",
        "stile": "VIDEO_LUNGO",
        "fonte": "", "fonte_url": "",
    }

    def test_i_capitoli_finiscono_in_descrizione(self):
        capitoli = "0:00 Uno\n1:30 Due\n3:00 Tre"
        testo = brain.costruisci_descrizione(self.DATI, None, capitoli)
        assert "Capitoli:" in testo
        assert "1:30 Due" in testo
        # In alto, prima delle righe di servizio: e' li' che si cercano.
        assert testo.index("Capitoli:") < testo.index("voce sintetica")

    def test_senza_capitoli_la_descrizione_non_cambia(self):
        testo = brain.costruisci_descrizione(self.DATI, None)
        assert "Capitoli" not in testo

    def test_il_video_lungo_non_si_tagga_come_short(self, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", True)
        tag = brain.costruisci_tag(self.DATI)
        assert not any("shorts" in t for t in tag), tag

    def test_lo_short_resta_taggato_come_short(self, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", False)
        tag = brain.costruisci_tag(dict(self.DATI, stile="VIRAL_HOOK_NEWS"))
        assert any("shorts" in t for t in tag), tag


class TestMemorieSeparatePerFormato:
    """Un video lungo non deve togliere argomenti agli Short, e viceversa."""

    VOCI = [
        {"titolo": "Short su Silksong", "lingua": "it", "formato": "short",
         "gioco": "Hollow Knight: Silksong"},
        {"titolo": "Lungo su Elden Ring", "lingua": "it", "formato": "lungo",
         "gioco": "ELDEN RING"},
    ]

    def test_lo_short_vede_solo_gli_short(self, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", False)
        visti = brain._stesso_formato(self.VOCI)
        assert [v["titolo"] for v in visti] == ["Short su Silksong"]

    def test_il_video_lungo_vede_solo_i_lunghi(self, monkeypatch):
        monkeypatch.setattr(config, "VIDEO_LUNGO", True)
        visti = brain._stesso_formato(self.VOCI)
        assert [v["titolo"] for v in visti] == ["Lungo su Elden Ring"]

    def test_le_voci_vecchie_contano_come_short(self, monkeypatch):
        """In cronologia ci sono cento video scritti prima che il formato
        esistesse: sono tutti Short."""
        monkeypatch.setattr(config, "VIDEO_LUNGO", False)
        vecchia = {"titolo": "Video di settembre", "lingua": "it"}
        assert brain._stesso_formato([vecchia]) == [vecchia]


class TestQuantoDeveDurare:

    def test_le_parole_per_sezione_seguono_la_durata_voluta(self, monkeypatch):
        monkeypatch.setattr(config, "MINUTI_VIDEO_LUNGO", 8.0)
        monkeypatch.setattr(config, "SEZIONI_VIDEO_LUNGO", 6)
        # 8 minuti a 150 parole al minuto sono 1.200 parole, sei sezioni da 200.
        assert lungo.parole_per_sezione() == 200

    def test_il_totale_sta_vicino_ai_minuti_chiesti(self, monkeypatch):
        monkeypatch.setattr(config, "MINUTI_VIDEO_LUNGO", 10.0)
        monkeypatch.setattr(config, "SEZIONI_VIDEO_LUNGO", 5)
        totale = lungo.parole_per_sezione() * 5
        minuti = totale / lungo.PAROLE_AL_MINUTO
        assert 9.5 <= minuti <= 10.5, minuti
