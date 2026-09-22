"""Test sulla veste grafica dei video.

Il montaggio vero non e' testabile qui (moviepy e whisper non sono installati
nella suite, per scelta), ma le vesti sono dati puri: si puo' verificare che
girino davvero e soprattutto che nessuna metta il testo dove non si legge.
Serve perche' nessuno guarda i video prima che escano: se una veste sbagliata
nasconde i sottotitoli dietro i comandi di YouTube, se ne accorge il pubblico.
"""
import json
import os
import re

import pytest

import config
import veste


def _memoria(monkeypatch, tmp_path, contenuto):
    percorso = tmp_path / "cronologia_trend.json"
    if contenuto is not None:
        percorso.write_text(json.dumps(contenuto), encoding="utf-8")
    monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(percorso))
    return percorso


CHIAVI = {
    "nome", "colore_testo", "colore_evidenza", "y_sottotitoli",
    "corpo_sottotitoli", "y_gameplay", "luminosita_sfondo", "banner",
    "barra", "zoom", "intensita_zoom", "ritmo",
}

# Altezza generosa del banner del titolo: tre righe da 64px con interlinea e
# margini, come le costruisce crea_banner_titolo() in maker.py.
ALTEZZA_BANNER = (64 + 18) * 3 + 40


class TestFormaDelleVesti:
    def test_ce_ne_sono_abbastanza_per_non_ripetersi_subito(self):
        assert len(veste.VESTI) >= 4

    def test_i_nomi_sono_unici(self):
        nomi = [v["nome"] for v in veste.VESTI]
        assert len(nomi) == len(set(nomi))

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_ha_tutte_le_chiavi(self, stile):
        assert set(stile) == CHIAVI

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_i_colori_sono_esadecimali(self, stile):
        for chiave in ("colore_testo", "colore_evidenza"):
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", stile[chiave]), chiave

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_il_verso_dello_zoom_e_uno_di_quelli_gestiti(self, stile):
        # maker.py tratta qualunque altro valore come "dentro": un refuso
        # passerebbe inosservato invece di cambiare qualcosa.
        assert stile["zoom"] in ("dentro", "fuori", "alternato")


class TestLeggibilita:
    """Questi non sono test di gusto: sono i limiti oltre i quali il testo
    finisce sotto l'interfaccia di YouTube o esce dallo schermo."""

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_i_sottotitoli_restano_nella_fascia_sicura(self, stile):
        assert veste.Y_SOTTOTITOLI_MIN <= stile["y_sottotitoli"] <= veste.Y_SOTTOTITOLI_MAX

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_il_banner_non_copre_i_sottotitoli(self, stile):
        if not stile["banner"]:
            return
        altezza, secondi = stile["banner"]
        fondo_banner = altezza * config.VIDEO_H + ALTEZZA_BANNER
        assert fondo_banner < stile["y_sottotitoli"] * config.VIDEO_H
        assert 0 < secondi <= 4

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_il_riquadro_gameplay_sta_sopra_i_sottotitoli(self, stile):
        assert 0.15 <= stile["y_gameplay"] < stile["y_sottotitoli"]

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_la_barra_e_sottile(self, stile):
        if not stile["barra"]:
            return
        spessore, colore = stile["barra"]
        assert 4 <= spessore <= 24
        assert len(colore) == 3 and all(0 <= c <= 255 for c in colore)

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_lo_sfondo_resta_scuro_ma_visibile(self, stile):
        assert 0.25 <= stile["luminosita_sfondo"] <= 0.65

    @pytest.mark.parametrize("stile", veste.VESTI, ids=lambda v: v["nome"])
    def test_il_ritmo_e_lo_zoom_restano_umani(self, stile):
        # Fuori da questi margini gli stacchi diventano epilettici o pigri, e
        # lo zoom o non si vede o sembra un errore di scala.
        assert 0.7 <= stile["ritmo"] <= 1.4
        assert 0.04 <= stile["intensita_zoom"] <= 0.2
        assert 80 <= stile["corpo_sottotitoli"] <= 140


class TestDifferenzaFraVesti:
    def test_due_vesti_di_fila_cambiano_piu_di_un_dettaglio(self):
        """Se il video di domani si distingue da quello di oggi per una sola
        sfumatura, tutto questo lavoro non e' servito a niente."""
        visibili = ("colore_testo", "colore_evidenza", "y_sottotitoli",
                    "corpo_sottotitoli", "banner", "barra", "zoom", "ritmo")
        for i, stile in enumerate(veste.VESTI):
            successiva = veste.VESTI[(i + 1) % len(veste.VESTI)]
            diverse = [c for c in visibili if stile[c] != successiva[c]]
            assert len(diverse) >= 3, f"{stile['nome']} -> {successiva['nome']}: {diverse}"


class TestRotazione:
    def test_senza_memoria_si_parte_dalla_prima(self, monkeypatch, tmp_path):
        _memoria(monkeypatch, tmp_path, None)
        assert veste.scegli_veste()["nome"] == veste.VESTI[0]["nome"]

    def test_si_prende_quella_dopo_l_ultima_usata(self, monkeypatch, tmp_path):
        _memoria(monkeypatch, tmp_path, [{"veste": veste.VESTI[0]["nome"]}])
        assert veste.scegli_veste()["nome"] == veste.VESTI[1]["nome"]

    def test_dopo_l_ultima_si_ricomincia(self, monkeypatch, tmp_path):
        _memoria(monkeypatch, tmp_path, [{"veste": veste.VESTI[-1]["nome"]}])
        assert veste.scegli_veste()["nome"] == veste.VESTI[0]["nome"]

    def test_un_nome_sparito_non_blocca_il_giro(self, monkeypatch, tmp_path):
        # Una veste tolta dall'elenco lascia il suo nome nella cronologia.
        _memoria(monkeypatch, tmp_path, [{"veste": "veste-che-non-esiste-piu"}])
        assert veste.scegli_veste()["nome"] == veste.VESTI[0]["nome"]

    def test_si_guarda_l_ultimo_record_che_ha_una_veste(self, monkeypatch, tmp_path):
        # I video usciti prima di questa modifica non hanno il campo: vanno
        # oltrepassati, non letti come "nessuna veste".
        _memoria(monkeypatch, tmp_path, [
            {"veste": veste.VESTI[1]["nome"]},
            {"titolo": "video vecchio senza veste"},
        ])
        assert veste.ultima_veste_usata() == veste.VESTI[1]["nome"]
        assert veste.scegli_veste()["nome"] == veste.VESTI[2]["nome"]

    def test_la_cronologia_a_stringhe_non_fa_esplodere_niente(self, monkeypatch, tmp_path):
        _memoria(monkeypatch, tmp_path, ["vecchio titolo", "altro titolo"])
        assert veste.ultima_veste_usata() is None
        assert veste.scegli_veste()["nome"] == veste.VESTI[0]["nome"]

    def test_un_file_illeggibile_non_ferma_il_video(self, monkeypatch, tmp_path):
        percorso = tmp_path / "cronologia_trend.json"
        percorso.write_text("{ questo non e' json", encoding="utf-8")
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(percorso))
        assert veste.scegli_veste()["nome"] == veste.VESTI[0]["nome"]


class TestAnnotazione:
    def test_si_scrive_sull_ultimo_record(self, monkeypatch, tmp_path):
        percorso = _memoria(monkeypatch, tmp_path, [{"titolo": "a"}, {"titolo": "b"}])
        veste.segna_veste("fuoco")
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        assert dati[1]["veste"] == "fuoco"
        assert "veste" not in dati[0]

    def test_senza_cronologia_non_si_scrive_niente(self, monkeypatch, tmp_path):
        percorso = _memoria(monkeypatch, tmp_path, [])
        veste.segna_veste("fuoco")
        assert json.loads(percorso.read_text(encoding="utf-8")) == []

    def test_un_errore_di_scrittura_non_ferma_la_pubblicazione(self, monkeypatch, tmp_path):
        # Il video e' gia' renderizzato: qui si perde solo la rotazione, e il
        # prossimo giro ripetera' questa veste. Non vale un'eccezione.
        _memoria(monkeypatch, tmp_path, [{"titolo": "a"}])
        monkeypatch.setattr(config, "FILE_CRONOLOGIA", str(tmp_path / "manca" / "x.json"))
        monkeypatch.setattr(veste, "_carica_cronologia", lambda: [{"titolo": "a"}])
        veste.segna_veste("fuoco")   # non deve sollevare


class TestMakerUsaDavveroLaVeste:
    """maker.py e' fuori portata per i test (moviepy non e' installato), ma
    una veste con una chiave che nessuno legge e' peggio di nessuna veste:
    sembra che cambi qualcosa e non cambia niente."""

    def test_ogni_chiave_compare_in_maker(self):
        sorgente = open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "maker.py"),
            encoding="utf-8").read()
        for chiave in CHIAVI:
            assert f'"{chiave}"' in sorgente, f"maker.py non legge mai '{chiave}'"

    def test_non_restano_costanti_grafiche_fisse(self):
        sorgente = open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "maker.py"),
            encoding="utf-8").read()
        for morta in ("Y_SOTTOTITOLI", "Y_BANNER", "Y_GAMEPLAY"):
            assert morta not in sorgente, f"{morta} e' tornata a essere fissa"
