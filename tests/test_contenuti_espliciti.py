"""Niente sesso, nudita' o leak espliciti, in nessuna lingua.

Il 12 ottobre 2026 lo Short inglese delle 20:00 (p3V5VCPA-iA) e' nato da
"Latest Leaked GTA 6 Video Shows Lucia Fully Naked" (IGN): "naked" non era
fra le parole a rischio, per non perdere Naked Snake. Il filtro si controlla
sulle notizie prima del modello, sul titolo e sullo script generati e in
main.py un'ultima volta prima del caricamento.
"""
import pytest

import brain
import config


TITOLO_DEL_12_OTTOBRE = ("Latest Leaked GTA 6 Video Shows Lucia Fully Naked, "
                         "Sparks Fan Skepticism")

SCRIPT_BUONO = (
    "Nessuno ti ha detto che questo boss si puo' battere senza sparare un colpo. "
    "Gli sviluppatori hanno lasciato una porta secondaria dietro la cascata. "
    "Serve solo aspettare che il temporale finisca, poi la strada si apre da sola. "
    "La community ci ha messo sei anni ad accorgersene, e ancora quasi nessuno lo "
    "sa. Iscriviti per gli altri segreti. E nessuno te lo aveva detto."
)


class TestContenutoEsplicito:
    @pytest.mark.parametrize("testo", [
        TITOLO_DEL_12_OTTOBRE,
        "Lucia Fully Naked",
        "GTA VI: leak da 24 minuti di gameplay e nudi integrali",
        "Nudità integrale per Jason e Lucia",
        "Lucia completamente nuda nel nuovo leak",
        "Grand Theft Auto VI: Leaked NSFW detail shocks fans",
        "Baldur's Gate 3 sex scenes explained",
        "Cyberpunk 2077 topless mod goes viral",
        "GTA 6 strip club footage leaked",
        "Scene di sesso in The Witcher 4?",
        "Il porno nei videogiochi",
    ])
    def test_scarta(self, testo):
        assert brain.contenuto_esplicito(testo)

    @pytest.mark.parametrize("testo", [
        "Metal Gear Solid Delta: Naked Snake torna su PS5",
        "The Naked Gun gets a game adaptation",
        "GTA 6, il trailer ufficiale batte ogni record",
        "GTA 6: Leaked clip raises doubts",
        "Sea of Thieves: la nuova stagione dei pirati",
        "Sussex studio announces new racing game",
        "Essex-based developer reveals Hardcore mode",
        "",
    ])
    def test_lascia_passare(self, testo):
        assert brain.contenuto_esplicito(testo) == ""

    def test_vale_in_tutte_e_due_le_lingue(self, monkeypatch):
        # Le ricerche italiane pescano anche titoli inglesi.
        for lingua in ("it", "en"):
            monkeypatch.setattr(config, "LINGUA", lingua)
            assert brain.contenuto_esplicito("Lucia Fully Naked")
            assert brain.contenuto_esplicito("Lucia nuda nel leak")


class TestNotizieFiltrate:
    @pytest.mark.parametrize("lingua", ["it", "en"])
    def test_la_notizia_del_12_ottobre_non_arriva_al_modello(self, lingua,
                                                            monkeypatch):
        monkeypatch.setattr(config, "LINGUA", lingua)
        voci = [(TITOLO_DEL_12_OTTOBRE, "IGN", "u1"),
                ("GTA 6 new trailer date confirmed by Rockstar", "IGN", "u2")]
        monkeypatch.setattr(brain, "_voci_rss", lambda ricerca: voci)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online()]
        assert TITOLO_DEL_12_OTTOBRE not in titoli
        assert "GTA 6 new trailer date confirmed by Rockstar" in titoli

    def test_scarta_anche_se_lo_dice_solo_il_sommario(self, monkeypatch):
        voci = [("GTA 6: the leak everyone is talking about", "IGN", "u1"),
                ("GTA 6 new trailer date confirmed by Rockstar", "IGN", "u2")]
        monkeypatch.setattr(brain, "_voci_rss", lambda ricerca: voci)
        monkeypatch.setattr(brain, "carica_cronologia", lambda: [])
        monkeypatch.setattr(brain, "_sommario_bing", lambda t: (
            "The clip shows Lucia fully naked." if "leak" in t else ""))
        titoli = [n["titolo"] for n in brain.recupera_trend_gaming_online()]
        assert titoli == ["GTA 6 new trailer date confirmed by Rockstar"]


class TestTitoloEScript:
    def test_titolo_esplicito_rifiutato(self):
        ok, motivo = brain.valida_titolo("GTA 6: Lucia Fully Naked 🤔", "GTA 6")
        assert not ok
        assert "naked" in motivo

    def test_titolo_pulito_accettato(self):
        ok, motivo = brain.valida_titolo("GTA 6: Leaked clip raises doubts 🤔",
                                         "GTA 6")
        assert ok, motivo

    def test_script_esplicito_rifiutato(self):
        script = ("Imagine stumbling upon a brand-new GTA VI clip that shows "
                  "Lucia completely naked. " + SCRIPT_BUONO)
        ok, motivo = brain.valida_script("GTA 6: Leaked clip raises doubts",
                                         script)
        assert not ok
        assert "naked" in motivo

    def test_script_pulito_accettato(self):
        ok, motivo = brain.valida_script("Un titolo qualsiasi", SCRIPT_BUONO)
        assert ok, motivo


class TestUltimoControlloPrimaDelCaricamento:
    def _pipeline(self, monkeypatch, dati, tmp_path):
        # La CI non installa moviepy (requirements-dev.txt): maker e analyst
        # si sostituiscono con moduli finti prima di importare main, e main
        # si toglie dalla cache alla fine per non lasciarlo legato ai finti.
        import sys
        import types
        finto_maker = types.ModuleType("maker")
        finto_maker.assembla_video_finale = lambda **kw: None
        finto_analyst = types.ModuleType("analyst")
        finto_analyst.aggiorna_performance = lambda: None
        monkeypatch.setitem(sys.modules, "maker", finto_maker)
        monkeypatch.setitem(sys.modules, "analyst", finto_analyst)
        monkeypatch.delitem(sys.modules, "main", raising=False)
        import main
        video = tmp_path / "video.mp4"
        video.write_bytes(b"x")
        caricati, errori = [], []
        monkeypatch.setattr(main, "prepara_uscita", lambda: True)
        monkeypatch.setattr(main.autoprofilo, "aggiorna_se_serve", lambda: None)
        monkeypatch.setattr(main, "token_youtube_scaduto", lambda: False)
        monkeypatch.setattr(main, "_scrivi_e_monta",
                            lambda tema: (dati, str(video), {}, ""))
        monkeypatch.setattr(main, "costruisci_descrizione", lambda *a: "desc")
        monkeypatch.setattr(main, "costruisci_tag", lambda d: [])
        monkeypatch.setattr(main.orari, "uscita_programmata", lambda: None)
        monkeypatch.setattr(main, "carica_short",
                            lambda **kw: caricati.append(kw) or "abc123")
        monkeypatch.setattr(main, "aggiorna_ultimo_video_id", lambda v: None)
        monkeypatch.setattr(main, "aggiorna_ultima_voce", lambda **kw: None)
        monkeypatch.setattr(main.copia_pubblica, "prepara", lambda *a: {})
        monkeypatch.setattr(main.notifier, "notifica_errore", errori.append)
        monkeypatch.setattr(main.notifier, "notifica_pubblicazione",
                            lambda *a: None)
        try:
            main.esegui_pipeline_samaritan()
        finally:
            sys.modules.pop("main", None)
        return caricati, errori

    def test_non_carica_un_video_esplicito(self, monkeypatch, tmp_path):
        dati = {"titolo": "GTA 6: Lucia Fully Naked", "script": SCRIPT_BUONO,
                "fonte": "", "descrizione": "", "gioco": "GTA 6"}
        caricati, errori = self._pipeline(monkeypatch, dati, tmp_path)
        assert caricati == []
        assert errori and "naked" in errori[0]

    def test_carica_un_video_pulito(self, monkeypatch, tmp_path):
        dati = {"titolo": "GTA 6: Leaked clip raises doubts",
                "script": SCRIPT_BUONO, "fonte": "", "descrizione": "",
                "gioco": "GTA 6"}
        caricati, errori = self._pipeline(monkeypatch, dati, tmp_path)
        assert len(caricati) == 1
        assert errori == []
