// Fiches détaillées : immeuble, locataire (baux + paiements + documents), bail.
import { get, post, patch, supprimer, peutEcrire, envoyerFichier } from "../api.js";
import { $, esc, toast, badge, vide, ouvrirModal, fermerModal, champ } from "../ui.js";
import { fcfa, dateFr, libellePeriode, TYPES_UNITE, comprimerImage, poidsKo } from "../format.js";

export async function rendre(params) {
  const route = location.hash.split("?")[0];
  if (route.startsWith("#/immeuble/")) return await ficheImmeuble(params[0]);
  if (route.startsWith("#/locataire/")) return await ficheLocataire(params[0]);
  if (route.startsWith("#/bail")) {
    const uniteId = new URLSearchParams(location.hash.split("?")[1] || "").get("unite");
    if (uniteId) return await ficheUnite(uniteId);
  }
  return `<div class="alerte erreur">Fiche introuvable.</div>`;
}

export async function apresRendu() {
  brancherBoutons();
}

// ================================================================ IMMEUBLE

async function ficheImmeuble(id) {
  const data = await get("/api/immeubles");
  const imm = (data.immeubles || []).find((i) => i.id === id);
  if (!imm) return `<div class="alerte erreur">Bien introuvable.</div>`;
  const caPotentiel = imm.unites.reduce((s, u) => s + u.loyer + u.charges, 0);
  return `
  <div class="entete-page"><h1>${esc(imm.nom)}</h1></div>
  <button class="btn-ligne gris petit" onclick="history.back()">← Retour</button>
  <div class="espace"></div>
  <div class="carte">
    <div class="ligne-flex"><span class="gris">Propriétaire</span><b>${esc(imm.proprietaire_nom)}</b></div>
    <div class="ligne-flex"><span class="gris">Quartier</span><b>${esc(imm.quartier || "—")}</b></div>
    <div class="ligne-flex"><span class="gris">Adresse</span><b>${esc(imm.adresse || "—")}</b></div>
    <div class="ligne-flex"><span class="gris">Loyer potentiel / mois</span><b class="montant">${fcfa(caPotentiel)}</b></div>
  </div>
  <div class="sous-titre">Unités (${imm.unites.length})</div>
  ${imm.unites.length ? `<div class="liste">${imm.unites.map((u) => `
    <div class="element" data-unite="${esc(u.id)}">
      <div class="avatar">${{ chambre: "🛏️", appartement: "🏢", maison: "🏠", local: "🏪", bureau: "💼" }[u.type] || "🏠"}</div>
      <div class="corps"><div class="titre">${esc(u.nom)}</div>
        <div class="detail">${TYPES_UNITE[u.type] || u.type} · ${u.bail_actif ? esc(u.bail_actif.locataire_nom) : "libre"}</div></div>
      <div class="droite"><div class="montant montant">${fcfa(u.loyer)}</div>${badge(u.statut)}</div>
    </div>`).join("")}</div>` : vide("🚪", "Aucune unité dans ce bien.")}
  <div class="espace"></div>
  ${peutEcrire() ? `<button class="btn-ligne" id="btn-doc-imm">📄 Ajouter un document</button>` : ""}`;
}

// ================================================================ UNITÉ -> BAIL

async function ficheUnite(uniteId) {
  const unites = (await get("/api/unites")).unites || [];
  const u = unites.find((x) => x.id === uniteId);
  if (!u) return `<div class="alerte erreur">Unité introuvable.</div>`;
  const bail = u.bail_actif;
  let bailDetail = null;
  if (bail) {
    try { bailDetail = await get(`/api/baux/${bail.id}`); } catch (e) { /* cache absent */ }
  }
  const bauxData = await get("/api/baux");
  const tousBaux = (bauxData.baux || []).filter((b) => b.unite_id === uniteId);

  return `
  <div class="entete-page"><h1>${esc(u.nom)}</h1>${badge(u.statut)}</div>
  <div class="carte">
    <div class="ligne-flex"><span class="gris">Bien</span><b>${esc(u.immeuble_nom)}</b></div>
    <div class="ligne-flex"><span class="gris">Type</span><b>${TYPES_UNITE[u.type] || u.type}</b></div>
    <div class="ligne-flex"><span class="gris">Loyer + charges</span><b class="montant">${fcfa(u.loyer + u.charges)}</b></div>
    ${u.notes ? `<div class="petit gris">${esc(u.notes)}</div>` : ""}
  </div>

  ${bailDetail ? await blocBail(bailDetail) : `
    <div class="carte centre">
      <p class="gras">Cette unité est libre</p>
      ${peutEcrire() ? `<button class="btn-ligne" id="btn-nouveau-bail">📝 Créer un bail (locataire)</button>` : ""}
    </div>`}

  ${tousBaux.length > 1 || (tousBaux.length === 1 && !bailDetail) ? `
    <div class="sous-titre">Historique des baux</div>
    <div class="liste">${tousBaux.filter((b) => !bailDetail || b.id !== bailDetail.id).map((b) => `
      <div class="element" style="cursor:default">
        <div class="avatar">📜</div>
        <div class="corps"><div class="titre">${esc(b.locataire_nom)}</div>
        <div class="detail">du ${dateFr(b.date_debut)} au ${b.date_fin ? dateFr(b.date_fin) : "…"}</div></div>
        <div class="droite">${badge(b.statut)}</div>
      </div>`).join("")}</div>` : ""}
  <div class="espace"></div>
  ${peutEcrire() ? `
    <button class="btn-ligne secondaire" id="btn-doc-unite">📄 Documents / scanner</button>
    <button class="btn-ligne gris" id="btn-retour-biens">← Retour aux biens</button>` : ""}`;
}

async function blocBail(b) {
  const eches = (b.echeances || []).slice(0, 6);
  const c = b.caution_detail || null;
  return `
  <div class="carte">
    <div class="ligne-flex"><b>📜 Bail — ${esc(b.locataire_nom)}</b>${badge(b.statut)}</div>
    <div class="petit gris">Depuis le ${dateFr(b.date_debut)} · ${b.duree_type === "triennale" ? "durée triennale" : b.duree_type}</div>
    <div class="espace"></div>
    <div class="ligne-flex"><span class="gris">Loyer + charges</span><b class="montant">${fcfa(b.loyer + b.charges)}</b></div>
    <div class="ligne-flex"><span class="gris">Échéance (payable d'avance)</span><b>le ${b.jour_echeance} du mois</b></div>
    <div class="ligne-flex"><span class="gris">Enregistrement DGID</span><b>${{ non: "à faire", en_cours: "en cours", fait: "fait ✔" }[b.enregistre_statut] || b.enregistre_statut}</b></div>
    ${b.enregistre_statut !== "fait" ? `<div class="alerte attention petit">Rappel : bail à enregistrer au Centre des services fiscaux (timbre 2 000 FCFA/feuille, 2 % du loyer annuel).</div>` : ""}
  </div>

  ${c ? blocCaution(b, c) : ""}

  ${eches.length ? `<div class="sous-titre">Échéances récentes</div>
  <div class="liste">${eches.map((e) => `
    <div class="element" style="cursor:default">
      <div class="avatar">${e.statut === "paye" ? "✅" : e.statut === "en_retard" ? "🔴" : "📅"}</div>
      <div class="corps"><div class="titre">${esc(e.periode_libelle)}</div>
      <div class="detail">payé ${fcfa(e.montant_paye)} / ${fcfa(e.montant_du)}</div></div>
      <div class="droite">${e.statut !== "paye" && peutEcrire() ? `<a class="btn-ligne petit vert" href="#/encaisser?echeance=${esc(e.id)}">Encaisser</a>` : badge(e.statut)}</div>
    </div>`).join("")}</div>` : ""}

  ${(b.historique_loyer || []).length > 1 ? `
  <details class="resume"><summary>Historique du loyer</summary><div class="interieur">
    <table class="table-simple">${b.historique_loyer.map((h) => `
      <tr><td>${dateFr(h.date_effet)}</td><td class="montant">${fcfa(h.loyer)}</td><td class="petit gris">${esc(h.motif)}</td></tr>`).join("")}
    </table></div></details>` : ""}

  ${peutEcrire() ? `
  <div class="grille-actions">
    <button class="btn" id="btn-modif-bail"><span class="ic">✏️</span>Modifier le bail</button>
    <button class="btn" id="btn-doc-bail"><span class="ic">📄</span>Documents</button>
    <button class="btn" id="btn-recu-caution"><span class="ic">🧾</span>Reçu de caution</button>
    <button class="btn" id="btn-recu-frais"><span class="ic">🧾</span>Reçu de frais</button>
    ${b.statut === "actif" ? `<button class="btn danger" id="btn-fin-bail"><span class="ic">🏁</span>Terminer le bail</button>` : ""}
  </div>` : ""}`;
}

// ================================================================ CAUTION (décret 2023-382)

function blocCaution(b, c) {
  const statuts = {
    aucune: { lib: "Aucune caution", cls: "libre" },
    partielle: { lib: "Partiellement versée", cls: "partiel" },
    soldee: { lib: "Versée intégralement", cls: "paye" },
    a_restituer: { lib: "À restituer", cls: "en_retard" },
    restituee: { lib: "Restituée ✔", cls: "paye" },
  };
  const st = statuts[c.statut] || statuts.aucune;
  const lignesEch = (c.echeancier || []).map((e) =>
    `<tr><td>${esc(e.libelle)}</td><td>${dateFr(e.date)}</td><td class="montant">${fcfa(e.montant)}</td></tr>`).join("");
  return `
  <div class="carte">
    <div class="ligne-flex"><b>🔐 Caution</b><span class="puce ${st.cls}">${st.lib}</span></div>
    <div class="espace"></div>
    <div class="ligne-flex"><span class="gris">Prévue au bail</span><b class="montant">${fcfa(c.prevue)}</b></div>
    <div class="ligne-flex"><span class="gris">Versée à ce jour</span><b class="montant">${fcfa(c.versee)}</b></div>
    ${c.reste_a_verser > 0 ? `<div class="ligne-flex"><span class="gris">Reste à verser</span><b class="montant" style="color:var(--orange,#e67e22)">${fcfa(c.reste_a_verser)}</b></div>` : ""}
    ${c.rembourse_le ? `
      <div class="ligne-flex"><span class="gris">Restituée le</span><b>${dateFr(c.rembourse_le)}</b></div>
      ${c.retenue > 0 ? `<div class="ligne-flex"><span class="gris">Retenue justifiée</span><b class="montant">${fcfa(c.retenue)}</b></div>
      ${c.retenue_motif ? `<div class="petit gris">Motif : ${esc(c.retenue_motif)}</div>` : ""}` : ""}` : `
    ${c.statut === "a_restituer" ? `
      <div class="ligne-flex"><b>À restituer</b><b class="montant" style="color:var(--rouge,#c0392b)">${fcfa(c.a_restituer)}</b></div>
      ${c.date_limite_restitution ? `<div class="ligne-flex"><span class="gris">Délai conseillé jusqu'au</span><b>${dateFr(c.date_limite_restitution)}</b></div>` : ""}
      ${c.en_retard_restitution ? `<div class="alerte erreur petit">⚠ Délai de restitution dépassé — pratique courante : 1 mois si état des lieux conforme, 2 mois si dégradations.</div>` : ""}` : ""}`}
    ${lignesEch ? `
    <details class="resume"><summary>Échéancier légal de versement (décret 2023-382)</summary>
      <div class="interieur">
        <table class="table-simple">${lignesEch}</table>
        <div class="petit gris">1 mois à l'entrée en jouissance, le reliquat étalé sur 12 mois (1/12e par mois) pour les baux ≤ 500 000 FCFA. La caution ne sert pas à payer le loyer : elle couvre les dégradations constatées à l'état des lieux de sortie.</div>
      </div></details>` : ""}
    ${peutEcrire() && c.statut !== "aucune" && c.statut !== "restituee" ? `
    <div class="grille-actions">
      ${c.reste_a_verser > 0 ? `<button class="btn" id="btn-recu-caution-v"><span class="ic">🧾</span>Encaisser un versement</button>` : ""}
      ${c.statut === "a_restituer" ? `<button class="btn danger" id="btn-restituer-caution"><span class="ic">↩️</span>Restituer la caution</button>` : ""}
    </div>` : ""}
  </div>`;
}

export async function uiRestituerCaution(bailId) {
  const b = await get(`/api/baux/${bailId}`);
  const c = b.caution_detail;
  if (!c) { toast("Situation de caution indisponible.", "erreur"); return; }
  ouvrirModal("Restituer la caution", `
  <form id="f-rest" class="formulaire">
    <div class="ligne-flex" style="margin:6px 0"><b>Caution versée</b><b class="montant">${fcfa(c.versee)}</b></div>
    <div class="alerte info petit">Pratique courante au Sénégal : restitution dans le mois de la remise des clés si l'état des lieux est conforme (2 mois si dégradations). Toute retenue doit être justifiée (état des lieux, devis).</div>
    ${champ({ nom: "montant_retenu", label: "Montant retenu (FCFA) — 0 si rien à retenir", type: "number", valeur: "0", attrs: 'min="0"' })}
    ${champ({ nom: "motif_retenue", label: "Motif de la retenue (obligatoire si retenue)", facultatif: true, placeholder: "Ex : dégradations état des lieux de sortie" })}
    ${champ({ nom: "date_remboursement", label: "Date de remboursement", type: "date", valeur: aujourdHui() })}
    <button class="btn-ligne rouge" type="submit">Enregistrer la restitution + reçu PDF</button>
  </form>`);
  $("#f-rest").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const r = await post(`/api/baux/${bailId}/caution/restituer`, {
        montant_retenu: parseInt(d.montant_retenu || 0, 10),
        motif_retenue: d.motif_retenue || "", date_remboursement: d.date_remboursement,
      });
      toast("Caution restituée — reçu " + r.recu.numero + " ✔", "succes");
      fermerModal();
      window.open(r.recu.lien_pdf, "_blank");
      location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

// ================================================================ LOCATAIRE

async function ficheLocataire(id) {
  const l = await get(`/api/locataires/${id}`);
  return `
  <div class="entete-page"><h1>${esc(l.nom)}</h1></div>
  <div class="carte">
    <div class="ligne-flex"><span class="gris">Téléphone</span><b>${esc(l.telephone || "—")}</b></div>
    <div class="ligne-flex"><span class="gris">WhatsApp</span><b>${esc(l.telephone_whatsapp || l.telephone || "—")}</b></div>
    ${l.notes ? `<div class="petit gris">${esc(l.notes)}</div>` : ""}
  </div>

  <div class="sous-titre">Baux</div>
  ${(l.baux || []).length ? l.baux.map((b) => `
    <div class="carte">
      <div class="ligne-flex"><b>${esc(b.unite_nom)} — ${esc(b.immeuble_nom)}</b>${badge(b.statut)}</div>
      <div class="petit gris">du ${dateFr(b.date_debut)} · loyer ${fcfa(b.loyer + b.charges)} · caution ${fcfa(b.caution)}</div>
      ${(b.echeances || []).slice(0, 3).map((e) => `
        <div class="ligne-flex petit" style="padding:4px 0">
          <span>${esc(e.periode_libelle)}</span>
          <span>${fcfa(e.montant_paye)} / ${fcfa(e.montant_du)} ${badge(e.statut)}</span>
        </div>`).join("")}
      ${peutEcrire() && b.statut === "actif" && (b.echeances || []).some((e) => e.statut !== "paye") ? `
        <a class="btn-ligne petit vert" href="#/encaisser?echeance=${esc((b.echeances || []).find((e) => e.statut !== "paye").id)}">Encaisser</a>` : ""}
    </div>`).join("") : vide("📜", "Aucun bail pour ce locataire.")}

  <div class="sous-titre">Derniers paiements</div>
  ${(l.paiements || []).length ? `<div class="liste">${l.paiements.slice(0, 10).map((p) => `
    <div class="element" style="cursor:default">
      <div class="avatar">${p.montant < 0 ? "↩️" : "💵"}</div>
      <div class="corps"><div class="titre montant">${fcfa(p.montant)}</div>
      <div class="detail">${dateFr(p.date)} · ${{ wave: "Wave", orange_money: "Orange Money", especes: "Espèces", virement: "Virement", cheque: "Chèque", autre: "Autre" }[p.mode] || p.mode}${p.annule ? " · ANNULÉ" : ""}</div></div>
      ${p.montant < 0 ? `<span class="puce en_retard">annulation</span>` : '<span class="puce paye">ok</span>'}
    </div>`).join("")}</div>` : vide("💵", "Aucun paiement enregistré.")}

  <div class="espace"></div>
  ${peutEcrire() ? `
  <div class="grille-actions">
    <button class="btn" id="btn-doc-loc"><span class="ic">📄</span>Ajouter un document</button>
    <button class="btn" id="btn-modif-loc"><span class="ic">✏️</span>Modifier</button>
  </div>` : ""}`;
}

// ================================================================ Branchements (après rendu)

export async function brancherTout() {
  // Cette fonction est appelée par app.js via apresRendu de la route ; simplification :
}

export async function apresRenduFiches() {
}

// Les branchements se font via les boutons présents dans le DOM :
export function brancherBoutons() {
  const b = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  b("btn-retour-biens", () => location.hash = "#/biens");
  b("btn-doc-imm", () => uiDocuments("immeuble", extraireId("#/immeuble/")));
  b("btn-doc-unite", () => uiDocuments("unite", new URLSearchParams(location.hash.split("?")[1]).get("unite")));
  b("btn-doc-loc", () => uiDocuments("locataire", extraireId("#/locataire/")));
  b("btn-modif-loc", () => uiModifierLocataire(extraireId("#/locataire/")));
  b("btn-nouveau-bail", () => uiNouveauBail(new URLSearchParams(location.hash.split("?")[1]).get("unite")));
  b("btn-doc-bail", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiDocuments("bail", bid));
  });
  b("btn-modif-bail", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiModifierBail(bid));
  });
  b("btn-fin-bail", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiTerminerBail(bid));
  });
  b("btn-recu-caution", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiRecuAutre(bid, "caution"));
  });
  b("btn-recu-frais", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiRecuAutre(bid, "frais_agence"));
  });
  b("btn-recu-caution-v", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiRecuAutre(bid, "caution"));
  });
  b("btn-restituer-caution", () => {
    const unite = new URLSearchParams(location.hash.split("?")[1]).get("unite");
    trouverBailId(unite).then((bid) => bid && uiRestituerCaution(bid));
  });
  document.querySelectorAll("[data-unite]").forEach((el) => {
    el.onclick = (e) => { e.stopPropagation(); location.hash = "#/bail?unite=" + el.dataset.unite; };
  });
}

function extraireId(prefixe) {
  const h = location.hash.split("?")[0];
  return h.startsWith(prefixe) ? h.slice(prefixe.length) : "";
}

async function trouverBailId(uniteId) {
  const unites = (await get("/api/unites")).unites || [];
  const u = unites.find((x) => x.id === uniteId);
  return u && u.bail_actif ? u.bail_actif.id : null;
}

// ================================================================ Formulaires

async function uiNouveauBail(uniteId) {
  const locs = (await get("/api/locataires")).locataires || [];
  if (!locs.length) { toast("Ajoutez d'abord un locataire.", "erreur"); location.hash = "#/locataires"; return; }
  const unites = (await get("/api/unites")).unites || [];
  const u = unites.find((x) => x.id === uniteId);
  ouvrirModal("Nouveau bail", `
  <form id="f-bail" class="formulaire">
    ${champ({ nom: "locataire_id", label: "Locataire", options: locs.map((l) => ({ valeur: l.id, libelle: `${l.nom} (${l.telephone || "sans tél"})` })) })}
    ${champ({ nom: "date_debut", label: "Date de début", type: "date", valeur: new Date().toISOString().slice(0, 10), attrs: "required" })}
    ${champ({ nom: "loyer", label: "Loyer mensuel (FCFA)", type: "number", valeur: String(u ? u.loyer : 0), attrs: 'min="0" required' })}
    ${champ({ nom: "charges", label: "Charges (FCFA)", type: "number", valeur: String(u ? u.charges : 0), attrs: 'min="0"' })}
    <div class="champs-2">
      ${champ({ nom: "jour_echeance", label: "Jour d'échéance", type: "number", valeur: "5", attrs: 'min="1" max="28"' })}
      ${champ({ nom: "caution", label: "Caution (FCFA)", type: "number", valeur: "0", attrs: 'min="0"' })}
    </div>
    <div class="aide">Loyer payable d'avance : attendu le jour d'échéance (ex. le 5), retard après le 10 — paramétrable. Caution (décret 2023-382) : max 2 mois, 1 mois à l'entrée puis 1/12e par mois pour les baux ≤ 500 000 FCFA.</div>
    ${champ({ nom: "duree_type", label: "Durée", options: [
      { valeur: "triennale", libelle: "Triennale (3 ans, reconduite)" },
      { valeur: "indeterminee", libelle: "Durée indéterminée" },
      { valeur: "autre", libelle: "Autre" }] })}
    <button class="btn-ligne" type="submit">Créer le bail</button>
  </form>`);
  $("#f-bail").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const r = await post("/api/baux", { ...d, unite_id: uniteId,
        loyer: parseInt(d.loyer, 10), charges: parseInt(d.charges || 0, 10),
        jour_echeance: parseInt(d.jour_echeance, 10), caution: parseInt(d.caution || 0, 10) });
      toast("Bail créé — l'échéance du mois est prête ✔", "succes");
      if (r.alertes && r.alertes.length) setTimeout(() => toast(r.alertes[0], ""), 800);
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function uiModifierBail(bailId) {
  const b = await get(`/api/baux/${bailId}`);
  ouvrirModal("Modifier le bail", `
  <form id="f-bail-m" class="formulaire">
    ${champ({ nom: "loyer", label: "Loyer mensuel (FCFA)", type: "number", valeur: String(b.loyer), attrs: 'min="0"' })}
    ${champ({ nom: "motif_loyer", label: "Motif du changement de loyer", facultatif: true, placeholder: "Ex : révision annuelle" })}
    ${champ({ nom: "charges", label: "Charges (FCFA)", type: "number", valeur: String(b.charges), attrs: 'min="0"' })}
    ${champ({ nom: "caution", label: "Caution (FCFA)", type: "number", valeur: String(b.caution), attrs: 'min="0"' })}
    ${champ({ nom: "jour_echeance", label: "Jour d'échéance", type: "number", valeur: String(b.jour_echeance), attrs: 'min="1" max="28"' })}
    ${champ({ nom: "enregistre_statut", label: "Enregistrement DGID", valeur: b.enregistre_statut, options: [
      { valeur: "non", libelle: "À faire" }, { valeur: "en_cours", libelle: "En cours" }, { valeur: "fait", libelle: "Fait" }] })}
    <button class="btn-ligne" type="submit">Enregistrer</button>
  </form>`);
  $("#f-bail-m").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await patch(`/api/baux/${bailId}`, { ...d, loyer: parseInt(d.loyer, 10),
        charges: parseInt(d.charges, 10), caution: parseInt(d.caution, 10), jour_echeance: parseInt(d.jour_echeance, 10) });
      toast("Bail mis à jour ✔", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function uiTerminerBail(bailId) {
  ouvrirModal("Terminer le bail", `
  <form id="f-fin" class="formulaire">
    <div class="alerte attention">Le bien repassera en « libre ». L'historique des paiements est conservé.</div>
    ${champ({ nom: "motif", label: "Motif de fin", placeholder: "Ex : départ du locataire", facultatif: true })}
    <button class="btn-ligne rouge" type="submit">Terminer le bail</button>
  </form>`);
  $("#f-fin").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post(`/api/baux/${bailId}/terminer`, { motif: d.motif || "" });
      toast("Bail terminé. Pensez à la décharge de clés et à la caution.", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function uiRecuAutre(bailId, type) {
  const b = await get(`/api/baux/${bailId}`);
  const titres = { caution: "Reçu de caution", frais_agence: "Reçu de frais d'agence", decharge: "Décharge de remise de clés" };
  const c = b.caution_detail;
  const sugCaution = c && c.echeancier && c.echeancier.length ? c.echeancier[0].montant : (b.caution || 0);
  ouvrirModal(titres[type] || "Reçu", `
  <form id="f-recu" class="formulaire">
    <p class="petit gris">${esc(b.locataire_nom)} — ${esc(b.unite_nom)}</p>
    ${type !== "decharge" ? champ({ nom: "montant", label: "Montant (FCFA)", type: "number", valeur: String(type === "caution" ? sugCaution : Math.round(b.loyer / 2)), attrs: 'min="0"' }) : ""}
    ${type === "caution" ? `<div class="aide">Décret 2023-382 : 1 mois à l'entrée, le reste étalé sur 12 mois (1/12e par mois) — baux ≤ 500 000 FCFA. Versée à ce jour : ${fcfa(c ? c.versee : 0)} / ${fcfa(b.caution)}.</div>` : ""}
    ${champ({ nom: "reference", label: "Référence", facultatif: true })}
    <button class="btn-ligne" type="submit">Générer le reçu PDF</button>
  </form>`);
  $("#f-recu").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const r = await post("/api/recus", { type, bail_id: bailId,
        montant: parseInt(d.montant || 0, 10), reference: d.reference || "" });
      if (r.alertes && r.alertes.length) toast(r.alertes[0], "");
      toast("Reçu " + r.recu.numero + " généré ✔", "succes");
      fermerModal();
      window.open(r.recu.lien_pdf, "_blank");
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function uiModifierLocataire(id) {
  const l = await get(`/api/locataires/${id}`);
  ouvrirModal("Modifier le locataire", `
  <form id="f-loc-m" class="formulaire">
    ${champ({ nom: "nom", label: "Nom complet", valeur: l.nom, attrs: "required" })}
    ${champ({ nom: "telephone", label: "Téléphone", type: "tel", valeur: l.telephone })}
    ${champ({ nom: "telephone_whatsapp", label: "WhatsApp", type: "tel", valeur: l.telephone_whatsapp })}
    ${champ({ nom: "notes", label: "Notes", type: "textarea", valeur: l.notes || "", facultatif: true })}
    <button class="btn-ligne" type="submit">Enregistrer</button>
  </form>`);
  $("#f-loc-m").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await patch(`/api/locataires/${id}`, d);
      toast("Locataire mis à jour ✔", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

// ================================================================ Documents / scanner (F12)

export function uiDocuments(attacheType, attacheId) {
  ouvrirModal("Ajouter un document", `
  <form id="f-doc" class="formulaire">
    ${champ({ nom: "type_document", label: "Type de document", options: [
      { valeur: "bail_signe", libelle: "Bail signé" },
      { valeur: "piece_identite", libelle: "Pièce d'identité" },
      { valeur: "titre_propriete", libelle: "Titre de propriété / attestation" },
      { valeur: "etat_des_lieux", libelle: "État des lieux" },
      { valeur: "recu_papier", libelle: "Reçu papier" },
      { valeur: "justificatif", libelle: "Justificatif de paiement" },
      { valeur: "facture_travaux", libelle: "Facture de travaux" },
      { valeur: "enregistrement", libelle: "Enregistrement du bail (DGID)" },
      { valeur: "autre", libelle: "Autre" }] })}
    <label>Photos ou PDF
      <input name="fichiers" type="file" accept="image/*,application/pdf" multiple capture="environment" required></label>
    <div class="aide">Plusieurs photos = un seul PDF. Les images sont compressées automatiquement.</div>
    <button class="btn-ligne" type="submit">Enregistrer le document</button>
  </form>`);
  $("#f-doc").onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const fichiers = Array.from(form.fichiers.files || []);
    if (!fichiers.length) { toast("Choisissez au moins un fichier.", "erreur"); return; }
    const bouton = form.querySelector("button[type=submit]");
    bouton.disabled = true; bouton.textContent = "Envoi…";
    try {
      const fd = new FormData();
      for (const f of fichiers) {
        fd.append("fichiers", f.type.startsWith("image/") && f.type !== "image/png" || f.type === "image/png"
          ? await comprimerImage(f) : f, f.name);
      }
      fd.append("attache_type", attacheType);
      fd.append("attache_id", attacheId);
      fd.append("type_document", form.type_document.value);
      const r = await envoyerFichier("/api/documents", fd);
      toast(r.message || "Document enregistré ✔", "succes");
      fermerModal();
    } catch (err) {
      toast(err.message, "erreur");
      bouton.disabled = false; bouton.textContent = "Enregistrer le document";
    }
  };
}
