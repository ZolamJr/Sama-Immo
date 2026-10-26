// Connexion : numéro de téléphone -> code OTP -> (inscription si nouveau).
import { post, definirSession } from "../api.js";
import { $, esc, toast } from "../ui.js";

// force le rendu de l'accueil même si le hash n'a pas changé (déconnexion -> connexion)
function allerAccueil() {
  location.hash = "#/accueil";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export async function rendre(app) {
  app.innerHTML = `
  <div class="ecran-login">
    <div class="logo-login"><div class="em">🏠</div><h1>SamaImmo</h1>
      <div class="gris">Gérez biens, locataires et loyers<br>en quelques secondes.</div></div>
    <div class="carte">
      <form id="f-tel">
        <label>Votre numéro de téléphone
          <input name="telephone" type="tel" inputmode="tel" placeholder="77 123 45 67" autocomplete="tel" required>
        </label>
        <div class="aide">Un code à 6 chiffres vous sera envoyé par SMS.</div>
        <button class="btn-ligne" type="submit">Recevoir le code</button>
      </form>
    </div>
  </div>`;

  $("#f-tel").onsubmit = async (e) => {
    e.preventDefault();
    const tel = new FormData(e.target).get("telephone");
    const bouton = e.target.querySelector("button");
    bouton.disabled = true; bouton.textContent = "Envoi en cours…";
    try {
      const r = await post("/api/auth/otp/request", { telephone: tel });
      etapeCode(app, tel, r.dev_code);
    } catch (err) {
      toast(err.message, "erreur");
      bouton.disabled = false; bouton.textContent = "Recevoir le code";
    }
  };
}

function etapeCode(app, tel, devCode) {
  app.innerHTML = `
  <div class="ecran-login">
    <div class="logo-login"><div class="em">🔑</div><h1>Code de connexion</h1></div>
    <div class="carte">
      ${devCode ? `<div class="alerte info">Mode démo — votre code : <b class="gros-tel">${devCode}</b></div>` : ""}
      <p class="petit gris centre">Envoyé au ${esc(tel)}</p>
      <form id="f-code">
        <input name="code" class="gros-tel" inputmode="numeric" maxlength="6" placeholder="••••••" 
               style="width:100%;padding:14px;text-align:center;letter-spacing:6px;border:1.5px solid var(--bord);border-radius:12px" required>
        <button class="btn-ligne" type="submit">Se connecter</button>
      </form>
      <button class="btn-ligne secondaire" id="btn-retour">Changer de numéro</button>
    </div>
  </div>`;
  $("#btn-retour").onclick = () => rendre(app);
  $("#f-code").onsubmit = async (e) => {
    e.preventDefault();
    const code = new FormData(e.target).get("code");
    try {
      const r = await post("/api/auth/otp/verify", { telephone: tel, code });
      if (r.inscription_requise) {
        etapeInscription(app, tel, r.jeton);
      } else {
        definirSession(r.token, r.user);
        if (r.role === "proprietaire") toast("Connecté en lecture seule (compte propriétaire).");
        allerAccueil();
      }
    } catch (err) {
      toast(err.message, "erreur");
    }
  };
}

function etapeInscription(app, tel, jeton) {
  app.innerHTML = `
  <div class="ecran-login">
    <div class="logo-login"><div class="em">🏢</div><h1>Créons votre agence</h1>
      <div class="gris">Première fois ici ? 2 informations suffisent.</div></div>
    <div class="carte">
      <form id="f-insc">
        <label>Nom de l'agence (ou votre nom)
          <input name="nom_agence" placeholder="Ex : Immo Mermoz" required>
        </label>
        <label>Votre nom
          <input name="nom" placeholder="Ex : Moussa Diop" required>
        </label>
        <button class="btn-ligne" type="submit">Créer mon compte</button>
      </form>
    </div>
  </div>`;
  $("#f-insc").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const r = await post("/api/auth/inscription", { jeton, ...d });
      definirSession(r.token, r.user);
      toast("Bienvenue ! Ajoutez un premier bien pour démarrer.", "succes");
      allerAccueil();
    } catch (err) {
      toast(err.message, "erreur");
    }
  };
}
