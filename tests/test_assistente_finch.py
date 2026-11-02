"""Test dell'assistente di Finch su Telegram (assistente_finch.py): tutto con finti."""
import assistente_finch as a


def test_compiti_da_approvare_filtra_per_stato():
    testo = '{"compiti":[{"titolo":"A","stato":"Da approvare"},{"titolo":"B","stato":"fatto"}]}'
    assert [c["titolo"] for c in a._compiti_da_approvare(testo)] == ["A"]
    assert a._compiti_da_approvare("non json") == []


def test_main_non_stampa_ne_domanda_ne_risposta(monkeypatch, capsys):
    for k, v in {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1",
                 "GROQ_API_KEY": "g", "FILE_ID": "f"}.items():
        monkeypatch.setenv(k, v)
    inviati = []
    monkeypatch.setattr(a, "scarica_vocale", lambda t, f: ("v.oga", b"x"))
    monkeypatch.setattr(a, "trascrivi", lambda c, n, au: "DOMANDA SEGRETA")
    monkeypatch.setattr(a, "costruisci_contesto", lambda: "ctx")
    monkeypatch.setattr(a, "rispondi", lambda c, d, ctx: "RISPOSTA SEGRETA")
    monkeypatch.setattr(a, "manda_voce", lambda t, ch, tx: inviati.append(("voce", tx)))
    a.main()
    fuori = capsys.readouterr()
    assert "SEGRETA" not in fuori.out + fuori.err
    assert inviati == [("voce", "RISPOSTA SEGRETA")]


def test_se_la_voce_cade_resta_il_testo(monkeypatch):
    for k, v in {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1",
                 "GROQ_API_KEY": "g", "FILE_ID": "f"}.items():
        monkeypatch.setenv(k, v)
    inviati = []
    monkeypatch.setattr(a, "scarica_vocale", lambda t, f: ("v.oga", b"x"))
    monkeypatch.setattr(a, "trascrivi", lambda c, n, au: "ciao")
    monkeypatch.setattr(a, "costruisci_contesto", lambda: "ctx")
    monkeypatch.setattr(a, "rispondi", lambda c, d, ctx: "ok")
    def guasta(*_): raise RuntimeError("giu")
    monkeypatch.setattr(a, "manda_voce", guasta)
    monkeypatch.setattr(a, "manda_testo", lambda t, ch, tx: inviati.append(tx))
    a.main()
    assert inviati == ["ok"]


def test_errore_avvisa_davide_senza_dettagli(monkeypatch):
    import pytest
    for k, v in {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1",
                 "GROQ_API_KEY": "g", "FILE_ID": "f"}.items():
        monkeypatch.setenv(k, v)
    inviati = []
    def guasta(*_): raise RuntimeError("dettaglio")
    monkeypatch.setattr(a, "scarica_vocale", guasta)
    monkeypatch.setattr(a, "manda_testo", lambda t, ch, tx: inviati.append(tx))
    with pytest.raises(SystemExit):
        a.main()
    assert "dettaglio" not in inviati[0]
