// Vérificateur statique d'imports/exports ES modules.
// Attrape les erreurs du type « does not provide an export named X »
// qui bloquent tout le démarrage de l'application.
// Usage : node scripts/check_imports.js
"use strict";
const fs = require("fs");
const path = require("path");

const RACINE = path.join(__dirname, "..", "app", "static", "js");
const ERREURS = [];

function fichiersJs(dir) {
  let out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out = out.concat(fichiersJs(p));
    else if (e.name.endsWith(".js")) out.push(p);
  }
  return out;
}

function exportsDu(fichier) {
  const src = fs.readFileSync(fichier, "utf8");
  const noms = new Set();
  // export function / async function / class / const / let / var
  for (const m of src.matchAll(/export\s+(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)/g)) noms.add(m[1]);
  for (const m of src.matchAll(/export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) noms.add(m[1]);
  // export { a, b as c }
  for (const m of src.matchAll(/export\s*\{([^}]*)\}/g)) {
    for (let part of m[1].split(",")) {
      part = part.trim();
      if (!part) continue;
      const as = part.split(/\s+as\s+/);
      noms.add((as[1] || as[0]).trim());
    }
  }
  if (/export\s+default/.test(src)) noms.add("default");
  return noms;
}

function verifier(fichier) {
  const src = fs.readFileSync(fichier, "utf8");
  const rel = (p) => path.resolve(path.dirname(fichier), p);

  // imports statiques : import { a, b as c } from "./x.js"
  for (const m of src.matchAll(/import\s+(?:([A-Za-z_$][\w$]*)\s*,\s*)?\{([^}]*)\}\s*from\s*["'](\.[^"']+)["']/g)) {
    const cible = rel(m[3]);
    if (!fs.existsSync(cible)) { ERREURS.push(`${path.relative(RACINE, fichier)}: fichier introuvable ${m[3]}`); continue; }
    const dispo = exportsDu(cible);
    for (let part of m[2].split(",")) {
      part = part.trim();
      if (!part) continue;
      const as = part.split(/\s+as\s+/);
      const nom = (as[1] || as[0]).trim();
      if (!dispo.has(nom)) {
        ERREURS.push(`${path.relative(RACINE, fichier)} importe « ${nom} » depuis ${m[3]} — export absent`);
      }
    }
  }
  // imports dynamiques : const { a, b } = await import("./x.js")
  for (const m of src.matchAll(/const\s+\{([^{}]*)\}\s*=\s*await\s+import\(["'](\.[^"']+)["']\)/g)) {
    const cible = rel(m[2]);
    if (!fs.existsSync(cible)) { ERREURS.push(`${path.relative(RACINE, fichier)}: fichier introuvable ${m[2]}`); continue; }
    const dispo = exportsDu(cible);
    for (let part of m[1].split(",")) {
      part = part.trim();
      if (!part) continue;
      if (!dispo.has(part)) {
        ERREURS.push(`${path.relative(RACINE, fichier)} importe (dynamique) « ${part} » depuis ${m[2]} — export absent`);
      }
    }
  }
}

const fichiers = fichiersJs(RACINE);
for (const f of fichiers) verifier(f);

if (ERREURS.length) {
  console.error(`✗ ${ERREURS.length} problème(s) d'import :`);
  for (const e of ERREURS) console.error("  -", e);
  process.exit(1);
} else {
  console.log(`✔ ${fichiers.length} modules analysés — tous les imports correspondent à des exports existants`);
}
