# SamaImmo — Gestion locative (Sénégal)

Application web installable (**PWA**) de gestion locative : biens, locataires, loyers,
quittances PDF vérifiables par QR code, relances WhatsApp, rapports propriétaires.
Conçue pour les gérants et agences du Sénégal : **très légère**, **hors ligne**, en français.

> Un seul service, une seule base, aucun coût de fonctionnement externe.
> Parfait jusqu'à ~100 agences ; migration PostgreSQL possible ensuite sans réécrire.

---

## 1. Démarrage en 2 minutes

### Sur votre machine (démo de demain)

```bash
./start.sh          # Linux / macOS / Git Bash
start.bat           # Windows (double-clic)
```

Puis ouvrir l'adresse affichée dans la fenêtre au lancement
(**http://localhost:8000**, ou 8001… si une autre application occupe
déjà ce port — le script choisit tout seul un port libre).

- Au premier lancement, le script propose de **charger les données de démonstration**
  (2 propriétaires, 5 unités, 5 baux, quittances, retards, paiement partiel) — répondre `O`.
- **Compte de démonstration** : téléphone `+221 770 000 000` — le code de connexion
  s'affiche à l'écran (mode démo OTP, voir §5).
- Pour repartir d'une base vierge : supprimer le dossier `data/` puis relancer.
- Pour regénérer la démo : `python3 scripts/seed_demo.py`.

### Premier lancement réel (parcours du cahier des charges, < 5 min)

1. Numéro de téléphone → code → nom de l'agence.
2. **Biens → +** → premier propriétaire + premier bien.
3. **Locataires → +** → locataire, puis **Biens → l'unité → Créer un bail**.
4. L'échéance du mois apparaît sur l'accueil, prête à **Encaisser**.
5. Après validation : écran de confirmation + **quittance PDF avec QR** → bouton WhatsApp.

### Installation comme application (PWA)

- **Android (Chrome)** : menu ⋮ → *Ajouter à l'écran d'accueil*. L'app s'ouvre
  en plein écran, fonctionne hors connexion.
- **iPhone (Safari)** : Partager → *Sur l'écran d'accueil* (notifications limitées sur iOS,
  voir §8).

---

## 2. Déploiement (VPS / serveur Linux)

### Option A — Docker simple ( derrière votre reverse proxy )

```bash
cp .env.example .env      # renseigner BASE_URL
docker compose up -d --build
```

L'application écoute sur le port 8000. Mettre HTTPS devant (nginx, Traefik…).

### Option B — Docker avec HTTPS automatique (Caddy)

```bash
# 1) DNS : gestion.mon-agence.sn -> IP du serveur
cp .env.example .env      # BASE_URL=https://gestion.mon-agence.sn
nano Caddyfile            # remplacer localhost par votre domaine
docker compose -f docker-compose.https.yml up -d --build
```

Certificat Let's Encrypt obtenu et renouvelé automatiquement.

### Sauvegardes (automatiques)

Copie quotidienne de la base dans `data/backups/` (heure et rétention configurables
dans `.env`), + export CSV de chaque table depuis **Paramètres → Données**.

---

## 3. Couverture du cahier des charges

| Fonction | État | Détails |
|---|---|---|
| F1 Connexion OTP téléphone | ✔ | Code 6 chiffres, anti-spam, expiration, 5 essais max. PIN local optionnel. |
| F2 Propriétaires | ✔ | Fiche, commission %, invitation : le propriétaire se connecte avec son numéro → **compte lecture seule automatique**. |
| F3 Biens & immeubles | ✔ | Immeuble → unités (loyer, charges, statut). Un bien seul = immeuble à 1 unité. |
| F4 Locataires & baux | ✔ | Bail, échéance mensuelle, caution, durée triennale/indéterminée, fin de bail → unité libre. |
| F5 Loyers & paiements | ✔ | **Loyer payable d'avance** (règle terrain v1.1) : échéance attendue le 5 du mois, **retard après le 10** ; premier loyer dû à la signature si le bail est signé après le 5. Statuts payé/partiel/en attente/en retard, preuve photo, **paiements jamais supprimés** : annulation par écriture motivée. |
| F6 Reçus & quittances | ✔ | PDF numéroté (Q-2026-00001), montant en chiffres **et en lettres**, signature + tampon apposés, **QR de vérification** page publique, empreinte SHA-256 enregistrée et contrôlée. Autres reçus : caution, frais d'agence, décharge de clés. Mention « modèle indicatif ». |
| F7 Relances | ✔ | Liste des retards **toutes périodes** triée par ancienneté, message pré-rédigé modifiable, wa.me en 1 clic, trace dans l'historique. |
| F8 Tableau de bord & rapports | ✔ | Accueil encaissé/attente/retard, occupation, activité récente. Rapport mensuel par propriétaire (commission, à reverser) en PDF partageable. |
| F9 Paramètres | ✔ | Profil agence, logo/tampon/signature, modèles de messages, export CSV. |
| F10 Hors ligne & synchronisation | ✔ | Coquille PWA en cache, lectures servies depuis l'appareil, **file d'attente** pour paiements/locataires/baux, indicateur « N en attente », numéro provisoire **ATT-…** transformé en numéro définitif, idempotence par UUID (aucun doublon), fiches : la version la plus récente gagne avec conflit signalé. |
| F11 Traçabilité & sécurité | ✔ | Journal d'audit (qui/quoi/quand/appareil), rôles responsable/employé/propriétaire, isolation stricte par agence. |
| F12 Numérisation | ✔ | Photo/import multi-pages → **un seul PDF**, compression automatique côté téléphone, rattachement en 3 clics (bail, locataire, bien, propriétaire, paiement). *(Détection de bords : V2)* |
| F13 Règles locales | ✔ | Écran Règles : terme (d'avance par défaut / terme échu décret 2023-382), **jour limite de retard (10)**, caution max (2 mois), étalement, frais agence max (½ mois), rappel enregistrement DGID. **Alertes douces, jamais bloquantes.** Historique de loyer par bail. |

**Règle des 3 clics** : encaisser (Accueil → Encaisser → valider), relancer
(Accueil → Relancer → envoyer), ajouter un locataire (Locataires → + → enregistrer).

---

## 4. Tests automatisés

```bash
python3 -m pytest tests/ -v
```

**42 tests** couvrant : parcours OTP complet, expiration de code, rôles (employé,
propriétaire lecture seule), CRUD complet, génération idempotente des échéances,
statuts, paiements partiels, annulation par écriture + quittance annulée,
frontières du retard (le 10 toléré, le 11 en retard), dates d'échéance (d'avance, premier loyer à la signature), idempotence de la synchronisation (rejeu sans doublon), « dernière version gagne »,
relances, rapports (commission, à reverser), documents multi-pages, journal d'audit,
export CSV, isolation entre agences, page publique de vérification (valide/annulée/
intégrité), montants en lettres, quittance avec signature et tampon.

---

## 5. Code SMS (OTP) : modes

| Mode | Quand | Comment |
|---|---|---|
| **Démo** (`OTP_DEV_MODE=true`) | Tests, formation, mise en route | Le code s'affiche à l'écran et dans les logs du serveur. Zéro dépendance, zéro coût. |
| **Passerelle HTTP** (`SMS_PROVIDER=http`) | Production | Renseigner `SMS_HTTP_URL` + `SMS_HTTP_KEY` dans `.env`. Fonctionne avec n'importe quel agrégateur (Orange SN API, agrégateur local, Twilio…) qui accepte un POST JSON. Le numéro de téléphone reste l'identifiant : tout opérateur (Orange, Free, Expresso). |

Le basculement ne demande **aucune modification de code**.

---

## 6. Architecture (volontairement légère)

```
┌────────────────────────────────────────────────┐
│            PWA (téléphone / ordinateur)        │
│  HTML/CSS/JS natifs (< 100 Ko, sans build)     │
│  Service worker : cache + repli hors ligne     │
│  IndexedDB : cache lectures + file d'attente   │
└───────────────────┬────────────────────────────┘
                    │ HTTPS / JSON
┌───────────────────┴────────────────────────────┐
│        FastAPI (async natif, 1 seul service)   │
│  46 endpoints · rôles · isolation par agence   │
│  Tâches de fond : échéances, sauvegardes       │
│  PDF : reportlab · QR : qrcode                 │
├────────────────────────────────────────────────┤
│  SQLite (mode WAL) — fichiers sur disque       │
│  data/app.db · data/files/ · data/backups/     │
└────────────────────────────────────────────────┘
```

- **Pourquoi pas Django + PostgreSQL + Celery + Redis (§8 du cahier des charges) ?**
  C'est l'architecture « équipe de 2-3 personnes sur 10 semaines ». Pour 100 agences,
  un service FastAPI async + SQLite en WAL suffit très largement, se déploie en 2 minutes
  et n'a aucun point de défaillance supplémentaire. Les modèles SQLAlchemy permettent
  une migration PostgreSQL ultérieure sans réécrire l'application.
- **Asynchronisme** : FastAPI/uvicorn (async natif) + SQLAlchemy async — les 100 agences
  partagent un petit nombre de workers sans blocage.
- **Idempotence hors ligne** : UUID générés sur l'appareil + `client_uuid` sur les
  paiements ; le serveur déduplique à la réception.
- **Confiance** : les paiements sont *append-only* ; une erreur se corrige par une
  écriture d'annulation négative motivée, visible dans l'historique et l'audit ;
  chaque quittance a une empreinte SHA-256 contrôlée sur sa page publique.

---

## 7. Structure du projet

```
sama-immo/
├── app/
│   ├── main.py            # assemblage + tâches de fond (échéances, sauvegardes)
│   ├── models.py          # modèle de données (§6 du cahier des charges)
│   ├── logique.py         # échéances, statuts, dashboard, rapports
│   ├── services.py        # paiements, reçus PDF numérotés, annulations
│   ├── pdf.py             # quittances/reçus/rapports (reportlab + QR)
│   ├── nombres.py         # montants en lettres (français)
│   ├── security.py        # OTP, JWT, rôles
│   ├── routers/           # auth, fiches, loyers, sync, documents, paramètres, public
│   └── static/            # PWA (index, manifest, sw.js, css, js)
├── scripts/seed_demo.py   # jeu de démonstration
├── tests/                 # 30 tests automatisés
├── Dockerfile · docker-compose.yml · docker-compose.https.yml · Caddyfile
├── requirements.txt · .env.example · start.sh · start.bat
```

---

## 8. Limites connues et points à valider (assumés pour le MVP)

- **iPhone** : installation PWA possible mais notifications limitées (contrainte Apple,
  documentée au §8 du cahier des charges). Un habillage natif plus tard ne demandera
  pas de réécrire.
- **Numéro provisoire hors ligne** (F10 `[À VALIDER]`) : implémenté sous la forme
  `ATT-{appareil}-{n°}` converti en numéro définitif à la synchronisation.
- **Modèles de documents** (quittance, reçu de caution, décharge) : structure usuelle
  adaptée au Sénégal, **à faire valider par le professionnel du secteur** (§13.3).
  La mention « document généré par l'application, modèle indicatif » figure en pied de page.
- **Scan** : compression + assemblage multi-pages PDF inclus ; détection de bords et
  OCR prévus en V2.
- **Envoi WhatsApp** : liens `wa.me` (zéro coût, zéro validation Meta), comme prévu au §8.
- **Gel des loyers annoncé en septembre 2026** : aucune règle codée en dur — tout est
  dans l'écran Règles, modifiable si l'arrêté paraît.
- Conformité CDP (protection des données) : à finaliser avant un lancement public large.

---

## 9. Comptes et rôles

| Rôle | Accès |
|---|---|
| **Gérant (responsable)** | Tout : paramètres, équipe, règles, journal d'audit, suppressions. |
| **Employé** | Gestion complète (biens, baux, encaissements, relances), sans paramètres ni audit. |
| **Propriétaire** | **Lecture seule** sur ses biens, loyers, rapports. Se connecte avec son numéro une fois invité. |
| Locataire | Pas de compte : quittances et relances par WhatsApp (§2 du cahier des charges). |

## 10. Ce que dit la loi sénégalaise (intégré, jamais bloquant)

Décret n° 2023-382 du 24 février 2023 (baux d'habitation ≤ 500 000 FCFA/mois, JO du 2 mars 2023) :

- **Caution ≤ 2 mois de loyer** ; **1 mois payable à l'entrée en jouissance**, le reliquat **étalé sur 12 mois** (1/12ᵉ par mois) — l'application calcule et affiche cet échéancier, et encaisse les versements.
- **Restitution** : l'application suit la date de remise des clés, propose le délai pratique (1 mois si état des lieux conforme, 2 mois si dégradations), **exige un motif pour toute retenue**, et génère un **reçu de restitution** (R-2026-…) vérifiable par QR.
- La caution **ne sert pas à payer le loyer** : rappel affiché sur la fiche du bail.
- **Commission d'agence ≤ ½ mois** de loyer (alerte douce).
- **Loyer payable à terme échu** selon le décret — sélectionnable dans Règles (le défaut de l'application reste le terme d'avance, pratique du terrain).
- Sans état des lieux d'entrée, le logement est présumé remis en bon état (rappel dans l'aide).

## 11. Relations entre acteurs (v1.2)

L'agence ne possède pas les biens : elle les **gère pour le compte des propriétaires** dans le cadre d'un **mandat de gestion** (dates, commission), suivi sur la fiche du rapport propriétaire — avec alerte quand un mandat arrive à échéance. Le **gérant** (et son équipe) travaille pour l'agence ; le **locataire** traite avec le gérant. Les quittances sont signées « *Le gérant — [agence]* » avec signature et tampon apposés automatiquement.

---

*SamaImmo v1.2 — MVP conforme au cahier des charges v0.3.*
*v1.2 (octobre 2026) : menu Gestion (les biens appartiennent aux propriétaires) ; mandats de gestion
agence↔propriétaire ; cautions conformes au décret 2023-382 (1 mois à l'entrée + 1/12ᵉ/mois,
restitution tracée avec retenues justifiées) ; cloche de notifications (retards, loyers attendus,
cautions à restituer, mandats et baux arrivant à échéance) ; exports PDF (état des loyers du mois,
état des arriérés, fiche locataire, journal d'activité) ; signature/tampon personnalisables avec
aperçu ; filtres, tris et boutons retour ; 42 tests automatisés.*
*v1.1 (1er octobre 2026) : loyer payable d'avance — attendu le 5, retard après le 10
(retour du terrain) ; terme échu du décret 2023-382 toujours configurable.*
