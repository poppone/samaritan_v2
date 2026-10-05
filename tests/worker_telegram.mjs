import worker, { interpreta, uscitaDaLanciare } from "../telegram/worker.js";
import assert from "node:assert";
assert.deepEqual(interpreta("/video il nuovo trailer di GTA 6"), {lingua:"it",lungo:false,privacy:"public",cosa:"uno Short in italiano",tema:"il nuovo trailer di GTA 6"});
assert.equal(interpreta("/en  Hollow Knight Silksong ").lingua, "en");
assert.equal(interpreta("/VIDEO@SamaritanBot Fortnite").tema, "Fortnite");
assert.equal(interpreta("/video"), null);
assert.equal(interpreta("ciao"), null);
assert.equal(interpreta(undefined), null);
assert.equal(interpreta("/lungo Elden Ring").lungo, true);
assert.equal(interpreta("/prova x").privacy, "private");
// finto fetch
const chiamate = [];
globalThis.fetch = async (url, opz) => { chiamate.push({url, opz}); return url.includes("github") ? new Response(null,{status:204}) : new Response("{}"); };
const env = {TELEGRAM_BOT_TOKEN:"t", TELEGRAM_CHAT_ID:"42", GITHUB_TOKEN:"g", SEGRETO_WEBHOOK:"s"};
const req = (chat, testo, segreto="s") => new Request("https://w.dev/telegram", {method:"POST", headers:{"X-Telegram-Bot-Api-Secret-Token":segreto}, body: JSON.stringify({message:{chat:{id:chat}, text:testo}})});
assert.equal((await worker.fetch(req(42,"/video GTA 6","sbagliato"), env)).status, 403);
assert.equal(chiamate.length, 0);
await worker.fetch(req(7,"/video GTA 6"), env); assert.equal(chiamate.length, 0);
await worker.fetch(req(42,"/video GTA 6"), env);
assert.equal(chiamate.length, 2);
const corpo = JSON.parse(chiamate[0].opz.body);
assert.deepEqual(corpo, {ref:"main", inputs:{tema:"GTA 6", privacy:"public", lingua:"it", lungo:"false"}});
assert.ok(JSON.parse(chiamate[1].opz.body).text.startsWith("Parto"));
await worker.fetch(req(42,"ciao"), env);
assert.ok(JSON.parse(chiamate[2].opz.body).text.includes("/video argomento"));
assert.equal((await worker.fetch(new Request("https://w.dev/registra?chiave=no"), env)).status, 403);
// partenze puntuali dai Cron Trigger
assert.equal(uscitaDaLanciare(Date.UTC(2026, 9, 1, 9, 0)), "1");
assert.equal(uscitaDaLanciare(Date.UTC(2026, 9, 1, 15, 0)), "3");
assert.equal(uscitaDaLanciare(Date.UTC(2026, 9, 1, 17, 30)), "4");
assert.equal(uscitaDaLanciare(Date.UTC(2026, 9, 1, 4, 0)), null);
// Ogni partenza, primo giro e riprova, arriva prima della sua uscita anche
// con l'ora legale (Roma = UTC+2): 14:00, 18:00, 20:00, 21:00 = 12, 16, 18, 19 UTC.
const USCITA_UTC = { "1": 12 * 60, "2": 16 * 60, "3": 18 * 60, "4": 19 * 60 };
for (const ora of ["09:00", "13:00", "15:00", "16:00", "10:30", "14:30", "16:30", "17:30"]) {
  const [h, m] = ora.split(":").map(Number);
  const slot = uscitaDaLanciare(Date.UTC(2026, 9, 1, h, m));
  assert.ok(slot, ora);
  assert.ok(h * 60 + m <= USCITA_UTC[slot] - 60, `${ora} parte troppo a ridosso dell'uscita ${slot}`);
}
const attese = [];
const ctx = { waitUntil: (p) => attese.push(p) };
chiamate.length = 0;
await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 1, 14, 30) }, env, ctx);
await Promise.all(attese);
assert.equal(chiamate.length, 1);
assert.ok(chiamate[0].url.endsWith("/actions/workflows/samaritan.yml/dispatches"));
assert.deepEqual(JSON.parse(chiamate[0].opz.body), {ref:"main", inputs:{slot:"2"}});
// un cron che non e' una partenza non lancia niente
chiamate.length = 0;
await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 1, 6, 20) }, env, ctx);
await Promise.all(attese);
assert.equal(chiamate.length, 0);
// se GitHub rifiuta, arriva un avviso su Telegram
globalThis.fetch = async (url, opz) => { chiamate.push({url, opz}); return url.includes("github") ? new Response("Bad credentials",{status:401}) : new Response("{}"); };
await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 1, 16, 0) }, env, ctx);
await Promise.all(attese);
assert.equal(chiamate.length, 2);
assert.ok(JSON.parse(chiamate[1].opz.body).text.includes("uscita 4"));
assert.ok(JSON.parse(chiamate[1].opz.body).text.includes("401"));
console.log("tutto ok");
