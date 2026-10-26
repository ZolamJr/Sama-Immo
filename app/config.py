"""Configuration centrale de l'application (surchargeable par variable d'environnement ou fichier .env)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
FILES_DIR = DATA_DIR / "files"
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "app.db"))
SECRET_PATH = DATA_DIR / "secret.key"


class Settings(BaseSettings):
    app_name: str = "SamaImmo"
    app_title: str = "SamaImmo — Gestion locative"
    # URL publique de base (utilisée dans les QR codes et liens de partage).
    # En production : https://mon-domaine.sn
    base_url: str = os.environ.get("BASE_URL", "http://localhost:8000")

    # OTP / connexion
    otp_dev_mode: bool = True          # True : le code s'affiche à l'écran (démo / avant branchement SMS)
    otp_ttl_min: int = 5               # durée de vie du code
    otp_len: int = 6
    otp_max_attempts: int = 5
    otp_resend_sec: int = 60           # anti-spam entre deux demandes
    jwt_ttl_days: int = 30

    # Envoi SMS (agrégateur) : console = logs seulement ; http = passerelle générique
    sms_provider: str = "console"      # console | http
    sms_http_url: str = ""
    sms_http_key: str = ""
    sms_sender_name: str = "SamaImmo"

    # Sauvegardes
    backup_hour: int = 3               # heure locale de la sauvegarde quotidienne
    backup_keep_days: int = 14

    # Règles locales par défaut (décret n° 2023-382) — modifiables par agence (F13)
    caution_max_mois: int = 2
    frais_agence_max_mois: float = 0.5
    rappel_enregistrement_jours: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


def get_jwt_secret() -> str:
    """Secret JWT persistant : généré une fois, conservé dans data/secret.key."""
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text().strip()
    s = secrets.token_hex(32)
    SECRET_PATH.write_text(s)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return s


JWT_SECRET = get_jwt_secret()
