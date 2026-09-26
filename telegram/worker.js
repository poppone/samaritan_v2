// Comandi da Telegram per Samaritan.
//
// popponetv scrive al bot "/video argomento" e parte subito un video su
// quell'argomento: questo Worker riceve il messaggio da Telegram e lancia la
// lavorazione su GitHub Actions, la stessa che si lancia a mano dal pulsante
// "Run workflow". Gira su Cloudflare Workers (gratis) e non consuma minuti di
// GitHub Actions per restare in ascolto.
//
// Variabili da impostare su Cloudflare (Settings > Variables and Secrets),
// tutte di tipo "Secret":
//   TELEGRAM_BOT_TOKEN  lo stesso token del bot che manda le notifiche
//   TELEGRAM_CHAT_ID    lo stesso chat id delle notifiche: solo lui comanda
//   GITHUB_TOKEN        token GitHub con permesso Actions sul solo samaritan_v2
//   SEGRETO_WEBHOOK     una parola a caso, lettere e numeri, inventata da lui
//
// Dopo il primo Deploy si apre una volta nel browser
//   https://<indirizzo-del-worker>/registra?chiave=<SEGRETO_WEBHOOK>
// e da quel momento Telegram consegna qui i messaggi del bot.

const REPOSITORY = "poppone/samaritan_v2";
const WORKFLOW = "samaritan.yml";

const COMANDI = {
  "/video": { lingua: "it", lungo: false, privacy: "public", cosa: "uno Short in italiano" },
  "/en": { lingua: "en", lungo: false, privacy: "public", cosa: "uno Short in inglese" },
  "/lungo": { lingua: "it", lungo: true, privacy: "public", cosa: "il video lungo in italiano" },
  "/prova": { lingua: "it", lungo: false, privacy: "private", cosa: "uno Short privato di prova" },
};

const AIUTO =
  "Scrivimi un comando seguito dall'argomento:\n\n" +
  "/video argomento: Short in italiano, esce subito\n" +
  "/en argomento: Short in inglese, esce subito\n" +
  "/lungo argomento: video lungo in italiano\n" +
  "/prova argomento: Short privato, lo vedi solo tu\n\n" +
  "Esempio: /video il nuovo trailer di GTA 6";

export function interpreta(testo) {
  const pulito = (testo || "").trim();
  const [primo, ...resto] = pulito.split(/\s+/);
  // Nei gruppi Telegram il comando arriva come /video@NomeDelBot.
  const comando = (primo || "").split("@")[0].toLowerCase();
  const scelta = COMANDI[comando];
  const tema = resto.join(" ").trim().slice(0, 200);
  if (!scelta || !tema) return null;
  return { ...scelta, tema };
}

async function rispondi(env, testo) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: testo }),
  });
}

async function lancia(env, ordine) {
  const r = await fetch(
    `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        // GitHub rifiuta le richieste senza User-Agent.
        "User-Agent": "samaritan-telegram",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          tema: ordine.tema,
          privacy: ordine.privacy,
          lingua: ordine.lingua,
          lungo: String(ordine.lungo),
        },
      }),
    },
  );
  // 204 = lavorazione accodata. Tutto il resto e' un problema da raccontare.
  return r.status === 204 ? null : `GitHub ha risposto ${r.status}: ${(await r.text()).slice(0, 300)}`;
}

async function registra(request, env) {
  const indirizzo = new URL(request.url);
  if (!env.SEGRETO_WEBHOOK || indirizzo.searchParams.get("chiave") !== env.SEGRETO_WEBHOOK) {
    return new Response("Chiave sbagliata.", { status: 403 });
  }
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: `${indirizzo.origin}/telegram`,
      secret_token: env.SEGRETO_WEBHOOK,
      allowed_updates: ["message"],
    }),
  });
  const esito = await r.json().catch(() => ({}));
  return new Response(
    esito.ok ? "Fatto: da adesso i comandi del bot arrivano a Samaritan." : `Telegram dice: ${esito.description || r.status}`,
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
}

export default {
  async fetch(request, env) {
    const percorso = new URL(request.url).pathname;
    if (request.method === "GET" && percorso === "/registra") return registra(request, env);
    if (request.method !== "POST" || percorso !== "/telegram") return new Response("Samaritan.");

    // Solo Telegram conosce il segreto: chiunque altro trovi l'indirizzo
    // non puo' far partire niente.
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.SEGRETO_WEBHOOK) {
      return new Response("no", { status: 403 });
    }
    const aggiornamento = await request.json().catch(() => ({}));
    const messaggio = aggiornamento.message || {};
    // Solo la sua chat comanda: il bot e' trovabile da chiunque su Telegram.
    if (String(messaggio.chat?.id ?? "") !== String(env.TELEGRAM_CHAT_ID)) return new Response("ok");

    const ordine = interpreta(messaggio.text);
    if (!ordine) {
      await rispondi(env, AIUTO);
      return new Response("ok");
    }
    const problema = await lancia(env, ordine);
    await rispondi(
      env,
      problema
        ? `Non sono riuscito a partire. ${problema}`
        : `Parto: ${ordine.cosa} su "${ordine.tema}". Quando e' pronto ti arriva qui.`,
    );
    // A Telegram si risponde sempre 200, anche quando GitHub fallisce:
    // altrimenti riconsegna lo stesso messaggio e partirebbero piu' video.
    return new Response("ok");
  },
};
