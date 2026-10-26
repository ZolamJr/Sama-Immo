// Formatage FCFA / dates / libellés.
export function fcfa(n) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const neg = n < 0;
  const s = Math.abs(Math.round(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return (neg ? "−" : "") + s + " FCFA";
}

export function dateFr(iso) {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function dateHeureFr(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }) +
    " à " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

export const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

export function periodeCourante() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
}

export function libellePeriode(p) {
  if (!p) return "—";
  const [a, m] = p.split("-");
  return MOIS[parseInt(m, 10) - 1] + " " + a;
}

export function periodesChoix(nbMoisAvant = 14) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < nbMoisAvant; i++) {
    const p = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
    out.push({ valeur: p, libelle: libellePeriode(p) });
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

export const STATUT_LIB = { paye: "Payé", partiel: "Partiel", en_attente: "En attente", en_retard: "En retard" };
export const MODES = { wave: "Wave", orange_money: "Orange Money", especes: "Espèces", virement: "Virement", cheque: "Chèque", autre: "Autre" };
export const TYPES_UNITE = { chambre: "Chambre", appartement: "Appartement", maison: "Maison", local: "Local", bureau: "Bureau" };

export function poidsKo(o) { return o >= 1048576 ? (o / 1048576).toFixed(1) + " Mo" : Math.max(1, Math.round(o / 1024)) + " Ko"; }

export function telWhatsApp(t) { return (t || "").replace(/[^0-9]/g, ""); }

export function aujourdHui() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

// Comprime une image côté client (connexions lentes, F12) avant envoi.
export function comprimerImage(fichier, maxCote = 1600, qualite = 0.72) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(fichier);
    img.onload = () => {
      const ech = Math.min(1, maxCote / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * ech);
      c.height = Math.round(img.height * ech);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((blob) => {
        URL.revokeObjectURL(url);
        if (blob) resolve(new File([blob], (fichier.name || "photo").replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }));
        else reject(new Error("Compression impossible"));
      }, "image/jpeg", qualite);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Image illisible")); };
    img.src = url;
  });
}
