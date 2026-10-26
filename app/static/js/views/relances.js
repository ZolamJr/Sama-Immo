// Relances (F7) : retards par ancienneté, recherche, tri, message pré-rédigé, WhatsApp en 1 clic + PDF (v1.2).
import { get, post, peutEcrire } from "../api.js";
import { $, esc, toast, vide } from "../ui.js";
import { fcfa, dateFr, telWhatsApp } from "../format.js";

export async function rendre() {
  const data = await get("/api/relances/retards");
  const retards = data.retards || [];
  return `
  <div class="entete-page"><h1>Loyers en retard</h1></div>
  <div class="sous-titre">Triés par ancienneté — touchez pour préparer le message.</div>
  <input id="rech-rel" type="search" placeholder="🔎 Rechercher un locataire ou un bien…"
         style="width:100%;padding:12px 14px;border:1.5px solid var(--bord);border-radius:12px;margin-bottom:8px;font-size:1rem">
  <div class="ligne-flex" style="gap:8px;margin-bottom:12px;flex-wrap:wrap">
    <select id="tri-rel" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="anciennete">Tri : ancienneté</option>
      <option value="montant">Tri : montant ↓</option>
      <option value="nom">Tri : nom</option>
    </select>
    <a class="btn-ligne secondaire petit" href="/api/rapports/arrieres.pdf" target="_blank" rel="noopener">📄 État des arriérés (PDF)</a>
  </div>
  ${retards.length ? `<div class="liste" id="liste-rel">${retards.map((e) => `
    <div class="element" data-rel="${esc(e.id)}" data-tel="${esc(telWhatsApp(e.locataire_telephone))}"
         data-nom="${esc((e.locataire_nom + " " + e.bien_libelle).toLowerCase())}" data-reste="${e.reste}" data-depuis="${esc(e.date_limite || e.date_echeance)}">
      <div class="avatar">🔴</div>
      <div class="corps">
        <div class="titre">${esc(e.locataire_nom)}</div>
        <div class="detail">${esc(e.bien_libelle)} · ${esc(e.periode_libelle)}</div>
        <div class="detail" style="color:var(--rouge)">En retard depuis le ${dateFr(e.date_limite || e.date_echeance)}</div>
      </div>
      <div class="droite"><div class="montant montant" style="color:var(--rouge)">${fcfa(e.reste)}</div>
        ${e.montant_paye > 0 ? `<span class="puce partiel">partiel</span>` : ""}</div>
    </div>`).join("")}</div>
  <div class="espace"></div>
  <div class="alerte info">💡 Astuce : le message est pré-rédigé et modifiable avant l'envoi WhatsApp.</div>`
  : vide("✅", "Aucun loyer en retard. Bravo !")}`;
}

export async function apresRendu() {
  const rafraichir = () => {
    const rechEl = document.getElementById("rech-rel");
    if (!rechEl) return;
    const q = (rechEl.value || "").toLowerCase();
    const tri = document.getElementById("tri-rel").value;
    const els = Array.from(document.querySelectorAll("#liste-rel .element"));
    for (const el of els) el.style.display = (!q || el.dataset.nom.includes(q)) ? "" : "none";
    if (tri === "montant") els.sort((a, b) => parseInt(b.dataset.reste, 10) - parseInt(a.dataset.reste, 10));
    else if (tri === "nom") els.sort((a, b) => a.dataset.nom.localeCompare(b.dataset.nom));
    else els.sort((a, b) => a.dataset.depuis.localeCompare(b.dataset.depuis));
    const conteneur = document.getElementById("liste-rel");
    if (conteneur) for (const el of els) conteneur.appendChild(el);
  };
  const rechEl = document.getElementById("rech-rel");
  if (rechEl) {
    rechEl.oninput = rafraichir;
    document.getElementById("tri-rel").onchange = rafraichir;
  }
  document.querySelectorAll("[data-rel]").forEach((el) => {
    el.onclick = () => preparerMessage(el.dataset.rel, el.dataset.tel);
  });
}

async function preparerMessage(echeanceId, tel) {
  const data = await get("/api/relances/retards");
  const e = (data.retards || []).find((x) => x.id === echeanceId);
  if (!e) return;
  const { ouvrirModal, fermerModal } = await import("../ui.js");
  ouvrirModal(`Relancer ${e.locataire_nom}`, `
    <div class="ligne-flex" style="margin:6px 0"><b>Reste dû</b><b class="montant" style="color:var(--rouge)">${fcfa(e.reste)}</b></div>
    <label class="petit gras">Message (modifiable)
      <textarea name="message" rows="5" style="margin-top:4px">${esc(e.message)}</textarea></label>
    <button class="btn-ligne vert" id="rel-envoyer">📲 Envoyer sur WhatsApp</button>
    <button class="btn-ligne secondaire" id="rel-annuler">Annuler</button>`);
  $("#rel-annuler").onclick = fermerModal;
  $("#rel-envoyer").onclick = async () => {
    const message = $("#modal textarea").value;
    const url = `https://wa.me/${tel}?text=${encodeURIComponent(message)}`;
    window.open(url, "_blank");
    if (peutEcrire()) {
      try { await post("/api/relances", { echeance_id: echeanceId, message, canal: "whatsapp" }); } catch (err) { /* trace best effort */ }
      toast("Relance enregistrée dans l'historique.", "succes");
    }
    fermerModal();
  };
}
