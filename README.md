# Samaritan

Sistema automatico di produzione e pubblicazione di video gaming su YouTube:
quattro Short verticali al giorno, due in italiano e due in inglese, e a
richiesta un video lungo 16:9 da otto minuti.

Non e' solo un generatore: misura la retention reale dei video pubblicati e
usa quei dati per decidere cosa produrre dopo.

> **Hai Samaritan per il tuo canale?** Non ti serve niente di questo file: si
> installa da una pagina web, `installa/index.html`, senza terminale e senza
> toccare il codice. I passi, spiegati per chi non programma, sono in
> [GUIDA_CLIENTE.md](GUIDA_CLIENTE.md). Per pubblicare la pagina chi possiede
> il repository modello deve segnarlo come *Template repository* e accendere
> GitHub Pages (vedi [Installazione per i clienti](#installazione-per-i-clienti)).

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

Sul video lungo la FASE 1 la fa `lungo.py` invece di `brain.py`: scaletta,
una sezione per volta, e un pezzo di audio per sezione da cui escono i
capitoli veri. Il resto del percorso e' identico.

## Il video lungo, e perche' esiste

YouTube ha **due** porte per il programma partner, e un canale di soli Short
ne puo' aprire una sola:

| | Serve | Il canale oggi |
|---|---|---|
| Short | 1.000 iscritti + **10 milioni** di visualizzazioni Short in 90 giorni | ~1.400 al giorno, servirebbero ~111.000 |
| Video lunghi | 1.000 iscritti + **4.000 ore** di visione pubbliche in 12 mesi | un video al giorno da otto minuti ci arriva con ~250-300 visualizzazioni vere al giorno |

Le ore guardate sugli Short **non contano** per la soglia delle 4.000 ore. Su
questi numeri la prima porta e' fuori portata di due ordini di grandezza e la
seconda no: per questo dal 22 settembre 2026 usciva anche un video lungo al
giorno, alle 20:00 italiane. **Dal 27 settembre 2026 non esce piu' da solo**:
i tre pubblicati hanno fatto 6, 0 e 0 visualizzazioni, quindi zero ore verso
la soglia. Si lancia a mano (`lungo` dal pulsante Run workflow, o `/lungo`
da Telegram).

Come e' fatto (`lungo.py`):

- **Si scrive a sezioni, non in un colpo solo.** Prima una scaletta (titolo,
  gioco, e per ogni sezione il suo titolo e cosa deve dire), poi una chiamata
  al modello per ogni sezione, ognuna sapendo come finiva la precedente. Otto
  minuti sono circa 1.200 parole: chiederle in una risposta sola significa
  farsi troncare a meta'.
- **I capitoli sono timestamp veri.** Ogni sezione ha il suo pezzo di audio,
  quindi la sua durata e' misurata e non stimata, e i capitoli finiscono in
  cima alla descrizione YouTube. Se non sono validi (meno di tre, il primo non
  a 00:00, due a meno di dieci secondi l'uno dall'altro) non vengono scritti
  affatto: YouTube in quel caso li ignorerebbe tutti.
- **Trailer ufficiali interi.** `config.SECONDI_TRAILER` passa da 45 secondi a
  quattro minuti, e i trailer scaricati da tre a sei: con spezzoni corti le
  stesse inquadrature tornerebbero sei o sette volte nello stesso video.
- **Sottotitoli a frase**, in basso, non una parola per volta al centro. Su
  otto minuti la forma dello Short vorrebbe oltre mille clip sovrapposti.
- **Le clip girate in casa contano di piu'**: `MAX_CLIP_MIE` passa da 2 a 8. E'
  li' che un video lungo smette di sembrare un montaggio automatico.

Da dove NON viene il materiale: da YouTube. Prendere spezzoni di gameplay dai
video di altri e' quello che fa bocciare la domanda di monetizzazione
("contenuti riutilizzati" piu' copyright), ed e' il controllo che si fa
proprio nel momento in cui si presenta la domanda. Le fonti restano due:
trailer e screenshot ufficiali degli store, e le registrazioni di popponetv in
`clip_mie/`.

Per provarlo a mano: tab Actions, **Run workflow**, spunta `lungo` e metti
`privacy` su `private`.

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

Al posto degli ultimi due vanno bene anche `YOUTUBE_CLIENT_ID`,
`YOUTUBE_CLIENT_SECRET` e `YOUTUBE_REFRESH_TOKEN`, che sono quelli che scrive
la pagina di installazione: niente file, niente pickle. Se ci sono tutti e due
i modi vince il pickle.

**Secrets opzionali**
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Variables opzionali**
`NOME_CANALE`, `VOCE_TTS`, `VOCE_TTS_EN`, `WHISPER_MODEL`

**I video di Poppone TV escono alle 14:00, alle 18:00, alle 20:00 e alle 21:00
italiane**, sempre, anche quando cambia l'ora legale. Sono le `uscite` del
profilo predefinito: un altro canale le sceglie in `canale.json` (vedi sotto).

- 14:00 e 18:00: Short in italiano.
- **20:00 e 21:00: Short in inglese**, stesso canale, pubblico diverso.
  Fino al 27 settembre 2026 alle 20:00 usciva il video lungo; i tre usciti
  hanno fatto 6, 0 e 0 visualizzazioni, e l'inglese rendeva almeno quanto
  l'italiano. Il lungo resta lanciabile a mano.

Orario e lingua di ogni uscita li legge `config.py` dal profilo del canale;
il formato lo passa il workflow con `VIDEO_LUNGO`. Una run lanciata a mano li
sceglie dal menu.

Quattro caricamenti al giorno stanno sotto il tetto di YouTube, che e' di sei
(la quota giornaliera dell'API e' 10.000 unita' e ogni caricamento ne costa
1.600).

Le regole anti-ripetizione (apertura, gioco, notizia gia' usata) valgono
**dentro una lingua sola**: il video inglese deve poter raccontare la stessa
notizia grossa di quello italiano, perche' parla ad altra gente. Ogni voce di
`cronologia_trend.json` porta scritta la sua lingua; quelle vecchie, che non ce
l'hanno, contano come italiane.

L'orario NON viene dal cron. GitHub fa partire le run schedulate in ritardo, e
il ritardo non si puo' prevedere: il 28 settembre 2026 e' arrivato a otto ore.
Quindi la pipeline parte di notte, dieci-tredici ore prima dell'uscita (`17 1`,
`17 3`, `17 5` e `17 6` UTC), carica il video privato e
chiede a YouTube di renderlo pubblico all'istante giusto: e' il campo
`publishAt`, e vale al minuto.

I quattro cron sono quattro **partenze** fisse, numerate da 1 a 4; il
workflow dice alla pipeline solo quale partenza e' (`USCITA_CRON`). Quale
uscita copre ciascuna lo decide `profilo.py` (`abbina_cron`) a partire dalle
`uscite` del profilo, controllando che ogni uscita cada fra
`MARGINE_MINIMO_ORE` (8) e `ANTICIPO_PARTENZA_ORE` (16) ore dopo la sua
partenza, con l'ora legale e senza. Una partenza che non ha un'uscita si ferma
in pochi secondi nel job `uscita`, prima di installare qualunque cosa. Per
cambiare un orario si cambia `canale.json`, non il workflow; i cron si toccano
solo per allargare il margine, e in quel caso va aggiornato anche
`profilo.CRON_USCITE` (un test li confronta). L'ora si calcola nel `fuso` del
profilo (default `Europe/Rome`), quindi al cambio di stagione non c'e' niente
da correggere a mano.

Se la run arriva talmente in ritardo da superare l'ora di uscita, il video
esce subito invece di aspettare il giorno dopo.

### La riserva di fine giornata

Il 21 settembre 2026 GitHub ha fatto partire una run con sette ore di ritardo e
un'altra non l'ha fatta partire affatto: il video delle 21:00 non e' mai
uscito. Il codice non c'entrava, ma il canale un video l'ha perso lo stesso.

Da qui un cron in piu' (`30 20` UTC, verso le 22:30 italiane) che non produce
un video suo. Guarda quali delle quattro uscite di oggi sono rimaste scoperte
e rifa' la piu' vecchia, una sola, **nel formato che quell'uscita voleva**,
pubblicandola subito; se sono tutte a posto termina in pochi secondi senza
fare niente. Si puo' lanciare anche a mano, dalla tab Actions, spuntando
`recupero`.

Il formato viaggia insieme all'orario proprio per questo: la riserva scopre
solo a lavorazione iniziata se le tocca uno Short verticale o il video lungo
orizzontale, e a quel punto richiama `config.applica_formato()` per rifare
tutte le misure.

Perche' questo non produca doppioni ogni lavorazione dichiara quale uscita sta
coprendo (`SLOT`, che finisce in `cronologia_trend.json`) e si ferma se quella
uscita ha gia' il suo video. Un video conta come pubblicato solo quando ha un
`video_id`: una lavorazione morta prima del caricamento lascia l'uscita
scoperta, che e' esattamente il caso in cui la riserva deve intervenire.

L'elenco delle uscite che la riserva controlla (`orari.slot_giornalieri()`)
viene dallo stesso profilo delle partenze, quindi non possono divergere. Le
uscite dopo le 22:30 italiane la riserva non le recupera: arriverebbe dopo.

Le run lanciate a mano dalla tab Actions (dove puoi anche scegliere tema e
visibilita') escono subito, nella lingua scelta se il canale pubblica in
quella lingua. Per rimpiazzare una partenza che non e' arrivata si scrive nel
campo `slot` il numero dell'uscita nella giornata (1-4) o il suo orario
(`18:00`): il video esce all'ora giusta e nella lingua di quell'uscita.

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

## Un canale che non parla di videogiochi (`canale.json`)

Samaritan e' nato per Poppone TV, ma di cosa parla il canale non e' piu'
scritto nel codice: sta in un file, `canale.json`, nella radice del progetto
(oppure dove dice la variabile `PROFILO_CANALE`). **Senza il file non cambia
niente**: vale il profilo di Poppone TV, con gli stessi prompt, le stesse
ricerche, gli stessi tag e Steam di sempre.

Per un altro argomento si parte da `canale.esempio.json`, che e' il profilo
completo di un canale di cucina con ogni campo spiegato:

```bash
cp canale.esempio.json canale.json
```

Cosa decide il profilo:

| Campo | Cosa cambia |
|---|---|
| `nome_canale`, `handle` | nome e link nella descrizione, nella chiamata all'azione e nei tag. `NOME_CANALE` e `HANDLE_CANALE` in `.env` o nei Secrets **vincono** sul file |
| `argomento`, `descrizione_argomento`, `descrizione_canale` | come i prompt chiamano l'argomento ("notizie di cucina", "canale YouTube di cucina italiana") |
| `soggetto`, `soggetto_plurale`, `genere`, `pubblico` | di cosa parla ogni video ("la ricetta", "un'altra ricetta", "per chi cucina a casa") |
| `ricerche` | le ricerche su Google News, una lista per lingua (`it`, `en`) |
| `parole_calde`, `nomi_grossi` | cosa fa salire una notizia in classifica |
| `tag_fissi`, `tag_fissi_lungo`, `hashtag_canale`, `hashtag_formato` | tag e hashtag di ogni video |
| `formati` | la descrizione di un formato come la legge il modello |
| `materiale` | `steam` (trailer e screenshot ufficiali, solo per i videogiochi) o `stock` (solo clip Pexels senza diritti) |
| `query_stock_riserva` | ricerche Pexels di riserva, in inglese |
| `categoria_youtube` | la categoria dell'upload (20 Gaming, 26 Stile e consigli, 17 Sport...) |
| `uscite` | da 1 a 4 uscite al giorno, ognuna `{"orario": "HH:MM", "lingua": "it"}`. Senza, due uscite (14:00 e 18:00) nella lingua delle ricerche; per il gaming quelle di Poppone TV |
| `fuso` | il fuso degli orari delle uscite (default `Europe/Rome`) |

Con `argomento` uguale a `gaming` il file eredita tutti i valori di Poppone TV
e basta scrivere quelli da cambiare. Con qualsiasi altro argomento **non
eredita niente di gaming**: `soggetto` e `ricerche` diventano obbligatori, il
materiale diventa `stock` e Steam non viene mai interrogato, nemmeno se il
modello nomina un gioco. Gli altri campi si ricavano da soli (vedi
`profilo.py`) e si possono comunque scrivere.

Il file si controlla all'avvio: un campo sconosciuto, un `materiale` che non
esiste, una lista di ricerche vuota fermano la lavorazione subito con un
messaggio in italiano, invece di far fallire il montaggio a meta'.

La regola sul materiale non cambia con l'argomento: **mai video di altri**.
Solo materiale ufficiale dell'editore (Steam), stock senza diritti (Pexels) o
clip girate dal proprietario del canale (`clip_mie/`).

Nella risposta del modello e in `cronologia_trend.json` il soggetto del video
resta nella chiave `gioco`, anche quando e' una ricetta: cambiarla vorrebbe
dire buttare la cronologia gia' scritta.

---

## Installazione per i clienti

Chi compra Samaritan non apre un terminale: copia il repository dal modello e
configura tutto da `installa/index.html`, una pagina statica che gira nel suo
browser e parla solo con `api.github.com` e con i server OAuth di Google. Scrive
`canale.json` con un commit (la prima volta azzera anche cronologia,
`performance.json` e le clip di `clip_mie/`, che sono del modello, e spegne
`promo.yml`), salva le chiavi nei Secrets cifrandole come chiede GitHub, fa il
giro OAuth di Google per il refresh token e lancia un video di prova privato.
La guida per il cliente e' [GUIDA_CLIENTE.md](GUIDA_CLIENTE.md).

Dove sta cosa (29 settembre 2026):

- **`poppone/samaritan-template`**, privato: la copia pulita da vendere, senza
  la memoria e le clip di Poppone TV. Va acceso **Settings > General >
  Template repository**. Un modello privato si copia solo se si ha accesso:
  il cliente si invita (in sola lettura) dopo che ha pagato. Il nome e' la
  costante `TEMPLATE_REPO` in cima alla pagina.
- **`poppone/samaritan-installa`**, pubblico: contiene solo la pagina, perche'
  GitHub Pages su un repository privato richiede un piano a pagamento. Con
  **Settings > Pages** sul ramo `main` la pagina e' su
  `https://poppone.github.io/samaritan-installa/`, ed e' quell'indirizzo che il
  cliente registra su Google come URI di reindirizzamento (Google accetta solo
  `https`).
- La pagina si sviluppa qui, in `installa/index.html`, e si copia negli altri
  due quando cambia. Rifiuta di scrivere sul modello e su questo repository.

`telegram/worker.js` resta di Poppone TV (ha il repository scritto dentro):
i clienti ricevono gli avvisi Telegram, ma non comandano la pipeline dal bot.

## I Reel che vendono Samaritan (Instagram)

Il canale YouTube parla di videogiochi. Il profilo Instagram parla di
Samaritan: un Reel al giorno con i suoi numeri veri, per far scrivere in DM
chi vuole la stessa macchina sul proprio canale.

    python promo.py            # scrive, monta e pubblica il Reel di oggi
    python promo.py --prova    # monta il Reel ma non lo pubblica

Su GitHub Actions gira da solo con il workflow `Samaritan Promo (Instagram)`.
Le due chiavi di Instagram si ricavano una volta sola: la procedura passo
passo e' in [GUIDA_INSTAGRAM.md](GUIDA_INSTAGRAM.md). Senza quelle chiavi la
lavorazione gira lo stesso, monta il Reel e lo manda su Telegram senza
pubblicarlo.

Questa parte e' tenuta separata da quella del canale di proposito: workflow
suo, memoria sua (`promo_cronologia.json`), e nessun modulo della pipeline di
YouTube la importa. Se Instagram cambia le regole, il canale non se ne accorge.

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
