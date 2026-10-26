"""Base de données : SQLite en mode WAL (fiable et léger, idéal pour ~100 agences)."""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH}",
    echo=False,
    connect_args={"timeout": 30, "check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite(dbapi_conn, _):  # pragma: no cover - infra
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Crée les tables si nécessaire + petites migrations SQLite (ALTER manuels)."""
    from sqlalchemy import text

    from .models import Base  # noqa: F401  (importe aussi tous les modèles)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all ne modifie pas les tables existantes : colonnes ajoutées à la main
        cols_ech = (await conn.execute(text("PRAGMA table_info(echeances)"))).fetchall()
        if cols_ech and "date_limite" not in {c[1] for c in cols_ech}:
            await conn.execute(text("ALTER TABLE echeances ADD COLUMN date_limite DATE"))
            await conn.execute(text(
                "UPDATE echeances SET date_limite = substr(periode,1,4)||'-'||substr(periode,6,2)||'-10'"))
        cols_regles = (await conn.execute(text("PRAGMA table_info(regles)"))).fetchall()
        if cols_regles and "jour_limite_paiement" not in {c[1] for c in cols_regles}:
            await conn.execute(text("ALTER TABLE regles ADD COLUMN jour_limite_paiement INTEGER DEFAULT 10"))
        # v1.2 — mandat de gestion (agence <-> propriétaire)
        cols_prop = (await conn.execute(text("PRAGMA table_info(proprietaires)"))).fetchall()
        if cols_prop:
            noms = {c[1] for c in cols_prop}
            if "mandat_debut" not in noms:
                await conn.execute(text("ALTER TABLE proprietaires ADD COLUMN mandat_debut DATE"))
            if "mandat_fin" not in noms:
                await conn.execute(text("ALTER TABLE proprietaires ADD COLUMN mandat_fin DATE"))
        # v1.2 — restitution de caution
        cols_baux = (await conn.execute(text("PRAGMA table_info(baux)"))).fetchall()
        if cols_baux:
            noms = {c[1] for c in cols_baux}
            if "caution_rembourse_le" not in noms:
                await conn.execute(text("ALTER TABLE baux ADD COLUMN caution_rembourse_le DATE"))
            if "caution_retenue" not in noms:
                await conn.execute(text("ALTER TABLE baux ADD COLUMN caution_retenue INTEGER DEFAULT 0"))
            if "caution_retenue_motif" not in noms:
                await conn.execute(text("ALTER TABLE baux ADD COLUMN caution_retenue_motif TEXT DEFAULT ''"))
