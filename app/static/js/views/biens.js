// Gestion (F3) : biens des propriétaires gérés par l'agence + filtres et tris (v1.2).
import { get, post, peutEcrire } from "../api.js";
import { $, esc, toast, badge, vide, ouvrirModal, fermerModal, champ } from "../ui.js";
import { fcfa, TYPES_UNITE, comprimerImage } from "../format.js";

export async function rendre() {
  const data = await get("/api/immeubles");
  const props = await get("/api/proprietaires");
  const immeubles = data.immeubles || [];
  const peutAjouter = peutEcrire();
  return `
  <div class="entete-page"><h1>Gestion</h1>
    ${peutAjouter ? `<button class="bouton-ajout" id="btn-ajout-bien">+</button>` : ""}</div>
  <div class="petit gris" style="margin:-6px 0 10px">Biens des propriétaires, gérés par l'agence dans le cadre de leur mandat.</div>
  <input id="recherche-bien" type="search" placeholder="🔎 Rechercher (bien, quartier, propriétaire)…"
         style="width:100%;padding:12px 14px;border:1.5px solid var(--bord);border-radius:12px;margin-bottom:8px;font-size:1rem">
  <div class="ligne-flex" style="gap:8px;margin-bottom:12px;flex-wrap:wrap">
    <select id="filtre-statut" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="tous">Toutes les unités</option>
      <option value="libre">Unités libres</option>
      <option value="occupe">Unités occupées</option>
    </select>
    <select id="tri-biens" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="nom">Trier : nom</option>
      <option value="proprietaire">Trier : propriétaire</option>
      <option value="unites">Trier : nb d'unités</option>
    </select>
  </div>
  <div id="liste-biens">
  ${immeubles.length ? immeubles.map((i) => `
    <div class="carte" style="cursor:pointer" data-imm="${esc(i.id)}" data-txt="${esc((i.nom + " " + (i.quartier || "") + " " + (i.proprietaire_nom || "")).toLowerCase())}" data-prop="${esc((i.proprietaire_nom || "").toLowerCase())}" data-nb="${i.unites.length}">
      <div class="ligne-flex"><b>${esc(i.nom)}</b>
        <span class="gras">${i.unites.length} unité(s)</span></div>
      <div class="petit gris">${esc(i.quartier || "")}${i.quartier && i.adresse ? " · " : ""}${esc(i.adresse || "")}</div>
      <div class="petit gris">Propriétaire : ${esc(i.proprietaire_nom || "—")}</div>
      <div class="espace"></div>
      <div class="liste">${i.unites.map((u) => `
        <div class="element" data-unite="${esc(u.id)}" data-statut="${esc(u.statut)}">
          <div class="avatar">${iconeType(u.type)}</div>
          <div class="corps"><div class="titre">${esc(u.nom)}</div>
          <div class="detail">${TYPES_UNITE[u.type] || u.type} · ${u.bail_actif ? esc(u.bail_actif.locataire_nom) : "libre"}</div></div>
          <div class="droite"><div class="montant montant">${fcfa(u.loyer)}</div>${badge(u.statut)}</div>
        </div>`).join("")}</div>
      ${peutAjouter ? `<button class="btn-ligne secondaire petit" data-ajout-unite="${esc(i.id)}">+ Ajouter une unité</button>` : ""}
    </div>`).join("")
  : vide("🏢", "Aucun bien pour le moment.", peutAjouter ? `<button class="btn-ligne" id="btn-ajout-bien-2">Ajouter un premier bien</button>` : "")}
  ${props.proprietaires && props.proprietaires.length === 0 && peutAjouter ? `<div class="alerte info">Ajoutez d'abord un propriétaire (onglet Paramètres ou bouton +).</div>` : ""}`;
}

function iconeType(t) {
  return { chambre: "🛏️", appartement: "🏢", maison: "🏠", local: "🏪", bureau: "💼" }[t] || "🏠";
}

export async function apresRendu() {
  // filtres et tris de la vue Gestion (v1.2)
  const rafraichir = () => {
    const rechEl = document.getElementById("recherche-bien");
    if (!rechEl) return;
    const q = (rechEl.value || "").toLowerCase();
    const statut = document.getElementById("filtre-statut").value;
    const tri = document.getElementById("tri-biens").value;
    const cartes = Array.from(document.querySelectorAll("#liste-biens [data-imm]"));
    for (const c of cartes) {
      const okRecherche = !q || c.dataset.txt.includes(q);
      let okStatut = true;
      if (statut !== "tous") {
        const unites = Array.from(c.querySelectorAll("[data-unite]"));
        okStatut = unites.some((u) => u.dataset.statut === statut);
      }
      c.style.display = okRecherche && okStatut ? "" : "none";
      c.querySelectorAll("[data-unite]").forEach((u) => {
        u.style.display = (statut === "tous" || u.dataset.statut === statut) ? "" : "none";
      });
    }
    if (tri === "proprietaire") cartes.sort((a, b) => a.dataset.prop.localeCompare(b.dataset.prop));
    else if (tri === "unites") cartes.sort((a, b) => parseInt(b.dataset.nb, 10) - parseInt(a.dataset.nb, 10));
    else cartes.sort((a, b) => a.dataset.txt.localeCompare(b.dataset.txt));
    const conteneur = document.getElementById("liste-biens");
    for (const c of cartes) conteneur.appendChild(c);
  };
  const rech = document.getElementById("recherche-bien");
  if (rech) {
    rech.oninput = rafraichir;
    document.getElementById("filtre-statut").onchange = rafraichir;
    document.getElementById("tri-biens").onchange = rafraichir;
  }
  document.querySelectorAll("[data-imm]").forEach((c) => {
    c.onclick = (e) => {
      if (e.target.closest("[data-unite]")) return;
      if (e.target.closest("[data-ajout-unite]")) return;
      location.hash = "#/immeuble/" + c.dataset.imm;
    };
  });
  document.querySelectorAll("[data-unite]").forEach((el) => {
    el.onclick = (e) => { e.stopPropagation(); location.hash = "#/bail?unite=" + el.dataset.unite; };
  });
  document.querySelectorAll("[data-ajout-unite]").forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); formulaireUnite(b.dataset.ajoutUnite); };
  });
  const ajout = () => formulaireImmeuble();
  const b1 = document.getElementById("btn-ajout-bien");
  const b2 = document.getElementById("btn-ajout-bien-2");
  if (b1) b1.onclick = ajout;
  if (b2) b2.onclick = ajout;
}

async function formulaireImmeuble() {
  const props = (await get("/api/proprietaires")).proprietaires || [];
  if (!props.length) {
    await formulaireProprietairePuis(() => formulaireImmeuble());
    return;
  }
  ouvrirModal("Nouveau bien", `
  <form id="f-imm" class="formulaire">
    ${champ({ nom: "nom", label: "Nom du bien", placeholder: "Ex : Immeuble Mermoz ou Appartement B2", attrs: "required" })}
    ${champ({ nom: "proprietaire_id", label: "Propriétaire", options: props.map((p) => ({ valeur: p.id, libelle: p.nom })) })}
    <div class="champs-2">
      ${champ({ nom: "quartier", label: "Quartier", placeholder: "Mermoz" })}
      ${champ({ nom: "adresse", label: "Adresse", facultatif: true })}
    </div>
    <button class="btn-ligne" type="submit">Enregistrer le bien</button>
  </form>`);
  $("#f-imm").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/immeubles", d);
      toast("Bien enregistré ✔", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function formulaireProprietairePuis(suite) {
  ouvrirModal("D'abord, un propriétaire", `
  <form id="f-prop" class="formulaire">
    ${champ({ nom: "nom", label: "Nom du propriétaire", attrs: "required" })}
    ${champ({ nom: "telephone", label: "Téléphone", type: "tel", placeholder: "77 123 45 67", attrs: "required" })}
    ${champ({ nom: "commission_pct", label: "Commission agence (%)", type: "number", valeur: "5", attrs: 'min="0" max="100" step="0.5"' })}
    <button class="btn-ligne" type="submit">Enregistrer</button>
  </form>`);
  $("#f-prop").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/proprietaires", { ...d, commission_pct: parseFloat(d.commission_pct) || 0 });
      toast("Propriétaire enregistré ✔", "succes");
      fermerModal(); suite();
    } catch (err) { toast(err.message, "erreur"); }
  };
}

async function formulaireUnite(immeubleId) {
  ouvrirModal("Nouvelle unité", `
  <form id="f-uni" class="formulaire">
    ${champ({ nom: "nom", label: "Nom / numéro", placeholder: "Ex : Chambre 3, Appart B2", attrs: "required" })}
    ${champ({ nom: "type", label: "Type", options: Object.entries(TYPES_UNITE).map(([v, l]) => ({ valeur: v, libelle: l })) })}
    ${champ({ nom: "loyer", label: "Loyer mensuel (FCFA)", type: "number", valeur: "0", attrs: 'min="0"' })}
    ${champ({ nom: "charges", label: "Charges mensuelles (FCFA)", type: "number", valeur: "0", attrs: 'min="0"', facultatif: true })}
    <button class="btn-ligne" type="submit">Enregistrer l'unité</button>
  </form>`);
  $("#f-uni").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/unites", { ...d, immeuble_id: immeubleId, loyer: parseInt(d.loyer || 0, 10), charges: parseInt(d.charges || 0, 10) });
      toast("Unité enregistrée ✔", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}
