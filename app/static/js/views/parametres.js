// Paramètres (F9, F11, F13) : agence, signature/tampon, employés, règles locales, modèles, PIN, export.
import { get, post, patch, peutEcrire, envoyerFichier, deconnexion, estProprietaire } from "../api.js";
import { $, esc, toast, ouvrirModal, fermerModal, champ, stock } from "../ui.js";
import { comprimerImage, dateHeureFr } from "../format.js";

export async function rendre() {
  if (estProprietaire()) {
    return `<div class="carte"><b>Compte propriétaire (lecture seule)</b>
      <p class="petit gris">Vous consultez vos biens, loyers et rapports. Contactez votre gérant pour toute modification.</p>
      <button class="btn-ligne gris" id="btn-deconnexion">Se déconnecter</button></div>`;
  }
  const d = await get("/api/agence");
  const a = d.agence;
  return `
  <div class="entete-page"><h1>Paramètres</h1></div>

  <details class="resume" open><summary>🏢 Mon agence</summary><div class="interieur">
    <form id="f-agence" class="formulaire">
      ${champ({ nom: "nom", label: "Nom de l'agence", valeur: a.nom })}
      ${champ({ nom: "telephone", label: "Téléphone", type: "tel", valeur: a.telephone })}
      ${champ({ nom: "email", label: "E-mail", type: "email", valeur: a.email, facultatif: true })}
      ${champ({ nom: "adresse", label: "Adresse", valeur: a.adresse, facultatif: true })}
      <button class="btn-ligne petit" type="submit">Enregistrer</button>
    </form>
    <div class="espace"></div>
    <div class="sous-titre">Personnalisation des documents</div>
    <div class="grille-actions">
      ${a.logo_path ? `<div class="carte centre" style="padding:10px"><img src="/api/agence/image/logo" alt="Logo" style="max-height:60px;max-width:120px;object-fit:contain"><button class="btn-ligne gris petit" data-retire="logo">Retirer</button></div>` : `<button class="btn" id="btn-logo"><span class="ic">🖼️</span>Logo</button>`}
      ${a.tampon_path ? `<div class="carte centre" style="padding:10px"><img src="/api/agence/image/tampon" alt="Tampon" style="max-height:60px;max-width:80px;object-fit:contain"><button class="btn-ligne gris petit" data-retire="tampon">Retirer</button></div>` : `<button class="btn" id="btn-tampon"><span class="ic">🖨️</span>Tampon</button>`}
      ${a.signature_path ? `<div class="carte centre" style="padding:10px"><img src="/api/agence/image/signature" alt="Signature" style="max-height:60px;max-width:120px;object-fit:contain"><button class="btn-ligne gris petit" data-retire="signature">Retirer</button></div>` : `<button class="btn" id="btn-signature"><span class="ic">✍️</span>Signature</button>`}
    </div>
    <div class="petit gris centre">Signature du gérant et tampon sont apposés automatiquement sur les quittances, reçus et rapports PDF.</div>
  </div></details>

  <details class="resume"><summary>🔐 Code PIN et sécurité</summary><div class="interieur">
    <p class="petit gris">Un code PIN demande à chaque ouverture de l'application sur ce téléphone.</p>
    <button class="btn-ligne secondaire petit" id="btn-pin">${stock.get("pin_hash") ? "Changer le code PIN" : "Activer un code PIN"}</button>
    ${stock.get("pin_hash") ? `<button class="btn-ligne gris petit" id="btn-pin-off">Désactiver le PIN</button>` : ""}
    <button class="btn-ligne gris petit" id="btn-deconnexion">Se déconnecter</button>
  </div></details>

  <details class="resume"><summary>👥 Équipe et rôles (F11)</summary><div class="interieur" id="zone-users">Chargement…</div></details>

  <details class="resume"><summary>📏 Règles locales (F13)</summary><div class="interieur" id="zone-regles">Chargement…</div></details>

  <details class="resume"><summary>💬 Modèles de messages (F9)</summary><div class="interieur" id="zone-modeles">Chargement…</div></details>

  <details class="resume"><summary>💾 Données et sauvegardes</summary><div class="interieur">
    <p class="petit gris">Sauvegarde automatique quotidienne du serveur. Exports CSV pour Excel.</p>
    <div class="grille-actions">
      ${["proprietaires", "immeubles", "unites", "locataires", "baux", "echeances", "paiements"].map((t) =>
        `<a class="btn" href="/api/export/${t}.csv"><span class="ic">📊</span>${t}</a>`).join("")}
    </div>
    <a class="btn-ligne secondaire petit" href="#/audit">👁️ Voir le journal d'activité</a>
  </div></details>

  <div class="petit gris centre">SamaImmo v1.2 — les paiements ne se suppriment jamais : une erreur se corrige par une écriture d'annulation motivée.</div>`;
}

export async function apresRendu() {
  document.getElementById("btn-deconnexion").onclick = () => { deconnexion(); location.hash = "#/login"; location.reload(); };
  const fAgence = document.getElementById("f-agence");
  if (fAgence) fAgence.onsubmit = async (e) => {
    e.preventDefault();
    try { await patch("/api/agence", Object.fromEntries(new FormData(e.target))); toast("Agence mise à jour ✔", "succes"); }
    catch (err) { toast(err.message, "erreur"); }
  };
  const up = (id, chemin, label) => {
    const b = document.getElementById(id);
    if (b) b.onclick = () => demanderImage(label, async (fichier) => {
      const fd = new FormData();
      fd.append("fichier", fichier, fichier.name);
      await envoyerFichier(chemin, fd);
      toast(label + " enregistré ✔", "succes");
    });
  };
  up("btn-logo", "/api/agence/logo", "Logo");
  up("btn-tampon", "/api/agence/tampon", "Tampon");
  up("btn-signature", "/api/agence/signature", "Signature");
  const bPin = document.getElementById("btn-pin");
  if (bPin) bPin.onclick = activerPIN;
  const bPinOff = document.getElementById("btn-pin-off");
  if (bPinOff) bPinOff.onclick = () => { stock.del("pin_hash"); toast("PIN désactivé."); location.reload(); };
  chargerUsers(); chargerRegles(); chargerModeles();
}

function demanderImage(label, suite) {
  const input = document.createElement("input");
  input.type = "file"; input.accept = "image/*";
  input.onchange = async () => {
    const f = input.files[0];
    if (!f) return;
    try { suite(await comprimerImage(f, 1200, 0.8)); }
    catch (err) { toast(err.message, "erreur"); }
  };
  input.click();
}

function activerPIN() {
  ouvrirModal("Code PIN", `
  <form id="f-pin" class="formulaire">
    <label>Code à 4-6 chiffres
      <input name="pin" type="password" inputmode="numeric" minlength="4" maxlength="6" required
             style="text-align:center;letter-spacing:6px;font-size:1.3rem"></label>
    <button class="btn-ligne" type="submit">Enregistrer le code</button>
  </form>`);
  $("#f-pin").onsubmit = async (e) => {
    e.preventDefault();
    const pin = new FormData(e.target).get("pin");
    if (!/^\d{4,6}$/.test(pin)) { toast("4 à 6 chiffres.", "erreur"); return; }
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pin));
    const h = Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
    stock.set("pin_hash", h);
    toast("Code PIN activé ✔", "succes");
    fermerModal(); location.reload();
  };
}

async function chargerUsers() {
  const zone = document.getElementById("zone-users");
  if (!zone) return;
  try {
    const d = await get("/api/users");
    zone.innerHTML = `
    <div class="liste">${d.users.map((u) => `
      <div class="element" style="cursor:default">
        <div class="avatar">${u.role === "responsable" ? "👔" : u.role === "proprietaire" ? "👤" : "🧑‍💼"}</div>
        <div class="corps"><div class="titre">${esc(u.nom)}</div>
        <div class="detail">${esc(u.telephone)} · ${{ responsable: "Responsable", employe: "Employé", proprietaire: "Propriétaire (lecture)" }[u.role]}</div></div>
        <div class="droite">${u.actif ? '<span class="puce paye">actif</span>' : '<span class="puce en_retard">désactivé</span>'}</div>
      </div>`).join("")}</div>
    <div class="espace"></div>
    <button class="btn-ligne secondaire petit" id="btn-ajout-user">+ Ajouter un employé</button>
    <div class="petit gris">L'employé se connecte avec son numéro (code SMS). Rôles : responsable (tout), employé (gestion sans paramètres).</div>`;
    document.getElementById("btn-ajout-user").onclick = () => {
      ouvrirModal("Ajouter un employé", `
      <form id="f-user" class="formulaire">
        ${champ({ nom: "nom", label: "Nom", attrs: "required" })}
        ${champ({ nom: "telephone", label: "Téléphone", type: "tel", attrs: "required" })}
        ${champ({ nom: "role", label: "Rôle", options: [
          { valeur: "employe", libelle: "Employé" }, { valeur: "responsable", libelle: "Responsable" }] })}
        <button class="btn-ligne" type="submit">Ajouter</button>
      </form>`);
      $("#f-user").onsubmit = async (e) => {
        e.preventDefault();
        try {
          const r = await post("/api/users", Object.fromEntries(new FormData(e.target)));
          toast(r.message || "Employé ajouté ✔", "succes");
          fermerModal(); chargerUsers();
        } catch (err) { toast(err.message, "erreur"); }
      };
    };
  } catch (e) { zone.innerHTML = `<div class="petit gris">${esc(e.message)}</div>`; }
}

async function chargerRegles() {
  const zone = document.getElementById("zone-regles");
  if (!zone) return;
  try {
    const d = await get("/api/regles");
    const r = d.regles;
    zone.innerHTML = `
    <form id="f-regles" class="formulaire">
      ${champ({ nom: "terme_paiement", label: "Terme de paiement", valeur: r.terme_paiement, options: [
        { valeur: "debut", libelle: "Début de mois — payable d'avance (pratique courante)" },
        { valeur: "fin", libelle: "Fin de mois — terme échu (décret 2023-382)" }] })}
      <div class="champs-2">
        ${champ({ nom: "jour_limite_paiement", label: "Retard après le (jour)", type: "number", valeur: String(r.jour_limite_paiement ?? 10), attrs: 'min="1" max="28"' })}
        ${champ({ nom: "revision_periodicite_mois", label: "Révision loyer (mois)", type: "number", valeur: String(r.revision_periodicite_mois), attrs: 'min="1"' })}
      </div>
      <div class="aide">Loyer attendu le jour d'échéance du bail (ex. le 5), en retard à partir du lendemain du jour limite (ex. le 11).</div>
      <div class="champs-2">
        ${champ({ nom: "caution_max_mois", label: "Caution max (mois)", type: "number", valeur: String(r.caution_max_mois), attrs: 'min="0" max="12"' })}
        ${champ({ nom: "caution_etalee_mois", label: "Étalement (mois)", type: "number", valeur: String(r.caution_etalee_mois), attrs: 'min="1" max="36"' })}
      </div>
      <div class="champs-2">
        ${champ({ nom: "frais_agence_max_mois", label: "Frais agence max (mois)", type: "number", valeur: String(r.frais_agence_max_mois), attrs: 'step="0.5" min="0"' })}
        ${champ({ nom: "rappel_enregistrement_jours", label: "Rappel enregistrement (jours)", type: "number", valeur: String(r.rappel_enregistrement_jours), attrs: 'min="1"' })}
      </div>
      <div class="petit gris">Défaut (pratique du terrain) : loyer payable d'avance, attendu le 5, retard après le 10. Le terme échu du décret 2023-382 reste sélectionnable. Alertes de conformité douces, jamais bloquantes.</div>
      <button class="btn-ligne petit" type="submit">Enregistrer les règles</button>
    </form>`;
    $("#f-regles").onsubmit = async (e) => {
      e.preventDefault();
      const d2 = Object.fromEntries(new FormData(e.target));
      try {
        await patch("/api/regles", {
          caution_max_mois: parseInt(d2.caution_max_mois, 10),
          caution_etalee_mois: parseInt(d2.caution_etalee_mois, 10),
          terme_paiement: d2.terme_paiement,
          jour_limite_paiement: parseInt(d2.jour_limite_paiement, 10),
          frais_agence_max_mois: parseFloat(d2.frais_agence_max_mois),
          revision_periodicite_mois: parseInt(d2.revision_periodicite_mois, 10),
          rappel_enregistrement_jours: parseInt(d2.rappel_enregistrement_jours, 10),
        });
        toast("Règles enregistrées ✔", "succes");
      } catch (err) { toast(err.message, "erreur"); }
    };
  } catch (e) { zone.innerHTML = `<div class="petit gris">${esc(e.message)}</div>`; }
}

async function chargerModeles() {
  const zone = document.getElementById("zone-modeles");
  if (!zone) return;
  try {
    const d = await get("/api/modeles");
    const relance = (d.modeles || []).find((m) => m.type === "relance");
    zone.innerHTML = `
    <form id="f-modele" class="formulaire">
      <label>Modèle de relance
        <textarea name="contenu" rows="5" style="margin-top:4px">${esc(relance ? relance.contenu : "")}</textarea></label>
      <div class="aide">Variables : {nom} {bien} {periode} {reste} {echeance} {agence}</div>
      <button class="btn-ligne petit" type="submit">Enregistrer le modèle</button>
    </form>`;
    $("#f-modele").onsubmit = async (e) => {
      e.preventDefault();
      const contenu = new FormData(e.target).get("contenu");
      try { await fetch("/api/modeles", { method: "PUT", headers: { "Content-Type": "application/json", Authorization: "Bearer " + localStorage.getItem("token") }, body: JSON.stringify({ type: "relance", contenu }) }).then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail || "Erreur"); });
        toast("Modèle enregistré ✔", "succes");
      } catch (err) { toast(err.message, "erreur"); }
    };
  } catch (e) { zone.innerHTML = `<div class="petit gris">${esc(e.message)}</div>`; }
}
