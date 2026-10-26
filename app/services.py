"""Services métier : paiements, annulations, reçus PDF numérotés, audit (F5, F6, F11).

Ces fonctions sont le point d'entrée UNIQUE pour créer un paiement — qu'il vienne de
l'API directe ou de la file de synchronisation hors ligne. C'est ce qui garantit
l'absence de doublon et la cohérence des reçus.
"""
from __future__ import annotations

import json
import secrets
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import log_action
from .config import FILES_DIR, settings
from .logique import MODES_PAIEMENT, periode_libelle
from .models import (Agence, Bail, CompteurRecu, Echeance, Immeuble, Locataire,
                     Paiement, Recu, Unite, User)
from .pdf import _fmt, generer_recu_pdf
from .security import normalize_phone

PREFIXES_RECUS = {"quittance": "Q", "caution": "C", "frais_agence": "F", "decharge": "D",
                  "restitution_caution": "R"}
MODES_VALIDES = set(MODES_PAIEMENT)


def nouveau_token() -> str:
    return secrets.token_urlsafe(18)


async def prochain_numero(db: AsyncSession, agence_id: str, recu_type: str) -> str:
    """Numérotation séquentielle par agence et par année : Q-2026-00001."""
    annee = date.today().year
    cpt = await db.get(CompteurRecu, {"agence_id": agence_id, "annee": annee})
    if not cpt:
        # il peut exister pour une autre année ; on crée la ligne de l'année
        exists = (await db.execute(
            select(CompteurRecu).where(CompteurRecu.agence_id == agence_id, CompteurRecu.annee == annee)
        )).scalars().first()
        if not exists:
            cpt = CompteurRecu(agence_id=agence_id, annee=annee, dernier=0)
            db.add(cpt)
    cpt.dernier += 1
    return f"{PREFIXES_RECUS.get(recu_type, 'R')}-{annee}-{cpt.dernier:05d}"


async def contexte_agence(db: AsyncSession, agence_id: str) -> dict:
    a = await db.get(Agence, agence_id)
    return {
        "id": a.id, "nom": a.nom, "telephone": a.telephone, "email": a.email,
        "adresse": a.adresse, "logo_path": a.logo_path, "signature_path": a.signature_path,
        "tampon_path": a.tampon_path,
    }


def verifier_appartenance(agence_obj: Agence | None, agence_id: str, msg: str = "Élément introuvable") -> None:
    if not agence_obj or agence_obj.agence_id != agence_id:
        raise HTTPException(404, msg)


async def contexte_bail(db: AsyncSession, bail_id: str, agence_id: str) -> tuple[Bail, Unite, Immeuble, Locataire]:
    bail = await db.get(Bail, bail_id)
    verifier_appartenance(bail, agence_id, "Bail introuvable")
    unite = await db.get(Unite, bail.unite_id)
    imm = await db.get(Immeuble, unite.immeuble_id)
    loc = await db.get(Locataire, bail.locataire_id)
    return bail, unite, imm, loc


async def enregistrer_paiement(
    db: AsyncSession,
    user: User,
    *,
    echeance_id: str,
    montant: int,
    mode: str,
    date_paiement: str | date,
    reference: str = "",
    client_uuid: str = "",
    device_id: str = "",
    preuve_path: str | None = None,
) -> tuple[Paiement, Recu, bool]:
    """Enregistre un paiement de loyer + génère la quittance PDF.
    Retourne (paiement, recu, deja_existant) — idempotent via client_uuid (F10)."""
    agence_id = user.agence_id
    if mode not in MODES_VALIDES:
        raise HTTPException(422, "Mode de paiement inconnu.")
    montant = int(montant)
    if montant <= 0:
        raise HTTPException(422, "Le montant doit être positif.")
    if isinstance(date_paiement, str):
        try:
            date_paiement = date.fromisoformat(date_paiement)
        except ValueError:
            raise HTTPException(422, "Date de paiement invalide (AAAA-MM-JJ).")

    echeance = await db.get(Echeance, echeance_id)
    verifier_appartenance(echeance, agence_id, "Échéance introuvable.")

    # Idempotence hors ligne : le même client_uuid ne crée jamais deux paiements.
    deja_existant = False
    if client_uuid:
        existant = (await db.execute(
            select(Paiement).where(Paiement.client_uuid == client_uuid, Paiement.agence_id == agence_id)
        )).scalars().first()
        if existant:
            recu = (await db.execute(select(Recu).where(Recu.paiement_id == existant.id))).scalars().first()
            return existant, recu, True

    paiement = Paiement(
        agence_id=agence_id,
        echeance_id=echeance.id,
        bail_id=echeance.bail_id,
        type="loyer",
        montant=montant,
        mode=mode,
        date_paiement=date_paiement,
        reference=(reference or "")[:200],
        preuve_path=preuve_path,
        saisi_par=user.id,
        device_id=device_id[:100],
        client_uuid=client_uuid[:64],
    )
    db.add(paiement)
    await db.flush()  # attribue les valeurs par défaut sans verrouiller la transaction

    recu = await _generer_quittance(db, user, paiement, device_id=device_id)
    await log_action(db, user, "paiement.cree", "paiement", paiement.id,
                     f"{montant} FCFA — {recu.numero}",
                     {"echeance": echeance.id, "periode": echeance.periode, "mode": mode,
                      "montant": montant, "recu_numero": recu.numero, "client_uuid": client_uuid},
                     device_id)
    await db.commit()
    return paiement, recu, deja_existant


async def _generer_quittance(db: AsyncSession, user: User, paiement: Paiement, device_id: str = "") -> Recu:
    """Génère la quittance PDF d'un paiement de loyer et son enregistrement."""
    agence = await contexte_agence(db, paiement.agence_id)
    echeance = await db.get(Echeance, paiement.echeance_id)
    bail, unite, imm, loc = await contexte_bail(db, paiement.bail_id, paiement.agence_id)

    numero = await prochain_numero(db, paiement.agence_id, "quittance")
    token = nouveau_token()
    chemin = str(FILES_DIR / "recus" / f"{numero.replace('/', '-')}.pdf")
    url_verif = f"{settings.base_url}/r/{token}"

    montant_du = echeance.montant_du if echeance else (bail.loyer + bail.charges)
    from .pdf import _san  # noqa
    from .nombres import montant_fcfa_lettres
    gerant = (user.nom or "").strip()
    blocs = [
        f"Je soussigné(e) {_san(gerant)}, gérant(e) de {_san(agence['nom'])}, déclare avoir reçu de "
        f"<b>{_san(loc.nom)}</b>, locataire du bien <b>{_san(unite.nom)} — {_san(imm.nom)}</b>"
        f" ({_san(imm.adresse)}{(', ' + imm.quartier) if imm.quartier else ''}), "
        f"la somme de <b>{_fmt(paiement.montant)} FCFA</b> "
        f"({_san(montant_fcfa_lettres(paiement.montant))}) "
        f"au titre du loyer et charges du mois de <b>{_san(periode_libelle(echeance.periode))}</b>, payable d'avance.",
    ]
    lignes = [
        ["Période", _san(periode_libelle(echeance.periode))],
        ["Loyer", f"{_fmt(bail.loyer)} FCFA"],
        ["Charges", f"{_fmt(bail.charges)} FCFA"],
        ["Total dû", f"{_fmt(montant_du)} FCFA"],
        ["Montant reçu", f"{_fmt(paiement.montant)} FCFA"],
    ]
    if echeance.date_limite:
        lignes.append(["Payable d'avance avant le", echeance.date_limite.strftime("%d/%m/%Y")])
    if paiement.montant < montant_du:
        lignes.append(["Reste à payer", f"{_fmt(montant_du - paiement.montant)} FCFA"])
        lignes.append(["Statut", "PAIEMENT PARTIEL"])
    else:
        lignes.append(["Statut", "SOLDÉ"])
    lignes += [
        ["Mode de paiement", MODES_PAIEMENT.get(paiement.mode, paiement.mode)],
        ["Date de paiement", paiement.date_paiement.strftime("%d/%m/%Y")],
    ]
    if paiement.reference:
        lignes.append(["Référence", _san(paiement.reference)])
    lignes.append(["Locataire", _san(loc.nom)])
    lignes.append(["Bien", f"{_san(unite.nom)} — {_san(imm.nom)}"])
    lignes.append(["Reçu n°", numero])

    empreinte = generer_recu_pdf(
        chemin, recu_type="quittance", numero=numero, url_verif=url_verif,
        agence=agence, lignes=lignes, blocs=[blocs[0],
            "Cette quittance est délivrée pour la somme effectivement reçue. "
            "Elle annule les reçus partiels précédents pour la même période une fois le solde réglé."],
        annule=paiement.annule,
    )
    recu = Recu(
        agence_id=paiement.agence_id, paiement_id=paiement.id, bail_id=paiement.bail_id,
        type="quittance", numero=numero, token=token, fichier_path=chemin, empreinte=empreinte,
        contenu=json.dumps({
            "numero": numero, "type": "quittance",
            "agence": agence["nom"], "locataire": loc.nom,
            "bien": f"{unite.nom} — {imm.nom}", "periode": periode_libelle(echeance.periode),
            "montant": paiement.montant, "mode": MODES_PAIEMENT.get(paiement.mode, paiement.mode),
            "date_paiement": paiement.date_paiement.isoformat(),
        }, ensure_ascii=False),
    )
    db.add(recu)
    await db.flush()
    return recu


async def annuler_paiement(db: AsyncSession, user: User, paiement_id: str, motif: str, device_id: str = "") -> tuple[Paiement, Paiement]:
    """Annulation par écriture : le paiement d'origine reste visible (marqué annulé)
    et une écriture négative motivée est créée (F5)."""
    if user.role not in ("responsable", "employe"):
        raise HTTPException(403, "Rôle insuffisant.")
    paiement = await db.get(Paiement, paiement_id)
    verifier_appartenance(paiement, user.agence_id, "Paiement introuvable.")
    if paiement.annule:
        raise HTTPException(422, "Ce paiement est déjà annulé.")
    if paiement.type != "loyer":
        raise HTTPException(422, "Seuls les paiements de loyer sont annulables ici.")
    motif = (motif or "").strip()
    if len(motif) < 3:
        raise HTTPException(422, "Un motif d'annulation est obligatoire.")

    ecriture = Paiement(
        agence_id=paiement.agence_id, echeance_id=paiement.echeance_id, bail_id=paiement.bail_id,
        type="annulation", montant=-paiement.montant, mode=paiement.mode,
        date_paiement=date.today(), reference=f"Annulation de {paiement.id[:8]}",
        motif_annulation=motif, saisi_par=user.id, device_id=device_id[:100],
        annule=False, annule_par_id=None,
    )
    db.add(ecriture)
    await db.flush()
    paiement.annule = True
    paiement.annule_par_id = ecriture.id

    # La quittance d'origine est marquée annulée et régénérée avec la mention.
    recu = (await db.execute(select(Recu).where(Recu.paiement_id == paiement.id))).scalars().first()
    if recu:
        recu.annule = True
        ancien = Path(recu.fichier_path)
        if ancien.exists():
            ancien.unlink()
        recu.annule = True
        empreinte = await _regenerer_quittance_annulee(db, paiement, recu)
        recu.empreinte = empreinte

    await log_action(db, user, "paiement.annule", "paiement", paiement.id,
                     f"-{paiement.montant} FCFA — motif : {motif}",
                     {"motif": motif, "ecriture_id": ecriture.id}, device_id)
    await db.commit()
    return paiement, ecriture


async def _regenerer_quittance_annulee(db: AsyncSession, paiement: Paiement, recu: Recu) -> str:
    """Régénère le PDF d'une quittance avec la mention ANNULÉ (l'original reste archivé)."""
    agence = await contexte_agence(db, paiement.agence_id)
    echeance = await db.get(Echeance, paiement.echeance_id)
    bail, unite, imm, loc = await contexte_bail(db, paiement.bail_id, paiement.agence_id)
    from .nombres import montant_fcfa_lettres
    from .pdf import _san
    url_verif = f"{settings.base_url}/r/{recu.token}"
    bloc = (f"Je soussigné(e) {_san(agence['nom'])}, gestionnaire, avais reçu de "
            f"<b>{_san(loc.nom)}</b>, locataire du bien <b>{_san(unite.nom)} — {_san(imm.nom)}</b>, "
            f"la somme de <b>{_fmt(paiement.montant)} FCFA</b> "
            f"({_san(montant_fcfa_lettres(paiement.montant))}) "
            f"au titre du loyer de la période <b>{_san(periode_libelle(echeance.periode))}</b>. "
            f"<b>Ce paiement a été annulé</b> : {_san(paiement.motif_annulation)}.")
    lignes = [
        ["Période", _san(periode_libelle(echeance.periode))],
        ["Montant d'origine", f"{_fmt(paiement.montant)} FCFA"],
        ["Mode", MODES_PAIEMENT.get(paiement.mode, paiement.mode)],
        ["Reçu n°", recu.numero],
        ["Statut", "ANNULÉ"],
    ]
    return generer_recu_pdf(recu.fichier_path, recu_type="quittance", numero=recu.numero,
                            url_verif=url_verif, agence=agence, lignes=lignes, blocs=[bloc],
                            annule=True)


async def creer_recu_autre(
    db: AsyncSession, user: User, *, recu_type: str, bail_id: str,
    montant: int = 0, reference: str = "", device_id: str = "",
) -> Recu:
    """Reçu de caution, reçu de frais d'agence, décharge de remise de clés (F6)."""
    if recu_type not in ("caution", "frais_agence", "decharge", "restitution_caution"):
        raise HTTPException(422, "Type de reçu inconnu.")
    bail, unite, imm, loc = await contexte_bail(db, bail_id, user.agence_id)
    agence = await contexte_agence(db, user.agence_id)
    numero = await prochain_numero(db, user.agence_id, recu_type)
    token = nouveau_token()
    chemin = str(FILES_DIR / "recus" / f"{numero.replace('/', '-')}.pdf")
    url_verif = f"{settings.base_url}/r/{token}"
    from .nombres import montant_fcfa_lettres
    from .pdf import _san

    gerant = (user.nom or "").strip()
    if recu_type == "caution":
        bloc = (f"Je soussigné(e) {_san(gerant)}, gérant(e) de {_san(agence['nom'])}, déclare avoir reçu de "
                f"<b>{_san(loc.nom)}</b>, locataire du bien <b>{_san(unite.nom)} — {_san(imm.nom)}</b>, "
                f"la somme de <b>{_fmt(montant)} FCFA</b> ({_san(montant_fcfa_lettres(montant))}) "
                f"au titre de la <b>caution</b> du bail démarrant le {bail.date_debut.strftime('%d/%m/%Y')}.")
        lignes = [
            ["Montant reçu", f"{_fmt(montant)} FCFA"],
            ["Caution prévue au bail", f"{_fmt(bail.caution)} FCFA"],
            ["Reste de caution dû", f"{_fmt(max(0, bail.caution - montant))} FCFA"],
            ["Locataire", _san(loc.nom)],
            ["Bien", f"{_san(unite.nom)} — {_san(imm.nom)}"],
            ["Reçu n°", numero],
        ]
    elif recu_type == "frais_agence":
        bloc = (f"Je soussigné(e) {_san(agence['nom'])}, agence immobilière, déclare avoir reçu de "
                f"<b>{_san(loc.nom)}</b> la somme de <b>{_fmt(montant)} FCFA</b> "
                f"({_san(montant_fcfa_lettres(montant))}) au titre des <b>frais d'agence</b> "
                f"pour le bail du bien {_san(unite.nom)} — {_san(imm.nom)}.")
        lignes = [
            ["Montant reçu", f"{_fmt(montant)} FCFA"],
            ["Loyer mensuel de référence", f"{_fmt(bail.loyer)} FCFA"],
            ["Locataire", _san(loc.nom)],
            ["Bien", f"{_san(unite.nom)} — {_san(imm.nom)}"],
            ["Reçu n°", numero],
        ]
    elif recu_type == "restitution_caution":
        # restitution = caution versée - retenue justifiée (décret 2023-382 : retenues sur justificatifs)
        retenue = max(0, getattr(bail, "caution_retenue", 0) or 0)
        motif = (getattr(bail, "caution_retenue_motif", "") or "").strip()
        versements = 0  # calculé par l'appelant via situation_caution ; ici montant = net restitué
        bloc = (f"Je soussigné(e) {_san(gerant)}, gérant(e) de {_san(agence['nom'])}, déclare avoir restitué à "
                f"<b>{_san(loc.nom)}</b>, locataire du bien <b>{_san(unite.nom)} — {_san(imm.nom)}</b>, "
                f"la somme de <b>{_fmt(montant)} FCFA</b> ({_san(montant_fcfa_lettres(montant))}) "
                f"au titre de la <b>restitution de la caution</b> du bail du {bail.date_debut.strftime('%d/%m/%Y')}"
                + (f", déduction faite d'une retenue de {_fmt(retenue)} FCFA ({_san(motif)})" if retenue > 0 else "")
                + ".")
        lignes = [
            ["Montant restitué", f"{_fmt(montant)} FCFA"],
            ["Caution versée (cumul)", f"{_fmt(montant + retenue)} FCFA"],
            ["Retenue justifiée", f"{_fmt(retenue)} FCFA" + (f" — {_san(motif)}" if motif else "")],
            ["Remise des clés", bail.date_fin.strftime("%d/%m/%Y") if bail.date_fin else "—"],
            ["Locataire", _san(loc.nom)],
            ["Bien", f"{_san(unite.nom)} — {_san(imm.nom)}"],
            ["Reçu n°", numero],
        ]
    else:  # decharge
        bloc = (f"Je soussigné(e) {_san(loc.nom)}, locataire du bien <b>{_san(unite.nom)} — {_san(imm.nom)}</b>, "
                f"déclare avoir reçu les clés du bien et en prendre possession en l'état. "
                f"La présente décharge est délivrée à {_san(agence['nom'])} pour le bail démarrant "
                f"le {bail.date_debut.strftime('%d/%m/%Y')}.")
        lignes = [
            ["Locataire", _san(loc.nom)],
            ["Bien", f"{_san(unite.nom)} — {_san(imm.nom)}"],
            ["Date de remise des clés", date.today().strftime("%d/%m/%Y")],
            ["Loyer mensuel", f"{_fmt(bail.loyer)} FCFA"],
            ["Caution versée", f"{_fmt(bail.caution)} FCFA"],
            ["Reçu n°", numero],
        ]
    if reference:
        lignes.append(["Référence", _san(reference)])

    empreinte = generer_recu_pdf(chemin, recu_type=recu_type, numero=numero, url_verif=url_verif,
                                 agence=agence, lignes=lignes, blocs=[bloc])
    recu = Recu(
        agence_id=user.agence_id, bail_id=bail.id, type=recu_type, numero=numero,
        token=token, fichier_path=chemin, empreinte=empreinte,
        contenu=json.dumps({
            "numero": numero, "type": recu_type, "agence": agence["nom"], "locataire": loc.nom,
            "bien": f"{unite.nom} — {imm.nom}", "montant": montant,
            "date": date.today().isoformat(),
        }, ensure_ascii=False),
    )
    db.add(recu)
    # Paiement hors loyer (caution/frais) enregistré dans le grand livre pour la trace
    if recu_type in ("caution", "frais_agence") and montant > 0:
        db.add(Paiement(
            agence_id=user.agence_id, bail_id=bail.id, type=recu_type, montant=montant,
            mode="autre", date_paiement=date.today(), reference=reference[:200],
            saisi_par=user.id, device_id=device_id[:100],
        ))
    await log_action(db, user, f"recu.{recu_type}", "recu", recu.id, numero,
                     {"montant": montant, "bail": bail.id}, device_id)
    await db.commit()
    return recu


async def telephone_whatsapp(loc: Locataire) -> str:
    return normalize_phone(loc.telephone_whatsapp or loc.telephone)
