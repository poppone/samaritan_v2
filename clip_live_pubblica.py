# -*- coding: utf-8 -*-
"""
Pubblica su YouTube le clip delle live che Finch ha approvato.

Gira nel workflow clip_live.yml a ogni push su clip_live/da_pubblicare/.
Le schede le scrive taglia_live (stato "da_approvare"); Finch le porta a
"approvato" e mette l'orario. Qui si pubblica SOLO cio' che e':
  - stato "approvato",
  - con un orario,
  - senza youtube_id (non ancora caricata),
  - con un video_url da cui scaricare l'mp4,
  - non marcata "piattaforma": "tiktok" (le versioni lunghe da 65-90 secondi
    sono per TikTok: le pubblica Davide o Metricool, non questo script).
Al massimo una clip per giorno di uscita, come ha deciso Finch: se due
approvate cadono nello stesso giorno esce la prima, l'altra resta ferma con
un avviso.

A differenza degli Short di Samaritan qui la dichiarazione di contenuto
sintetico e' False: voce e faccia sono di popponetv, non generate.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

DIR_PROGETTO = os.path.dirname(os.path.abspath(__file__))
CARTELLA = os.path.join(DIR_PROGETTO, "clip_live", "da_pubblicare")
FUSO = ZoneInfo("Europe/Rome")
# YouTube vuole publishAt nel futuro: sotto questo margine si pubblica subito.
MARGINE = timedelta(minutes=15)
TAG_BASE = ["popponetv", "twitch", "live", "gaming", "shorts"]
SITO = "https://www.davidedurazzi.it"


def leggi_schede(cartella=CARTELLA):
    schede = []
    if not os.path.isdir(cartella):
        return schede
    for nome in sorted(os.listdir(cartella)):
        if not nome.endswith(".json"):
            continue
        percorso = os.path.join(cartella, nome)
        with open(percorso, encoding="utf-8") as f:
            schede.append((percorso, json.load(f)))
    return schede


def leggi_orario(valore):
    """ISO 8601. Senza fuso si intende ora italiana."""
    if not valore:
        return None
    orario = datetime.fromisoformat(str(valore).replace("Z", "+00:00"))
    if orario.tzinfo is None:
        orario = orario.replace(tzinfo=FUSO)
    return orario


def da_pubblicare(schede):
    """Le schede da caricare adesso, in ordine di orario, una per giorno."""
    pronte, giorni_occupati = [], set()
    for _p, s in schede:
        if s.get("stato") == "pubblicato" and s.get("orario"):
            giorni_occupati.add(leggi_orario(s["orario"]).astimezone(FUSO).date())
    candidate = []
    for percorso, s in schede:
        if (s.get("stato") == "approvato" and s.get("orario")
                and not s.get("youtube_id") and s.get("video_url")
                and s.get("piattaforma", "youtube") != "tiktok"):
            candidate.append((leggi_orario(s["orario"]), percorso, s))
    candidate.sort(key=lambda c: c[0])
    rimandate = []
    for orario, percorso, s in candidate:
        giorno = orario.astimezone(FUSO).date()
        if giorno in giorni_occupati:
            rimandate.append((percorso, s))
            continue
        giorni_occupati.add(giorno)
        pronte.append((orario, percorso, s))
    return pronte, rimandate


def scarica(url, destinazione, token=None):
    import requests
    intestazioni = {}
    if "api.github.com" in url:
        intestazioni["Accept"] = "application/octet-stream"
        if token:
            intestazioni["Authorization"] = f"Bearer {token}"
    with requests.get(url, headers=intestazioni, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(destinazione, "wb") as f:
            for pezzo in r.iter_content(1024 * 1024):
                f.write(pezzo)


def tag_della(scheda):
    tag = list(TAG_BASE)
    gioco = (scheda.get("gioco") or "").strip()
    if gioco:
        tag.insert(0, gioco)
    return tag


def descrizione_con_sito(scheda):
    """La descrizione della scheda con il link alla home di davidedurazzi.it.

    Una clip della live non ha un articolo suo: porta alla home, con gli UTM
    per vedere nelle statistiche del sito chi arriva dalle clip. Il link sta
    dopo il primo paragrafo, prima di "altro". Se c'e' gia' non si ripete.
    """
    descrizione = scheda.get("descrizione") or ""
    if "davidedurazzi.it" in descrizione:
        return descrizione
    url = SITO + "/?" + urlencode({
        "utm_source": "youtube",
        "utm_medium": "short",
        "utm_campaign": f"clip-live-{scheda.get('id') or 'senza-id'}",
    })
    riga = f"Notizie e approfondimenti: {url}"
    primo, sep, resto = descrizione.partition("\n\n")
    if not sep:
        return f"{descrizione}\n\n{riga}" if descrizione else riga
    return f"{primo}\n\n{riga}\n\n{resto}"


def salva(percorso, scheda):
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(scheda, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _avvisa(testo):
    try:
        import notifier
        notifier.invia_messaggio(testo)
    except Exception as e:
        print(f"[Telegram] {e}")


def main():
    pronte, rimandate = da_pubblicare(leggi_schede(CARTELLA))
    for percorso, s in rimandate:
        s["avviso_pubblicazione"] = ("Un'altra clip esce gia' lo stesso giorno: "
                                     "cambia l'orario per pubblicarla.")
        salva(percorso, s)
        print(f"[Rimandata] {s['id']}: giorno gia' occupato")
    if not pronte:
        print("Nessuna clip approvata da pubblicare.")
        return 0

    import uploader
    token = os.getenv("GITHUB_TOKEN")
    adesso = datetime.now(FUSO)
    errori = 0
    for orario, percorso, s in pronte:
        quando = orario if orario - adesso > MARGINE else None
        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, f"{s['id']}.mp4")
            try:
                scarica(s["video_url"], video, token)
                video_id = uploader.carica_short(
                    video, s["titolo"], descrizione_con_sito(s),
                    tag=tag_della(s), privacy="public",
                    pubblica_alle=quando, contenuto_sintetico=False)
            except Exception as e:
                video_id = None
                print(f"[Errore] {s['id']}: {e}")
        if not video_id:
            errori += 1
            s["avviso_pubblicazione"] = "Caricamento fallito, vedi i log del workflow."
            salva(percorso, s)
            _avvisa(f"Clip live {s['id']}: caricamento su YouTube fallito.")
            continue
        s["youtube_id"] = video_id
        s["stato"] = "pubblicato"
        s["caricato_il"] = adesso.isoformat(timespec="seconds")
        s.pop("avviso_pubblicazione", None)
        salva(percorso, s)
        ora = f"alle {orario.astimezone(FUSO):%H:%M del %d/%m}" if quando else "subito"
        _avvisa(f"Clip live in uscita {ora}: {s['titolo']}\n"
                f"https://youtube.com/shorts/{video_id}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
