// Journal d'audit (F11) : qui a fait quoi, quand, depuis quel appareil.
import { get } from "../api.js";
import { $, esc, vide } from "../ui.js";
import { dateHeureFr } from "../format.js";

const ICONES = {
  "paiement.cree": "💵", "paiement.annule": "↩️", "paiement.preuve": "🧾",
  "bail.cree": "📜", "bail.termine": "🏁", "locataire.cree": "👤", "locataire.modifie": "✏️",
  "immeuble.cree": "🏢", "unite.creee": "🚪", "recu.quittance": "🧾", "relance.envoyee": "🔔",
  "rapport.genere": "📊", "agence.modifiee": "🏢", "regles.modifiees": "📏",
  "user.ajoute": "🧑‍💼", "document.ajoute": "📄", "document.supprime": "🗑️",
};

export async function rendre() {
  const data = await get("/api/audit?limit=150");
  const logs = data.logs || [];
  return `
  <div class="entete-page"><h1>Journal d'activité</h1></div>
  <div class="sous-titre">Traçabilité complète : chaque action est horodatée et rattachée à son auteur.</div>
  <input id="recherche-audit" type="search" placeholder="🔎 Filtrer (action, nom…)"
         style="width:100%;padding:12px 14px;border:1.5px solid var(--bord);border-radius:12px;margin-bottom:8px">
  <div class="ligne-flex" style="gap:8px;margin-bottom:12px;flex-wrap:wrap">
    <select id="filtre-auteur" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="tous">Tous les auteurs</option>
      ${Array.from(new Set(logs.map((l) => l.user).filter(Boolean))).map((u) =>
        `<option value="${esc(u.toLowerCase())}">${esc(u)}</option>`).join("")}
    </select>
    <a class="btn-ligne secondaire petit" href="/api/audit/export.pdf" target="_blank" rel="noopener">📄 Exporter le journal (PDF)</a>
  </div>
  ${logs.length ? `<div class="liste" id="liste-audit">${logs.map((l) => `
    <div class="element" style="cursor:default;align-items:flex-start" data-txt="${esc((l.action + " " + l.user_nom + " " + l.objet_libelle).toLowerCase())}" data-auteur="${esc((l.user || "").toLowerCase())}">
      <div class="avatar">${ICONES[l.action] || "•"}</div>
      <div class="corps">
        <div class="titre">${esc(libelleFr(l.action))}${l.objet_libelle ? ` — ${esc(l.objet_libelle)}` : ""}</div>
        <div class="detail">${esc(l.user || "système")} · ${dateHeureFr(l.date)}${l.device_id ? " · appareil " + esc(l.device_id.slice(0, 8)) : ""}</div>
      </div>
    </div>`).join("")}</div>` : vide("👁️", "Aucune action enregistrée.")}`;
}

function libelleFr(a) {
  const lib = {
    "paiement.cree": "Paiement enregistré", "paiement.annule": "Paiement annulé (écriture motivée)",
    "paiement.preuve": "Preuve jointe à un paiement", "bail.cree": "Bail créé", "bail.modifie": "Bail modifié",
    "bail.termine": "Bail terminé", "locataire.cree": "Locataire ajouté", "locataire.modifie": "Locataire modifié",
    "locataire.supprime": "Locataire supprimé", "immeuble.cree": "Bien ajouté", "immeuble.modifie": "Bien modifié",
    "immeuble.supprime": "Bien supprimé", "unite.creee": "Unité ajoutée", "unite.modifiee": "Unité modifiée",
    "unite.supprimee": "Unité supprimée", "recu.quittance": "Quittance émise", "recu.caution": "Reçu de caution",
    "recu.frais_agence": "Reçu de frais d'agence", "recu.decharge": "Décharge de clés",
    "relance.envoyee": "Relance envoyée", "rapport.genere": "Rapport généré",
    "agence.modifiee": "Profil agence modifié", "agence.logo": "Logo mis à jour", "agence.tampon": "Tampon mis à jour",
    "agence.signature": "Signature mise à jour", "regles.modifiees": "Règles locales modifiées",
    "modele.modifie": "Modèle de message modifié", "user.ajoute": "Utilisateur ajouté", "user.modifie": "Utilisateur modifié",
    "document.ajoute": "Document ajouté", "document.supprime": "Document supprimé",
    "compte.cree": "Compte agence créé", "compte.proprietaire_cree": "Compte propriétaire activé",
    "proprietaire.cree": "Propriétaire ajouté", "proprietaire.modifie": "Propriétaire modifié",
  };
  return lib[a] || a;
}

export async function apresRendu() {
  const rech = document.getElementById("recherche-audit");
  if (rech) rech.oninput = () => {
    const q = rech.value.toLowerCase();
    document.querySelectorAll("#liste-audit .element").forEach((el) => {
      el.style.display = el.dataset.txt.includes(q) ? "" : "none";
    });
  };
}
