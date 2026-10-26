// Test de fumée : charge RÉELLEMENT chaque module de l'application avec des
// stubs navigateur minimaux. Attrape les erreurs de liaison (import d'un export
// inexistant) et les erreurs de premier niveau — exactement la classe de bug
// qui bloquait le démarrage sur « logo figé ».
// Usage : node scripts/smoke_modules.mjs
"use strict";
import { pathToFileURL } from "url";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const ici = path.dirname(fileURLToPath(import.meta.url));
const jsDir = path.join(ici, "..", "app", "static", "js");

// ---- stubs navigateur (les modules ne touchent le DOM qu'à l'exécution) ----
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.document = {
  getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
  addEventListener: () => {}, createElement: () => ({}), dispatchEvent: () => {},
};
globalThis.window = { addEventListener: () => {} };
globalThis.navigator = { onLine: true };
globalThis.location = { hash: "#/accueil", origin: "http://localhost:8000" };
globalThis.fetch = () => Promise.reject(new Error("réseau coupé (test)"));
globalThis.indexedDB = { open: () => ({ addEventListener: () => {} }) };
globalThis.URL.createObjectURL = () => "blob:test";

function fichiersJs(dir) {
  let out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out = out.concat(fichiersJs(p));
    else if (e.name.endsWith(".js")) out.push(p);
  }
  return out;
}

let echecs = 0;
const fichiers = fichiersJs(jsDir).filter((f) => !f.endsWith("app.js")); // app.js se lance tout seul
for (const f of fichiers) {
  try {
    await import(pathToFileURL(f).href + `?cache=${Date.now()}`);
    console.log("OK  ", path.relative(jsDir, f));
  } catch (e) {
    echecs++;
    console.error("ÉCHEC", path.relative(jsDir, f), "->", e.message);
  }
}
if (echecs) { console.error(`\n✗ ${echefs} module(s) en échec`); process.exit(1); }
console.log(`\n✔ ${fichiers.length} modules chargés sans erreur (liaison + premier niveau)`);
