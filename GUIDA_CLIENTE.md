# Samaritan sul tuo canale: la guida

Questa guida ti porta da zero al primo video, senza terminale e senza
toccare il codice. Tutto si fa da una pagina web, la **pagina di
installazione**, il cui indirizzo ti arriva insieme a Samaritan (finisce con
`/installa/`).

Ci vogliono tre quarti d'ora, la prima volta. Tieni la pagina aperta dall'inizio
alla fine: se la chiudi, i passi gia' fatti restano fatti, ma il token GitHub
(passo 2) va incollato di nuovo.

## Cosa ti serve

- Un **account GitHub** (gratuito). E' dove vive la tua copia di Samaritan e
  dove, ogni notte, i video vengono preparati.
- L'**account Google del tuo canale YouTube**.
- Una **chiave Groq** (gratuita, da [console.groq.com/keys](https://console.groq.com/keys)):
  e' l'intelligenza artificiale che scrive i testi.
- Una **chiave Pexels** (gratuita, da [pexels.com/api](https://www.pexels.com/api/)):
  sono le clip video senza diritti.
- Facoltativi: una chiave ElevenLabs per una voce piu' realistica (a
  pagamento; senza, si usa una voce gratuita) e un bot Telegram per ricevere
  gli avvisi sul telefono.

## Cosa la pagina fa e cosa no

- Gira tutta nel tuo browser. Parla solo con GitHub e con i server di accesso
  di Google; scarica una libreria di cifratura da `cdn.jsdelivr.net`.
- **Non ti chiede mai la password** di Google o di YouTube. Quando serve, ti
  manda sulla pagina di Google, e la password la scrivi li'.
- Token e chiavi restano in memoria finche' la pagina e' aperta e finiscono
  solo nei **Secrets** della tua copia su GitHub, cifrati: da li' nemmeno
  GitHub te li rimostra.

## Passo 1: copia Samaritan sul tuo GitHub

Apri il link del passo 1, scegli un nome (per esempio `samaritan`), seleziona
**Private** e premi **Create repository**. Copia l'indirizzo della pagina che
si apre, tipo `https://github.com/mario/samaritan`.

## Passo 2: dai alla pagina l'accesso alla tua copia

La pagina ha bisogno di un "token", una specie di chiave a tempo che apre solo
la tua copia. Si crea da
[github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new):

1. **Token name**: quello che vuoi, per esempio `installazione samaritan`.
2. **Expiration**: 7 giorni bastano.
3. **Repository access**: *Only select repositories*, e scegli la tua copia.
4. **Permissions > Repository permissions**, mettendo *Read and write* su:
   **Contents**, **Secrets**, **Actions**. *Metadata* si aggiunge da solo.
   Nient'altro.
5. **Generate token**, e copia il token (comincia con `github_pat_`).

Nella pagina incolla l'indirizzo della tua copia e il token, e premi
**Verifica l'accesso**. Deve comparire "Collegato a ...".

Finita l'installazione puoi cancellare il token dalla stessa pagina di GitHub:
a Samaritan non serve piu'.

## Passo 3: descrivi il tuo canale

- **Nome del canale** e **handle** (quello che comincia con `@`).
- **Di cosa parla**: *Videogiochi* oppure *Altro argomento*. Con un altro
  argomento scrivi come lo diresti dopo la parola "notizie" (per esempio "di
  cucina") e di cosa parla ogni video, al singolare (per esempio "ricetta").
- **Ricerche di notizie**: una per riga, come le scriveresti su Google News.
  Samaritan racconta notizie vere, trovate con queste ricerche. Per i
  videogiochi puoi lasciarle vuote.
- **Uscite della giornata**: da una a quattro, ognuna con l'ora e la lingua.
  Il video si prepara di notte e YouTube lo pubblica da solo all'ora esatta.
  Sotto le uscite la pagina ti dice quali orari sono possibili: se ne scegli
  uno fuori, te lo dice prima di salvare.

Premi **Salva il canale nel repository**. Al primo salvataggio Samaritan
azzera anche la sua memoria: quella che c'era era del canale da cui e' stato
copiato.

**Una regola che non cambia mai:** Samaritan non usa video di altri. Per i
videogiochi usa solo trailer e immagini ufficiali degli editori (da Steam);
per ogni altro argomento solo clip senza diritti di Pexels.

## Passo 4: le chiavi dei servizi

Incolla la chiave Groq e la chiave Pexels (e, se le hai, quelle facoltative) e
premi **Salva le chiavi**.

Per gli avvisi su Telegram: crea un bot con [@BotFather](https://t.me/BotFather)
(ti da' il *token del bot*), poi scrivi al tuo bot un messaggio qualsiasi e
chiedi a [@userinfobot](https://t.me/userinfobot) il tuo *chat id*.

## Passo 5: collega YouTube

E' il passo piu' lungo, e si fa una volta sola. Serve a dare a Samaritan il
permesso di caricare video sul tuo canale e di leggerne le statistiche.
Accedi a Google con **l'account del canale**.

1. Apri la [Google Cloud Console](https://console.cloud.google.com/projectcreate)
   e crea un progetto (il nome non conta).
2. Nel menu, **API e servizi > Libreria**: cerca e attiva
   **YouTube Data API v3**, poi cerca e attiva **YouTube Analytics API**.
3. **API e servizi > Schermata di consenso OAuth**: tipo **Esterno**, compila
   nome dell'app e le email richieste, salva.
   Poi premi **Pubblica app**: lo stato deve diventare **In produzione**.
   **Questo e' il punto dove si sbaglia piu' spesso.** Se l'app resta in
   modalita' *Test*, dopo 7 giorni Google spegne il permesso e i video
   smettono di uscire senza nessun avviso.
4. **API e servizi > Credenziali > Crea credenziali > ID client OAuth**:
   tipo **Applicazione web**. In **URI di reindirizzamento autorizzati**
   aggiungi l'indirizzo che la pagina di installazione ti mostra al passo 5,
   copiato esattamente. Crea.
5. Copia **ID client** e **Client secret** nella pagina e premi
   **Autorizza con Google**.
6. Google ti chiede con quale account entrare: scegli quello del canale.
   Vedrai l'avviso **"Google non ha verificato questa app"**: e' normale,
   l'app e' tua e la usi solo tu. Premi *Avanzate* e poi *Vai a ...*, e dai
   i permessi richiesti.
7. Tornato sulla pagina, **incolla di nuovo il token GitHub** al passo 2 e
   premi *Verifica l'accesso* (la pagina non lo porta con se' durante il giro
   su Google, apposta). Poi premi **Salva il collegamento**.

## Passo 6: il video di prova

Premi **Fai il video di prova**. Samaritan prepara un video **privato**: lo
vedi solo tu, in YouTube Studio. Ci mette dai 10 ai 20 minuti; la pagina ti
da' il link per seguire la lavorazione su GitHub (un pallino giallo che
diventa una spunta verde).

Se il video c'e', hai finito: da stanotte Samaritan lavora da solo, alle ore
che hai scelto.

## Dopo l'installazione

- **Cambiare orari, ricerche o argomento**: riapri la pagina, rifai il passo
  2 e il passo 3, compilando di nuovo tutto il modulo (la pagina non rilegge
  quello salvato). La memoria del tuo canale resta: si azzera solo la prima
  volta.
- **Fermare tutto**: nella tua copia su GitHub, tab **Actions**, workflow
  *Samaritan*, menu `...` > **Disable workflow**. Per ripartire,
  **Enable workflow**.
- **Un video in piu' a mano**: tab **Actions** > *Samaritan* > **Run
  workflow**.

## Se qualcosa non va

| Cosa vedi | Cosa vuol dire |
|---|---|
| "il token non e' valido o e' scaduto" | Rifai il token del passo 2. |
| "il repository non esiste o il token non puo' vederlo" | Nel token, *Only select repositories* deve includere la tua copia. |
| "Questo e' il modello di Samaritan, non la tua copia" | Hai incollato l'indirizzo del modello: fai prima il passo 1. |
| Google dice `redirect_uri_mismatch` | L'indirizzo al punto 4 del passo 5 non e' identico a quello mostrato dalla pagina. |
| "Google non ha dato il refresh token" | Rifai *Autorizza con Google*. |
| Un'email di GitHub "Run failed" | Apri il link: in alto c'e' il messaggio d'errore in italiano. Il piu' comune e' una chiave mancante (passo 4). |
| I video smettono di uscire dopo una settimana | L'app Google e' rimasta in *Test*: fai **Pubblica app** (passo 5, punto 3) e ripeti i punti 5-7. |
