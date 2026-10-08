"""Test sul riconoscimento del gioco.

E' la logica piu' delicata del progetto: se sbaglia, lo Short parla di un
gioco e mostra il gameplay di un altro. Nessun test tocca la rete.
"""
import json
import os
import sys
import types

import config
import gameplay


class TestNumeroSequel:
    """Il numero di capitolo e' cio' che separa quasi tutti i sequel."""

    def test_numero_arabo(self):
        assert gameplay._numero_sequel("Portal 2") == 2

    def test_numero_romano(self):
        assert gameplay._numero_sequel("Grand Theft Auto V") == 5
        assert gameplay._numero_sequel("Grand Theft Auto IV") == 4

    def test_senza_numero(self):
        assert gameplay._numero_sequel("Portal") is None
        assert gameplay._numero_sequel("Cyberpunk") is None


class TestSomiglianza:
    """La ricerca Steam restituisce SEMPRE qualcosa: il punteggio decide
    se quel qualcosa e' davvero il gioco di cui parla lo Short."""

    def test_nome_identico(self):
        assert gameplay._somiglianza("Cyberpunk 2077", "Cyberpunk 2077") == 1.0

    def test_capitoli_diversi_sempre_rifiutati(self):
        # Testualmente si somigliano al 97%, ma sono due giochi diversi.
        assert gameplay._somiglianza(
            "Grand Theft Auto V",
            "Grand Theft Auto IV: The Complete Edition",
        ) == 0.0

    def test_portal_non_e_portal_2(self):
        assert gameplay._somiglianza("Portal", "Portal 2") == 0.0
        assert gameplay._somiglianza("Portal 2", "Portal") == 0.0

    def test_sottotitolo_ignorato(self):
        # 'Witcher 3' DEVE matchare 'The Witcher 3: Wild Hunt'
        punteggio = gameplay._somiglianza(
            "The Witcher 3", "The Witcher 3: Wild Hunt"
        )
        assert punteggio >= gameplay.SOGLIA_CORRISPONDENZA

    def test_minecraft_non_e_minecraft_dungeons(self):
        # Minecraft su Steam non esiste: Steam risponde 'Minecraft Dungeons'.
        # Meglio lo stock generico che il gioco sbagliato.
        punteggio = gameplay._somiglianza("Minecraft", "Minecraft Dungeons")
        assert punteggio < gameplay.SOGLIA_CORRISPONDENZA


    def test_una_parola_in_piu_e_un_altro_gioco(self):
        # 26 settembre 2026: lo Short su The Last of Us e' uscito col
        # gameplay di questo gioco, match 0.85.
        assert gameplay._somiglianza("The Last of Us", "The Last Kich Of Us") == 0.0
        assert gameplay._somiglianza("Elden Ring", "ELDEN RING NIGHTREIGN") == 0.0

    def test_le_edizioni_sono_lo_stesso_gioco(self):
        for cercato, ufficiale in [
            ("Grand Theft Auto V", "Grand Theft Auto V Enhanced"),
            ("Grand Theft Auto V", "Grand Theft Auto V Legacy"),
            ("The Last of Us Part I", "The Last of Us™ Part I"),
            ("The Last of Us Part II Remastered", "The Last of Us™ Part II Remastered"),
            ("Call of Duty Black Ops 6", "Call of Duty®: Black Ops 6"),
            ("Counter-Strike 2", "Counter-Strike 2"),
            ("Hollow Knight Silksong", "Hollow Knight: Silksong"),
        ]:
            assert gameplay._somiglianza(cercato, ufficiale) >= gameplay.SOGLIA_CORRISPONDENZA, ufficiale

    def test_gli_accenti_non_fanno_due_giochi_diversi(self):
        # Il modello scrive 'Pokemon' e 'Ghost of Yotei', i negozi li scrivono
        # con l'accento: senza appianarli il video usciva con clip generiche.
        for cercato, ufficiale in [
            ("Pokemon Legends Z-A", "Pokémon Legends: Z-A"),
            ("Ghost of Yotei", "Ghost of Yōtei"),
        ]:
            assert gameplay._somiglianza(cercato, ufficiale) >= \
                gameplay.SOGLIA_CORRISPONDENZA, ufficiale

    def test_il_simbolo_del_marchio_non_diventa_le_lettere_tm(self):
        assert gameplay._normalizza("The Last of Us™ Part I") == \
            "the last of us part i"

    def test_the_last_of_us_cerca_la_parte_uno(self):
        nome = gameplay.ALIAS_GIOCHI[gameplay._normalizza("The Last of Us")]
        assert gameplay._somiglianza(nome, "The Last of Us™ Part I") >= gameplay.SOGLIA_CORRISPONDENZA


class TestVariantiNome:
    def test_toglie_il_sottotitolo(self):
        varianti = gameplay._varianti_nome("Elden Ring: Shadow of the Erdtree")
        assert "Elden Ring" in varianti

    def test_tiene_sempre_il_nome_originale(self):
        assert "Cyberpunk 2077" in gameplay._varianti_nome("Cyberpunk 2077")


class TestAlias:
    def test_le_abbreviazioni_note_sono_normalizzate(self):
        # Rete di sicurezza per quando il modello scrive 'gta 5' invece del
        # titolo ufficiale.
        assert gameplay.ALIAS_GIOCHI[gameplay._normalizza("GTA 5")] == \
            "Grand Theft Auto V"
        assert gameplay.ALIAS_GIOCHI[gameplay._normalizza("CS:GO")] == \
            "Counter-Strike 2"


# ===========================================================================
# MATERIALE CHE NON SI RIPETE
# ===========================================================================
class TestRotazione:
    def test_lista_vuota(self):
        assert gameplay.ruota([], 3) == []

    def test_salto_zero_non_cambia_niente(self):
        assert gameplay.ruota([1, 2, 3], 0) == [1, 2, 3]

    def test_si_comincia_da_un_altro_punto(self):
        assert gameplay.ruota([1, 2, 3], 1) == [2, 3, 1]

    def test_un_salto_piu_lungo_della_lista_gira_intorno(self):
        assert gameplay.ruota([1, 2, 3], 7) == [2, 3, 1]

    def test_gli_elementi_ci_sono_tutti_comunque(self):
        # Ruotare non deve mai perdere materiale: il montaggio conta sul
        # numero di sorgenti che gli arriva.
        for salto in range(8):
            assert sorted(gameplay.ruota([1, 2, 3, 4], salto)) == [1, 2, 3, 4]


class TestQuantiVideoSuQuestoGioco:
    def _cronologia(self, monkeypatch, tmp_path, contenuto):
        percorso = tmp_path / "cronologia_trend.json"
        percorso.write_text(json.dumps(contenuto), encoding="utf-8")
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(percorso))

    def test_senza_gioco_non_si_conta_niente(self):
        assert gameplay.video_gia_fatti("") == 0

    def test_file_mancante(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        assert gameplay.video_gia_fatti("Hades II") == 0

    def test_conta_solo_lo_stesso_gioco(self, monkeypatch, tmp_path):
        self._cronologia(monkeypatch, tmp_path, [
            {"gioco": "Hades II"},
            {"gioco": "Elden Ring"},
            {"gioco": "Hades II"},
        ])
        assert gameplay.video_gia_fatti("Hades II") == 2

    def test_i_capitoli_diversi_non_si_sommano(self, monkeypatch, tmp_path):
        # Stessa regola che vale per la ricerca Steam: Hades e Hades II sono
        # due giochi, e il materiale del primo non e' gia' stato usato.
        self._cronologia(monkeypatch, tmp_path, [{"gioco": "Hades"}])
        assert gameplay.video_gia_fatti("Hades II") == 0

    def test_le_abbreviazioni_note_contano_come_il_nome_intero(self, monkeypatch, tmp_path):
        self._cronologia(monkeypatch, tmp_path, [{"gioco": "GTA V"}])
        assert gameplay.video_gia_fatti("Grand Theft Auto V") == 1

    def test_i_record_senza_gioco_non_contano(self, monkeypatch, tmp_path):
        self._cronologia(monkeypatch, tmp_path, [
            {"gioco": ""}, {"titolo": "senza campo"}, "vecchio formato a stringa",
        ])
        assert gameplay.video_gia_fatti("Hades II") == 0

    def test_un_file_rotto_non_ferma_il_video(self, monkeypatch, tmp_path):
        percorso = tmp_path / "cronologia_trend.json"
        percorso.write_text("{ non e' json", encoding="utf-8")
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(percorso))
        assert gameplay.video_gia_fatti("Hades II") == 0


FILMATI = {"movies": [
    {"id": 1, "highlight": True, "name": "Trailer A", "mp4": {"max": "http://a"}},
    {"id": 2, "highlight": True, "name": "Trailer B", "mp4": {"max": "http://b"}},
    {"id": 3, "highlight": False, "name": "Teaser C", "mp4": {"max": "http://c"}},
]}


class TestTrailerDiversiAOgniGiro:
    def _registra(self, monkeypatch):
        """Sostituisce ffmpeg: segna cosa sarebbe stato scaricato e da che secondo."""
        chiamate = []

        def finto(url, destinazione, salta=gameplay.SALTA_INTRO_SEC):
            chiamate.append((destinazione, salta))
            return True

        monkeypatch.setattr(gameplay, "_estrai_mp4", finto)
        monkeypatch.setattr(config, "DIR_TEMP", "/tmp")
        return chiamate

    def test_il_primo_video_prende_i_trailer_principali(self, monkeypatch):
        chiamate = self._registra(monkeypatch)
        gameplay.scarica_trailer_steam(42, FILMATI, quanti=2, salto=0)
        assert [c[0] for c in chiamate] == ["/tmp/steam_42_1.mp4", "/tmp/steam_42_2.mp4"]

    def test_il_secondo_video_sullo_stesso_gioco_ne_prende_altri(self, monkeypatch):
        chiamate = self._registra(monkeypatch)
        gameplay.scarica_trailer_steam(42, FILMATI, quanti=2, salto=1)
        assert chiamate[0][0] == "/tmp/steam_42_2.mp4"

    def test_i_trailer_principali_restano_prima_degli_altri(self, monkeypatch):
        # La rotazione non deve far scivolare un teaser davanti ai trailer
        # scelti dall'editore: cambia il materiale, non la qualita'.
        chiamate = self._registra(monkeypatch)
        gameplay.scarica_trailer_steam(42, FILMATI, quanti=3, salto=1)
        assert [c[0] for c in chiamate][:2] == ["/tmp/steam_42_2.mp4", "/tmp/steam_42_1.mp4"]
        assert chiamate[2][0] == "/tmp/steam_42_3.mp4"

    def test_anche_il_punto_di_taglio_si_sposta(self, monkeypatch):
        chiamate = self._registra(monkeypatch)
        gameplay.scarica_trailer_steam(42, FILMATI, quanti=1, salto=0)
        primo = chiamate[0][1]
        chiamate.clear()
        gameplay.scarica_trailer_steam(42, FILMATI, quanti=1, salto=1)
        assert chiamate[0][1] != primo

    def test_se_il_trailer_e_troppo_corto_si_ripiega_sull_inizio(self, monkeypatch):
        """Un trailer di trenta secondi non ha un secondo 70: senza ripiego il
        video resterebbe senza quella sorgente."""
        tentati = []

        def finto(url, destinazione, salta=gameplay.SALTA_INTRO_SEC):
            tentati.append(salta)
            return salta == 0

        monkeypatch.setattr(gameplay, "_estrai_mp4", finto)
        monkeypatch.setattr(config, "DIR_TEMP", "/tmp")
        percorsi = gameplay.scarica_trailer_steam(42, FILMATI, quanti=1, salto=3)
        assert percorsi == ["/tmp/steam_42_2.mp4"]   # salto 3 su due principali
        assert tentati[-1] == 0 and len(tentati) == 3

    def test_senza_filmati_non_esplode(self, monkeypatch):
        self._registra(monkeypatch)
        assert gameplay.scarica_trailer_steam(42, {"movies": []}, salto=2) == []


class TestScreenshotDiversiAOgniGiro:
    def _finti_screenshot(self, quanti):
        return {"screenshots": [{"id": i, "path_full": f"http://s/{i}"}
                                for i in range(quanti)]}

    def _registra(self, monkeypatch):
        scaricati = []

        class Risposta:
            content = b"x" * 30_000

        def finta_get(url, timeout=None, headers=None):
            scaricati.append(url)
            return Risposta()

        monkeypatch.setattr(gameplay.requests, "get", finta_get)
        monkeypatch.setattr(config, "DIR_TEMP", "/tmp")
        return scaricati

    def test_il_secondo_video_prende_il_gruppo_dopo(self, monkeypatch):
        scaricati = self._registra(monkeypatch)
        gameplay.scarica_screenshot_steam(42, self._finti_screenshot(12),
                                          quanti=4, salto=1)
        assert scaricati[0] == "http://s/4"

    def test_con_pochi_screenshot_si_gira_intorno_invece_di_restare_a_secco(self, monkeypatch):
        scaricati = self._registra(monkeypatch)
        percorsi = gameplay.scarica_screenshot_steam(42, self._finti_screenshot(5),
                                                     quanti=4, salto=1)
        assert len(percorsi) == 4
        assert len(set(scaricati)) == len(scaricati)


class TestQualeFfmpeg:
    """Quale binario si usa non e' un dettaglio: quello di imageio-ffmpeg va in
    segmentation fault sugli stream HLS di Steam, e con lui i video escono di
    soli screenshot fermi."""

    def test_si_preferisce_quello_di_sistema(self, monkeypatch):
        monkeypatch.setattr(gameplay.shutil, "which",
                            lambda nome: "/usr/bin/ffmpeg" if nome == "ffmpeg" else None)
        assert gameplay._ffmpeg() == "/usr/bin/ffmpeg"

    def test_senza_quello_di_sistema_si_ripiega_su_imageio(self, monkeypatch):
        monkeypatch.setattr(gameplay.shutil, "which", lambda nome: None)
        import types
        finto = types.ModuleType("imageio_ffmpeg")
        finto.get_ffmpeg_exe = lambda: "/altrove/ffmpeg"
        monkeypatch.setitem(__import__("sys").modules, "imageio_ffmpeg", finto)
        assert gameplay._ffmpeg() == "/altrove/ffmpeg"

    def test_senza_niente_si_prova_comunque_il_nome_nudo(self, monkeypatch):
        monkeypatch.setattr(gameplay.shutil, "which", lambda nome: None)
        import sys as _sys
        monkeypatch.setitem(_sys.modules, "imageio_ffmpeg", None)
        assert gameplay._ffmpeg() == "ffmpeg"


class TestCategoriaDelleClipMie:
    """Le clip girate in casa si montano solo dove sono a tema: un volante
    dentro una notizia su GTA 6 toglie piu' di quanto aggiunga."""

    def test_il_genere_steam_decide(self):
        dati = {"genres": [{"description": "Racing"}, {"description": "Sports"}]}
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", dati) == "guida"

    def test_il_genere_steam_vince_anche_scritto_in_minuscolo(self):
        dati = {"genres": [{"description": "racing"}]}
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", dati) == "guida"

    def test_marvel_rivals_dichiara_otto_generi_e_non_e_un_gioco_di_guida(self):
        # Il 7 ottobre 2026 lo Short su Marvel Rivals e' uscito con dentro le
        # clip del volante: Steam gli fa dichiarare anche "Racing".
        dati = {"genres": [{"description": d} for d in (
            "Action", "Adventure", "Casual", "Massively Multiplayer",
            "Racing", "RPG", "Strategy", "Free To Play")]}
        assert gameplay.categoria_clip_mie("Marvel Rivals", dati) is None

    def test_i_giochi_di_guida_veri_restano_riconosciuti(self):
        # Liste vere, lette da Steam il 8 ottobre 2026.
        forza = {"genres": [{"description": d} for d in (
            "Action", "Adventure", "Racing", "Simulation", "Sports")]}
        f1 = {"genres": [{"description": d} for d in ("Racing", "Sports")]}
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", forza) == "guida"
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", f1) == "guida"

    def test_una_lista_lunga_vale_se_un_genere_conferma(self):
        # Sei generi, ma Sports e Simulation dicono che si guida davvero.
        crew = {"genres": [{"description": d} for d in (
            "Action", "Adventure", "Massively Multiplayer", "Racing",
            "Simulation", "Sports")]}
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", crew) == "guida"

    def test_senza_generi_non_si_decide_dal_nulla(self):
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque", {}) is None
        assert gameplay.categoria_clip_mie("Un Gioco Qualunque",
                                           {"genres": []}) is None

    def test_senza_steam_decide_il_nome(self):
        # I giochi appena annunciati su Steam spesso non ci sono ancora, ed e'
        # proprio di quelli che parlano le notizie.
        assert gameplay.categoria_clip_mie("Assetto Corsa Evolution") == "guida"
        assert gameplay.categoria_clip_mie("Forza Horizon 6") == "guida"
        assert gameplay.categoria_clip_mie("EA SPORTS WRC") == "guida"

    def test_la_punteggiatura_non_ferma_il_riconoscimento(self):
        assert gameplay.categoria_clip_mie("F1® 26") == "guida"

    def test_un_gioco_puo_essere_una_categoria_da_solo(self):
        assert gameplay.categoria_clip_mie("Fortnite") == "fortnite"
        assert gameplay.categoria_clip_mie("Fortnite x Kingdom Hearts") == "fortnite"

    def test_un_gioco_qualunque_non_ha_categoria(self):
        assert gameplay.categoria_clip_mie("Grand Theft Auto VI") is None
        assert gameplay.categoria_clip_mie("Hades II") is None
        assert gameplay.categoria_clip_mie("") is None
        assert gameplay.categoria_clip_mie(None) is None

    def test_un_genere_diverso_non_apre_la_cartella(self):
        dati = {"genres": [{"description": "Action"}]}
        assert gameplay.categoria_clip_mie("Doom", dati) is None


class TestQualiClipMie:
    def _cartella(self, monkeypatch, tmp_path, nomi):
        radice = tmp_path / "clip_mie"
        (radice / "guida").mkdir(parents=True)
        for nome in nomi:
            (radice / "guida" / nome).write_bytes(b"x")
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(radice))
        return radice

    def test_senza_categoria_non_si_monta_niente(self, monkeypatch, tmp_path):
        self._cartella(monkeypatch, tmp_path, ["a.mp4"])
        assert gameplay.clip_mie(None) == []

    def test_cartella_mancante_non_ferma_il_video(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(tmp_path / "niente"))
        assert gameplay.clip_mie("guida") == []

    def test_ne_prende_al_massimo_quante_ne_dice_il_config(self, monkeypatch, tmp_path):
        self._cartella(monkeypatch, tmp_path, ["a.mp4", "b.mp4", "c.mp4"])
        monkeypatch.setattr(config, "MAX_CLIP_MIE", 2)
        assert len(gameplay.clip_mie("guida")) == 2

    def test_due_video_di_fila_non_aprono_con_la_stessa_clip(self, monkeypatch, tmp_path):
        self._cartella(monkeypatch, tmp_path, ["a.mp4", "b.mp4", "c.mp4"])
        monkeypatch.setattr(config, "MAX_CLIP_MIE", 1)
        primo = gameplay.clip_mie("guida", salto=0)
        secondo = gameplay.clip_mie("guida", salto=1)
        assert primo != secondo

    def test_i_file_che_non_sono_video_restano_fuori(self, monkeypatch, tmp_path):
        self._cartella(monkeypatch, tmp_path, ["a.mp4", "note.txt", "b.MOV"])
        monkeypatch.setattr(config, "MAX_CLIP_MIE", 5)
        presi = [os.path.basename(p) for p in gameplay.clip_mie("guida")]
        assert presi == ["a.mp4", "b.MOV"]

    def test_zero_clip_richieste(self, monkeypatch, tmp_path):
        self._cartella(monkeypatch, tmp_path, ["a.mp4"])
        assert gameplay.clip_mie("guida", quante=0) == []


class TestLeClipMieNelMateriale:
    """Si aggiungono al materiale del gioco, non lo sostituiscono."""

    def _senza_steam(self, monkeypatch, tmp_path, nomi=("a.mp4", "b.mp4")):
        radice = tmp_path / "clip_mie"
        (radice / "guida").mkdir(parents=True)
        for nome in nomi:
            (radice / "guida" / nome).write_bytes(b"x")
        monkeypatch.setattr(config, "DIR_CLIP_MIE", str(radice))
        monkeypatch.setattr(config, "USA_STEAM", False)
        monkeypatch.setattr(config, "MAX_CLIP_MIE", 2)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        # Il ripiego su Pexels importa maker, che si porta dietro moviepy e
        # numpy: qui non serve nessuno dei due, serve solo che non scarichi.
        finto = types.ModuleType("maker")
        finto.scarica_clip_sfondo = lambda query, quante=None: []
        monkeypatch.setitem(sys.modules, "maker", finto)

    def test_un_gioco_di_guida_le_prende(self, monkeypatch, tmp_path):
        self._senza_steam(monkeypatch, tmp_path)
        sorgenti, _ = gameplay.procura_materiale("Assetto Corsa Evolution")
        assert sum(1 for s in sorgenti if s.get("mia")) == 2

    def test_un_gioco_qualunque_non_le_prende(self, monkeypatch, tmp_path):
        self._senza_steam(monkeypatch, tmp_path)
        sorgenti, _ = gameplay.procura_materiale("Grand Theft Auto VI")
        assert [s for s in sorgenti if s.get("mia")] == []

    def test_non_sono_materiale_ufficiale_di_quel_gioco(self, monkeypatch, tmp_path):
        # Il resoconto conta come 'ufficiali' le sorgenti col campo gioco: una
        # clip del volante non e' materiale di Assetto Corsa Evolution.
        self._senza_steam(monkeypatch, tmp_path)
        sorgenti, _ = gameplay.procura_materiale("Forza Horizon 6")
        assert all(s["gioco"] is None for s in sorgenti if s.get("mia"))


class TestDettagliDeiGiochiPerAdulti:
    """Il 26 settembre 2026 Cyberpunk 2077 ed Elden Ring non davano ne' trailer
    ne' screenshot: Steam risponde senza dati ai giochi vietati ai minori
    finche' non riceve la verifica dell'eta'. Il video ripiegava su Pexels."""

    class _Risposta:
        def __init__(self, dati):
            self._dati = dati

        def raise_for_status(self):
            pass

        def json(self):
            return self._dati

    def _steam(self, monkeypatch, risposte):
        chiamate = []

        def finto_get(url, params=None, cookies=None, timeout=None):
            chiamate.append(cookies)
            return self._Risposta(risposte[len(chiamate) - 1])

        monkeypatch.setattr(gameplay.requests, "get", finto_get)
        return chiamate

    def test_senza_verifica_riprova_con_l_eta(self, monkeypatch):
        pieno = {"1091500": {"success": True, "data": {
            "name": "Cyberpunk 2077", "movies": [{"id": 1}]}}}
        chiamate = self._steam(monkeypatch, [{"1091500": {"success": False}}, pieno])
        dati = gameplay.dettagli_gioco(1091500)
        assert dati["movies"] == [{"id": 1}]
        assert chiamate[0] is None
        assert chiamate[1]["birthtime"] == "0"

    def test_un_gioco_normale_basta_la_prima_domanda(self, monkeypatch):
        pieno = {"10": {"success": True, "data": {"screenshots": [{"id": 1}]}}}
        chiamate = self._steam(monkeypatch, [pieno])
        assert gameplay.dettagli_gioco(10)["screenshots"]
        assert len(chiamate) == 1

    def test_dati_senza_materiale_restano_come_ripiego(self, monkeypatch):
        vuoto = {"10": {"success": True, "data": {"name": "Solo testo"}}}
        self._steam(monkeypatch, [vuoto, vuoto, vuoto])
        assert gameplay.dettagli_gioco(10) == {"name": "Solo testo"}

    def test_steam_irraggiungibile_non_rompe_niente(self, monkeypatch):
        def rotto(*a, **k):
            raise ConnectionError("giu'")
        monkeypatch.setattr(gameplay.requests, "get", rotto)
        assert gameplay.dettagli_gioco(10) is None


class TestGtaViDalSitoRockstar:
    """GTA VI su Steam non c'e': fino al 27 settembre 2026 ogni video su GTA VI
    usciva con clip Pexels generiche. I trailer arrivano dalla pagina
    Downloads di Rockstar."""

    PAGINA = (
        '<a href="https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Trailer_1/GTAVI_Trailer_1.mp4">'
        '"https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Trailer_2/GTAVI_Trailer_2.mp4"'
        ' https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Trailer_1/GTAVI_Trailer_1.mp4'
        ' https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Official_Cover_Art_Landscape/GTAVI_Official_Cover_Art_Landscape.mp4'
    )

    class _Risposta:
        def __init__(self, testo, errore=None):
            self.text = testo
            self._errore = errore

        def raise_for_status(self):
            if self._errore:
                raise self._errore

    def test_riconosce_tutti_i_modi_di_scrivere_gta_vi(self):
        for nome in ("GTA 6", "GTA VI", "gta6", "Grand Theft Auto VI",
                     "Grand Theft Auto 6"):
            assert gameplay.gioco_con_pagina_ufficiale(nome) == "gta6", nome

    def test_gli_altri_gta_restano_a_steam(self):
        for nome in ("GTA V", "Grand Theft Auto V", "GTA San Andreas",
                     "Grand Theft Auto IV", "Cyberpunk 2077", "", None):
            assert gameplay.gioco_con_pagina_ufficiale(nome) is None, nome

    def test_legge_i_trailer_dalla_pagina_senza_la_copertina(self, monkeypatch):
        monkeypatch.setattr(gameplay.requests, "get",
                            lambda *a, **k: self._Risposta(self.PAGINA))
        elenco = gameplay.trailer_dalla_pagina_ufficiale("gta6")
        assert [u.rsplit("/", 1)[1] for u in elenco] == [
            "GTAVI_Trailer_1.mp4", "GTAVI_Trailer_2.mp4"]

    def test_se_la_pagina_non_risponde_usa_gli_indirizzi_noti(self, monkeypatch):
        def rotta(*a, **k):
            raise gameplay.requests.ConnectionError("giu'")
        monkeypatch.setattr(gameplay.requests, "get", rotta)
        assert gameplay.trailer_dalla_pagina_ufficiale("gta6") == \
            gameplay.PAGINE_UFFICIALI["gta6"]["riserva"]

    def test_il_video_su_gta_vi_monta_i_trailer_ufficiali(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "STEAM_MAX_TRAILER", 3)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay.requests, "get",
                            lambda *a, **k: self._Risposta(self.PAGINA))
        scaricati = []

        def finto(url, destinazione, salta=0, durata=None, a_1080=False):
            assert a_1080, "i trailer Rockstar sono 4K: vanno ridotti"
            scaricati.append(url)
            open(destinazione, "wb").close()
            return True
        monkeypatch.setattr(gameplay, "_estrai_mp4", finto)

        def steam_vietato(*a, **k):
            raise AssertionError("GTA VI non va cercato su Steam")
        monkeypatch.setattr(gameplay, "cerca_gioco_steam", steam_vietato)

        sorgenti, nome = gameplay.procura_materiale("GTA 6", minimo=2)
        assert nome == "Grand Theft Auto VI"
        assert len(scaricati) == 2
        assert all(s["gioco"] == "Grand Theft Auto VI" for s in sorgenti)
        assert all("akamaized.net/VI/downloads/videos/" in u for u in scaricati)


class TestIndirizzoDelNome:
    """PlayStation ed Epic cercano i giochi per pezzo di indirizzo."""

    def test_apostrofo_e_numero(self):
        assert gameplay._indirizzo_nome("Marvel's Spider-Man 2") == \
            "marvels-spider-man-2"

    def test_le_lettere_accentate_diventano_semplici(self):
        # Con un trattino al posto della o lunga la pagina non esiste.
        assert gameplay._indirizzo_nome("Ghost of Yōtei") == "ghost-of-yotei"

    def test_niente_nome_niente_indirizzo(self):
        assert gameplay._indirizzo_nome(None) == ""
        assert gameplay._indirizzo_nome("   ") == ""


class _RispostaFinta:
    """Risposta HTTP finta: testo o json, con errore opzionale."""

    def __init__(self, testo="", dati=None, errore=None, status_code=200):
        self.text = testo
        self.status_code = status_code
        self._dati = dati
        self._errore = errore

    def raise_for_status(self):
        if self._errore:
            raise self._errore

    def json(self):
        if self._dati is None:
            raise ValueError("non e' json")
        return self._dati


def _finta_rete(monkeypatch, risposte, chiamate=None):
    """`risposte` e' una lista di (pezzo_di_url, risposta): vince il primo
    pezzo contenuto nell'indirizzo chiesto. Nessun pezzo: errore 404."""
    chiamate = chiamate if chiamate is not None else []

    def finto_get(url, timeout=None, headers=None, **extra):
        chiamate.append(url)
        for pezzo, risposta in risposte:
            if pezzo in url:
                return risposta
        return _RispostaFinta(errore=gameplay.requests.HTTPError("404"))

    monkeypatch.setattr(gameplay.requests, "get", finto_get)
    return chiamate


class TestPlayStation:
    """'Ghost of Yotei' su Steam non c'e': il 5 ottobre 2026 lo Short e'
    uscito con clip Pexels. Sony i filmati li pubblica nella scheda."""

    SCHEDA = (
        '<video src="https://gmedia.playstation.com/is/content/SIEPDC/global_pdc'
        '/en/games/pdps/g/gh/ghost-of-yotei/videos/annuncio.mp4&#34;,&#34;asset">'
        '"https://vulcan.dl.playstation.net/img/rnd/202108/1922/IXaqDecMqWm5.mp4"'
        '"https://gmedia.playstation.com/is/content/SIEPDC/hardware/ps5-pro'
        '/channel-specific-content/PS5-Pro-All-Features.mp4"'
    )

    def test_prende_i_filmati_dai_due_cdn_e_lascia_fuori_lo_spot(self, monkeypatch):
        _finta_rete(monkeypatch, [("playstation.com/en-us/games",
                                   _RispostaFinta(self.SCHEDA))])
        trovato = gameplay.materiale_playstation("Ghost of Yotei")
        assert trovato["video"] == [
            "https://gmedia.playstation.com/is/content/SIEPDC/global_pdc/en/games"
            "/pdps/g/gh/ghost-of-yotei/videos/annuncio.mp4",
            "https://vulcan.dl.playstation.net/img/rnd/202108/1922/IXaqDecMqWm5.mp4",
        ]

    def test_l_indirizzo_finisce_esattamente_su_mp4(self, monkeypatch):
        # Nella pagina l'indirizzo continua con altro testo: ffmpeg con la
        # coda attaccata non scaricherebbe niente.
        _finta_rete(monkeypatch, [("playstation.com", _RispostaFinta(self.SCHEDA))])
        trovato = gameplay.materiale_playstation("Ghost of Yotei")
        assert all(u.endswith(".mp4") for u in trovato["video"])

    def test_se_la_scheda_non_esiste_si_prova_senza_sottotitolo(self, monkeypatch):
        chiamate = _finta_rete(monkeypatch, [
            ("ghost-of-tsushima/", _RispostaFinta(self.SCHEDA)),
        ])
        trovato = gameplay.materiale_playstation(
            "Ghost of Tsushima: Director's Cut")
        assert trovato and trovato["video"]
        assert "ghost-of-tsushima-directors-cut" in chiamate[0]
        assert chiamate[1].endswith("/ghost-of-tsushima/")

    def test_gioco_che_su_playstation_non_c_e(self, monkeypatch):
        _finta_rete(monkeypatch, [])
        assert gameplay.materiale_playstation("Gears of War") is None

    def test_una_scheda_senza_filmati_non_vale(self, monkeypatch):
        _finta_rete(monkeypatch, [("playstation.com",
                                   _RispostaFinta("<p>niente video</p>"))])
        assert gameplay.materiale_playstation("Astro Bot") is None


    def test_i_filmati_del_gioco_giusto_vanno_davanti(self, monkeypatch):
        # In fondo alla scheda di Spider-Man 2 ci sono i filmati dei giochi
        # consigliati: diciannove in tutto, e i primi tre vanno montati.
        pagina = (
            '"https://vulcan.dl.playstation.net/img/rnd/202310/consigliato.mp4"'
            '"https://gmedia.playstation.com/is/content/SIEPDC/global_pdc/en'
            '/games/pdps/s/sp/spider-man-2/hero/video/trailer.mp4"'
        )
        _finta_rete(monkeypatch, [("playstation.com", _RispostaFinta(pagina))])
        trovato = gameplay.materiale_playstation("Spider-Man 2")
        assert trovato["video"][0].endswith("/spider-man-2/hero/video/trailer.mp4")


class TestIlNegozioCheFrena:
    """Un 403 non vuol dire 'non esiste' come il 404: vuol dire 'troppe
    richieste'. Il 6 ottobre 2026 PlayStation ha cominciato a rispondere 403
    anche sui giochi che un minuto prima aveva trovato."""

    def test_dopo_una_pausa_si_riprova_una_volta(self, monkeypatch):
        risposte = [_RispostaFinta(status_code=403),
                    _RispostaFinta("eccomi")]
        monkeypatch.setattr(gameplay.time, "sleep", lambda s: None)
        monkeypatch.setattr(gameplay.requests, "get",
                            lambda *a, **k: risposte.pop(0))
        assert gameplay._scarica_pagina("http://x").text == "eccomi"

    def test_due_volte_di_fila_e_si_lascia_perdere(self, monkeypatch):
        chiamate = []

        def finto(*a, **k):
            chiamate.append(1)
            return _RispostaFinta(
                status_code=403,
                errore=gameplay.requests.HTTPError("403"))
        monkeypatch.setattr(gameplay.time, "sleep", lambda s: None)
        monkeypatch.setattr(gameplay.requests, "get", finto)
        try:
            gameplay._scarica_pagina("http://x")
            assert False, "doveva alzare l'errore"
        except gameplay.requests.HTTPError:
            pass
        assert len(chiamate) == 2

    def test_un_404_non_si_riprova(self, monkeypatch):
        chiamate = []

        def finto(*a, **k):
            chiamate.append(1)
            return _RispostaFinta(status_code=404,
                                  errore=gameplay.requests.HTTPError("404"))
        monkeypatch.setattr(gameplay.requests, "get", finto)
        try:
            gameplay._scarica_pagina("http://x")
        except gameplay.requests.HTTPError:
            pass
        assert len(chiamate) == 1


class TestDoppioniDiMisura:
    """Nelle pagine Nintendo lo stesso disegno c'e' a tre misure: senza
    accorparli si prenderebbero tre dei quattro posti disponibili."""

    def test_si_tiene_la_misura_piu_grande(self):
        elenco = ["http://x/foto_image1280w.jpg", "http://x/foto_image1600w.jpg"]
        assert gameplay._senza_doppioni_di_misura(elenco) == \
            ["http://x/foto_image1600w.jpg"]

    def test_quella_senza_suffisso_vince(self):
        elenco = ["http://x/foto_image1280w.jpg", "http://x/foto.jpg"]
        assert gameplay._senza_doppioni_di_misura(elenco) == ["http://x/foto.jpg"]

    def test_due_disegni_diversi_restano_due(self):
        elenco = ["http://x/uno.jpg", "http://x/due_image950w.jpg"]
        assert len(gameplay._senza_doppioni_di_misura(elenco)) == 2


class TestSoloSchermate:
    """Nelle schede ci sono anche fasce e sfondi del sito: in uno Short
    verticale si vedono per quello che sono, grafica di contorno."""

    def test_fasce_e_sfondi_restano_fuori(self):
        elenco = ["http://x/CI_Gioco_Banner_EN.jpg",
                  "http://x/CI_Gioco_Background.jpg",
                  "http://x/CI_Gioco_Scena_1.jpg"]
        assert gameplay._solo_schermate(elenco) == ["http://x/CI_Gioco_Scena_1.jpg"]

    def test_se_il_filtro_svuota_tutto_meglio_il_dubbio_che_lo_stock(self):
        elenco = ["http://x/CI_Gioco_Banner_EN.jpg"]
        assert gameplay._solo_schermate(elenco) == elenco


class TestEpic:
    """Fortnite e' uno degli argomenti che portano piu' pubblico e su Steam
    non c'e'. La pagina del negozio e' JavaScript, l'API che la riempie no."""

    SCHEDA = (
        '{"videoUrl":"https://epic-games-store-cdn.qstv.on.epicgames.com/output'
        '/aaaa-1111/output.mp4","altro":"https://epic-games-store-cdn.qstv.on'
        '.epicgames.com/output/bbbb-2222/output.mp4"}'
    )

    def test_prende_i_filmati_della_scheda(self, monkeypatch):
        _finta_rete(monkeypatch, [("store-content.ak.epicgames.com",
                                   _RispostaFinta(self.SCHEDA))])
        trovato = gameplay.materiale_epic("Fortnite")
        assert len(trovato["video"]) == 2
        assert trovato["video"][0].endswith("/aaaa-1111/output.mp4")

    def test_gioco_che_su_epic_non_c_e(self, monkeypatch):
        _finta_rete(monkeypatch, [])
        assert gameplay.materiale_epic("Pokemon Legends Z-A") is None


class TestNintendo:
    """Nintendo non pubblica mp4 nelle schede, ma pubblica le schermate
    ufficiali: valgono come gli screenshot Steam, animati in Ken Burns."""

    RICERCA = {"response": {"docs": [
        {"title": "Pokémon Legends: Z-A",
         "url": "/en-gb/Games/Nintendo-Switch-2-games/Pokemon-Legends-Z-A-2533423.html"},
    ]}}
    PAGINA = (
        '<img src="https://www.nintendo.com/eu/media/images/01_website_elements'
        '/icons/favicon.png">'
        '<img src="https://www.nintendo.com/eu/media/images/09_switch2_games'
        '/pokemon-legends-za/scena-nuova.jpg">'
        '<img src="https://www.nintendo.com/eu/media/images/08_content_images'
        '/nswitch_1/CI_NSwitch_1.jpg">'
        '<img src="https://www.nintendo.com/eu/media/images/08_content_images'
        '/nswitch_1/CI_NSwitch_2.jpg">'
        '<img src="https://www.nintendo.com/eu/media/images/02_logos'
        '/logo-nintendo.png">'
    )

    def test_prende_solo_le_schermate_del_gioco(self, monkeypatch):
        _finta_rete(monkeypatch, [
            ("search.nintendo-europe.com", _RispostaFinta(dati=self.RICERCA)),
            ("nintendo.com/en-gb/Games", _RispostaFinta(self.PAGINA)),
        ])
        trovato = gameplay.materiale_nintendo("Pokemon Legends Z-A")
        assert trovato["video"] == []
        # Le icone e i loghi del sito restano fuori; le schermate per la
        # stampa vanno davanti alle altre immagini del gioco.
        assert len(trovato["immagini"]) == 3
        assert all("08_content_images" in u for u in trovato["immagini"][:2])
        assert trovato["immagini"][2].endswith("/scena-nuova.jpg")
        assert trovato["nome"] == "Pokémon Legends: Z-A"

    def test_un_gioco_diverso_viene_scartato(self, monkeypatch):
        # La ricerca Nintendo risponde sempre qualcosa, come quella di Steam.
        ricerca = {"response": {"docs": [
            {"title": "Minecraft Dungeons", "url": "/en-gb/x.html"}]}}
        chiamate = _finta_rete(monkeypatch, [
            ("search.nintendo-europe.com", _RispostaFinta(dati=ricerca)),
            ("nintendo.com/en-gb", _RispostaFinta(self.PAGINA)),
        ])
        assert gameplay.materiale_nintendo("Minecraft") is None
        assert not any("/en-gb/x.html" in u for u in chiamate), \
            "la scheda sbagliata non va nemmeno aperta"

    def test_ricerca_rotta_non_ferma_niente(self, monkeypatch):
        _finta_rete(monkeypatch, [
            ("search.nintendo-europe.com",
             _RispostaFinta(errore=gameplay.requests.ConnectionError("giu'"))),
        ])
        assert gameplay.materiale_nintendo("Pokemon Legends Z-A") is None


class TestXbox:
    """Il catalogo Microsoft da' le schermate ufficiali; la lista dei video
    e' sempre vuota, quindi da Xbox arrivano solo immagini."""

    SUGGERIMENTI = {"ResultSets": [{"Suggests": [
        {"Title": "Gears of War: E-Day",
         "Metas": [{"Key": "BigCatalogId", "Value": "9N4PT8HGCDHQ"}]},
    ]}]}
    CATALOGO = {"Products": [{"LocalizedProperties": [{"Images": [
        {"ImagePurpose": "Screenshot", "Width": 3840, "Height": 2160,
         "Uri": "//store-images.s-microsoft.com/image/apps.1.jpg"},
        {"ImagePurpose": "Screenshot", "Width": 1920, "Height": 1080,
         "Uri": "//store-images.s-microsoft.com/image/apps.2.jpg"},
        {"ImagePurpose": "Screenshot", "Width": 200, "Height": 112,
         "Uri": "//store-images.s-microsoft.com/image/apps.piccola.jpg"},
        {"ImagePurpose": "Poster", "Width": 1440, "Height": 2160,
         "Uri": "//store-images.s-microsoft.com/image/apps.poster.jpg"},
    ]}]}]}

    def test_prende_le_schermate_grandi_con_indirizzo_completo(self, monkeypatch):
        _finta_rete(monkeypatch, [
            ("msstoreapiprod", _RispostaFinta(dati=self.SUGGERIMENTI)),
            ("displaycatalog", _RispostaFinta(dati=self.CATALOGO)),
        ])
        trovato = gameplay.materiale_xbox("Gears of War E-Day")
        assert trovato["immagini"] == [
            "https://store-images.s-microsoft.com/image/apps.1.jpg",
            "https://store-images.s-microsoft.com/image/apps.2.jpg",
        ]
        assert trovato["video"] == []

    def test_i_suggerimenti_senza_gruppi_funzionano_uguale(self, monkeypatch):
        piatti = {"Suggests": self.SUGGERIMENTI["ResultSets"][0]["Suggests"]}
        _finta_rete(monkeypatch, [
            ("msstoreapiprod", _RispostaFinta(dati=piatti)),
            ("displaycatalog", _RispostaFinta(dati=self.CATALOGO)),
        ])
        assert gameplay.materiale_xbox("Gears of War E-Day")["immagini"]

    def test_un_gioco_diverso_viene_scartato(self, monkeypatch):
        suggerimenti = {"Suggests": [
            {"Title": "Halo Infinite",
             "Metas": [{"Key": "BigCatalogId", "Value": "X"}]}]}
        chiamate = _finta_rete(monkeypatch, [
            ("msstoreapiprod", _RispostaFinta(dati=suggerimenti)),
            ("displaycatalog", _RispostaFinta(dati=self.CATALOGO)),
        ])
        assert gameplay.materiale_xbox("Halo 3") is None
        assert not any("displaycatalog" in u for u in chiamate)


class TestMaterialeDaiNegozi:
    """Nessuno dei quattro negozi ha sempre tutto: i filmati li danno
    PlayStation ed Epic, le schermate Nintendo e Xbox."""

    def test_somma_i_filmati_di_uno_e_le_schermate_dell_altro(self, monkeypatch):
        monkeypatch.setattr(gameplay, "materiale_playstation",
                            lambda n: {"nome": "Il Gioco", "video": ["v1"],
                                       "immagini": []})
        monkeypatch.setattr(gameplay, "materiale_epic", lambda n: None)
        monkeypatch.setattr(gameplay, "materiale_nintendo",
                            lambda n: {"nome": "Altro nome", "video": [],
                                       "immagini": ["i1", "i2"]})
        monkeypatch.setattr(gameplay, "materiale_xbox", lambda n: None)
        trovato = gameplay.materiale_dai_negozi("Il Gioco", 3, 4)
        assert trovato == {"nome": "Il Gioco", "video": ["v1"],
                           "immagini": ["i1", "i2"]}

    def test_un_negozio_rotto_non_ferma_gli_altri(self, monkeypatch):
        def rotto(nome):
            raise ConnectionError("giu'")
        monkeypatch.setattr(gameplay, "materiale_playstation", rotto)
        monkeypatch.setattr(gameplay, "materiale_epic",
                            lambda n: {"nome": "Fortnite", "video": ["v1"],
                                       "immagini": []})
        monkeypatch.setattr(gameplay, "materiale_nintendo", lambda n: None)
        monkeypatch.setattr(gameplay, "materiale_xbox", lambda n: None)
        assert gameplay.materiale_dai_negozi("Fortnite", 3, 4)["video"] == ["v1"]

    def test_quando_c_e_abbastanza_non_si_chiede_agli_altri(self, monkeypatch):
        interrogati = []

        def finto(etichetta, risultato):
            def cerca(nome):
                interrogati.append(etichetta)
                return risultato
            return cerca

        monkeypatch.setattr(gameplay, "materiale_playstation", finto(
            "ps", {"nome": "X", "video": ["v1", "v2"], "immagini": ["i1"]}))
        monkeypatch.setattr(gameplay, "materiale_epic", finto("epic", None))
        monkeypatch.setattr(gameplay, "materiale_nintendo", finto("nintendo", None))
        monkeypatch.setattr(gameplay, "materiale_xbox", finto("xbox", None))
        gameplay.materiale_dai_negozi("X", quanti_video=2, quante_immagini=1)
        assert interrogati == ["ps"]

    def test_in_nessun_negozio_vuol_dire_niente(self, monkeypatch):
        for nome in ("materiale_playstation", "materiale_epic",
                     "materiale_nintendo", "materiale_xbox"):
            monkeypatch.setattr(gameplay, nome, lambda n: None)
        assert gameplay.materiale_dai_negozi("Gioco Inventato") is None


class TestScaricoDaiNegozi:
    def test_i_filmati_epic_si_chiamano_tutti_uguale_e_non_si_sovrascrivono(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "SECONDI_TRAILER", 45)
        scaricati = []

        def finto(url, destinazione, salta=0, durata=None, a_1080=False):
            scaricati.append(destinazione)
            open(destinazione, "wb").close()
            return True
        monkeypatch.setattr(gameplay, "_estrai_mp4", finto)

        percorsi = gameplay.scarica_mp4_ufficiali(
            ["https://cdn/output/a/output.mp4", "https://cdn/output/b/output.mp4"],
            "fortnite", quanti=2)
        assert len(set(percorsi)) == 2
        assert len(percorsi) == 2

    def test_le_schermate_girano_come_quelle_steam(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        chiesti = []

        def finta(url, destinazione, minimo=20_000):
            chiesti.append(url)
            open(destinazione, "wb").close()
            return True
        monkeypatch.setattr(gameplay, "_scarica_immagine", finta)

        elenco = [f"http://s/{i}" for i in range(12)]
        percorsi = gameplay.scarica_immagini_dai_negozi(
            elenco, "gioco", quante=4, salto=1)
        assert len(percorsi) == 4
        assert chiesti[0] == "http://s/4"


class TestEsclusiveConsoleNelVideo:
    """Sui trenta Short prima del 6 ottobre 2026, sei sono usciti con clip
    Pexels perche' il gioco su Steam non c'era."""

    def _finto_maker(self, monkeypatch, scarica):
        # maker importa numpy, che nei test non c'e': si mette al suo posto
        # un modulo finto, come fa TestClipMieNelMontaggio.
        finto = types.ModuleType("maker")
        finto.scarica_clip_sfondo = scarica
        monkeypatch.setitem(sys.modules, "maker", finto)

    def test_un_gioco_fuori_da_steam_monta_il_materiale_del_suo_negozio(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "USA_ALTRI_NEGOZI", True)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "STEAM_MAX_TRAILER", 3)
        monkeypatch.setattr(config, "STEAM_MAX_SCREENSHOT", 4)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay, "cerca_gioco_steam", lambda n: (None, None))
        monkeypatch.setattr(gameplay, "clip_mie", lambda c, s: [])
        monkeypatch.setattr(gameplay, "materiale_dai_negozi",
                            lambda n, v=3, i=4: {
                                "nome": "Ghost of Yotei",
                                "video": ["https://gmedia/annuncio.mp4"],
                                "immagini": ["https://img/1.jpg", "https://img/2.jpg"]})

        def finto_mp4(url, destinazione, salta=0, durata=None, a_1080=False):
            open(destinazione, "wb").close()
            return True
        monkeypatch.setattr(gameplay, "_estrai_mp4", finto_mp4)
        monkeypatch.setattr(gameplay, "_scarica_immagine",
                            lambda u, d, minimo=20_000: (open(d, "wb").close() or True))

        def pexels_vietato(*a, **k):
            raise AssertionError("col materiale del negozio Pexels non serve")
        self._finto_maker(monkeypatch, pexels_vietato)

        sorgenti, nome = gameplay.procura_materiale("Ghost of Yōtei", minimo=3)
        assert nome == "Ghost of Yotei"
        assert [s["tipo"] for s in sorgenti] == ["video", "immagine", "immagine"]
        assert all(s["gioco"] == "Ghost of Yotei" for s in sorgenti)

    def test_senza_materiale_nei_negozi_si_ripiega_su_pexels(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "USA_ALTRI_NEGOZI", True)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay, "cerca_gioco_steam", lambda n: (None, None))
        monkeypatch.setattr(gameplay, "clip_mie", lambda c, s: [])
        monkeypatch.setattr(gameplay, "materiale_dai_negozi", lambda n, v=3, i=4: None)
        self._finto_maker(monkeypatch,
                          lambda query, quante=3: ["stock.mp4"] * quante)
        sorgenti, nome = gameplay.procura_materiale("Gioco Inventato", minimo=3)
        assert nome is None
        assert all(s["gioco"] is None for s in sorgenti)

    def test_con_l_interruttore_spento_i_negozi_non_si_toccano(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "USA_ALTRI_NEGOZI", False)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay, "cerca_gioco_steam", lambda n: (None, None))
        monkeypatch.setattr(gameplay, "clip_mie", lambda c, s: [])

        def vietato(*a, **k):
            raise AssertionError("interruttore spento")
        monkeypatch.setattr(gameplay, "materiale_dai_negozi", vietato)
        self._finto_maker(monkeypatch,
                          lambda query, quante=3: ["stock.mp4"] * quante)
        assert gameplay.procura_materiale("Qualsiasi", minimo=3)[1] is None

    def test_un_gioco_su_steam_non_passa_dai_negozi(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "USA_STEAM", True)
        monkeypatch.setattr(config, "USA_ALTRI_NEGOZI", True)
        monkeypatch.setattr(config, "DIR_TEMP", str(tmp_path))
        monkeypatch.setattr(config, "STEAM_MAX_TRAILER", 3)
        monkeypatch.setattr(config, "STEAM_MAX_SCREENSHOT", 4)
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "niente.json"))
        monkeypatch.setattr(gameplay, "cerca_gioco_steam",
                            lambda n: (42, "Cyberpunk 2077"))
        monkeypatch.setattr(gameplay, "dettagli_gioco", lambda a: {"movies": [{"id": 1}]})
        monkeypatch.setattr(gameplay, "scarica_trailer_steam",
                            lambda *a, **k: ["t1.mp4", "t2.mp4", "t3.mp4"])
        monkeypatch.setattr(gameplay, "scarica_screenshot_steam", lambda *a, **k: [])
        monkeypatch.setattr(gameplay, "clip_mie", lambda c, s: [])

        def vietato(*a, **k):
            raise AssertionError("il gioco e' su Steam: i negozi non servono")
        monkeypatch.setattr(gameplay, "materiale_dai_negozi", vietato)
        sorgenti, nome = gameplay.procura_materiale("Cyberpunk 2077", minimo=3)
        assert nome == "Cyberpunk 2077"
        assert len(sorgenti) == 3
