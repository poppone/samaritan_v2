# -*- coding: utf-8 -*-
"""Test sulla notifica Telegram, che e' la strada per pubblicare su TikTok.

La pipeline pubblica da sola su YouTube; su TikTok il video lo carica lui a
mano, e l'unica cosa che glielo rende veloce e' trovarsi sul telefono il file
e la didascalia gia' pronta. Qui si verifica che quel secondo messaggio parta,
e soprattutto che non possa mai far saltare il resto.
"""
import config
import notifier


DATI = {
    "titolo": "GTA 6: la mappa che gira online e' falsa",
    "descrizione": "Due righe sul contenuto.\nE la domanda finale?",
    "gioco": "Grand Theft Auto VI",
    "stile": "MYTH_BUSTING_VIRAL",
    "fonte": "Rockstar smentisce la mappa (Everyeye)",
    "fonte_url": "https://news.example.com/gta6-mappa",
}


class TestDidascaliaTikTok:
    def test_non_invia_niente_se_telegram_non_e_configurato(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", False)
        assert notifier.invia_didascalia_tiktok(DATI) is False

    def test_manda_un_messaggio_copiabile(self, monkeypatch):
        inviati = []
        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", True)
        monkeypatch.setattr(notifier, "invia_messaggio",
                            lambda testo: inviati.append(testo) or True)

        assert notifier.invia_didascalia_tiktok(DATI) is True
        assert len(inviati) == 1
        # Il blocco <code> e' quello che su Telegram si copia toccandolo.
        assert "<code>" in inviati[0]
        assert "IA" in inviati[0]          # il promemoria dell'etichetta
        # Il titolo deve arrivare INTATTO: Telegram capisce solo &lt; &gt; e
        # &amp;, quindi un apostrofo trasformato in &#x27; resterebbe scritto
        # cosi' nel testo che lui incolla su TikTok.
        assert DATI["titolo"] in inviati[0]
        assert "&#x27;" not in inviati[0]

    def test_se_la_didascalia_non_esce_non_rompe_niente(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", True)
        monkeypatch.setattr(notifier, "_didascalia_tiktok", lambda dati: "")
        assert notifier.invia_didascalia_tiktok(DATI) is False

    def test_un_errore_dentro_brain_resta_dentro_brain(self, monkeypatch):
        # Il punto della modifica: se la didascalia esplode, la pipeline che
        # ha appena pubblicato su YouTube non se ne deve accorgere.
        def esplode(dati):
            raise RuntimeError("brain rotto")

        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", True)
        monkeypatch.setattr("brain.costruisci_didascalia_tiktok", esplode)
        assert notifier._didascalia_tiktok(DATI) == ""


class TestNotificaPubblicazione:
    def test_manda_prima_il_video_e_poi_la_didascalia(self, monkeypatch):
        ordine = []
        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", True)
        monkeypatch.setattr(notifier, "invia_video",
                            lambda p, d="": ordine.append("video") or True)
        monkeypatch.setattr(notifier, "invia_didascalia_tiktok",
                            lambda dati: ordine.append("tiktok") or True)

        notifier.notifica_pubblicazione(DATI, "abc123", "/tmp/non-esiste.mp4")
        assert ordine == ["video", "tiktok"]

    def test_la_didascalia_parte_anche_se_youtube_e_fallito(self, monkeypatch):
        # Il file locale c'e' lo stesso, quindi su TikTok e' ancora pubblicabile.
        ordine = []
        monkeypatch.setattr(config, "TELEGRAM_ATTIVO", True)
        monkeypatch.setattr(notifier, "invia_video", lambda p, d="": False)
        monkeypatch.setattr(notifier, "invia_messaggio",
                            lambda testo: ordine.append("testo") or True)
        monkeypatch.setattr(notifier, "invia_didascalia_tiktok",
                            lambda dati: ordine.append("tiktok") or True)

        notifier.notifica_pubblicazione(DATI, None, "/tmp/non-esiste.mp4")
        assert ordine == ["testo", "tiktok"]
