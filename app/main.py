"""SamaImmo — application de gestion locative (Sénégal). Point d'entrée.

Un seul service : API FastAPI (async) + interface PWA servie en statique + SQLite.
"""
from __future__ import annotations

import asyncio
import contextlib
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import DATA_DIR, FILES_DIR, settings
from .db import SessionLocal, engine, init_db
from .routers import auth, documents, fiches, loyers, parametres, public, sync

BACKUP_DIR = DATA_DIR / "backups"


async def _tache_echeances() -> None:
    """Chaque heure : crée les échéances manquantes du mois pour toutes les agences (F5).
    Idempotent (contrainte unique bail+période) — un crash ne crée jamais de doublon."""
    from sqlalchemy import select

    from .logique import ensure_echeances_agence
    from .models import Agence
    dernier_jour = None
    while True:
        try:
            aujourdhui = date.today()
            if aujourdhui != dernier_jour:  # au changement de jour (donc le 1er), on régénère
                dernier_jour = aujourdhui
                async with SessionLocal() as db:
                    agences = (await db.execute(select(Agence))).scalars().all()
                    for a in agences:
                        try:
                            await ensure_echeances_agence(db, a.id)
                        except Exception as e:  # noqa: BLE001
                            print(f"[tache] échéances agence {a.id}: {e}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[tache] boucle échéances : {e}", flush=True)
        await asyncio.sleep(3600)


def _sauvegarder_db() -> Path | None:
    """Sauvegarde physique de SQLite via l'API backup (cohérente même en cours d'écriture)."""
    from .config import DB_PATH
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        cible = BACKUP_DIR / f"app-{date.today().strftime('%Y%m%d-%H%M')}.db"
        src = sqlite3.connect(str(DB_PATH), timeout=30)
        dst = sqlite3.connect(str(cible))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        return cible
    except Exception as e:  # noqa: BLE001
        print(f"[backup] échec : {e}", flush=True)
        return None


async def _tache_backups() -> None:
    """Sauvegarde quotidienne à l'heure configurée, rétention de N jours (§7)."""
    dernier = None
    while True:
        maintenant = datetime.now()
        cible = maintenant.replace(hour=settings.backup_hour, minute=5, second=0, microsecond=0)
        if dernier != cible.date() and maintenant >= cible:
            chemin = await asyncio.to_thread(_sauvegarder_db)
            if chemin:
                dernier = cible.date()
                print(f"[backup] sauvegarde créée : {chemin.name}", flush=True)
                # rétention
                anciens = sorted(BACKUP_DIR.glob("app-*.db"))
                limite = date.today() - timedelta(days=settings.backup_keep_days)
                for ancien in anciens:
                    try:
                        if datetime.fromtimestamp(ancien.stat().st_mtime).date() < limite:
                            ancien.unlink()
                    except OSError:
                        pass
        await asyncio.sleep(600)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    Path(FILES_DIR).mkdir(parents=True, exist_ok=True)
    t1 = asyncio.create_task(_tache_echeances())
    t2 = asyncio.create_task(_tache_backups())
    print(f"[demarrage] {settings.app_name} prêt — base : {DATA_DIR / 'app.db'}", flush=True)
    try:
        yield
    finally:
        t1.cancel()
        t2.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(t1, t2)
        await engine.dispose()


app = FastAPI(title=settings.app_title, version="1.1.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")

app.include_router(auth.router)
app.include_router(parametres.router)
app.include_router(fiches.router)
app.include_router(loyers.router)
app.include_router(sync.router)
app.include_router(documents.router)
app.include_router(public.router)  # /r/{token}, /p/{token} — avant le montage statique

# Service worker et manifeste doivent rester à la racine
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
