#!/usr/bin/env bash
# ============================================================
#  SamaImmo — démarrage Linux / macOS
#  Utilisation :  bash start.sh
#  Chaque étape s'affiche : si ça s'arrête, vous voyez où.
# ============================================================
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
cd "$(dirname "$0")"

echo "====================================================="
echo "  SamaImmo — démarrage"
echo "====================================================="

# ---- [1/7] projet bien extrait (pas lancé depuis le zip) ----
if [ ! -f "requirements.txt" ] || [ ! -f "app/main.py" ]; then
  echo "[1/7] [ERREUR] Fichiers du projet introuvables."
  echo "       Vous avez probablement lancé le script depuis l'archive ZIP sans l'extraire."
  echo "       Extrayez TOUTE l'archive (clic droit > Extraire ici, ou : unzip samaimmo-v1.2.zip)"
  exit 1
fi
echo "[1/7] Fichiers du projet : OK"

# ---- [2/7] Python 3.10 minimum ----
PY=""
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "[2/7] [ERREUR] Python est introuvable sur cette machine."
  echo "       Ubuntu/Debian : sudo apt install python3 python3-venv"
  echo "       Fedora        : sudo dnf install python3"
  echo "       Autre         : https://www.python.org/downloads/"
  exit 1
fi
if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
  echo "[2/7] [ERREUR] Python 3.10 ou plus récent requis. Version actuelle : $("$PY" --version 2>&1)"
  exit 1
fi
echo "[2/7] $("$PY" --version 2>&1) : OK"

# ---- [3/7] environnement virtuel (créé s'il manque) ----
if [ ! -x ".venv/bin/python" ]; then
  echo "[3/7] Création de l'environnement virtuel…"
  if ! "$PY" -m venv .venv 2>/tmp/samaimmo-venv.log; then
    echo "[3/7] [ERREUR] Création de l'environnement virtuel impossible."
    echo "       Cause fréquente sur Ubuntu/Debian, il manque le paquet venv. Faites :"
    echo "           sudo apt install python3-venv"
    echo "       puis relancez :  bash start.sh"
    echo "       Détail technique : $(tail -2 /tmp/samaimmo-venv.log 2>/dev/null)"
    exit 1
  fi
else
  echo "[3/7] Environnement virtuel : présent"
fi

# ---- [4/7] dépendances (installées ou RÉINSTALLÉES si incomplètes) ----
if ! ./.venv/bin/python -c "import uvicorn, fastapi, sqlalchemy, reportlab, qrcode, PIL, jwt" >/dev/null 2>&1; then
  echo "[4/7] Installation des dépendances (2 à 5 minutes selon la connexion)…"
  echo "       Laissez cette fenêtre ouverte — la progression s'affiche ci-dessous :"
  echo "       ------------------------------------------------------------------"
  ./.venv/bin/python -m pip install --upgrade pip --quiet 2>/dev/null
  if ! ./.venv/bin/python -m pip install -r requirements.txt; then
    echo "       ------------------------------------------------------------------"
    echo "[4/7] [ERREUR] L'installation a échoué : vérifiez la connexion internet,"
    echo "       puis relancez :  bash start.sh   (l'installation reprendra où elle en était)"
    exit 1
  fi
  echo "       ------------------------------------------------------------------"
  echo "[4/7] Installation terminée."
else
  echo "[4/7] Dépendances : déjà installées"
fi

# ---- [5/7] configuration ----
[ -f .env ] || cp .env.example .env
echo "[5/7] Configuration : OK"

# ---- [6/7] données de démo (premier lancement, sans blocage) ----
if [ ! -f data/app.db ]; then
  echo ""
  printf "Charger les données de démonstration (2 propriétaires, 5 biens, quittances) ? (o/N) "
  read -r REP || REP=""
  if [ "$REP" = "o" ] || [ "$REP" = "O" ]; then
    if ./.venv/bin/python scripts/seed_demo.py; then
      echo "Démo chargée."
    else
      echo "⚠ Démo non chargée (sans gravité) : l'application démarre avec une base vide."
      echo "  Vous pourrez créer votre agence avec votre propre numéro de téléphone."
    fi
  fi
fi
echo "[6/7] Données : OK"

# ---- [7/7] choix automatique d'un port libre ----
port_occupe() {
  "$PY" -c "import sys, socket; s = socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', $1)) == 0 else 1)" >/dev/null 2>&1
}
PORT=8000
ESSAIS=0
while port_occupe "$PORT"; do
  echo "       Port $PORT occupé par une autre application → essai du port $((PORT + 1))…"
  PORT=$((PORT + 1))
  ESSAIS=$((ESSAIS + 1))
  if [ "$ESSAIS" -ge 20 ]; then
    echo "[7/7] [ERREUR] Aucun port libre entre 8000 et 8019."
    exit 1
  fi
done
export BASE_URL="http://localhost:$PORT"
echo "[7/7] Port choisi : $PORT"

# ouverture automatique du navigateur (si l'environnement le permet)
URL="http://localhost:$PORT"
if command -v xdg-open >/dev/null 2>&1; then (xdg-open "$URL" >/dev/null 2>&1 &)
elif command -v open >/dev/null 2>&1; then (open "$URL" >/dev/null 2>&1 &)
fi

echo ""
echo "  ====================================================="
echo ""
echo "    SamaImmo démarre sur :  http://localhost:$PORT"
echo ""
echo "    Le navigateur s'ouvre tout seul ; sinon ouvrez"
echo "    vous-même l'adresse ci-dessus."
echo ""
echo "    Compte de démo :  +221 770 000 000"
echo "    (code de connexion affiché à l'écran)"
echo ""
echo "    Pour arrêter : Ctrl+C"
echo "    Gardez cette fenêtre ouverte pendant l'utilisation."
echo ""
echo "  ====================================================="
echo ""

# ---- lancement (sans exec : si ça échoue, on voit pourquoi) ----
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
CODE=$?
echo ""
if [ "$CODE" -eq 130 ]; then
  echo "[Serveur arrêté proprement (Ctrl+C).]"
else
  echo "[Le serveur s'est arrêté — code $CODE.]"
  echo " Pour voir l'erreur exacte, relancez la commande seule :"
  echo "     ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  echo " puis envoyez le message affiché."
fi
printf "Appuyez sur Entrée pour fermer…"
read -r _ || true
