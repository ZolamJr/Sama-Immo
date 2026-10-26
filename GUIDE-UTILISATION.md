# Guide complet SamaImmo — utilisation en conditions réelles

*Ce guide vous fait vivre une journée complète de gérant avec les données de
démonstration déjà chargées. Suivez les étapes dans l'ordre : chaque action est
exactement celle que vous ferez avec vos vrais locataires.*

---

## 0. Démarrage (2 minutes)

```bash
cd sama-immo
bash start.sh        # Windows : double-cliquer sur start.bat
```

- Le navigateur s'ouvre tout seul sur l'application (sinon ouvrez l'adresse
  affichée dans le terminal, par ex. `http://localhost:8000`).
- **Connexion démo** : téléphone **+221 770 000 000** → touchez « Recevoir le
  code » → le code à 6 chiffres **s'affiche à l'écran** (mode démo) → saisissez-le.
- Vous arrivez sur l'accueil : *Bonjour Moussa 👋*

> ⚠ **Important** : gardez la fenêtre du terminal ouverte pendant toute
> l'utilisation — c'est elle qui fait tourner l'application. Pour arrêter : Ctrl+C.

### Ce que contient la démo

| | |
|---|---|
| Agence | Immo Mermoz Gestion (Moussa Diop) |
| Propriétaires | Ousmane Sow (commission 5 %) · Mariama Fall (8 %) |
| Biens | Immeuble Mermoz (4 unités) · Villa Almadies (1 unité) |
| Locataires | Aïssatou, Ibrahima, Fatou, Cheikh, Sokhna — chacun son bail |
| Situation au 1er octobre | octobre déjà encaissé pour 3 locataires ; **Cheikh (450 000) et Fatou (95 000) en attente** ; **4 loyers d'août/septembre en retard (1 050 000)** |

L'accueil doit afficher environ : **Encaissé 1 405 000 · En attente 545 000 · En retard 1 050 000 (4)**.
(Si vos chiffres diffèrent un peu, c'est que vous avez déjà fait des paiements — normal.)

---

## 1. Visite guidée (30 secondes)

L'écran d'accueil, c'est votre tableau de bord :

- la **carte bleue** : encaissé / en attente / en retard du mois ;
- les **gros boutons** : Encaisser, Relancer (les gestes du quotidien) ;
- les **4 boutons carrés** : Biens, Locataires, Rapports, Paramètres ;
- la **barre du bas** : navigation (Accueil, Encaisser, Biens, Locataires, Relances).

---

## 2. SIMULATION — La journée du gérant, le 1er octobre

### Étape 1 — Encaisser un loyer complet ✅ (LE geste clé)

Cheikh Gueye arrive à l'agence et paie son loyer d'octobre (Local commercial,
450 000 FCFA) par Wave.

1. **Accueil** → touchez **« Encaisser un loyer »**
2. La liste des loyers du mois s'affiche. Touchez la ligne **« Cheikh Gueye —
   Local commercial »** (450 000 FCFA, *En attente*)
3. L'écran de paiement s'affiche :
   - **Montant** : pré-rempli à **450 000** (ne touchez à rien)
   - **Mode** : **Wave** (déjà sélectionné)
   - **Date** : aujourd'hui — **Référence** : tapez `TX-1001` (facultatif)
4. Touchez **« ✔ Valider le paiement »**

**✔ À observer** : un écran de confirmation vert type transfert Wave apparaît,
avec le gros montant, le récapitulatif, le **numéro de quittance** (Q-2026-00XXX)
et deux boutons : **Envoyer la quittance (WhatsApp)** et **Télécharger le PDF**.

5. Touchez **« 📲 Envoyer la quittance (WhatsApp) »** → WhatsApp s'ouvre avec le
   message déjà rédigé et le lien de vérification — il ne reste qu'à choisir le
   contact et envoyer. *(Sur ordinateur, WhatsApp Web s'ouvre.)*
6. Touchez **« Télécharger le PDF »** → ouvrez le fichier : c'est la quittance
   officielle (montant en chiffres **et en lettres**, « payable d'avance avant le
   10/10/2026 », QR code en bas).
7. **« Terminer »** → retour à l'accueil.

**✔ À observer** : l'encaissé du mois est passé de 1 405 000 à **1 855 000 FCFA**,
et l'activité récente montre « Paiement enregistré — 450 000 FCFA ».

---

### Étape 2 — Encaisser un paiement PARTIEL

Fatou Kane (Chambre 3, 95 000 FCFA) ne peut payer que 50 000 aujourd'hui.

1. **Encaisser un loyer** → touchez **« Fatou Kane — Chambre 3 »** (95 000)
2. Dans **Montant**, effacez et tapez **50000**
3. Mode : **Orange Money** → **Valider**

**✔ À observer** : l'écran de confirmation affiche le paiement de 50 000 ; la
quittance mentionne **« Reste à payer : 45 000 FCFA — PAIEMENT PARTIEL »**.
Sur l'accueil, « En attente » est maintenant de **45 000 FCFA**.

> 💡 Le mois prochain, Fatou devra le loyer du mois + les 45 000 restants :
> chaque échéance garde son propre reste à payer, rien ne se perd.

---

### Étape 3 — Relancer un locataire en retard

Cheikh doit encore août et septembre (900 000 FCFA au total).

1. Accueil → touchez la **carte « En retard »** ou le bouton **« Relancer »**
2. La liste des retards, **triée par ancienneté** (le plus ancien en premier),
   s'affiche : Cheikh août, Cheikh septembre, Fatou août, Fatou septembre
3. Touchez la ligne **Cheikh Gueye — août 2026**
4. Le message est **déjà rédigé** : *« Bonjour Cheikh Gueye, nous vous rappelons
   que le loyer de Local commercial pour août 2026 d'un montant de 450 000 FCFA
   est en attente depuis le 2026-08-10… »* — modifiez-le si vous voulez
5. **« 📲 Envoyer sur WhatsApp »** → WhatsApp s'ouvre, message prêt

**✔ À observer** : une confirmation « Relance enregistrée dans l'historique ».
La relance est tracée (visible dans Paramètres → Journal d'activité).

---

### Étape 4 — Vérifier une quittance par QR code (la confiance)

1. Reprenez le PDF de l'étape 1 (ou demandez-le au locataire)
2. Scannez le **QR code** en bas de la quittance avec le téléphone
   (ou ouvrez le lien `…/r/xxxx` du message WhatsApp)

**✔ À observer** : une **page publique** s'affiche : *✔ REÇU AUTHENTIQUE*,
avec le numéro, le locataire, le bien, la période, le montant — et la mention
« Intégrité du fichier : conforme (SHA-256 vérifiée) ». C'est ce que verra un
propriétaire ou un locataire qui vérifie une quittance. Personne ne peut
fabriquer un faux.

---

### Étape 5 — Rapport au propriétaire (fin de mois)

1. **Rapports** → la liste des propriétaires s'affiche avec leurs chiffres
2. Touchez **Ousmane Sow** → détail : encaissé, commission 5 %, **à reverser**
3. Touchez **« 📄 Générer le PDF du rapport »**
4. **« 📲 Envoyer sur WhatsApp »** → le rapport part au propriétaire avec le lien

**✔ À observer** : le PDF contient le tableau récapitulatif et le détail par
bien. Après les étapes 1 et 2, Ousmane devrait afficher environ
**1 180 000 encaissés · commission 59 000 · à reverser 1 121 000**.

---

### Étape 6 — Encaisser une échéance d'un MOIS PRÉCÉDENT

Cheikh veut aussi régler septembre :

1. **Encaisser un loyer** → en haut, **« Mois concerné »** → choisissez
   **septembre 2026**
2. La liste montre les loyers de septembre non soldés → touchez Cheikh →
   le montant pré-rempli est **450 000** → Validez

**✔ À observer** : le retard de septembre disparaît de la liste « Relances » ;
le compteur « En retard » de l'accueil baisse d'autant.

---

## 2 bis. NOUVEAUTÉS v1.2 à essayer

### La cloche de notifications 🔔
En haut à droite : un badge rouge affiche le nombre d'actions à faire. Touchez-la :
loyers en retard, loyers attendus aujourd'hui, **cautions à restituer** (Fatou, partie
il y a 45 jours — délai dépassé !), mandat de Mariama Fall qui expire bientôt.
Chaque notification mène en 1 clic à l'écran concerné.

### La caution conforme au décret 2023-382 (à tester)
1. **Gestion** → Local commercial (Cheikh Gueye) → descendez au bloc **🔐 Caution**
2. **✔ À observer** : prévue 900 000 (2 mois), versée 862 500, reste 37 500 —
   avec l'**échéancier légal** : 1 mois à l'entrée + 1/12ᵉ par mois
3. **Gestion** → Chambre 3 (Fatou Kane) → l'ancien bail terminé montre une caution
   **à restituer** avec délai dépassé → touchez **« Restituer la caution »** :
   saisissez une retenue (ex. 10 000, motif « dégradations état des lieux »)
   → reçu de restitution **R-2026-…** vérifiable par QR

### Le mandat de gestion (relation agence ↔ propriétaire)
**Rapports** → touchez un propriétaire → carte **🤝 Mandat de gestion** : dates,
commission, alerte quand il expire. Modifiable en 1 clic.
Les biens appartiennent aux propriétaires — le menu s'appelle désormais **Gestion**.

### Les exports PDF (en plus de la quittance et du rapport propriétaire)
- **Encaisser** → « 📄 État des loyers du mois (PDF) » : le bordereau récapitulatif
- **Relances** → « 📄 État des arriérés (PDF) » : la liste pour vos démarches
- **Fiche locataire** → « 📄 Fiche récapitulative (PDF) » : baux + paiements
- **Paramètres → Journal d'activité** → « 📄 Exporter le journal (PDF) »

### Filtres, tris, retours
Chaque liste a désormais une **recherche**, des **filtres** (statut, auteur) et des
**tris**. Les fiches détaillées ont un bouton **← Retour**. Depuis une fiche
locataire, « 💵 Encaisser un loyer de ce locataire » filtre directement la liste.

### Signature et tampon personnalisés
**Paramètres → Mon agence** : importez une photo de **signature** et de **tampon**
(elles apparaissent en aperçu) — apposées automatiquement sur les quittances,
reçus et rapports PDF. Les quittances sont signées « Le gérant — [votre agence] ».

## 3. Créer VOTRE agence (parcours réel, moins de 5 minutes)

Faites-le après la simulation, pour passer en vrai :

1. **Paramètres** → tout en bas **« Se déconnecter »**
2. Entrez **votre numéro de téléphone** → code affiché à l'écran →
   « Créons votre agence » : nom de l'agence + votre nom → **Créer**
3. **Biens → +** → premier propriétaire (nom, téléphone, commission %)
   → le bien (nom, quartier) → touchez le bien → **+ Ajouter une unité**
   (type, loyer, charges)
4. **Locataires → +** → nom + téléphone (WhatsApp)
5. **Biens** → touchez l'unité → **« 📝 Créer un bail »** :
   - locataire, date de début, **loyer**, charges
   - **jour d'échéance : 5** (payable d'avance) · caution (2 mois max, alerte au-delà)
6. Retour à l'accueil : **l'échéance du mois est déjà là, prête à encaisser** ✔

> C'est le critère n°1 du cahier des charges : *première quittance en moins de
> 5 minutes*. Chronométrez-vous !

---

## 4. La gestion quotidienne (raccourcis depuis **Gestion**)

| Je veux… | Chemin |
|---|---|
| Modifier un loyer (avec historique et motif) | Gestion → unité → ✏️ Modifier le bail |
| Terminer un bail (départ) | Gestion → unité → 🏁 Terminer le bail → le bien repasse en *libre* |
| Encaisser / suivre la **caution** | Gestion → unité → bloc 🔐 Caution (échéancier légal 2023-382) |
| Faire un reçu de **frais d'agence** | Gestion → unité → 🧾 Reçu de frais (alerte si > ½ mois) |
| Faire une **décharge de remise de clés** | Biens → unité → 🧾 (dans « Reçu de caution » changer le type… ou depuis le bail) |
| **Scanner/rattacher un document** (bail signé, pièce d'identité…) | Fiche → 📄 Documents → choisir le type → photo(s)/PDF → les photos deviennent un seul PDF compressé |
| Corriger un paiement erroné | Jamais de suppression ! Paiements → annulation **avec motif obligatoire** → écriture d'annulation visible + quittance marquée ANNULÉ |
| Ajouter un employé | Paramètres → Équipe (il se connecte avec son numéro ; rôle employé = gestion sans paramètres) |
| Inviter un propriétaire en lecture seule | Ajoutez son numéro dans sa fiche propriétaire → il se connecte avec ce numéro → compte lecture seule automatique |
| Activer un code PIN à l'ouverture | Paramètres → Code PIN |
| Voir qui a fait quoi | Paramètres → Journal d'activité (chaque action horodatée, avec l'appareil) |
| Exporter vers Excel | Paramètres → Données → exports CSV |

---

## 5. L'écran des Règles (Paramètres → Règles locales)

Par défaut, conformément à la pratique du terrain :

- **Terme** : *Début de mois — payable d'avance*
- **Retard après le** : **10** (le loyer est attendu le 5, en retard le 11)
- Caution max : 2 mois · frais d'agence max : ½ mois

Tout est modifiable et **jamais bloquant** : si une saisie dépasse une règle,
vous recevez une **alerte douce** mais l'action passe. Le terme échu du décret
2023-382 reste sélectionnable si votre professionnel le préfère.

---

## 6. Hors ligne — encaisser sans réseau (à tester absolument)

1. **Coupez la connexion** (Wi-Fi/4G) — l'application reste ouverte
2. **Encaissez un loyer** comme à l'étape 1
3. **✔ À observer** : bandeau « ⚠ Hors ligne », le paiement passe avec un
   **numéro provisoire ATT-…**, et la barre du haut affiche **« 1 en attente »**
4. **Rallumez la connexion** → dans les 15 secondes, synchronisation
   automatique : « 1 action synchronisée ✔ »
5. **✔ À observer** : le numéro définitif (Q-2026-…) remplace le provisoire,
   **sans doublon** — même si la connexion avait coupé *pendant* l'envoi.

---

## 7. Dépannage

| Symptôme | Solution |
|---|---|
| « J'arrive pas à encaisser » : cliquer un locataire me ramène à l'accueil | Corrigé dans la v1.1.3 — re-téléchargez le dernier ZIP, supprimez l'ancien dossier, ré-extraisez, et faites **Ctrl+F5** une fois dans le navigateur |
| La liste « Encaisser » est vide | Vérifiez le **mois** en haut de la liste ; tout est peut-être déjà soldé (🎉 s'affiche) |
| Logo figé au démarrage | Ctrl+F5 ; vérifiez que vous êtes bien sur `http://localhost:…` et non le fichier index.html ; le message exact s'affiche maintenant sous le logo |
| Le code de connexion n'apparaît pas | Regardez la fenêtre du terminal — il y est aussi écrit (`[OTP] …`) |
| « Le port 8000 est occupé » | Le script prend automatiquement le port suivant — ouvrez l'adresse affichée |
| WhatsApp ne s'ouvre pas | Le lien est `wa.me/…` : il faut WhatsApp installé (téléphone) ou WhatsApp Web (ordinateur) |
| Le PDF ne se télécharge pas | Désactivez temporairement le bloqueur de pop-up |

---

## 8. Récapitulatif des règles métier implémentées

- **Caution** (décret 2023-382) : max 2 mois, 1 mois à l'entrée + 1/12ᵉ/mois ; restitution tracée avec retenues justifiées obligatoirement

- Loyer **payable d'avance**, attendu le **5**, **retard après le 10** (paramétrable)
- Premier loyer d'un bail signé après le 5 : **dû à la signature**
- Caution : max **2 mois** (décret 2023-382), alerte douce au-delà
- Frais d'agence : max **½ mois** pour ≤ 500 000 FCFA, alerte douce
- **Paiements jamais supprimés** : correction par écriture d'annulation motivée
- Chaque quittance : numéro unique, **QR de vérification publique**, empreinte SHA-256
- Journal d'audit complet : qui, quoi, quand, depuis quel appareil

*Bonne démonstration ! 🏠*
