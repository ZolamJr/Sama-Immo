// Petits utilitaires d'interface : toast, modale, échappement, montants.
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Stockage local sécurisé : dans certains contextes (page ouverte en fichier,
// iframe, réglages stricts), localStorage lève une exception et tuerait l'application.
export const stock = {
  get(cle) { try { return localStorage.getItem(cle); } catch { return null; } },
  set(cle, val) { try { localStorage.setItem(cle, val); } catch { /* ignoré */ } },
  del(cle) { try { localStorage.removeItem(cle); } catch { /* ignoré */ } },
  sessionGet(cle) { try { return sessionStorage.getItem(cle); } catch { return null; } },
  sessionSet(cle, val) { try { sessionStorage.setItem(cle, val); } catch { /* ignoré */ } },
};

export function $(sel, racine = document) { return racine.querySelector(sel); }
export function $$(sel, racine = document) { return Array.from(racine.querySelectorAll(sel)); }

let _toastTimer = null;
export function toast(message, type = "") {
  const conteneur = document.getElementById("toast");
  const div = document.createElement("div");
  div.className = "toast-msg " + type;
  div.textContent = message;
  conteneur.appendChild(div);
  setTimeout(() => div.remove(), 4200);
}

export function ouvrirModal(titre, contenuHtml, onOuvert) {
  const fond = $("#modal-fond"), modal = $("#modal");
  modal.innerHTML = `<button class="fermer" data-fermer>✕</button><h3>${esc(titre)}</h3>` + contenuHtml;
  fond.classList.remove("cache");
  modal.querySelector("[data-fermer]").onclick = fermerModal;
  fond.onclick = (e) => { if (e.target === fond) fermerModal(); };
  if (onOuvert) onOuvert(modal);
}
export function fermerModal() { $("#modal-fond").classList.add("cache"); }

export function confirmer(texte) {
  return new Promise((resolve) => {
    ouvrirModal("Confirmation", `
      <p>${esc(texte)}</p>
      <button class="btn-ligne rouge" id="conf-oui">Oui, continuer</button>
      <button class="btn-ligne secondaire" id="conf-non">Annuler</button>`);
    $("#conf-oui").onclick = () => { fermerModal(); resolve(true); };
    $("#conf-non").onclick = () => { fermerModal(); resolve(false); };
  });
}

// Champ de formulaire réutilisable
export function champ({ nom, label, type = "text", valeur = "", aide = "", facultatif = false, options = null, attrs = "" }) {
  if (options) {
    const opts = options.map((o) =>
      `<option value="${esc(o.valeur)}" ${String(o.valeur) === String(valeur) ? "selected" : ""}>${esc(o.libelle)}</option>`).join("");
    return `<label>${esc(label)}${facultatif ? ' <span class="facultatif">(facultatif)</span>' : ""}
      <select name="${nom}" ${attrs}>${opts}</select></label>${aide ? `<div class="aide">${esc(aide)}</div>` : ""}`;
  }
  return `<label>${esc(label)}${facultatif ? ' <span class="facultatif">(facultatif)</span>' : ""}
    <input name="${nom}" type="${type}" value="${esc(valeur ?? "")}" ${attrs}></label>${aide ? `<div class="aide">${esc(aide)}</div>` : ""}`;
}

export function lireFormulaire(form) {
  const data = {};
  new FormData(form).forEach((v, k) => { data[k] = typeof v === "string" ? v.trim() : v; });
  return data;
}

export function badge(statut) {
  const lib = { paye: "Payé", partiel: "Partiel", en_attente: "En attente", en_retard: "En retard",
    occupe: "Occupé", libre: "Libre", actif: "Actif", termine: "Terminé" }[statut] || statut;
  return `<span class="puce ${esc(statut)}">${esc(lib)}</span>`;
}

export function vide(em, texte, action = "") {
  return `<div class="vide"><span class="em">${em}</span>${esc(texte)}${action}</div>`;
}
