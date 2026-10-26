// Rapports (F8) : rapport mensuel par propriétaire, PDF partageable par WhatsApp.
import { get, post, patch, peutEcrire } from "../api.js";
import { $, esc, toast, vide } from "../ui.js";
import { fcfa, libellePeriode, periodeCourante, periodesChoix, telWhatsApp, dateFr } from "../format.js";

export async function rendre() {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const pid = params.get("proprietaire");
  if (pid) return await detail(pid, params.get("periode") || periodeCourante());
  const periode = params.get("periode") || periodeCourante();
  const data = await get(`/api/rapports/proprietaires?periode=${periode}`);
  const rapports = data.rapports || [];
  return `
  <div class="entete-page"><h1>Rapports</h1></div>
  <label class="petit gras">Mois
    <select id="choix-periode" style="margin-top:4px">${periodesChoix().map((p) =>
      `<option value="${p.valeur}" ${p.valeur === periode ? "selected" : ""}>${p.libelle}</option>`).join("")}</select></label>
  <div class="espace"></div>
  <div class="carte carte-solde">
    <div class="libelle">Total encaissé — ${esc(data.periode_libelle)}</div>
    <div style="font-size:1.6rem;font-weight:800" class="montant">${fcfa(rapports.reduce((s, r) => s + r.encaisse, 0))}</div>
    <div class="lignes">
      <div class="ligne-item"><div class="lib">Commissions</div><div class="val montant">${fcfa(rapports.reduce((s, r) => s + r.commission, 0))}</div></div>
      <div class="ligne-item"><div class="lib">À reverser</div><div class="val montant">${fcfa(rapports.reduce((s, r) => s + r.a_reverser, 0))}</div></div>
    </div>
  </div>
  ${rapports.length ? `<div class="liste">${rapports.map((r) => `
    <div class="element" data-prop="${esc(r.proprietaire_id)}">
      <div class="avatar">👤</div>
      <div class="corps"><div class="titre">${esc(r.nom)}</div>
        <div class="detail">encaissé ${fcfa(r.encaisse)} · à reverser ${fcfa(r.a_reverser)}</div></div>
      <div class="droite">${r.nb_en_retard ? `<span class="puce en_retard">${r.nb_en_retard} retard(s)</span>` : '<span class="puce paye">à jour</span>'}</div>
    </div>`).join("")}</div>`
  : vide("📊", "Aucun propriétaire avec des biens pour ce mois.")}`;
}

async function detail(pid, periode) {
  const r = await get(`/api/rapports/proprietaire/${pid}?periode=${periode}`);
  const p = r.proprietaire;
  return `
  <div class="entete-page"><h1>Rapport — ${esc(p.nom)}</h1></div>
  <button class="btn-ligne gris petit" onclick="history.back()">← Retour</button>
  <div class="espace"></div>
  <div class="petit gris">${esc(r.periode_libelle)} · commission agence ${p.commission_pct} %</div>
  <div class="espace"></div>
  <div class="carte">
    <div class="ligne-flex"><b>🤝 Mandat de gestion</b>
      ${p.mandat_fin ? `<span class="puce ${new Date(p.mandat_fin) < new Date() ? "en_retard" : "paye"}">${new Date(p.mandat_fin) < new Date() ? "expiré" : "en cours"}</span>` : '<span class="puce libre">non renseigné</span>'}</div>
    <div class="espace"></div>
    <div class="ligne-flex"><span class="gris">Convention agence ↔ propriétaire</span><b>${esc(p.nom)}</b></div>
    <div class="ligne-flex"><span class="gris">Début du mandat</span><b>${p.mandat_debut ? dateFr(p.mandat_debut) : "—"}</b></div>
    <div class="ligne-flex"><span class="gris">Fin du mandat</span><b>${p.mandat_fin ? dateFr(p.mandat_fin) : "—"}</b></div>
    <div class="ligne-flex"><span class="gris">Commission</span><b>${p.commission_pct} % des loyers encaissés</b></div>
    ${peutEcrire() ? `<div class="espace"></div><button class="btn-ligne secondaire petit" id="btn-mandat">✏️ Modifier le mandat / la commission</button>` : ""}
  </div>
  <div class="carte">
    <div class="ligne-flex"><span>Loyers attendus</span><b class="montant">${fcfa(r.du)}</b></div>
    <div class="ligne-flex"><span>Encaissé</span><b class="montant" style="color:var(--vert)">${fcfa(r.encaisse)}</b></div>
    <div class="ligne-flex"><span>Reste à encaisser</span><b class="montant" style="color:var(--orange)">${fcfa(r.reste_a_encaisser)}</b></div>
    <div class="ligne-flex"><span>Commission (${r.proprietaire.commission_pct} %)</span><b class="montant">${fcfa(r.commission)}</b></div>
    <div class="ligne-flex"><b>Montant à reverser</b><b class="montant" style="font-size:1.2rem;color:var(--bleu-fonce)">${fcfa(r.a_reverser)}</b></div>
  </div>
  ${(r.biens || []).length ? `
  <div class="sous-titre">Détail par bien</div>
  ${r.biens.map((b) => `
  <details class="resume"><summary><span>${esc(b.immeuble)}</span><span class="montant gras">${fcfa(b.paye)}</span></summary>
    <div class="interieur">
      <div class="ligne-flex petit"><span>Unités</span><b>${b.nb_unites}</b></div>
      <div class="ligne-flex petit"><span>Attendu</span><b class="montant">${fcfa(b.du)}</b></div>
      <div class="ligne-flex petit"><span>Encaissé</span><b class="montant">${fcfa(b.paye)}</b></div>
      <div class="ligne-flex petit"><span>Reste</span><b class="montant">${fcfa(b.reste)}</b></div>
      <div class="petit gris">${b.unites.map((u) => esc(u.nom)).join(" · ")}</div>
    </div></details>`).join("")}` : ""}
  <div class="espace"></div>
  ${peutEcrire() ? `<button class="btn-ligne primaire" id="btn-pdf">📄 Générer le PDF du rapport</button>
  <button class="btn-ligne secondaire" onclick="history.back()">← Retour</button>`
  : `<button class="btn-ligne secondaire" onclick="history.back()">← Retour</button>`}`;
}

export async function apresRendu() {
  const sel = $("#choix-periode");
  if (sel) sel.onchange = () => {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    location.hash = "#/rapports?periode=" + sel.value + (params.get("proprietaire") ? "&proprietaire=" + params.get("proprietaire") : "");
  };
  const btnMandat = document.getElementById("btn-mandat");
  if (btnMandat) btnMandat.onclick = async () => {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const pid = params.get("proprietaire");
    const r = await get(`/api/rapports/proprietaire/${pid}?periode=${params.get("periode") || periodeCourante()}`);
    const p = r.proprietaire;
    const { ouvrirModal, fermerModal, champ } = await import("../ui.js");
    ouvrirModal("Mandat de gestion", `
    <form id="f-mandat" class="formulaire">
      <div class="aide">Le mandat formalise la relation agence ↔ propriétaire : l'agence gère les biens et encaisse les loyers pour son compte, contre une commission.</div>
      ${champ({ nom: "commission_pct", label: "Commission agence (%)", type: "number", valeur: String(p.commission_pct), attrs: 'min="0" max="100" step="0.5"' })}
      <div class="champs-2">
        ${champ({ nom: "mandat_debut", label: "Début du mandat", type: "date", valeur: p.mandat_debut || "", facultatif: true })}
        ${champ({ nom: "mandat_fin", label: "Fin du mandat", type: "date", valeur: p.mandat_fin || "", facultatif: true })}
      </div>
      <button class="btn-ligne" type="submit">Enregistrer</button>
    </form>`);
    $("#f-mandat").onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      try {
        await patch(`/api/proprietaires/${pid}`, {
          commission_pct: parseFloat(d.commission_pct) || 0,
          mandat_debut: d.mandat_debut || null, mandat_fin: d.mandat_fin || null,
        });
        toast("Mandat mis à jour ✔", "succes");
        fermerModal(); location.reload();
      } catch (err) { toast(err.message, "erreur"); }
    };
  };
  document.querySelectorAll("[data-prop]").forEach((el) => {
    el.onclick = () => {
      const params = new URLSearchParams(location.hash.split("?")[1] || "");
      location.hash = "#/rapports?proprietaire=" + el.dataset.prop + "&periode=" + (params.get("periode") || periodeCourante());
    };
  });
  const btnPdf = document.getElementById("btn-pdf");
  if (btnPdf) btnPdf.onclick = async () => {
    btnPdf.disabled = true; btnPdf.textContent = "Génération…";
    try {
      const params = new URLSearchParams(location.hash.split("?")[1] || "");
      const r = await post(`/api/rapports/proprietaire/${params.get("proprietaire")}/pdf?periode=${params.get("periode") || periodeCourante()}`, {});
      btnPdf.disabled = false; btnPdf.textContent = "📄 Générer le PDF du rapport";
      const rapportData = r.rapport;
      const message = `Bonjour, voici le rapport de gestion de ${rapportData.periode_libelle} : ` +
        `encaissé ${fcfa(rapportData.encaisse)}, à reverser ${fcfa(rapportData.a_reverser)} FCFA. ${r.lien_public}`;
      const tel = telWhatsApp(rapportData.proprietaire.telephone);
      ouvrirPartage(r.lien_public, r.lien_pdf, tel, message);
    } catch (err) {
      toast(err.message, "erreur");
      btnPdf.disabled = false; btnPdf.textContent = "📄 Générer le PDF du rapport";
    }
  };
}

function ouvrirPartage(lienPublic, lienPdf, tel, message) {
  import("../ui.js").then(({ ouvrirModal, fermerModal }) => {
    ouvrirModal("Rapport prêt 📄", `
      <div class="alerte info">Lien de vérification :<br><b class="petit">${esc(lienPublic)}</b></div>
      <a class="btn-ligne vert" href="https://wa.me/${tel}?text=${encodeURIComponent(message)}" target="_blank" rel="noopener">📲 Envoyer sur WhatsApp</a>
      <a class="btn-ligne secondaire" href="${lienPdf}" target="_blank" rel="noopener">⬇ Télécharger le PDF</a>
      <button class="btn-ligne gris" id="part-fermer">Fermer</button>`);
    document.getElementById("part-fermer").onclick = fermerModal;
  });
}
