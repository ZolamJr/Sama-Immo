// Client API : authentification, cache hors ligne, file d'attente et synchronisation (F10).
import { cacheGet, cacheSet, cacheVider, outboxAjouter, outboxListe, outboxRetirer, metaGet, metaSet, uuid, deviceId } from "./db.js";
import { toast, stock } from "./ui.js";

const BASE = "";
let token = stock.get("token") || "";
let utilisateur = JSON.parse(stock.get("user") || "null");

export function session() { return { token, utilisateur }; }
export function connecte() { return !!token; }
export function estProprietaire() { return utilisateur && utilisateur.role === "proprietaire"; }
export function peutEcrire() { return utilisateur && utilisateur.role !== "proprietaire"; }

export function definirSession(t, u) {
  token = t; utilisateur = u;
  stock.set("token", t);
  stock.set("user", JSON.stringify(u));
}
export function deconnexion() {
  token = ""; utilisateur = null;
  stock.del("token"); stock.del("user");
  cacheVider();
}

function entetes(json = true) {
  const h = { "X-Device-Id": deviceId() };
  if (token) h["Authorization"] = "Bearer " + token;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function _fetch(chemin, options) {
  const rep = await fetch(BASE + chemin, { ...options, headers: entetes(options.json !== false) });
  if (rep.status === 401 && !chemin.startsWith("/api/auth")) {
    deconnexion();
    location.hash = "#/login";
    throw new Error("Session expirée, reconnectez-vous.");
  }
  return rep;
}

// ---------------------------------------------------------------- Lecture (cache hors ligne)
export async function get(chemin, { silent = false } = {}) {
  try {
    const rep = await _fetch(chemin, { method: "GET" });
    const data = await rep.json();
    if (!rep.ok) throw new ErreurApi(rep.status, data.detail || data.message || "Erreur", data);
    cacheSet(chemin, data);
    return data;
  } catch (e) {
    if (e instanceof ErreurApi) throw e;
    e = _erreurReseau(e);
    // réseau indisponible -> cache local
    const c = await cacheGet(chemin);
    if (c) {
      if (!silent) marquerHorsLigne(true);
      return c.v;
    }
    marquerHorsLigne(true);
    throw new ErreurApi(0, "Hors ligne : aucune donnée en cache pour cette vue.", {});
  }
}

export class ErreurApi extends Error {
  constructor(statut, message, data) { super(message); this.statut = statut; this.data = data; }
}

function _erreurReseau(e) {
  if (e instanceof TypeError) return new ErreurApi(0, "Connexion indisponible — vérifiez le réseau.", {});
  return e;
}

// ---------------------------------------------------------------- Écritures (avec repli hors ligne)
export async function post(chemin, corps, { horsLigneAutorise = false, typeAction = null, payloadAction = null } = {}) {
  try {
    const rep = await _fetch(chemin, { method: "POST", body: JSON.stringify(corps ?? {}) });
    const data = await rep.json();
    if (!rep.ok) throw new ErreurApi(rep.status, data.detail || data.message || "Erreur", data);
    return data;
  } catch (e) {
    if (e instanceof ErreurApi) throw e;
    if (!horsLigneAutorise) throw _erreurReseau(e);
    return _mettreEnFile(typeAction, payloadAction ? payloadAction() : corps);
  }
}

export async function patch(chemin, corps, { horsLigneAutorise = false, typeAction = null, extra = {} } = {}) {
  try {
    const rep = await _fetch(chemin, { method: "PATCH", body: JSON.stringify(corps ?? {}) });
    const data = await rep.json();
    if (!rep.ok) throw new ErreurApi(rep.status, data.detail || data.message || "Erreur", data);
    return data;
  } catch (e) {
    if (e instanceof ErreurApi) throw e;
    if (!horsLigneAutorise) throw _erreurReseau(e);
    return _mettreEnFile(typeAction, { ...corps, ...extra, updated_at: new Date().toISOString() });
  }
}

export async function supprimer(chemin) {
  const rep = await _fetch(chemin, { method: "DELETE" });
  const data = await rep.json().catch(() => ({}));
  if (!rep.ok) throw new ErreurApi(rep.status, data.detail || "Suppression impossible", data);
  return data;
}

export async function envoyerFichier(chemin, formData) {
  const rep = await _fetch(chemin, { method: "POST", body: formData, json: false });
  const data = await rep.json();
  if (!rep.ok) throw new ErreurApi(rep.status, data.detail || "Envoi impossible", data);
  return data;
}

export async function telecharger(chemin) {
  const rep = await _fetch(chemin, { method: "GET" });
  if (!rep.ok) throw new ErreurApi(rep.status, "Téléchargement impossible", {});
  return rep;
}

// ---------------------------------------------------------------- File d'attente hors ligne
async function _mettreEnFile(type, payload) {
  marquerHorsLigne(true);
  const id = await outboxAjouter({ type, payload });
  await majBadge();
  toast("Hors ligne : action enregistrée, elle partira dès le retour du réseau.", "");
  return { hors_ligne: true, action_id: id };
}

// Paiements en attente : superposition locale pour l'affichage immédiat (numéro provisoire).
export async function pendingPaiements() { return (await metaGet("pending_paiements")) || []; }
export async function ajouterPendingPaiement(p) {
  const liste = await pendingPaiements();
  liste.push(p);
  await metaSet("pending_paiements", liste);
}
async function retirerPendingParAction(actionId) {
  const liste = await pendingPaiements();
  await metaSet("pending_paiements", liste.filter((x) => x.action_id !== actionId));
}

// Locataires créés hors ligne en attente (affichage immédiat).
export async function pendingLocataires() { return (await metaGet("pending_locataires")) || []; }
export async function ajouterPendingLocataire(l) {
  const liste = await pendingLocataires();
  liste.push(l);
  await metaSet("pending_locataires", liste);
}
async function retirerPendingLocataires() { await metaSet("pending_locataires", []); }

// ---------------------------------------------------------------- Synchronisation
let _enCours = false;
export async function synchroniser(manuel = false) {
  if (_enCours || !token || !navigator.onLine) { if (manuel) toast("Rien à synchroniser."); return; }
  _enCours = true;
  try {
    let actions = await outboxListe();
    if (!actions.length) { await majBadge(); return; }
    let envoyes = 0, erreurs = 0, conflicts = 0;
    while (actions.length) {
      const lot = actions.slice(0, 15);
      const rep = await fetch(BASE + "/api/sync", {
        method: "POST", headers: entetes(),
        body: JSON.stringify({ device_id: deviceId(), actions: lot.map((a) => ({ id: String(a.id), type: a.type, payload: a.payload })) }),
      });
      if (!rep.ok) { // réseau/serveur indisponible : on retentera plus tard
        if (rep.status === 401) { deconnexion(); location.hash = "#/login"; }
        break;
      }
      const data = await rep.json();
      for (const r of data.resultats || []) {
        const cle = parseInt(r.id, 10);
        if (r.status === "applied" || r.status === "duplicate") {
          await outboxRetirer(cle);
          await retirerPendingParAction(cle);
          if (r.status === "applied") envoyes++;
        } else if (r.status === "conflict") {
          await outboxRetirer(cle);
          await retirerPendingParAction(cle);
          conflicts++;
        } else {
          const msg = String(r.message || "");
          const definitif = /introuvable|invalide|inconnu|déjà|manquant|Occupé|louée/i.test(msg);
          if (definitif) {
            await outboxRetirer(cle);
            await retirerPendingParAction(cle);
            erreurs++;
            toast("Action non synchronisée : " + msg, "erreur");
          } // sinon : gardée pour retry (téléphone, échéance obsolète…)
        }
      }
      await retirerPendingLocataires();
      actions = await outboxListe();
    }
    await majBadge();
    marquerHorsLigne(false);
    if (envoyes > 0) toast(envoyes + " action(s) synchronisée(s) ✔", "succes");
    if (conflicts > 0) toast(conflicts + " fiche(s) mise(s) à jour depuis un autre appareil (version la plus récente conservée).", "");
    if ((envoyes || conflicts) && typeof document !== "undefined") {
      document.dispatchEvent(new CustomEvent("sync-fait"));
    }
  } finally {
    _enCours = false;
  }
}

// ---------------------------------------------------------------- Indicateurs interface
export function marquerHorsLigne(horsLigne) {
  const el = document.getElementById("badge-hors-ligne");
  if (el) el.classList.toggle("visible", horsLigne || !navigator.onLine);
}

export async function majBadge() {
  const el = document.getElementById("badge-attente");
  if (!el) return;
  const n = (await outboxListe()).length;
  el.textContent = n ? `${n} en attente` : "";
  el.classList.toggle("visible", n > 0);
}

export function demarrerSync() {
  window.addEventListener("online", () => { marquerHorsLigne(false); synchroniser(); });
  window.addEventListener("offline", () => marquerHorsLigne(true));
  setInterval(() => synchroniser(), 15000);
  synchroniser();
  majBadge();
}

export { uuid, deviceId };
