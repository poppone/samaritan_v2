"""L'assistente di Finch su Telegram: risponde ai vocali di Davide.

Il Worker di Cloudflare (telegram/worker.js) riceve il vocale e lancia questo
programma passandogli solo l'identificativo del file (FILE_ID). Qui il vocale
si scarica, si trascrive con Groq, si risponde leggendo i file della stanza
(bacheca, guardiano, ultimo verbale) e la risposta torna su Telegram, scritta
e a voce con la voce gratuita di Edge-TTS.

Non e' Finch con tutta la sua memoria: e' un assistente leggero, sempre
dichiarato come intelligenza artificiale. Non esegue azioni: pubblicare,
spendere o mandare email resta a Finch e a Davide.

ATTENZIONE: il repository e' pubblico e i log delle lavorazioni anche. Il testo
del vocale e la risposta non vanno mai stampati: qui si stampano solo gli esiti.
"""
import asyncio
import json
import os
import sys

import requests

REPO_STANZA = "poppone/davidedurazzi-sito"
RAW = f"https://raw.githubusercontent.com/{REPO_STANZA}/main"
API_STANZA = f"https://api.github.com/repos/{REPO_STANZA}/contents/stanza/diario"
MODELLO_TRASCRIZIONE = os.environ.get("ASSISTENTE_MODELLO_TRASCRIZIONE") or "whisper-large-v3-turbo"
MODELLI_RISPOSTA = [m.strip() for m in (os.environ.get("GROQ_MODELLI") or
                    "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
VOCE = os.environ.get("FINCH_VOCE") or "it-IT-GiuseppeNeural"
LIMITE_FILE = 5 * 1024 * 1024
LIMITE_RISPOSTA = 700
LIMITE_CONTESTO = 7000

ISTRUZIONI = (
    "Sei l'assistente di Finch, il direttore della stanza degli agenti di "
    "Davide Durazzi. Sei un'intelligenza artificiale e lo dici se te lo chiedono. "
    "Rispondi in italiano, in modo breve (al massimo 600 caratteri), gentile e "
    "senza fretta: Davide e' spesso stanco. Usa SOLO i dati qui sotto; se non "
    "lo sai, dillo. Non inventare numeri. Non esegui azioni: se Davide chiede "
    "di pubblicare, mandare email, spendere o cambiare qualcosa, rispondi che "
    "lo deve scrivere a Finch nel thread della stanza. Non parlare di chiavi "
    "o password."
)


def _scarica_testo(url):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "assistente-finch"})
        return r.text if r.ok else ""
    except requests.RequestException:
        return ""


def _compiti_da_approvare(testo):
    try:
        dati = json.loads(testo)
    except ValueError:
        return []
    voci = dati if isinstance(dati, list) else dati.get("compiti", [])
    return [v for v in voci if isinstance(v, dict)
            and str(v.get("stato", "")).lower() == "da approvare"]


def costruisci_contesto():
    """Cosa sa l'assistente: compiti per Davide, guardiano e ultimo verbale."""
    parti = []
    compiti = _compiti_da_approvare(_scarica_testo(f"{RAW}/stanza/bacheca.json"))
    if compiti:
        righe = [f"- {str(c.get('titolo', 'compito'))[:120]}" for c in compiti[:10]]
        parti.append("Compiti da approvare per Davide:\n" + "\n".join(righe))
    else:
        parti.append("Compiti da approvare per Davide: nessuno.")
    try:
        g = json.loads(_scarica_testo(f"{RAW}/stanza/guardiano.json"))
        problemi = [f"- {c['nome']}: {c['esito']}" for c in g.get("controlli", [])
                    if c.get("esito") != "ok"][:8]
        parti.append(f"Guardiano: {g.get('riassunto')}\n" + "\n".join(problemi))
    except (ValueError, TypeError, KeyError):
        pass
    try:
        elenco = requests.get(API_STANZA, timeout=20,
                              headers={"User-Agent": "assistente-finch"}).json()
        ultimo = sorted(f["name"] for f in elenco if f["name"].endswith(".md"))[-1]
        verbale = _scarica_testo(f"{RAW}/stanza/diario/{ultimo}")
        parti.append(f"Ultimo verbale ({ultimo}):\n{verbale[:2500]}")
    except (ValueError, TypeError, KeyError, IndexError, requests.RequestException):
        pass
    return "\n\n".join(parti)[:LIMITE_CONTESTO]


def scarica_vocale(token, file_id):
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    info = r.json()["result"]
    if info.get("file_size", 0) > LIMITE_FILE:
        raise RuntimeError("vocale troppo grande")
    f = requests.get(f"https://api.telegram.org/file/bot{token}/{info['file_path']}",
                     timeout=60)
    f.raise_for_status()
    return os.path.basename(info["file_path"]), f.content


def trascrivi(chiave, nome, audio):
    from groq import Groq
    esito = Groq(api_key=chiave).audio.transcriptions.create(
        file=(nome, audio), model=MODELLO_TRASCRIZIONE, language="it")
    return (esito.text or "").strip()


def rispondi(chiave, domanda, contesto):
    from groq import Groq
    client = Groq(api_key=chiave)
    ultimo_errore = None
    for modello in MODELLI_RISPOSTA:
        try:
            r = client.chat.completions.create(
                model=modello, temperature=0.3, max_tokens=600,
                messages=[
                    {"role": "system", "content": f"{ISTRUZIONI}\n\nDATI:\n{contesto}"},
                    {"role": "user", "content": domanda},
                ])
            testo = (r.choices[0].message.content or "").strip()
            if testo:
                return testo[:LIMITE_RISPOSTA]
        except Exception as e:  # noqa: BLE001 - si prova il modello dopo
            ultimo_errore = type(e).__name__
    raise RuntimeError(f"nessun modello ha risposto ({ultimo_errore})")


async def _sintetizza(testo, percorso):
    import edge_tts
    await edge_tts.Communicate(text=testo, voice=VOCE).save(percorso)


def manda_testo(token, chat, testo):
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat, "text": testo}, timeout=30)


def manda_voce(token, chat, testo):
    percorso = "risposta_finch.mp3"
    asyncio.run(_sintetizza(testo, percorso))
    with open(percorso, "rb") as audio:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendAudio",
                          data={"chat_id": chat, "title": "Finch", "performer": "Assistente di Finch",
                                "caption": testo[:1024]},
                          files={"audio": audio}, timeout=60)
    r.raise_for_status()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    chiave = os.environ.get("GROQ_API_KEY")
    file_id = (os.environ.get("FILE_ID") or "").strip()
    if not (token and chat and chiave and file_id):
        sys.exit("Mancano TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY o FILE_ID")
    try:
        nome, audio = scarica_vocale(token, file_id)
        domanda = trascrivi(chiave, nome, audio)
        if not domanda:
            manda_testo(token, chat, "Non ho sentito niente nel vocale, riprova.")
            print("[Assistente] Vocale vuoto")
            return
        risposta = rispondi(chiave, domanda, costruisci_contesto())
    except Exception as e:  # noqa: BLE001 - Davide deve sapere che non e' andata
        manda_testo(token, chat, "Non sono riuscito a rispondere al vocale. "
                    "Scrivimi nel thread della stanza, ti rispondo li'.")
        sys.exit(f"[Assistente] Errore: {type(e).__name__}")
    try:
        manda_voce(token, chat, risposta)
        print("[Assistente] Risposta inviata a voce")
    except Exception as e:  # noqa: BLE001 - se la voce cade, resta il testo
        manda_testo(token, chat, risposta)
        print(f"[Assistente] Voce non riuscita ({type(e).__name__}): risposta inviata scritta")


if __name__ == "__main__":
    main()
