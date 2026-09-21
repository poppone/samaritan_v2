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

        def finta_get(url, timeout=None):
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
