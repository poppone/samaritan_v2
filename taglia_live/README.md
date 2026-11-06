# Clip dalle live Twitch

Taglia gli Short dalle live Twitch del canale davidedurazzi e li consegna a Finch, che decide
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

## GPU

Whisper gira sulla GPU NVIDIA. All'avvio lo script la prova con un secondo di
audio: se non risponde **si ferma** con un errore che dice cosa manca, invece
di passare alla CPU (sulla CPU i sottotitoli uscivano confusi). cuBLAS e cuDNN
arrivano dai pacchetti pip `nvidia-cublas-cu12` e `nvidia-cudnn-cu12`
(in `requirements.txt`): lo script aggiunge da solo le loro cartelle `bin`,
non serve copiare DLL dentro `ctranslate2`. Per usare apposta la CPU:
`WHISPER_DISPOSITIVO=cpu` nel `.env`.

## Ascolto prima del voto

Con `--prova`, alla fine di ogni live `ascolta.py` riascolta l'audio vero di
ogni clip (con i bip) con un Whisper piu' grande (`WHISPER_MODELLO_ASCOLTO`,
default `large-v3-turbo`) e scrive `ascolto.md` nella cartella della live:
silenzio prima della prima parola, parole al secondo, quanto i sottotitoli
coincidono con quello che si sente, picchi di volume (reazioni). Le clip si
votano dopo averlo letto, non dai soli fotogrammi. A mano:
`python ascolta.py lavoro/<id della live>`.

Per farlo partire da solo ogni notte: Utilita' di pianificazione di Windows,
azione `taglia_live.bat`, e la variabile d'ambiente `CLIP_AUTO=1` cosi' la
finestra si chiude da sola alla fine.

## Versione lunga per TikTok

Il Creator Rewards Program di TikTok paga solo video di oltre un minuto. Per i
2 momenti migliori di ogni live (`CLIP_TIKTOK_PER_LIVE`, 0 per spegnere) lo
script monta anche una versione da 65-90 secondi, con id che finisce in `_tt`
e `"piattaforma": "tiktok"`. Finch la approva come le altre, ma
`clip_live_pubblica.py` non la carica su YouTube: la pubblica Davide da TikTok
Studio (o Metricool).

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

Ogni segnale si misura rispetto ai 10 minuti attorno, non alla media della
live: un'ora di chat fitta all'inizio (tutti salutano) non vince piu' sui
picchi veri. I messaggi di saluto ("ciao", "buonasera", "eccomi") non
contano. Nelle live oltre 90 minuti si saltano i primi 10 minuti e le clip
si spargono: al primo giro poche per ogni mezz'ora, poi si riempie.

## Impaginazione

La webcam cambia posto da gioco a gioco, quindi la si cerca clip per clip
(OpenCV, rilevatore YuNet, `impaginazione.py`):

- **volto piccolo** in un angolo (si gioca): webcam ingrandita in alto, gioco
  ritagliato in basso, sottotitoli sulla giunta;
- **volto grande** (Contraddittorio, chiacchiere): scena intera al centro su
  sfondo sfocato;
- **nessuna webcam** (alexdieci gioca senza facecam): il centro del gioco in
  3:4, 1080x1440, su sfondo sfocato, invece della scena intera alta 607 pixel.

La scelta finisce nella scheda (`"impaginazione": "divisa"` o `"centro"`).
Il modello YuNet (`modelli/face_detection_yunet_2023mar.onnx`, 230 KB) viene
da opencv_zoo, licenza MIT.
