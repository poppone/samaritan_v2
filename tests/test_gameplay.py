"""Test sul riconoscimento del gioco.

E' la logica piu' delicata del progetto: se sbaglia, lo Short parla di un
gioco e mostra il gameplay di un altro. Nessun test tocca la rete.
"""
import json

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
