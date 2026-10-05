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
//
// Lo stesso Worker fa anche partire le uscite del giorno all'ora giusta, se
// su Cloudflare gli si aggiungono i Cron Trigger (Settings > Trigger Events):
//   0,20,40 4,6 * * *
//   0 5,7 * * *
// Vedi PARTENZE_PUNTUALI qui sotto.

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

// Le partenze delle uscite, in ora UTC. I cron di GitHub partono con ore di
// ritardo (il 29 e il 30 settembre e il 1 ottobre 2026 nessuna partenza
// notturna era arrivata alle 6 del mattino) e ogni mattina andavano lanciate
// a mano: quelli di Cloudflare scattano al minuto. Ogni partenza lancia una
// lavorazione con "slot", che pubblica all'orario dell'uscita (publishAt),
// non subito. Il secondo giro, due ore dopo, e' la riprova per chi e' caduto
// al primo: chi ha gia' il suo video si ferma col freno anti-doppioni, e
// anche le partenze di GitHub, quando arrivano.
// Uscite di Poppone TV: 1 = 14:00 (italiano), 2 = 18:00, 3 = 20:00 e
// 4 = 21:00 (inglese).
// Dal 5 ottobre 2026 ogni uscita parte circa tre ore prima del suo orario e
// non tutte alle 6 del mattino: la notizia si sceglie poche ore prima di
// uscire, quando e' ancora fresca. Il secondo giro e' un'ora e mezza dopo,
// sempre prima dell'uscita, anche con l'ora solare (dal 26 ottobre le
// uscite sono un'ora piu' tardi in UTC, quindi il margine cresce).
export const PARTENZE_PUNTUALI = {
  "09:00": "1", "13:00": "2", "15:00": "3", "16:00": "4",
  "10:30": "1", "14:30": "2", "16:30": "3", "17:30": "4",
};

export function uscitaDaLanciare(quando) {
  const t = new Date(quando);
  const ora = `${String(t.getUTCHours()).padStart(2, "0")}:${String(t.getUTCMinutes()).padStart(2, "0")}`;
  return PARTENZE_PUNTUALI[ora] || null;
}

async function rispondi(env, testo) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: testo }),
  });
}

async function lancia(env, ordine, inputs) {
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
        inputs: inputs || {
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

async function partenzaPuntuale(env, quando) {
  const slot = uscitaDaLanciare(quando);
  if (!slot) return;
  const problema = await lancia(env, null, { slot });
  // Un avviso solo se qualcosa non va: quando va bene arriva gia' la
  // notifica della lavorazione, con il link o con "niente da fare".
  if (problema) await rispondi(env, `La partenza dell'uscita ${slot} non e' partita. ${problema}`);
}

export default {
  async scheduled(evento, env, ctx) {
    ctx.waitUntil(partenzaPuntuale(env, evento.scheduledTime));
  },

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
