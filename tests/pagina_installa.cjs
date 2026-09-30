// Apre installa/index.html in Chromium senza rete e ci fa girare dentro le
// funzioni pure della pagina. Lo lancia tests/test_installa.py:
//
//   node tests/pagina_installa.cjs installa/index.html casi.json
//
// casi.json: {"moduli": [...], "profili": [...], "blake": ["hex", ...]}
// Stampa su stdout un JSON con gli errori della pagina e i risultati.
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

// Un GitHub finto, dentro il browser: risponde alle chiamate della pagina a
// api.github.com e se le segna. Nessuna richiesta esce davvero.
const REPO = "/repos/mario/samaritan";
const ALBERO_DEL_MODELLO = [
  { path: "main.py", mode: "100644", type: "blob", sha: "a" },
  { path: "performance.json", mode: "100644", type: "blob", sha: "b" },
  { path: "clip_mie", mode: "040000", type: "tree", sha: "c" },
  { path: "clip_mie/LEGGIMI.md", mode: "100644", type: "blob", sha: "d" },
  { path: "clip_mie/gol.mp4", mode: "100644", type: "blob", sha: "e" },
];

async function finGitHub(p) {
  const chiamate = [];
  let albero = ALBERO_DEL_MODELLO;
  const risposte = {
    [`GET ${REPO}`]: { full_name: "mario/samaritan", private: true, default_branch: "main" },
    [`GET ${REPO}/git/ref/heads/main`]: { object: { sha: "c1" } },
    [`GET ${REPO}/git/commits/c1`]: { sha: "c1", tree: { sha: "t1" } },
    [`GET ${REPO}/git/trees/t1?recursive=1`]: () => ({ tree: albero }),
    [`POST ${REPO}/git/trees`]: { sha: "t2" },
    [`POST ${REPO}/git/commits`]: { sha: "c2" },
    [`PATCH ${REPO}/git/refs/heads/main`]: { object: { sha: "c2" } },
    [`PUT ${REPO}/actions/workflows/promo.yml/disable`]: null,
    [`POST ${REPO}/actions/workflows/samaritan.yml/dispatches`]: null,
    [`GET ${REPO}/actions/workflows/samaritan.yml/runs?event=workflow_dispatch&per_page=1`]:
      { workflow_runs: [{ html_url: "https://github.com/mario/samaritan/actions/runs/1" }] },
  };
  const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
                 "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE" };
  await p.route("https://api.github.com/**", (r) => {
    const q = r.request();
    if (q.method() === "OPTIONS") return r.fulfill({ status: 204, headers: cors });
    const u = new URL(q.url());
    const chiave = `${q.method()} ${u.pathname}${u.search}`;
    chiamate.push({ chiave, corpo: q.postData() ? JSON.parse(q.postData()) : null,
                    auth: q.headers()["authorization"] || "" });
    if (!(chiave in risposte)) return r.fulfill({ status: 404, headers: cors, body: '{"message":"Not Found"}' });
    let corpo = risposte[chiave];
    if (typeof corpo === "function") corpo = corpo();
    if (corpo === null) return r.fulfill({ status: 204, headers: cors });
    return r.fulfill({ status: 200, headers: cors, contentType: "application/json", body: JSON.stringify(corpo) });
  });
  const esito = (id) => p.evaluate((id) => {
    const el = document.getElementById(id);
    return { classe: el.className, testo: el.textContent };
  }, id);
  const risultato = {};

  // Il modello stesso si rifiuta, prima di chiamare GitHub.
  await p.fill("#repo", "https://github.com/poppone/samaritan-template");
  await p.fill("#token", "github_pat_finto");
  await p.click("#verifica-github");
  risultato.modello = await esito("esito-github");

  // Nemmeno il repository di Poppone TV: la prima installazione ne
  // azzererebbe la memoria.
  await p.fill("#repo", "https://github.com/poppone/samaritan_v2");
  await p.click("#verifica-github");
  risultato.poppone = await esito("esito-github");

  await p.fill("#repo", "https://github.com/mario/samaritan");
  await p.click("#verifica-github");
  await p.waitForFunction(() => document.getElementById("esito-github").className.includes("ok"));
  risultato.verifica = await esito("esito-github");

  // Primo salvataggio: nel repository c'e' ancora la memoria del modello.
  await p.click("#salva-canale");
  await p.waitForFunction(() => document.getElementById("esito-canale").className !== "esito");
  risultato.primo = await esito("esito-canale");
  risultato.chiamate_primo = chiamate.splice(0);

  // Secondo salvataggio: canale.json c'e' gia', la memoria non si tocca.
  albero = ALBERO_DEL_MODELLO.concat([{ path: "canale.json", mode: "100644", type: "blob", sha: "f" }]);
  await p.evaluate(() => { document.getElementById("esito-canale").className = "esito"; });
  await p.click("#salva-canale");
  await p.waitForFunction(() => document.getElementById("esito-canale").className !== "esito");
  risultato.secondo = await esito("esito-canale");
  risultato.chiamate_secondo = chiamate.splice(0);

  await p.click("#lancia-prova");
  await p.waitForFunction(() => document.getElementById("esito-prova").className !== "esito", null,
                          { timeout: 15000 });
  risultato.prova = await esito("esito-prova");
  risultato.chiamate_prova = chiamate.splice(0);
  risultato.memoria = await p.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }));
  return risultato;
}

(async () => {
  const [pagina, fileCasi] = process.argv.slice(2);
  const casi = JSON.parse(fs.readFileSync(fileCasi, "utf-8"));
  const browser = await chromium.launch();
  const errori = [];
  const richieste = [];
  try {
    const p = await browser.newPage();
    p.on("pageerror", (e) => errori.push(String(e)));
    p.on("console", (m) => { if (m.type() === "error") errori.push(m.text()); });
    // Niente rete: la pagina all'apertura non deve chiedere niente a nessuno.
    await p.route("**/*", (r) => {
      if (r.request().url().startsWith("file:")) return r.continue();
      richieste.push(r.request().url());
      return r.abort();
    });
    await p.goto("file://" + path.resolve(pagina));
    await p.fill("#nome_canale", "Il mio canale");
    await p.fill("#handle", "@IlMioCanale");
    const risultato = await p.evaluate((casi) => {
      const S = window.Samaritan;
      const esa = (h) => Uint8Array.from((h.match(/../g) || []).map((x) => parseInt(x, 16)));
      const aEsa = (b) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
      return {
        costanti: S.costanti,
        predefinito: S.costruisciProfilo(S.leggiModulo()),
        anteprima: document.getElementById("anteprima").textContent,
        costruiti: casi.moduli.map((m) => {
          const profilo = S.costruisciProfilo(m);
          return { profilo, errori: S.validaProfilo(profilo) };
        }),
        validazioni: casi.profili.map((pr) => S.validaProfilo(pr)),
        argomenti: S.argomenti.map((k) => {
          const profilo = S.costruisciProfilo(S.moduloDaArgomento(k, S.leggiModulo()));
          return { chiave: k, profilo, errori: S.validaProfilo(profilo) };
        }),
        vietati: S.vietati,
        vietato: (casi.testi || []).map((t) => S.argomentoVietato(t)),
        finestre: S.finestre(S.scostamenti("Europe/Rome")),
        blake: casi.blake.map((h) => [aEsa(S.blake2b(esa(h), 24)), aEsa(S.blake2b(esa(h), 64))]),
        repository: ["https://github.com/mario/samaritan", "mario/samaritan.git", "boh"]
          .map((t) => S.leggiRepository(t)),
        memoria: { local: localStorage.length, session: sessionStorage.length },
      };
    }, casi);
    risultato.errori_pagina = errori;
    risultato.richieste = richieste.slice();
    risultato.github = await finGitHub(p);
    risultato.errori_pagina_github = errori.slice(risultato.errori_pagina.length);
    process.stdout.write(JSON.stringify(risultato));
  } finally {
    await browser.close();
  }
})().catch((e) => {
  process.stderr.write(String(e && e.stack || e));
  process.exit(1);
});
