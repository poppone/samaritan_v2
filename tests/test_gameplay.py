"""Test sul riconoscimento del gioco.

E' la logica piu' delicata del progetto: se sbaglia, lo Short parla di un
gioco e mostra il gameplay di un altro. Nessun test tocca la rete.
"""
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
