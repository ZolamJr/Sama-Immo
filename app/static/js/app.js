// SamaImmo — routeur et coquille de l'application.
import { connecte, estProprietaire, demarrerSync, synchroniser, majBadge, get } from "./api.js";
import { $, esc, toast, ouvrirModal, fermerModal, stock } from "./ui.js";
import * as vLogin from "./views/login.js";
import * as vAccueil from "./views/accueil.js";
import * as vEncaisser from "./views/encaisser.js";
import * as vRelances from "./views/relances.js";
import * as vBiens from "./views/biens.js";
import * as vLocataires from "./views/locataires.js";
import * as vFiches from "./views/fiches.js";
import * as vRapports from "./views/rapports.js";
import * as vParametres from "./views/parametres.js";
import * as vAudit from "./views/audit.js";

const app = document.getElementById("app");

const ROUTES = {
  "/": { vue: vAccueil, titre: "Accueil" },
  "/accueil": { vue: vAccueil, titre: "Accueil" },
  "/encaisser": { vue: vEncaisser, titre: "Encaisser un loyer" },
  "/relances": { vue: vRelances, titre: "Relances" },
  "/biens": { vue: vBiens, titre: "Gestion" },
  "/immeuble": { vue: vFiches, titre: "Immeuble" },
  "/locataires": { vue: vLocataires, titre: "Locataires" },
  "/locataire": { vue: vFiches, titre: "Locataire" },
  "/bail": { vue: vFiches, titre: "Bail" },
  "/rapports": { vue: vRapports, titre: "Rapports" },
  "/parametres": { vue: vParametres, titre: "Paramètres" },
  "/audit": { vue: vAudit, titre: "Journal d'activité" },
};

function shell(contenuHtml) {
  const u = JSON.parse(stock.get("user") || "{}");
  const proprio = estProprietaire();
  app.innerHTML = `
  <div class="barre-haut">
    <div class="logo">🏠 ${esc(u.nom || u.telephone || "")}</div>
    <div class="droite">
      <span id="badge-hors-ligne" class="badge-hors-ligne">⚠ Hors ligne</span>
      <span id="badge-attente" class="badge-attente"></span>
      <button id="btn-cloche" title="Notifications" style="background:none;border:none;color:#fff;font-size:1.15rem;min-width:44px;min-height:44px;cursor:pointer;position:relative">🔔<span id="cloche-compteur" style="position:absolute;top:4px;right:2px;background:var(--rouge,#d32f2f);color:#fff;font-size:0.62rem;font-weight:700;border-radius:999px;padding:1px 5px;display:none"></span></button>
      <button id="btn-sync" title="Synchroniser" style="background:none;border:none;color:#fff;font-size:1.15rem;min-width:44px;min-height:44px;cursor:pointer">⟳</button>
    </div>
  </div>
  <div class="contenu" id="contenu">${contenuHtml}</div>
  <nav class="onglets">
    <a href="#/accueil" data-route="/accueil"><span class="ic">🏠</span>Accueil</a>
    ${proprio ? "" : `<a href="#/encaisser" data-route="/encaisser"><span class="ic">💵</span>Encaisser</a>`}
    <a href="#/biens" data-route="/biens"><span class="ic">🏢</span>Gestion</a>
    <a href="#/locataires" data-route="/locataires"><span class="ic">👤</span>Locataires</a>
    ${proprio ? "" : `<a href="#/relances" data-route="/relances"><span class="ic">🔔</span>Relances</a>`}
  </nav>`;
  $("#btn-sync").onclick = () => synchroniser(true);
  const cloche = $("#btn-cloche");
  if (cloche) cloche.onclick = () => afficherNotifications();
  majBadge();
  majNotifications();
  document.querySelectorAll("nav.onglets a").forEach((a) => {
    a.classList.toggle("actif", a.dataset.route === routeActuelle()[0]);
  });
}

function routeActuelle() {
  const h = location.hash.replace(/^#/, "") || "/";
  // le chemin est la partie avant « ? » ; les paramètres d'URL sont lus par les vues
  const parties = h.split("?")[0].split("/").filter(Boolean);
  const chemin = "/" + (parties[0] || "");
  return [chemin, parties.slice(1)];
}

async function router() {
  const [chemin, params] = routeActuelle();
  if (!connecte()) {
    await vLogin.rendre(app);
    return;
  }
  const route = ROUTES[chemin] || ROUTES["/"];
  app.innerHTML = `<div class="splash"><div class="splash-logo">🏠</div><div class="splash-sous">Chargement…</div></div>`;
  let html = "";
  try {
    html = await route.vue.rendre(params, shell);
  } catch (e) {
    html = `<div class="carte"><div class="alerte erreur">${esc(e.message)}</div>
      <button class="btn-ligne" onclick="location.hash='#/accueil'">Retour à l'accueil</button></div>`;
  }
  if (!connecte()) return; // déconnecté pendant le chargement
  shell(html);
  document.querySelectorAll("nav.onglets a").forEach((a) => {
    a.classList.toggle("actif", a.dataset.route === chemin || (chemin === "/" && a.dataset.route === "/accueil"));
  });
  try { await route.vue.apresRendu && route.vue.apresRendu(params); } catch (e) { console.error(e); }
  majNotifications();
  window.scrollTo(0, 0);
}

// Verrou PIN local optionnel (F1)
async function verrouPIN() {
  if (!stock.get("pin_hash") || stock.sessionGet("pin_ok")) return true;
  return new Promise((resolve) => {
    ouvrirModal("Code PIN", `
      <p class="petit gris">Entrez votre code PIN pour ouvrir l'application.</p>
      <input id="pin-saisi" type="password" inputmode="numeric" maxlength="6" style="width:100%;padding:14px;font-size:1.4rem;text-align:center;letter-spacing:8px;border:1.5px solid var(--bord);border-radius:12px">
      <button class="btn-ligne" id="pin-ok">Déverrouiller</button>`);
    const verifier = async () => {
      const v = $("#pin-saisi").value;
      const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v));
      const h = Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
      if (h === stock.get("pin_hash")) {
        stock.sessionSet("pin_ok", "1");
        fermerModal();
        resolve(true);
      } else {
        $("#pin-saisi").value = "";
        toast("Code PIN incorrect", "erreur");
      }
    };
    $("#pin-ok").onclick = verifier;
    $("#pin-saisi").addEventListener("keydown", (e) => { if (e.key === "Enter") verifier(); });
  });
}

async function demarrer() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  if (connecte() && !(await verrouPIN())) { await demarrer(); return; }
  await router();
  demarrerSync();
}

// notifications : chargées après chaque navigation (silencieuses hors ligne)
let _dernieresNotifications = [];
export async function majNotifications() {
  const compteur = document.getElementById("cloche-compteur");
  if (!compteur || !connecte()) return;
  try {
    const d = await get("/api/notifications", { silent: true });
    _dernieresNotifications = d.notifications || [];
    const n = _dernieresNotifications.reduce((s2, x) => s2 + (x.nombre || 0), 0);
    compteur.textContent = n > 99 ? "99+" : String(n);
    compteur.style.display = n > 0 ? "" : "none";
  } catch { /* hors ligne : on garde les dernières connues */ }
}

function afficherNotifications() {
  if (!_dernieresNotifications.length) {
    ouvrirModal("Notifications 🔔", `<div class="vide"><span class="em">✅</span>Rien à signaler : aucun retard, aucune action en attente.</div>`);
    return;
  }
  ouvrirModal("Notifications 🔔", _dernieresNotifications.map((n) => `
    <a href="${n.lien}" class="element" style="text-decoration:none;color:inherit;display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bord,#eee)" data-notif-fermer>
      <div class="avatar">${n.gravite === "alerte" ? "🔴" : "🔵"}</div>
      <div class="corps" style="flex:1">
        <div class="titre" style="font-weight:700">${esc(n.titre)}</div>
        <div class="detail petit gris" style="color:#666">${esc(n.detail)}</div>
      </div>
      <div style="font-size:1.3rem">›</div>
    </a>`).join(""));
  document.querySelectorAll("[data-notif-fermer]").forEach((a) => {
    a.onclick = (e) => { e.preventDefault(); fermerModal(); location.hash = a.getAttribute("href"); };
  });
}

window.addEventListener("hashchange", router);
document.addEventListener("sync-fait", () => { router(); majNotifications(); });

function montrerErreur(e) {
  const c = document.getElementById("contenu") || document.getElementById("app");
  if (c) c.innerHTML = `<div class="carte" style="max-width:420px;margin:40px auto">
    <div class="alerte erreur"><b>L'application n'a pas pu démarrer.</b><br>${esc(e && e.message || e)}</div>
    <div class="petit gris">1) Rechargez avec <b>Ctrl+F5</b><br>
    2) Vérifiez que l'adresse est <b>http://localhost:8000</b> (pas un fichier ouvert directement)<br>
    3) Touche <b>F12</b> → onglet Console → copiez le message rouge et envoyez-le</div>
  </div>`;
}

demarrer().catch(montrerErreur);

// Si après 8 secondes l'écran de démarrage est toujours là, on explique quoi faire.
setTimeout(() => {
  const sous = document.getElementById("splash-sous");
  const splash = document.querySelector("#app .splash");
  if (splash && sous && !sous.getAttribute("data-err") && sous.textContent !== "Chargement…") return;
  if (splash && sous && !sous.getAttribute("data-err")) {
    sous.setAttribute("data-err", "1");
    sous.innerHTML = "⚠ Toujours bloqué au démarrage ?<br>" +
      "1) Rechargez avec <b>Ctrl+F5</b><br>" +
      "2) Vérifiez l'adresse : <b>http://localhost:8000</b> (à ouvrir dans le navigateur, pas le fichier index.html)<br>" +
      "3) Touche <b>F12</b> → Console → copiez le message rouge";
  }
}, 8000);
