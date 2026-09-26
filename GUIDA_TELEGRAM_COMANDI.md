# Lanciare un video da Telegram

Scrivi al bot di Samaritan, quello che ti manda le notifiche:

| Messaggio | Cosa parte |
|---|---|
| `/video il nuovo trailer di GTA 6` | Short in italiano, esce appena pronto |
| `/en Hollow Knight Silksong` | Short in inglese, esce appena pronto |
| `/lungo Elden Ring` | Video lungo in italiano (16:9) |
| `/prova Cyberpunk 2077` | Short privato: lo vedi solo tu su YouTube Studio |

Il bot risponde subito "Parto", e quando il video e' caricato ti arriva la
solita notifica con il link. Qualunque altro messaggio fa comparire l'elenco
dei comandi. Solo la tua chat puo' comandare: se qualcun altro trova il bot,
non succede niente.

Il comando passa da un piccolo programma su Cloudflare (gratis), il file
`telegram/worker.js`, che riceve i messaggi del bot e lancia la lavorazione su
GitHub come faresti tu dal pulsante "Run workflow". Si prepara una volta sola,
dal computer, in circa un quarto d'ora.

> **Attenzione.** Tre dei valori qui sotto (token GitHub, token del bot,
> segreto) sono **password**. Vanno solo nelle caselle di Cloudflare indicate,
> **mai in chat**, nemmeno con Claude.

## 1. Il token GitHub

1. Su github.com: foto profilo in alto a destra > **Settings** > in fondo a
   sinistra **Developer settings** > **Personal access tokens** >
   **Fine-grained tokens** > **Generate new token**.
2. Nome: `Samaritan Telegram`. Scadenza: la piu' lunga che ti propone.
3. **Repository access**: *Only select repositories* > `poppone/samaritan_v2`.
4. **Permissions** > **Repository permissions** > **Actions**: *Read and write*.
   Nient'altro.
5. **Generate token** e copialo (e' una password: tienilo aperto solo fino al
   punto 3).

## 2. Token del bot e numero della tua chat

- Token del bot: su Telegram apri **@BotFather** > `/mybots` > il bot di
  Samaritan > **API Token**. E' lo stesso che hai messo su GitHub come
  `TELEGRAM_BOT_TOKEN` (password).
- Numero della chat: scrivi qualunque cosa a **@userinfobot**, ti risponde con
  il tuo `Id`, un numero. Deve essere lo stesso di `TELEGRAM_CHAT_ID`.

## 3. Il Worker su Cloudflare

1. Crea un account gratuito su https://dash.cloudflare.com.
2. **Workers & Pages** > **Create** > **Create Worker** (quello "Hello World").
   Nome: `samaritan-telegram`. **Deploy**.
3. **Edit code**: cancella tutto, incolla il contenuto di
   [`telegram/worker.js`](telegram/worker.js), **Deploy**.
4. Torna al Worker > **Settings** > **Variables and Secrets** > **Add**, quattro
   volte, sempre di tipo **Secret**:

   | Nome | Valore |
   |---|---|
   | `GITHUB_TOKEN` | il token del punto 1 |
   | `TELEGRAM_BOT_TOKEN` | il token del bot |
   | `TELEGRAM_CHAT_ID` | il numero di @userinfobot |
   | `SEGRETO_WEBHOOK` | una parola inventata, solo lettere e numeri, almeno 20 caratteri |

   Poi **Deploy**.
5. In alto nella pagina del Worker c'e' il suo indirizzo, del tipo
   `https://samaritan-telegram.TUONOME.workers.dev`. Apri nel browser:

   `https://samaritan-telegram.TUONOME.workers.dev/registra?chiave=` seguito
   dalla parola di `SEGRETO_WEBHOOK`.

   Deve comparire "Fatto: da adesso i comandi del bot arrivano a Samaritan."

## 4. Prova

Scrivi al bot `/prova Cyberpunk 2077`. Entro pochi secondi risponde "Parto", e
fra dieci-quindici minuti arriva il video privato.

## Se qualcosa non va

- **"GitHub ha risposto 401" o "403"**: il token GitHub e' sbagliato, scaduto,
  o senza il permesso *Actions: Read and write*. Rifallo (punto 1) e sostituiscilo.
- **"Chiave sbagliata"** aprendo `/registra`: la parola dopo `chiave=` non e'
  identica a `SEGRETO_WEBHOOK`.
- **Il bot non risponde**: rifai il punto 3.5; controlla che `TELEGRAM_CHAT_ID`
  sia il tuo numero.
- Ogni comando fa partire la sua lavorazione, anche se un'altra e' gia' in
  corso: non aspetta e non toglie il posto alle uscite programmate. Due comandi
  uguali fanno due video uguali.
