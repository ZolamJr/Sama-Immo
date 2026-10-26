// Locataires (F4) : liste + ajout en 3 clics, accès à la fiche complète (baux, paiements, documents).
import { get, post, patch, peutEcrire, pendingLocataires } from "../api.js";
import { $, esc, toast, vide, ouvrirModal, fermerModal, champ } from "../ui.js";
import { fcfa, dateFr } from "../format.js";

export async function rendre() {
  const [data, pend] = await Promise.all([get("/api/locataires"), pendingLocataires()]);
  const locs = data.locataires || [];
  const tous = [...locs, ...pend.map((p) => ({ ...p, nom: p.nom + " (à synchroniser)" }))];
  return `
  <div class="entete-page"><h1>Locataires</h1>
    ${peutEcrire() ? `<button class="bouton-ajout" id="btn-ajout-loc">+</button>` : ""}</div>
  <input id="recherche-loc" type="search" placeholder="🔎 Rechercher un nom…"
         style="width:100%;padding:12px 14px;border:1.5px solid var(--bord);border-radius:12px;margin-bottom:8px;font-size:1rem">
  <div class="ligne-flex" style="gap:8px;margin-bottom:12px;flex-wrap:wrap">
    <select id="filtre-loc" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="tous">Tous les locataires</option>
      <option value="actif">Avec bail en cours</option>
      <option value="sans">Sans bail en cours</option>
    </select>
  </div>
  ${tous.length ? `<div class="liste" id="liste-loc">${tous.map((l) => `
    <div class="element" data-loc="${esc(l.id)}" data-nom="${esc(l.nom.toLowerCase())}" data-baux="${l.nb_baux_actifs || 0}">
      <div class="avatar">👤</div>
      <div class="corps"><div class="titre">${esc(l.nom)}</div>
        <div class="detail">${esc(l.telephone || "sans téléphone")}</div></div>
      <div class="droite">${l.nb_baux_actifs ? `<span class="puce occupe">${l.nb_baux_actifs} bail(s)</span>` : `<span class="puce libre">aucun bail</span>`}</div>
    </div>`).join("")}</div>` : vide("👤", "Aucun locataire enregistré.")}`;
}

export async function apresRendu() {
  const rech = document.getElementById("recherche-loc");
  if (rech) rech.oninput = () => {
    const q = rech.value.toLowerCase();
    document.querySelectorAll("#liste-loc .element").forEach((el) => {
      el.style.display = el.dataset.nom.includes(q) ? "" : "none";
    });
  };
  document.querySelectorAll("[data-loc]").forEach((el) => {
    el.onclick = () => { location.hash = "#/locataire/" + el.dataset.loc; };
  });
  const btn = document.getElementById("btn-ajout-loc");
  if (btn) btn.onclick = formulaireAjout;
}

function formulaireAjout() {
  ouvrirModal("Nouveau locataire", `
  <form id="f-loc" class="formulaire">
    ${champ({ nom: "nom", label: "Nom complet", placeholder: "Ex : Aïssatou Ndiaye", attrs: "required" })}
    ${champ({ nom: "telephone", label: "Téléphone", type: "tel", placeholder: "77 123 45 67", attrs: "required" })}
    ${champ({ nom: "telephone_whatsapp", label: "WhatsApp", type: "tel", placeholder: "Identique si vide", facultatif: true })}
    ${champ({ nom: "notes", label: "Notes", type: "textarea", facultatif: true })}
    <button class="btn-ligne" type="submit">Enregistrer</button>
  </form>`);
  $("#f-loc").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/locataires", d);
      toast("Locataire enregistré ✔", "succes");
      fermerModal(); location.reload();
    } catch (err) { toast(err.message, "erreur"); }
  };
}
