# Clip dalle live Twitch

Taglia gli Short dalle live di popponetv e li consegna a Finch, che decide
quali escono e quando. Gira sul PC, non su GitHub Actions.

```
PC: taglia_live.bat
  └─ VOD Twitch → momenti migliori → clip 9:16 con sottotitoli
       ├─ mp4  → Release "clip-AAAA-MM-GG" di samaritan_v2
       └─ JSON → clip_live/da_pubblicare/<id>.json  (stato "da_approvare")
Finch (ogni mattina alle 7:52)
  └─ voti dei revisori, titolo, orario → stato "approvato"
GitHub Actions: clip_live.yml
  └─ scarica l'mp4, lo carica su YouTube programmato → stato "pubblicato"
```

## Prima volta

1. **ffmpeg** nel PATH (lo stesso che usa gia' Samaritan).
2. **Token GitHub**: github.com → Settings → Developer settings →
   Fine-grained tokens → Generate. Repository: solo `samaritan_v2`.
   Permessi: *Contents: Read and write*. Copialo nel `.env` della cartella
   principale come `GITHUB_TOKEN_CLIP=`. Non incollarlo mai in chat.
3. **Chat (facoltativo ma consigliato)**: scarica TwitchDownloaderCLI da
   github.com/lay295/TwitchDownloader/releases e metti il percorso dell'exe
   in `TWITCHDOWNLOADER=`. Senza, i momenti si trovano solo dall'audio.
4. Doppio clic su `taglia_live.bat`: la prima volta prepara l'ambiente
   Python (cerca prima Python 3.12, piu' sicuro per faster-whisper).

## Uso

| Comando | Cosa fa |
|---|---|
| `taglia_live.bat` | taglia le ultime live non ancora fatte (massimo 2) |
| `taglia_live.bat --vod 123456789` | taglia una live precisa |
| `taglia_live.bat --prova` | monta le clip in `lavoro/` senza caricare niente |

Il primo giro fallo con `--prova` e guarda le clip in `taglia_live/lavoro/`.

Per farlo partire da solo ogni notte: Utilita' di pianificazione di Windows,
azione `taglia_live.bat`, e la variabile d'ambiente `CLIP_AUTO=1` cosi' la
finestra si chiude da sola alla fine.

## Cosa c'e' nella scheda

```json
{
  "id": "2345678901_03712", "titolo": "...", "descrizione": "...",
  "gioco": "Assetto Corsa", "data_live": "2026-10-15",
  "secondo_inizio_vod": 3712, "durata": 34, "punteggio": 78, "lingua": "it",
  "video_url": "https://api.github.com/repos/.../releases/assets/...",
  "stato": "da_approvare", "voti": {}, "orario": null, "youtube_id": null,
  "avvisi": [], "trascrizione": "..."
}
```

`avvisi` puo' contenere `insulti`, `dati_personali`, `utente_chat`: la clip
non viene scartata, ma il punteggio scende e Finch la vede in fondo.

`orario` lo mette Finch, in ISO 8601 (`2026-10-17T16:00:00+02:00`). Se manca
il fuso si intende ora italiana. Al massimo una clip per giorno: se due
approvate cadono lo stesso giorno esce la prima e l'altra resta ferma con
`avviso_pubblicazione`.

## Come trova i momenti

Vedi `punteggio.py`: energia dell'audio (urli, risate) piu' chat (messaggi al
secondo, e soprattutto reazioni come "ahah", "LUL", "clip"), con la chat
anticipata di 7 secondi perche' arriva in ritardo. Picchi distanti almeno
90 secondi, clip da 15 a 60 secondi: 22 di contesto prima del picco, 12 dopo.
