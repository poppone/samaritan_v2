# Samaritan su Instagram: come si accende

Questa e' la parte che devo fare io, ma che posso fare solo io fino a un certo
punto: le chiavi di Instagram le puo' creare solo chi possiede l'account.
Sono venti minuti, una volta sola.

Quando hai finito, Samaritan pubblica da solo un Reel al giorno sul profilo
nuovo: il diario dei suoi numeri, che serve a far scrivere in DM chi vuole la
stessa macchina sul proprio canale.

---

## 1. Il profilo Instagram (5 minuti)

1. Apri un profilo **nuovo**, separato da quello personale. Il nome dovrebbe
   dire cosa fa: per esempio `samaritan.ai`.
2. Vai in **Impostazioni > Tipo di account e strumenti > Passa a un account
   professionale**.

Questo passaggio non e' saltabile: su un profilo normale l'API di Instagram
non pubblica, risponde errore e basta.

Nella biografia va la frase che vende, e quella e' la riga piu' importante di
tutto il profilo. Qualcosa tipo:

> Il mio canale YouTube pubblica da solo. L'ho scritto io.
> Lo installo anche sul tuo: scrivimi in DM.

---

## 2. L'app Meta (10 minuti)

L'app serve solo come chiave: non la vede nessuno, non va pubblicata e non
deve passare nessuna revisione, perche' pubblica su un account tuo. E' la
differenza con TikTok, dove invece la revisione ci voleva.

1. Vai su **developers.facebook.com**, accedi e apri **Le mie app > Crea
   app**.
2. Quando ti chiede a cosa serve, scegli la voce che parla di **Instagram**.
3. Dentro l'app, apri il pannello di configurazione di Instagram (si chiama
   qualcosa come *API setup with Instagram login*).
4. Nel primo riquadro c'e' **Generate access token**: aggiungi il tuo account
   Instagram, accetta il collegamento e genera il token.
5. Copia due cose e tienile da parte:
   - il **token** (una stringa lunghissima);
   - l'**ID dell'account Instagram** (un numero lungo, scritto li' vicino).

Il token dura **60 giorni**. Quando scade, il Reel smette di uscire: si
rigenera da questa stessa pagina e si risostituisce al passo 3. Mettitelo in
calendario, oppure dimmelo e ti avviso io quando manca poco.

> Se il pannello di Meta ha parole diverse da quelle scritte qui, mandami uno
> screenshot invece di provare a indovinare: cambiano i nomi delle voci ogni
> pochi mesi.

---

## 3. Le chiavi dentro Samaritan (2 minuti)

Sul repository, **Settings > Secrets and variables > Actions > New repository
secret**, e aggiungi questi due:

| Nome del secret     | Cosa ci metti                          |
|---------------------|----------------------------------------|
| `INSTAGRAM_TOKEN`   | il token lungo del passo 2             |
| `INSTAGRAM_USER_ID` | il numero dell'account Instagram       |

Finche' questi due non ci sono, la lavorazione gira lo stesso: monta il Reel,
te lo manda su Telegram e non pubblica niente. Non da' errore.

C'e' anche una variabile facoltativa (**Variables**, non Secrets):
`CONTATTO_PROMO`, che e' la frase con cui la didascalia chiude. Di default
dice `scrivimi in DM`.

---

## 4. La prova (3 minuti)

Sul repository, **Actions > Samaritan Promo (Instagram) > Run workflow**, con
la spunta **prova** attiva: monta il Reel e te lo manda su Telegram senza
pubblicarlo. Guardalo, e se ti piace rilancialo senza la spunta.

Da li' in poi va da solo: un Reel al giorno, di sera.

---

## Cosa succede quando qualcuno ti scrive

Il Reel non vende da solo, porta solo la persona in DM. Quello che dici tu
dopo e' la vendita, e conviene averlo gia' pronto invece di improvvisarlo:

- cosa fa Samaritan, in due righe;
- quanto costa installarlo sul loro canale;
- cosa gli serve avere (un canale YouTube, e le chiavi gratuite di Groq e
  Pexels, che si fanno in dieci minuti);
- quanto ci metti.

Se mi dici il prezzo che vuoi fare, ti preparo io i messaggi pronti.
