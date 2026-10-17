# -*- coding: utf-8 -*-
"""Copia pubblica dello Short, per ripubblicarlo su TikTok senza toccarlo.

Su TikTok il video lo ripubblica la stanza degli agenti (davidedurazzi-sito,
cartella stanza/): il Direttore lo propone a Davide nel pannello e, se lui
approva, lo programma su Metricool. Metricool vuole il file a un indirizzo
pubblico, e lo Short esiste solo sul runner: qui lo si carica su Vercel Blob
e l'indirizzo finisce nella cronologia, accanto al video_id.

Senza BLOB_READ_WRITE_TOKEN non fa niente. Un errore qui non deve mai
fermare la pipeline: il video su YouTube e' gia' uscito.
"""
import os
from datetime import datetime, timedelta, timezone

import requests

API = "https://blob.vercel-storage.com"
VERSIONE_API = "9"          # quella di @vercel/blob 0.27
CARTELLA = "samaritan/"
GIORNI_TENUTA = 4           # il piano gratuito ha 1 GB: 4 video al giorno


def _token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()


def _intestazioni(token, **altre):
    h = {"authorization": f"Bearer {token}", "x-api-version": VERSIONE_API}
    h.update(altre)
    return h


def carica(percorso, nome, token):
    """Carica il file e restituisce l'indirizzo pubblico, o None."""
    with open(percorso, "rb") as f:
        r = requests.put(
            API + "/",
            params={"pathname": CARTELLA + nome},
            data=f,
            headers=_intestazioni(token, **{"x-content-type": "video/mp4",
                                            "x-add-random-suffix": "1"}),
            timeout=300,
        )
    if not r.ok:
        print(f"[Warning Copia] Vercel Blob HTTP {r.status_code}: {r.text[:200]}")
        return None
    return r.json().get("url")


def pulisci(token, adesso=None):
    """Cancella le copie piu' vecchie di GIORNI_TENUTA. Restituisce quante."""
    adesso = adesso or datetime.now(timezone.utc)
    limite = adesso - timedelta(days=GIORNI_TENUTA)
    vecchie, cursore = [], None
    for _ in range(20):
        params = {"prefix": CARTELLA, "limit": "1000"}
        if cursore:
            params["cursor"] = cursore
        r = requests.get(API + "/", params=params,
                         headers=_intestazioni(token), timeout=30)
        if not r.ok:
            print(f"[Warning Copia] Elenco Vercel Blob HTTP {r.status_code}")
            break
        j = r.json()
        for b in j.get("blobs", []):
            quando = datetime.fromisoformat(str(b.get("uploadedAt", "")).replace("Z", "+00:00"))
            if quando < limite:
                vecchie.append(b["url"])
        if not j.get("hasMore"):
            break
        cursore = j.get("cursor")
    if vecchie:
        requests.post(API + "/delete", json={"urls": vecchie},
                      headers=_intestazioni(token), timeout=30)
    return len(vecchie)


def prepara(percorso_video, video_id, dati):
    """Campi da aggiungere alla voce di cronologia, o {} se non si puo'."""
    token = _token()
    if not token or not video_id or not percorso_video:
        return {}
    try:
        url = carica(percorso_video, f"{video_id}.mp4", token)
        if not url:
            return {}
        campi = {"video_file_url": url}
        try:
            from brain import costruisci_didascalia_tiktok, normalizza_didascalia
            # Normalizzata anche qui, subito prima di finire in cronologia:
            # niente '\n' scritto per esteso ne' spazi doppi nel testo salvato.
            didascalia = normalizza_didascalia(costruisci_didascalia_tiktok(dati))
            if didascalia:
                campi["didascalia_tiktok"] = didascalia
        except Exception as e:
            print(f"[Warning Copia] Didascalia TikTok non preparata: {e}")
        try:
            pulisci(token)
        except Exception as e:
            print(f"[Warning Copia] Pulizia non riuscita: {e}")
        print(f"[Copia] Short pronto per TikTok: {url}")
        return campi
    except Exception as e:
        print(f"[Warning Copia] Copia pubblica non riuscita: {e}")
        return {}
