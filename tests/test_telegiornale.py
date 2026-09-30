# -*- coding: utf-8 -*-
"""Test sul profilo telegiornale ('telegiornale': true in canale.json).

Un telegiornale automatico ha tre promesse da tenere: racconta solo notizie
vere con la loro fonte, non tocca morti, crimini e tragedie, e dice a schermo
che le immagini sono di repertorio. Nessun test tocca la rete.
"""
import json
import os

import pytest

import brain
import config
import profilo

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESEMPIO_TG = os.path.join(RADICE, "canale.telegiornale.esempio.json")


@pytest.fixture
def tg(monkeypatch):
    p = profilo.carica(ESEMPIO_TG)
    monkeypatch.setattr(profilo, "_attivo", p)
    monkeypatch.setattr(config, "NOME_CANALE", p.nome_canale)
    monkeypatch.setattr(config, "HANDLE_CANALE", p.handle)
    monkeypatch.setattr(config, "LINGUA", "it")
    return p


def _dati_tg(**altro):
    with open(ESEMPIO_TG, encoding="utf-8") as f:
        dati = json.load(f)
    dati.update(altro)
    return dati


class TestProfilo:
    def test_l_esempio_e_un_telegiornale_valido(self, tg):
        assert tg.telegiornale is True
        assert tg.materiale == "stock"

    def test_senza_temi_esclusi_prende_quelli_delicati(self, tg):
        assert tg.temi_esclusi == profilo.TEMI_DELICATI

    def test_i_temi_esclusi_scritti_sostituiscono_quelli_delicati(self):
        p = profilo.da_dizionario(_dati_tg(temi_esclusi={"it": ["calcio"]}))
        assert p.temi_esclusi_per("it") == ("calcio",)
        assert p.temi_esclusi_per("en") == ()

    def test_poppone_tv_non_e_un_telegiornale(self):
        p = profilo.predefinito()
        assert p.telegiornale is False
        assert p.temi_esclusi_per("it") == ()

    def test_un_canale_normale_non_filtra_niente(self):
        dati = _dati_tg()
        del dati["telegiornale"]
        assert profilo.da_dizionario(dati).temi_esclusi == {}

    def test_telegiornale_deve_essere_vero_o_falso(self):
        with pytest.raises(profilo.ProfiloNonValido, match="telegiornale"):
            profilo.da_dizionario(_dati_tg(telegiornale="si"))

    def test_un_telegiornale_non_usa_steam(self):
        with pytest.raises(profilo.ProfiloNonValido):
            profilo.da_dizionario({"argomento": "gaming", "telegiornale": True})


class TestTemiEsclusi:
    @pytest.mark.parametrize("titolo", [
        "Incidente sull'A1, tre morti e due feriti",
        "Omicidio a Milano, fermato un uomo",
        "E' morto il cantante che aveva vinto Sanremo",
        "Guerra, nuovi attacchi nella notte",
    ])
    def test_scarta_le_notizie_delicate(self, tg, titolo):
        assert brain._tema_escluso(titolo)

    @pytest.mark.parametrize("titolo", [
        "Bollette, da ottobre cambia tutto: cosa sapere",
        "Una notizia bomba sul nuovo iPhone",
        "Borsa, crash evitato: Milano chiude in rialzo",
        "Mortificato il ministro dopo la gaffe",
        "Sinner vince a Pechino e sale al primo posto",
    ])
    def test_lascia_passare_le_altre(self, tg, titolo):
        assert brain._tema_escluso(titolo) == ""

    def test_senza_accenti_e_maiuscole(self):
        assert brain._tema_escluso("STRAGE sfiorata", ("strage",)) == "strage"
        assert brain._tema_escluso("E' stata una tragedìa", ("tragedia",)) == "tragedia"

    def test_le_notizie_delicate_non_arrivano_al_modello(self, tg, monkeypatch):
        voci = [
            ("Tre morti in un incidente sulla statale", "ANSA", "u1"),
            ("Pensioni, da gennaio aumento per tutti", "Il Sole 24 Ore", "u2"),
        ]
        monkeypatch.setattr(brain, "_voci_rss", lambda ricerca: voci)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        notizie = brain.recupera_trend_gaming_online()
        assert [n["titolo"] for n in notizie] == ["Pensioni, da gennaio aumento per tutti"]

    def test_scarta_anche_se_lo_dice_solo_il_sommario(self, tg, monkeypatch):
        voci = [("Lutto nel mondo della musica", "ANSA", "u1"),
                ("Pensioni, da gennaio aumento per tutti", "Il Sole 24 Ore", "u2")]
        monkeypatch.setattr(brain, "_voci_rss", lambda ricerca: voci)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "_sommario_bing", lambda t: (
            "Il cantante e' morto ieri a 80 anni." if "Lutto" in t else ""))
        notizie = brain.recupera_trend_gaming_online()
        assert [n["titolo"] for n in notizie] == ["Pensioni, da gennaio aumento per tutti"]


class TestFormati:
    def test_solo_formati_di_notizia(self, tg, monkeypatch):
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        for _ in range(30):
            formato = brain.scegli_formato([{"titolo": "x"}])
            assert brain.FORMATI_VIDEO[formato]["richiede_fatto"]

    def test_senza_notizie_niente_video(self, tg, monkeypatch):
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        with pytest.raises(RuntimeError, match="telegiornale"):
            brain.scegli_formato([])

    def test_poppone_tv_senza_notizie_fa_un_evergreen(self, monkeypatch):
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        formato = brain.scegli_formato([])
        assert not brain.FORMATI_VIDEO[formato]["richiede_fatto"]


class TestPrompt:
    NOTIZIE = [{"titolo": "Pensioni, da gennaio aumento per tutti",
                "fonte": "Il Sole 24 Ore", "link": "", "sommario": ""}]

    def test_il_prompt_chiede_lo_stile_da_telegiornale(self, tg):
        prompt = brain._costruisci_system_prompt("VIRAL_HOOK_NEWS", self.NOTIZIE, [], [])
        assert "STILE TELEGIORNALE" in prompt
        assert "testata" in prompt

    def test_poppone_tv_non_lo_riceve(self):
        prompt = brain._costruisci_system_prompt("VIRAL_HOOK_NEWS", self.NOTIZIE, [], [])
        assert "STILE TELEGIORNALE" not in prompt

    def test_uno_script_senza_notizia_viene_scartato(self, tg, monkeypatch):
        risposta = json.dumps({
            "titolo": "Pensioni: cosa cambia davvero", "gioco": "Pensioni",
            "script": " ".join(["Le pensioni cambiano ogni anno."] * 12),
            "query_video": "city skyline aerial", "descrizione": "Righe.",
            "indice_notizia": -1})
        visti = []

        class FinteCompletions:
            @staticmethod
            def create(**kw):
                visti.append(kw["messages"][1]["content"])

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
        monkeypatch.setattr(brain, "recupera_trend_gaming_online", lambda **k: self.NOTIZIE)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "salva_in_cronologia", lambda r: None)
        with pytest.raises(RuntimeError):
            brain.genera_script_samaritan()
        assert any("un telegiornale racconta solo quelle" in v for v in visti)


class TestCartello:
    """maker si porta dietro moviepy, che la CI non installa: qui si salta."""

    def test_testata_della_fonte(self):
        maker = pytest.importorskip("maker")
        assert maker.testata_della_fonte("Pensioni, aumento (Il Sole 24 Ore)") == "Il Sole 24 Ore"
        assert maker.testata_della_fonte("") == ""
        assert maker.testata_della_fonte("Titolo senza testata") == ""

    def test_il_cartello_sta_sopra_i_sottotitoli(self):
        maker = pytest.importorskip("maker")
        img = maker.crea_cartello_tg(
            "Pensioni, da gennaio aumento per tutti: ecco quanto e chi lo riceve "
            "davvero secondo le nuove tabelle", "Il Sole 24 Ore")
        fine = maker.Y_CARTELLO_TG + img.shape[0] / config.VIDEO_H
        assert fine < 0.58          # i sottotitoli partono dal 58%
        assert img.shape[1] <= config.VIDEO_W

    def test_la_descrizione_dice_repertorio(self, tg):
        riga = brain._riga_materiale({"gioco": ""}, {"sorgenti_stock": 4})
        assert "repertorio" in riga
