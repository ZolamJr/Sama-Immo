// Encaisser un loyer : échéance -> montant pré-rempli -> confirmation Wave-like -> quittance WhatsApp.
// Accueil -> Encaisser -> choisir le locataire -> valider = 3 clics (§3).
import { get, post, peutEcrire, pendingPaiements, uuid, deviceId, ajouterPendingPaiement, synchroniser, majBadge } from "../api.js";
import { $, esc, toast, badge, vide } from "../ui.js";
import { fcfa, dateFr, libellePeriode, periodeCourante, periodesChoix, MODES, telWhatsApp, aujourdHui } from "../format.js";

export async function rendre() {
  if (!peutEcrire()) return `<div class="carte"><div class="alerte info">Compte propriétaire : consultation seule.</div></div>`;
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  if (params.get("echeance")) return await fichePaiement(params.get("echeance"));
  return await listeChoix();
}

async function listeChoix() {
  const paramsQ = new URLSearchParams(location.hash.split("?")[1] || "");
  const periode = paramsQ.get("periode") || periodeCourante();
  const filtreLoc = paramsQ.get("locataire") || "";
  const data = await get(`/api/echeances?periode=${periode}`);
  const pend = await pendingPaiements();
  const parId = new Map();
  for (const p of pend) parId.set(p.echeance_id, (parId.get(p.echeance_id) || 0) + p.montant);
  const nonSoldees = data.echeances.filter((e) => e.statut !== "paye");
  const melangees = nonSoldees.map((e) => {
    const enPlus = parId.get(e.id) || 0;
    if (!enPlus) return e;
    return { ...e, montant_paye: e.montant_paye + enPlus, reste: Math.max(0, e.reste - enPlus), a_sync: true };
  });
  melangees.sort((a, b) => (b.statut === "en_retard" ? 1 : 0) - (a.statut === "en_retard" ? 1 : 0));

  return `
  <div class="entete-page"><h1>Encaisser un loyer</h1></div>
  ${filtreLoc ? `<button class="btn-ligne gris petit" id="btn-retour-loc">← Retour à la fiche du locataire</button>` : ""}
  <label class="petit gras">Mois concerné
    <select id="choix-periode" style="margin-top:4px">${periodesChoix().map((p) =>
      `<option value="${p.valeur}" ${p.valeur === periode ? "selected" : ""}>${p.libelle}</option>`).join("")}</select></label>
  <div class="espace"></div>
  <input id="rech-ech" type="search" placeholder="🔎 Rechercher un locataire ou un bien…"
         style="width:100%;padding:12px 14px;border:1.5px solid var(--bord);border-radius:12px;margin-bottom:8px;font-size:1rem">
  <div class="ligne-flex" style="gap:8px;margin-bottom:12px;flex-wrap:wrap">
    <select id="filtre-statut-ech" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="tous">Tous les statuts</option>
      <option value="en_attente">En attente</option>
      <option value="partiel">Partiels</option>
      <option value="en_retard">En retard</option>
    </select>
    <select id="tri-ech" style="padding:8px 10px;border:1.5px solid var(--bord);border-radius:10px">
      <option value="defaut">Tri : retards d'abord</option>
      <option value="nom">Tri : nom du locataire</option>
      <option value="montant">Tri : montant ↓</option>
      <option value="limite">Tri : date limite</option>
    </select>
  </div>
  ${melangees.length ? `<div class="liste" id="liste-ech">${melangees.map((e) => `
    <div class="element" data-ech="${esc(e.id)}" data-statut="${esc(e.statut)}" data-nom="${esc((e.locataire_nom + " " + e.bien_libelle).toLowerCase())}" data-reste="${e.reste}" data-limite="${esc(e.date_limite || e.date_echeance)}" data-loc="${esc(e.locataire_id)}">
      <div class="avatar">${e.statut === "en_retard" ? "🔴" : "💵"}</div>
      <div class="corps">
        <div class="titre">${esc(e.locataire_nom)}</div>
        <div class="detail">${esc(e.bien_libelle)} · ${esc(e.periode_libelle)}${filtreLoc && e.locataire_id !== filtreLoc ? " (autre locataire)" : ""}</div>
      </div>
      <div class="droite"><div class="montant montant">${fcfa(e.reste)}</div>${badge(e.statut)}${e.a_sync ? ' <span class="puce partiel">à sync.</span>' : ""}</div>
    </div>`).join("")}</div>` : vide("🎉", "Tout est encaissé pour " + libellePeriode(periode) + " !")}
  <div class="espace"></div>
  <a class="btn-ligne secondaire" href="#/relances">Voir les retards</a>
  <a class="btn-ligne secondaire" href="/api/rapports/loyers-mois.pdf?periode=${periode}" target="_blank" rel="noopener">📄 État des loyers du mois (PDF)</a>`;
}

async function fichePaiement(echeanceId) {
  const ech = await get(`/api/echeances/${echeanceId}`);
  const reste = Math.max(0, ech.reste);

  return `
  <div class="entete-page"><h1>Paiement de loyer</h1></div>
  <div class="carte">
    <div class="ligne-flex"><b>${esc(ech.locataire_nom)}</b>${badge(ech.statut)}</div>
    <div class="petit gris">${esc(ech.bien_libelle)}</div>
    <div class="petit gris">Période : ${esc(ech.periode_libelle)} · loyer attendu le ${dateFr(ech.date_echeance)}${ech.date_limite ? ` · retard après le ${dateFr(ech.date_limite)}` : ""}</div>
    <div class="espace"></div>
    <div class="ligne-flex"><span>Total dû</span><b class="montant">${fcfa(ech.montant_du)}</b></div>
    <div class="ligne-flex"><span>Déjà payé</span><b class="montant" style="color:var(--vert)">${fcfa(ech.montant_paye)}</b></div>
    <div class="ligne-flex"><b>Reste à payer</b><b class="montant" style="color:var(--rouge);font-size:1.2rem">${fcfa(reste)}</b></div>
  </div>

  <form id="f-paiement" class="carte formulaire" data-locataire="${esc(ech.locataire_nom)}"
        data-bien="${esc(ech.bien_libelle)}" data-periode="${esc(ech.periode_libelle)}"
        data-tel="${esc(telWhatsApp(ech.locataire_telephone))}">
    <label>Montant reçu (FCFA)
      <input name="montant" type="number" inputmode="numeric" min="1" value="${reste}" required>
    </label>
    <div class="aide">Montant pré-rempli : ajustez pour un paiement partiel.</div>
    <label>Mode de paiement
      <select name="mode">
        ${Object.entries(MODES).map(([k, v]) => `<option value="${k}" ${k === "wave" ? "selected" : ""}>${v}</option>`).join("")}
      </select></label>
    <div class="champs-2">
      <label>Date
        <input name="date_paiement" type="date" value="${aujourdHui()}" required></label>
      <label>Référence <span class="facultatif">(facultatif)</span>
        <input name="reference" placeholder="Ex : TX Wave"></label>
    </div>
    <button class="btn-ligne vert" type="submit">✔ Valider le paiement</button>
    <a class="btn-ligne secondaire" href="#/encaisser">Annuler</a>
  </form>`;
}

export async function apresRendu() {
  const sel = $("#choix-periode");
  if (sel) sel.onchange = () => {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    location.hash = "#/encaisser?periode=" + sel.value + (params.get("locataire") ? "&locataire=" + params.get("locataire") : "");
  };
  const retourLoc = document.getElementById("btn-retour-loc");
  if (retourLoc) retourLoc.onclick = () => history.back();
  // filtres / tri / recherche (v1.2) + filtre locataire venu de sa fiche
  const paramsQ = new URLSearchParams(location.hash.split("?")[1] || "");
  const filtreLoc = paramsQ.get("locataire") || "";
  const rafraichir = () => {
    const rechEl = document.getElementById("rech-ech");
    if (!rechEl) return;
    const q = (rechEl.value || "").toLowerCase();
    const statut = document.getElementById("filtre-statut-ech").value;
    const tri = document.getElementById("tri-ech").value;
    const els = Array.from(document.querySelectorAll("#liste-ech .element"));
    for (const el of els) {
      const ok = (!q || el.dataset.nom.includes(q))
        && (statut === "tous" || el.dataset.statut === statut)
        && (!filtreLoc || el.dataset.ech === filtreLoc || true); // le locataire ciblé reste en tête
      el.style.display = ok ? "" : "none";
    }
    if (filtreLoc) {
      // le locataire ciblé passe en premier
      els.sort((a, b) => 0); // ordre conservé ; mise en avant visuelle ci-dessous
    }
    if (tri === "nom") els.sort((a, b) => a.dataset.nom.localeCompare(b.dataset.nom));
    else if (tri === "montant") els.sort((a, b) => parseInt(b.dataset.reste, 10) - parseInt(a.dataset.reste, 10));
    else if (tri === "limite") els.sort((a, b) => a.dataset.limite.localeCompare(b.dataset.limite));
    const conteneur = document.getElementById("liste-ech");
    if (conteneur) for (const el of els) conteneur.appendChild(el);
  };
  const rechEl = document.getElementById("rech-ech");
  if (rechEl) {
    rechEl.oninput = rafraichir;
    document.getElementById("filtre-statut-ech").onchange = rafraichir;
    document.getElementById("tri-ech").onchange = rafraichir;
    if (filtreLoc) {
      // pré-filtrage : ne montrer que les échéances de ce locataire
      document.querySelectorAll("#liste-ech .element").forEach((el) => {
        const ech = trouverEcheanceLoc(el);
        el.style.display = ech ? "" : "none";
      });
    }
    rafraichir();
  }
  document.querySelectorAll("[data-ech]").forEach((el) => {
    el.onclick = () => { location.hash = "#/encaisser?echeance=" + el.dataset.ech; };
  });
  const form = document.getElementById("f-paiement");
  if (form) brancherFormulaire(form);
}

// associe chaque échéance affichée à son locataire (pour le filtre ?locataire=)
let _cacheEcheancesLoc = null;
async function trouverEcheanceLoc(el) {
  if (!_cacheEcheancesLoc) {
    try {
      const paramsQ = new URLSearchParams(location.hash.split("?")[1] || "");
      const periode = paramsQ.get("periode") || periodeCourante();
      const data = await get(`/api/echeances?periode=${periode}`, { silent: true });
      _cacheEcheancesLoc = data.echeances || [];
    } catch { _cacheEcheancesLoc = []; }
  }
  const ech = _cacheEcheancesLoc.find((x) => x.id === el.dataset.ech);
  const filtreLoc = new URLSearchParams(location.hash.split("?")[1] || "").get("locataire");
  return !filtreLoc || (ech && ech.locataire_id === filtreLoc);
}

function brancherFormulaire(form) {
  form.onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    const bouton = form.querySelector("button[type=submit]");
    bouton.disabled = true; bouton.textContent = "Enregistrement…";
    const echeanceId = new URLSearchParams(location.hash.split("?")[1] || "").get("echeance");
    const corps = {
      echeance_id: echeanceId, montant: parseInt(d.montant, 10), mode: d.mode,
      date_paiement: d.date_paiement, reference: d.reference || "", client_uuid: uuid(),
    };
    const ctx = {
      locataire: form.dataset.locataire, bien: form.dataset.bien,
      periode: form.dataset.periode, telephone: form.dataset.tel,
      montant: corps.montant, mode: d.mode,
    };
    try {
      // En ligne : enregistrement direct. Hors ligne : file d'attente + affichage immédiat (F10).
      const resultat = await post("/api/paiements", corps, {
        horsLigneAutorise: true, typeAction: "paiement.create", payloadAction: () => corps,
      });
      if (resultat.hors_ligne) {
        const numeroProv = "ATT-" + deviceId() + "-" + String(Date.now()).slice(-4);
        await ajouterPendingPaiement({ action_id: resultat.action_id, echeance_id: echeanceId,
          montant: corps.montant, numero_prov: numeroProv, date: corps.date_paiement });
        await majBadge();
        synchroniser();
        ecranSucces({ ...ctx, numero: numeroProv, provisoire: true, client_uuid: corps.client_uuid });
        return;
      }
      ecranSucces({ ...ctx, numero: resultat.recu && resultat.recu.numero,
        lienPdf: resultat.recu && resultat.recu.lien_pdf, lienVerif: resultat.recu && resultat.recu.lien_verif,
        dejaExistant: resultat.deja_existant });
    } catch (err) {
      toast(err.message === "Failed to fetch" ? "Réseau indisponible, réessayez." : err.message, "erreur");
      bouton.disabled = false; bouton.textContent = "✔ Valider le paiement";
    }
  };
}

function ecranSucces(s) {
  const agence = (JSON.parse((function(){try{return localStorage.getItem("user")}catch(e){return null}})() || "{}").nom || "");
  const messageWa = `Bonjour ${s.locataire}, voici votre quittance de loyer n° ${s.numero} pour ${s.periode} ` +
    `(${fcfa(s.montant)}). Merci de votre confiance.` +
    (s.lienVerif ? ` Vérifiable ici : ${location.origin}${s.lienVerif}` : "");
  const urlWa = `https://wa.me/${s.telephone}?text=${encodeURIComponent(messageWa)}`;
  document.getElementById("contenu").innerHTML = `
  <div class="carte succes">
    <div class="rond">✔</div>
    <h2>Paiement enregistré</h2>
    <div class="gris">${s.dejaExistant ? "Ce paiement était déjà enregistré (pas de doublon créé)." : ""}</div>
    <div class="montant-gros montant">${fcfa(s.montant)}</div>
    <div class="recap">
      <div class="ligne"><span>Locataire</span><b>${esc(s.locataire)}</b></div>
      <div class="ligne"><span>Bien</span><b>${esc(s.bien)}</b></div>
      <div class="ligne"><span>Période</span><b>${esc(s.periode)}</b></div>
      <div class="ligne"><span>Mode</span><b>${esc(MODES[s.mode] || s.mode)}</b></div>
      <div class="ligne"><span>Quittance</span><b>${esc(s.numero || "—")}</b></div>
    </div>
    ${s.provisoire
      ? `<div class="alerte attention">⚠ Hors ligne : la quittance ${esc(s.numero)} est provisoire.
         Le numéro définitif sera attribué à la synchronisation.</div>`
      : `<a class="btn-ligne vert" href="${urlWa}" target="_blank" rel="noopener">📲 Envoyer la quittance (WhatsApp)</a>`}
    ${s.lienPdf ? `<a class="btn-ligne secondaire" href="${s.lienPdf}" target="_blank" rel="noopener">⬇ Télécharger le PDF</a>` : ""}
    <button class="btn-ligne" onclick="location.hash='#/accueil'">Terminer</button>
  </div>`;
}
