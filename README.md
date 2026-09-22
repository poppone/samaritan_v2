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
        veste.py     sceglie la veste grafica, diversa a ogni video
        maker.py     stacco ogni 2-3s, zoom, sfondo sfocato, sottotitoli
FASE 3  uploader.py  upload su YouTube
        notifier.py  notifica Telegram + didascalia pronta per TikTok
```

## E su TikTok?

Su TikTok Samaritan **non** pubblica da solo: servirebbe un'app registrata su
TikTok for Developers e la loro revisione, e finche' non la si supera tutto
cio' che l'API pubblica resta visibile solo a chi lo carica.

Il video pero' va bene per TikTok cosi' com'e' (verticale 1080x1920, MP4,
25-30 secondi), quindi a fine pipeline Telegram manda due messaggi: il file
del video e, subito sotto, la didascalia gia' pronta in un blocco che si copia
toccandolo. Caricarlo a mano sono trenta secondi.

La didascalia non e' la descrizione di YouTube: niente link al canale (su
TikTok non sono cliccabili) e niente righe di credito, solo titolo, un rigo di
contenuto e gli hashtag. Quando si pubblica va attivata a mano l'etichetta
"Contenuto generato dall'IA": su YouTube la dichiara `uploader.py`, su TikTok
no.

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

**La notizia si sceglie, non si sorteggia.** Quattro ricerche diverse su Google
News per lingua, quindici voci ciascuna, e poi una classifica: pesa il gioco
grosso, pesano le parole che dicono che la notizia e' viva (`esce`, `data`,
`gratis`, `leak`, `crossover`) e pesa il comparire in piu' di una ricerca, che
e' il segno che sta girando. La piu' alta arriva al modello per prima.

**E pesano soprattutto le parole che il pubblico cerca davvero.** Da YouTube
Analytics si legge cosa la gente ha scritto nella ricerca per finire su un
video del canale (`insightTrafficSourceDetail` filtrato su `YT_SEARCH`); i
termini si salvano in `performance.json` sotto `ricerche` e si scendono alle
parole, perche' nessuna notizia ripetera' mai la frase intera che qualcuno ha
digitato. Una notizia che tocca quelle parole sale. E' l'unico pezzo della
classifica che non e' un'ipotesi scritta a mano: il resto dice cosa pensiamo
interessi, questo dice cosa e' stato misurato. Quando il dato manca (token
senza permesso Analytics, canale nuovo) il punteggio resta quello di prima.

> Su questo rapporto `maxResults` **non puo' superare 25**. Chiedendone di piu'
> l'API non restituisce meno righe: fallisce tutta la richiesta con un 500 e
> `FIELD_UNKNOWN_VALUE` su `max-results`, che non somiglia per niente a un
> limite superato. E' costato una giornata di termini mancanti.

Insieme ai termini si legge anche **da dove arrivano le visualizzazioni**
(`insightTrafficSourceType`: feed Shorts, ricerca, suggeriti, home e
iscrizioni), salvato in `performance.json` sotto `sorgenti` e stampato nel log
in percentuale. Serve a sapere se lavorare sulla ricerca abbia senso: su un
canale di soli Short il pubblico puo' arrivare quasi tutto dal feed, e in quel
caso le parole cercate non sono il segnale da inseguire. E' una domanda a cui
si risponde coi numeri, non a intuito.

**Il materiale girato in casa.** In `clip_mie/<categoria>/` stanno gli spezzoni
registrati da popponetv: sono l'unico pezzo dei video che non arriva da uno
store, e sono anche la risposta piu' diretta alla regola YouTube sui contenuti
prodotti in serie. Si montano **solo nei video della loro categoria** — un
volante dentro una notizia su GTA 6 toglie piu' di quanto aggiunga — e la
categoria si ricava dal genere dichiarato da Steam o, quando il gioco su Steam
non c'e', dal nome del gioco. Ruotano come i trailer, cosi' due Short sullo
stesso gioco non aprono con la stessa clip. Istruzioni per aggiungerne in
`clip_mie/README.md`.

**Sullo stesso gioco non esce due volte lo stesso materiale.** Quanti Short
sono gia' usciti su quel titolo (contati sulla cronologia) decide da che punto
dell'elenco si comincia a pescare trailer e screenshot, e da che secondo del
trailer si taglia lo spezzone. I trailer principali scelti dall'editore
restano comunque davanti ai teaser: cambia il materiale, non la qualita'. Se
un trailer e' troppo corto per il taglio spostato, si ripiega sul punto
normale e poi sull'inizio, invece di perdere la sorgente.

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
| `GROQ_MODELLI` | opzionale: modelli da provare, separati da virgola |
| `PEXELS_API_KEY` | pexels.com/api (gratuita) |
| `ELEVENLABS_API_KEY` | elevenlabs.io/app/settings/api-keys (a consumo, opzionale) |
| `TELEGRAM_BOT_TOKEN` | @BotFather su Telegram (opzionale) |
| `TELEGRAM_CHAT_ID` | @userinfobot su Telegram (opzionale) |

> La voce prova tre motori in ordine: ElevenLabs, Edge-TTS, gTTS. ElevenLabs e'
> il piu' realistico ma si paga a caratteri; senza `ELEVENLABS_API_KEY` viene
> saltato e la voce resta quella Microsoft di prima, senza che nulla si rompa.
> La voce si sceglie con `ELEVENLABS_VOCE`, che accetta il nome come si legge
> sul sito (es. `Marco`) oppure l'id; vuoto significa la prima voce
> dell'account. Piu' nomi separati da virgola (es. `Marco, Giulia, Luca`)
> vengono alternati, un video a testa: Samaritan annota in
> `cronologia_trend.json` quale voce ha usato e il giro dopo passa alla
> successiva. L'annotazione arriva solo se ElevenLabs ha prodotto l'audio
> davvero, cosi' il campo `voce` dice con che voce parla il video e non quale
> era stata scelta; se e' entrato un ripiego, il turno non e' speso. Un nome che nell'account non esiste salta il proprio turno
> invece di far ripiegare tutto sulla voce Microsoft. Uno Short da 400 caratteri costa circa 400 crediti, quindi due
> video al giorno stanno dentro il piano da 30.000 al mese e non dentro quello
> gratuito da 10.000.

> Groq sposta i modelli fra i piani senza preavviso: quando quelli in uso
> diventano irraggiungibili la chiamata risponde `404 model_not_found`. In quel
> caso non serve toccare il codice, basta aggiornare `GROQ_MODELLI` con nomi
> presi da https://console.groq.com/docs/models. Il valore di default e'
> `openai/gpt-oss-120b,openai/gpt-oss-20b`, disponibili sul piano gratuito;
> `llama-3.3-70b-versatile` e `llama-3.1-8b-instant` sono passati a Enterprise
> il 18 settembre 2026.
>
> Se nessun modello risponde, Samaritan **non pubblica**: la pipeline fallisce
> con un errore invece di mandare online un testo di ripiego generico.

> `.env`, `client_secret.json` e `token.pickle` sono in `.gitignore` e non
> devono mai finire in un commit. Il test `tests/test_regressioni.py` lo
> verifica a ogni push: se uno di questi file torna sotto controllo di
> versione, la CI diventa rossa.

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

> **Nota per chi aveva gia' il repository prima del 18 settembre 2026**: fino a
> quella data `token.pickle` era committato per errore. Ora e' stato rimosso dal
> repository, quindi al primo `git pull` sparisce anche dalla tua cartella: e'
> normale, rifai il passaggio qui sopra. Quel vecchio token andrebbe anche
> revocato da https://myaccount.google.com/permissions, perche' resta comunque
> nella storia di git.

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

## 5. Test

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

I test coprono solo logica pura e non toccano la rete: riconoscimento del gioco
su Steam (il controllo che impedisce a 'Portal' di scaricare 'Portal 2'),
validazione dello script, punteggi e pesi dei formati, piu' alcune guardie di
regressione. Per questo `requirements-dev.txt` e' piu' leggero di
`requirements.txt`: niente torch, whisper e moviepy.

Girano da soli a ogni push e a ogni pull request
(`.github/workflows/test.yml`).

## 6. Automazione su GitHub Actions

```bash
python setup_secrets.py
```

Stampa i valori base64 da incollare in **Settings > Secrets and variables > Actions**:

**Secrets obbligatori**
`GROQ_API_KEY`, `PEXELS_API_KEY`, `CLIENT_SECRET_B64`, `YOUTUBE_TOKEN_B64`

**Secrets opzionali**
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Variables opzionali**
`NOME_CANALE`, `VOCE_TTS`, `VOCE_TTS_EN`, `WHISPER_MODEL`

**I video escono alle 14:00, alle 18:00 e alle 21:00 italiane**, sempre, anche
quando cambia l'ora legale. **Quello delle 21:00 e' in inglese**: stesso
canale, pubblico diverso, per misurare se l'inglese rende piu' dell'italiano
invece di deciderlo a naso. La lingua la passa il workflow con `LINGUA`, e una
run lanciata a mano la sceglie dal menu.

Le regole anti-ripetizione (apertura, gioco, notizia gia' usata) valgono
**dentro una lingua sola**: il video inglese deve poter raccontare la stessa
notizia grossa di quello italiano, perche' parla ad altra gente. Ogni voce di
`cronologia_trend.json` porta scritta la sua lingua; quelle vecchie, che non ce
l'hanno, contano come italiane.

L'orario NON viene dal cron. GitHub fa partire le run schedulate in ritardo, e
il ritardo non si puo' prevedere: fra il 17 e il 19 settembre 2026 e' andato da
un'ora e quaranta a tre ore e mezza. Quindi la pipeline parte con circa quattro
ore e mezza di anticipo (`30 7`, `30 11` e `30 14` UTC), carica il video privato e
chiede a YouTube di renderlo pubblico all'istante giusto: e' il campo
`publishAt`, e vale al minuto.

Per cambiare l'ora di uscita si cambia `ORARIO_USCITA` in
`.github/workflows/samaritan.yml`, un valore per ciascun cron; i cron si
toccano solo per allargare il margine. L'ora si calcola in ora italiana vera
(`FUSO_USCITA`, default `Europe/Rome`), quindi al cambio di stagione non c'e'
piu' niente da correggere a mano.

Se la run arriva talmente in ritardo da superare l'ora di uscita, il video
esce subito invece di aspettare il giorno dopo.

### La riserva di fine giornata

Il 21 settembre 2026 GitHub ha fatto partire una run con sette ore di ritardo e
un'altra non l'ha fatta partire affatto: il video delle 21:00 non e' mai
uscito. Il codice non c'entrava, ma il canale un video l'ha perso lo stesso.

Da qui un quarto cron (`30 20` UTC, verso le 22:30 italiane) che non produce un
video suo. Guarda quali delle tre uscite di oggi sono rimaste scoperte e rifa'
la piu' vecchia, una sola, pubblicandola subito; se sono tutte a posto termina
in pochi secondi senza fare niente. Si puo' lanciare anche a mano, dalla tab
Actions, spuntando `recupero`.

Perche' questo non produca doppioni ogni lavorazione dichiara quale uscita sta
coprendo (`SLOT`, che finisce in `cronologia_trend.json`) e si ferma se quella
uscita ha gia' il suo video. Un video conta come pubblicato solo quando ha un
`video_id`: una lavorazione morta prima del caricamento lascia l'uscita
scoperta, che e' esattamente il caso in cui la riserva deve intervenire.

L'elenco delle uscite sta in `orari.py` (`SLOT_GIORNALIERI`) e nei cron del
workflow: sono due copie della stessa cosa, e un test controlla che dicano lo
stesso.

Le run lanciate a mano dalla tab Actions (dove puoi anche scegliere tema e
visibilita') non programmano niente: escono subito.

---

## Come viene confezionato il video

Lo script e' meta' del lavoro: l'altra meta' e' quello che rende il video
raggiungibile. `brain.py` confeziona tutto e `valida_titolo()` blocca quello
che non rispetta le regole, rigenerando invece di pubblicare.

**Titolo** (`valida_titolo`, un titolo bocciato viene riscritto, non caricato):

| Regola | Perche' |
|---|---|
| massimo 60 caratteri | oltre, il feed Shorts da telefono tronca proprio la fine |
| il gioco dev'essere nominato | senza, il video non e' raggiungibile dalla ricerca |
| niente maiuscolo integrale | YouTube lo tratta come titolo spam |
| una sola emoji, in fondo | in apertura ruba il posto alla keyword |
| niente `#Shorts` | YouTube riconosce il formato verticale da solo |

Le sigle sono riconosciute: un titolo che dice "GTA 6" soddisfa la regola
anche se il nome ufficiale del gioco e' "Grand Theft Auto VI".

**Descrizione** (`costruisci_descrizione`): due righe generate, poi il LINK
della notizia (non solo il nome della testata), l'attribuzione del materiale,
la dichiarazione di contenuto sintetico, il link al canale e tre hashtag che
cambiano col video. Il primo hashtag e' l'unico che YouTube mostra sopra al
titolo, quindi ci va il gioco.

**Tag** (`costruisci_tag`): quattro fissi piu' il nome del canale, piu' quelli
che cambiano (gioco, saga senza il numero, gioco + tema). Tag identici su ogni
upload sono una delle impronte che fanno riconoscere un canale automatizzato.

**Miniatura** (`maker.crea_miniatura`): tre o quattro parole dell'amo, grandi,
su un fotogramma scurito dello sfondo, caricate insieme al video. Senza,
YouTube estrae un fotogramma a caso: nel feed non cambia niente, nella griglia
del canale e nella ricerca si vede eccome. Serve il canale verificato via
telefono: se non lo e', YouTube risponde 403 e il video sale lo stesso senza
miniatura.

**Veste grafica** (`veste.py`): colori dei sottotitoli, altezza a cui
compaiono, corpo del testo, presenza e posizione del banner del titolo,
spessore e colore della barra di avanzamento, verso dello zoom, velocita' degli
stacchi. Non e' una sola: ce ne sono cinque e ruotano, una per video. Due Short
di fila non hanno mai lo stesso aspetto, e non e' una questione estetica: un
canale i cui video sono tutti visivamente identici e' il profilo che YouTube
chiama "contenuto ripetitivo" e non ammette alla monetizzazione.

La rotazione si ricorda dove e' arrivata scrivendo il nome della veste in
`cronologia_trend.json`, e lo scrive solo a rendering riuscito: se il video non
esce, quella veste non e' spesa e tocca a lei il giro dopo. Aggiungere o
togliere vesti significa modificare la lista `VESTI`; `tests/test_veste.py`
boccia le combinazioni in cui il testo finirebbe fuori dallo schermo o sotto i
comandi di YouTube.

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
| `HANDLE_CANALE` | handle YouTube, finisce nella descrizione di ogni video |
| `USA_STEAM` | `0` per tornare allo stock generico invece del gameplay reale |
| `ZOOM_GAMEPLAY` | quanto ingrandire il riquadro di gameplay (1.0 = larghezza piena) |
| `STEAM_MAX_TRAILER` / `STEAM_MAX_SCREENSHOT` | quanto materiale scaricare per video |
| `MAX_CLIP_MIE` | quante clip girate in casa entrano in uno Short (2) |

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
