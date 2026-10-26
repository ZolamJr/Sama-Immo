"""F12 — Numérisation : import de photos (compressées côté client) ou PDF,
assemblage multi-pages en un seul PDF, rattachement à une fiche en 3 clics."""
from __future__ import annotations

import io
import secrets
import uuid as uuid_mod
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import device_id_from, log_action
from ..config import FILES_DIR
from ..security import get_db
from ..models import (Bail, Document, Immeuble, Locataire, Paiement,
                      Proprietaire, Unite, User)
from ..security import current_user, responsable_only, staff_or_responsable
from ..serializers import ser_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

TYPES_DOC = {
    "bail_signe": "Bail signé", "piece_identite": "Pièce d'identité",
    "titre_propriete": "Titre de propriété / attestation", "etat_des_lieux": "État des lieux",
    "recu_papier": "Reçu papier", "justificatif": "Justificatif de paiement",
    "facture_travaux": "Facture de travaux", "enregistrement": "Enregistrement du bail (DGID)",
    "autre": "Autre",
}
ATTACHE = {"bail", "locataire", "unite", "immeuble", "proprietaire", "paiement"}
TAILLE_MAX = 10 * 1024 * 1024  # 10 Mo par fichier


async def _verifier_cible(db: AsyncSession, agence_id: str, attache_type: str, attache_id: str):
    modeles = {"bail": Bail, "locataire": Locataire, "unite": Unite,
               "immeuble": Immeuble, "proprietaire": Proprietaire, "paiement": Paiement}
    obj = await db.get(modeles[attache_type], attache_id)
    if not obj or obj.agence_id != agence_id:
        raise HTTPException(404, "Fiche de rattachement introuvable.")
    return obj


@router.post("")
async def ajouter_documents(
    request: Request,
    fichiers: list[UploadFile] = File(...),
    attache_type: str = Form(...),
    attache_id: str = Form(...),
    type_document: str = Form("autre"),
    user: User = Depends(staff_or_responsable),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "proprietaire":
        raise HTTPException(403, "Lecture seule.")
    if attache_type not in ATTACHE:
        raise HTTPException(422, f"Rattachement invalide : {', '.join(sorted(ATTACHE))}.")
    if type_document not in TYPES_DOC:
        raise HTTPException(422, "Type de document inconnu.")
    if len(fichiers) > 10:
        raise HTTPException(422, "10 fichiers maximum par envoi.")
    await _verifier_cible(db, user.agence_id, attache_type, attache_id)

    images: list[bytes] = []
    pdf_unique: bytes | None = None
    for f in fichiers:
        donnees = await f.read()
        if len(donnees) > TAILLE_MAX:
            raise HTTPException(413, f"{f.filename} : trop lourd (max 10 Mo). Comprimez la photo.")
        ct = (f.content_type or "").lower()
        if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            images.append(donnees)
        elif ct == "application/pdf":
            if pdf_unique is not None or images:
                raise HTTPException(422, "Mélange PDF + images non supporté : envoyez soit un PDF, soit des photos.")
            pdf_unique = donnees
        else:
            raise HTTPException(422, f"{f.filename} : format non supporté (image ou PDF).")

    nom_base = (fichiers[0].filename or "document").rsplit(".", 1)[0][:200] or "document"

    if pdf_unique is not None:
        chemin = FILES_DIR / "uploads" / f"doc-{uuid_mod.uuid4().hex}.pdf"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(pdf_unique)
        mimetype, pages, poids = "application/pdf", 1, len(pdf_unique)
    elif len(images) == 1:
        ext = "jpg"
        chemin = FILES_DIR / "uploads" / f"doc-{uuid_mod.uuid4().hex}.{ext}"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(images[0])
        mimetype, pages, poids = "image/jpeg", 1, len(images[0])
    else:
        # plusieurs photos -> un seul PDF (une page par photo)
        chemin, poids = _assembler_pdf_images(images)
        mimetype, pages = "application/pdf", len(images)

    doc = Document(
        agence_id=user.agence_id, attache_type=attache_type, attache_id=attache_id,
        type_document=type_document, nom=nom_base, fichier_path=str(chemin),
        mimetype=mimetype, poids=poids, pages=pages, saisi_par=user.id,
    )
    db.add(doc)
    await log_action(db, user, "document.ajoute", "document", doc.id, nom_base,
                     {"type": type_document, "attache": attache_type, "pages": pages},
                     device_id_from(request))
    await db.commit()
    return {"document": ser_document(doc), "message": f"Document enregistré ({pages} page(s), {poids // 1024} Ko)."}


def _assembler_pdf_images(images: list[bytes]) -> tuple[Path, int]:
    """Assemble des images JPEG/PNG en un PDF une page par image (F12)."""
    from PIL import Image as PILImage, ImageOps
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    chemin = FILES_DIR / "uploads" / f"doc-{uuid_mod.uuid4().hex}.pdf"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(chemin), pagesize=A4)
    larg, haut = A4
    for donnees in images:
        img_io = io.BytesIO(donnees)
        with PILImage.open(img_io) as im:
            im = ImageOps.exif_transpose(im)  # respecte l'orientation de la photo
            img_path = chemin.with_suffix(f".tmp-{secrets.token_hex(3)}.jpg")
            im.convert("RGB").save(img_path, "JPEG", quality=70)
        with PILImage.open(img_path) as im:
            w, h = im.size
        marge = 10
        ech = min((larg - 2 * marge) / w, (haut - 2 * marge) / h)
        dw, dh = w * ech, h * ech
        c.drawImage(str(img_path), (larg - dw) / 2, (haut - dh) / 2, width=dw, height=dh)
        c.showPage()
        img_path.unlink(missing_ok=True)
    c.save()
    return chemin, chemin.stat().st_size


@router.get("")
async def lister_documents(attache_type: str = "", attache_id: str = "",
                           user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Document).where(Document.agence_id == user.agence_id)
    if attache_type and attache_id:
        query = query.where(Document.attache_type == attache_type, Document.attache_id == attache_id)
    docs = (await db.execute(query.order_by(Document.created_at.desc()))).scalars().all()
    return {"documents": [dict(ser_document(d), type_libelle=TYPES_DOC.get(d.type_document, d.type_document))
                          for d in docs]}


@router.get("/{did}/fichier")
async def obtenir_fichier(did: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    d = await db.get(Document, did)
    if not d or d.agence_id != user.agence_id:
        raise HTTPException(404, "Document introuvable.")
    if not Path(d.fichier_path).exists():
        raise HTTPException(404, "Fichier absent.")
    return FileResponse(d.fichier_path, media_type=d.mimetype, filename=Path(d.fichier_path).name)


@router.delete("/{did}")
async def supprimer_document(did: str, request: Request,
                             user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    d = await db.get(Document, did)
    if not d or d.agence_id != user.agence_id:
        raise HTTPException(404, "Document introuvable.")
    await log_action(db, user, "document.supprime", "document", d.id, d.nom,
                     {"type": d.type_document, "attache": d.attache_type}, device_id_from(request))
    Path(d.fichier_path).unlink(missing_ok=True)
    await db.delete(d)
    await db.commit()
    return {"ok": True}
