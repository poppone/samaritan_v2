# Samaritan

Sistema automatico di produzione e pubblicazione di YouTube Shorts gaming.

Non e' solo un generatore: misura la retention reale dei video pubblicati e
usa quei dati per decidere cosa produrre dopo.

```
FASE 0  analyst.py   scarica la retention reale degli ultimi 90 giorni
FASE 1  brain.py     sceglie il formato (pesato sui dati) e scrive lo script
                     ancorandolo a notizie gaming VERE
FASE 2  gameplay.py  trailer e screenshot UFFICIALI del gioco da Steam
        voice.py     voce neurale Edge-TTS
        maker.py     stacco ogni 2-3s, zoom, sfondo sfocato, sottotitoli
FASE 3  uploader.py  upload su YouTube
        notifier.py  notifica Telegram
```

## Da dove viene il gameplay

`brain.py` identifica il gioco esatto di cui parla lo Short. `gameplay.py` lo
cerca su Steam e scarica **trailer e screenshot ufficiali di quel gioco**.

Sono asset che l'editore pubblica apposta per essere diffusi, quindi non c'e'
niente da rubare. L'audio originale viene sempre scartato e sostituito dalla
voce sintetica: e' l'audio il canale su cui il Content ID rivendica quasi
sempre, quindi il rischio residuo e' basso.

**Scaricare gameplay da YouTube e' stato scartato di proposito**, anche con
licenza Creative Commons: viola i Termini di Servizio di YouTube, cioe' della
piattaforma stessa su cui il canale deve monetizzare.

Se il gioco non e' su Steam (Minecraft, Fortnite, un titolo non ancora uscito),
Samaritan **rifiuta il ripiego sul gioco sbagliato** e usa stock Pexels. Un
controllo sul numero di capitolo impedisce che 'Grand Theft Auto V' finisca per
scaricare gameplay di 'Grand Theft Auto IV', o 'Portal' quello di 'Portal 2'.

I trailer Steam sono 16:9: vengono montati dentro il 9:16 con sfondo sfocato
ricavato dal frame stesso, che e' il formato standard degli Shorts gaming.

---

## 1. Installazione

```bash
pip install -r requirements.txt
```

Serve anche **FFmpeg** nel PATH:
- Windows: `winget install Gyan.FFmpeg`
- Linux: `sudo apt install ffmpeg`

## 2. Configurazione

```bash
cp .env.example .env
```

Poi compila `.env`:

| Variabile | Dove ottenerla |
|---|---|
| `GROQ_API_KEY` | console.groq.com (gratuita) |
| `PEXELS_API_KEY` | pexels.com/api (gratuita) |
| `TELEGRAM_BOT_TOKEN` | @BotFather su Telegram (opzionale) |
| `TELEGRAM_CHAT_ID` | @userinfobot su Telegram (opzionale) |

> `.env`, `client_secret.json` e `token.pickle` sono in `.gitignore`.
> Non finiranno mai su GitHub.

## 3. Autenticazione YouTube (una sola volta)

Metti `client_secret.json` (da Google Cloud Console, OAuth Desktop App) nella
cartella, poi:

```bash
python -c "from uploader import ottieni_credenziali; ottieni_credenziali()"
```

Si apre il browser: autorizza il canale. Viene creato `token.pickle`.

> **Se stai aggiornando da una versione precedente**: cancella il vecchio
> `token.pickle` e rifai questo passaggio. Il nuovo token include lo scope
> `yt-analytics.readonly`, senza il quale il feedback loop non funziona.

## 4. Uso

```bash
python main.py                          # tema libero
python main.py "easter egg nascosti"    # tema specifico

python brain.py                         # solo lo script, senza produrre nulla
python voice.py                         # prova la voce
python gameplay.py "Cyberpunk 2077"     # prova il download del gameplay
python maker.py                         # produci il video senza caricarlo
python analyst.py                       # report performance e pesi dei formati
```

## 5. Automazione su GitHub Actions

```bash
python setup_secrets.py
```

Stampa i valori base64 da incollare in **Settings > Secrets and variables > Actions**:

**Secrets obbligatori**
`GROQ_API_KEY`, `PEXELS_API_KEY`, `CLIENT_SECRET_B64`, `YOUTUBE_TOKEN_B64`

**Secrets opzionali**
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Variables opzionali**
`NOME_CANALE`, `VOCE_TTS`, `WHISPER_MODEL`

Il workflow parte alle 14:00 e alle 20:00 ora italiana, oppure a mano dalla
tab Actions (dove puoi anche scegliere tema e visibilita').

---

## Personalizzazione rapida

Tutto si regola da `.env`, senza toccare il codice:

| Variabile | Effetto |
|---|---|
| `VOCE_TTS` | `it-IT-DiegoNeural`, `it-IT-IsabellaNeural`, `it-IT-GiuseppeNeural` |
| `VOCE_VELOCITA` | `+12%` di default. Piu' alto = piu' concitato |
| `STACCO_MIN` / `STACCO_MAX` | durata degli stacchi di montaggio |
| `NUM_CLIP_SFONDO` | quante clip diverse scaricare |
| `WHISPER_MODEL` | `tiny` (veloce, impreciso) / `base` / `small` (lento, preciso) |
| `PRIVACY_STATUS` | `public` = pubblica subito, `private` = aspetta la tua OK |
| `USA_STEAM` | `0` per tornare allo stock generico invece del gameplay reale |
| `ZOOM_GAMEPLAY` | quanto ingrandire il riquadro di gameplay (1.0 = larghezza piena) |
| `STEAM_MAX_TRAILER` / `STEAM_MAX_SCREENSHOT` | quanto materiale scaricare per video |

I formati video si modificano nel dizionario `FORMATI_VIDEO` in `brain.py`.

---

## Note su policy e monetizzazione

- I video sono dichiarati correttamente come contenuti sintetici
  (`containsSyntheticMedia: True`). Dichiararlo NON penalizza; dichiarare il
  falso e' una violazione.
- `brain.py` impedisce al modello di inventare leak o date di uscita: i
  formati factual accettano solo notizie realmente scaricate dall'RSS, con la
  fonte citata in descrizione.
- Gli Shorts monetizzano pochissimo (0,01-0,04 EUR ogni 1000 views in Italia).
  Servono a far crescere gli iscritti: il ricavo vero arriva da affiliazioni,
  sponsor e video long-form.
- Attivare Telegram e guardare 10 secondi di ogni video prima che vada online
  e' la differenza tra "contenuto assistito dall'AI" e "contenuto
  mass-produced". La seconda categoria non e' monetizzabile.
