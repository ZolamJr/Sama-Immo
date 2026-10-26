// Écran d'accueil style Wave : solde du mois en haut, gros boutons, activité récente.
import { get, estProprietaire, peutEcrire, pendingPaiements } from "../api.js";
import { esc, badge, vide } from "../ui.js";
import { fcfa, dateHeureFr, libellePeriode, telWhatsApp } from "../format.js";

export async function rendre() {
  const [dash, pend] = await Promise.all([get("/api/dashboard"), pendingPaiements()]);
  const encaisseAffiche = dash.encaisse + pend.reduce((s, p) => s + p.montant, 0);
  const u = JSON.parse((function(){try{return localStorage.getItem("user")}catch(e){return null}})() || "{}");
  const bonjour = (u.nom || "").split(" ")[0] || "Bonjour";
  const proprio = estProprietaire();

  const alertesEnreg = (dash.baux_a_enregistrer || []).length ? `
    <div class="alerte attention">📝 ${dash.baux_a_enregistrer.length} bail(s) à enregistrer auprès du Centre
    des services fiscaux (délai de ${30} jours). <a href="#/biens">Voir les biens</a></div>` : "";

  const duJour = dash.echeances_du_jour ? `<div class="alerte info">📅 ${dash.echeances_du_jour} échéance(s) tombent aujourd'hui.</div>` : "";

  const actions = proprio ? "" : `
  <div class="grille-actions">
    <a class="btn primaire" href="#/encaisser"><span class="ic">💵</span>Encaisser un loyer</a>
    <a class="btn" href="#/relances"><span class="ic">🔔</span>Relancer</a>
  </div>`;

  return `
  <div class="entete-page"><h1>Bonjour ${esc(bonjour)} 👋</h1></div>

  <div class="carte carte-solde">
    <div class="libelle">Loyers du mois — ${esc(dash.periode_libelle)}</div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px">
      <span class="libelle">Encaissé</span><b style="font-size:1.55rem" class="montant">${fcfa(encaisseAffiche)}</b>
    </div>
    <div class="lignes">
      <div class="ligne-item"><div class="lib">En attente</div><div class="val montant">${fcfa(dash.en_attente)}</div></div>
      <div class="ligne-item"><div class="lib">En retard</div><div class="val montant">${fcfa(dash.en_retard)}</div></div>
    </div>
  </div>

  ${actions}
  ${duJour}
  ${dash.nb_en_retard > 0 && !proprio ? `<a href="#/relances" class="alerte erreur" style="text-decoration:none;display:block">
      ⚠ ${dash.nb_en_retard} loyer(s) en retard — voir la liste</a>` : ""}
  ${alertesEnreg}

  <div class="grille-actions">
    <a class="btn" href="#/biens"><span class="ic">🏢</span>Gestion</a>
    <a class="btn" href="#/locataires"><span class="ic">👤</span>Locataires</a>
    <a class="btn" href="#/rapports"><span class="ic">📊</span>Rapports</a>
    <a class="btn" href="#/parametres"><span class="ic">⚙️</span>Paramètres</a>
  </div>

  ${dash.occupation && dash.occupation.total ? `
  <div class="carte">
    <div class="ligne-flex"><b>Taux d'occupation</b><span class="gras">${dash.occupation.taux} %</span></div>
    <div class="petit gris">${dash.occupation.occupees} unité(s) occupée(s) sur ${dash.occupation.total}</div>
  </div>` : ""}

  <div class="sous-titre">Activité récente</div>
  ${(dash.activite || []).length ? `<div class="liste">${(dash.activite).map((a) => `
    <div class="element" style="cursor:default">
      <div class="avatar">${iconeAction(a.action)}</div>
      <div class="corps"><div class="titre">${esc(libelleAction(a))}</div>
      <div class="detail">${esc(a.user || "")} · ${dateHeureFr(a.date)}</div></div>
    </div>`).join("")}</div>` : vide("🗂️", "Aucune activité pour le moment.")}

  <div class="petit gris centre espace">${pend.length ? `⚠ ${pend.length} paiement(s) local(aux), pas encore synchronisés.` : ""}</div>
  `;
}

function iconeAction(a) {
  if (a.startsWith("paiement")) return "💵";
  if (a.startsWith("bail")) return "📜";
  if (a.startsWith("recu")) return "🧾";
  if (a.startsWith("relance")) return "🔔";
  if (a.startsWith("locataire")) return "👤";
  if (a.startsWith("rapport")) return "📊";
  return "•";
}

function libelleAction(a) {
  const lib = {
    "paiement.cree": "Paiement enregistré", "paiement.annule": "Paiement annulé",
    "paiement.preuve": "Preuve jointe", "bail.cree": "Nouveau bail", "bail.termine": "Bail terminé",
    "recu.quittance": "Quittance émise", "recu.caution": "Reçu de caution", "recu.frais_agence": "Reçu de frais d'agence",
    "recu.decharge": "Décharge de clés", "relance.envoyee": "Relance envoyée",
    "locataire.cree": "Locataire ajouté", "immeuble.cree": "Bien ajouté", "unite.creee": "Unité ajoutée",
    "rapport.genere": "Rapport généré", "compte.cree": "Compte créé",
  }[a.action];
  return (lib || a.action) + (a.libelle ? ` — ${a.libelle}` : "");
}
