"""Offerte, merch, sport, paragoni e leaker: le notizie che non rendono.

Dati API dal 5 all'11 ottobre 2026: gli Short sui giochi veri fanno
600-1.000 visualizzazioni, quelli su merch, offerte e football americano
1-8, le storie di leaker 49-67.
"""
import pytest

import brain
import config
import profilo


@pytest.fixture(autouse=True)
def poppone(monkeypatch):
    monkeypatch.setattr(profilo, "attivo", profilo.predefinito)


class TestOfferteMerchSport:
    @pytest.mark.parametrize("lingua,titolo", [
        ("en", "GTA 6 merch frenzy hits stores"),
        ("en", "Pokemon: Prime Day steals you can't miss"),
        ("en", "NFL star Kyle Juszczyk shows his Pokemon lineup"),
        ("it", "Survival Zelda-like: sconto da non perdere su Instant Gaming"),
        ("it", "Le migliori offerte PS5 del Black Friday"),
        ("en", "Pokemon: Holiday Plush Collection Shocks Fans"),
        ("en", "Promising Western PS5 Action Game: Release Date Revealed"),
        ("it", "Un promettente survival arriva su PS5"),
    ])
    def test_scartate(self, monkeypatch, lingua, titolo):
        monkeypatch.setattr(config, "LINGUA", lingua)
        assert brain._tema_escluso(titolo)

    @pytest.mark.parametrize("lingua,titolo", [
        ("en", "EA FC 27 holds off Minecraft Dungeons II in UK charts"),
        ("en", "EA Sports FC 27 football ratings revealed"),
        ("en", "NBA 2K27 gets a new trailer"),
        ("en", "Game Pass October lineup revealed"),
        ("en", "Toy Story characters join Fortnite"),
        ("it", "EA FC 27, il calcio di EA cambia motore"),
        ("it", "GTA 6, nuovo trailer annunciato da Rockstar"),
    ])
    def test_i_giochi_veri_restano(self, monkeypatch, lingua, titolo):
        monkeypatch.setattr(config, "LINGUA", lingua)
        assert brain._tema_escluso(titolo) == ""


class TestParagone:
    @pytest.mark.parametrize("titolo", [
        "Survival Zelda-like: sconto o mito?",
        "Un nuovo gioco in stile Zelda",
        "A Fortnite-style shooter from a tiny studio",
    ])
    def test_il_paragone_non_e_il_gioco(self, titolo):
        assert not brain._nomina_un_grosso(titolo)

    @pytest.mark.parametrize("titolo", [
        "Zelda: nuovo trailer",
        "Fortnite adds a Zelda-like mode",
        "GTA 6 alla Gamescom",
    ])
    def test_il_gioco_nominato_resta(self, titolo):
        assert brain._nomina_un_grosso(titolo)


class TestLeaker:
    def test_un_leaker_vale_meno_della_stessa_notizia_ufficiale(self, monkeypatch):
        monkeypatch.setattr(config, "LINGUA", "en")
        leaker = brain._punteggio_notizia("GTA 6 leaker shares new clip")
        ufficiale = brain._punteggio_notizia("GTA 6 shares new clip")
        assert leaker == ufficiale + brain.PUNTI_INDISCREZIONE

    def test_leak_non_e_piu_una_parola_calda(self, monkeypatch):
        monkeypatch.setattr(config, "LINGUA", "it")
        assert (brain._punteggio_notizia("GTA 6: leak della mappa")
                == brain._punteggio_notizia("GTA 6: la mappa")
                + brain.PUNTI_INDISCREZIONE)
