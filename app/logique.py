"""Logique locative : échéances mensuelles, statuts, tableaux de bord (F5, F8)."""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Bail, Echeance, Immeuble, Locataire, Paiement, Proprietaire, Regles, Unite

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

MODES_PAIEMENT = {
    "wave": "Wave", "orange_money": "Orange Money", "especes": "Espèces",
    "virement": "Virement", "cheque": "Chèque", "autre": "Autre",
}


def periode_courante(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.year:04d}-{d.month:02d}"


def periode_libelle(periode: str) -> str:
    annee, mois = periode.split("-")
    return f"{MOIS_FR[int(mois) - 1]} {annee}"


def periode_suivante(periode: str) -> str:
    annee, mois = int(periode[:4]), int(periode[5:7])
    if mois == 12:
        return f"{annee + 1:04d}-01"
    return f"{annee:04d}-{mois + 1:02d}"


def periode_precedente(periode: str) -> str:
    annee, mois = int(periode[:4]), int(periode[5:7])
    if mois == 1:
        return f"{annee - 1:04d}-12"
    return f"{annee:04d}-{mois - 1:02d}"


def _jour_dans_mois(annee: int, mois: int, jour: int) -> date:
    return date(annee, mois, min(jour, calendar.monthrange(annee, mois)[1]))


def _date_limite(apres: date, jour_limite: int) -> date:
    """Dernier jour pour payer : le `jour_limite` (ex. 10) du mois de l'échéance,
    ou du mois suivant si l'échéance tombe après ce jour (1er loyer à la signature,
    terme échu)."""
    if apres.day <= jour_limite:
        return _jour_dans_mois(apres.year, apres.month, jour_limite)
    y, m = (apres.year + 1, 1) if apres.month == 12 else (apres.year, apres.month + 1)
    return _jour_dans_mois(y, m, jour_limite)


def date_echeance_de_periode(periode: str, terme: str, jour: int) -> date:
    """Terme 'debut' (payable d'avance, pratique courante) : le jour d'échéance du mois concerné.
    Terme 'fin' (décret 2023-382, terme échu) : fin du mois de jouissance."""
    annee, mois = int(periode[:4]), int(periode[5:7])
    dernier = calendar.monthrange(annee, mois)[1]
    if terme == "fin":
        return date(annee, mois, dernier)
    return date(annee, mois, min(jour or 5, dernier))


def periodes_pour_bail(bail: Bail, jusqu_a: date | None = None, max_recul_mois: int = 24) -> list[str]:
    """Liste des périodes couvertes par un bail (du mois de début au mois courant)."""
    jusqu_a = jusqu_a or date.today()
    debut = bail.date_debut
    fin = min(bail.date_fin or jusqu_a, jusqu_a)
    periodes: list[str] = []
    cur = f"{debut.year:04d}-{debut.month:02d}"
    limite = f"{fin.year:04d}-{fin.month:02d}"
    limite_passee = 0
    while cur <= limite and limite_passee < max_recul_mois + 24:
        periodes.append(cur)
        cur = periode_suivante(cur)
        limite_passee += 1
    # pas plus de `max_recul_mois` avant aujourd'hui (sécurité anti-boucle sur vieux bail)
    today_p = periode_courante(jusqu_a)
    while periodes and _mois_ecarts(periodes[0], today_p) > max_recul_mois:
        periodes.pop(0)
    return periodes


def _mois_ecarts(p1: str, p2: str) -> int:
    a1, m1 = int(p1[:4]), int(p1[5:7])
    a2, m2 = int(p2[:4]), int(p2[5:7])
    return (a2 - a1) * 12 + (m2 - m1)


async def regles_agence(db: AsyncSession, agence_id: str) -> Regles:
    r = (await db.execute(select(Regles).where(Regles.agence_id == agence_id))).scalars().first()
    if not r:
        r = Regles(agence_id=agence_id)
        db.add(r)
        await db.commit()
    return r


async def ensure_echeances_agence(db: AsyncSession, agence_id: str) -> int:
    """Crée les échéances manquantes pour les baux actifs (idempotent).

    Règle par défaut (retour du terrain, octobre 2026) : loyer payable D'AVANCE,
    attendu le jour d'échéance (ex. le 5), retard au-delà du jour limite (ex. le 10).
    Le terme échu du décret 2023-382 reste sélectionnable dans les Règles (F13)."""
    regles = await regles_agence(db, agence_id)
    aujourdhui = date.today()
    jour_limite = regles.jour_limite_paiement or 10
    creees = 0
    baux = (await db.execute(select(Bail).where(Bail.agence_id == agence_id, Bail.statut == "actif"))).scalars().all()
    for bail in baux:
        for idx, periode in enumerate(periodes_pour_bail(bail, aujourdhui)):
            existe = await db.execute(
                select(Echeance.id).where(Echeance.bail_id == bail.id, Echeance.periode == periode)
            )
            if existe.scalars().first():
                continue
            annee, mois = int(periode[:4]), int(periode[5:7])
            if regles.terme_paiement == "fin":
                # terme échu : fin du mois de jouissance
                date_ech = date(annee, mois, calendar.monthrange(annee, mois)[1])
            elif idx == 0 and bail.date_debut.day > bail.jour_echeance:
                # premier loyer d'un bail signé après le jour d'échéance : à la signature
                date_ech = bail.date_debut
            else:
                # payable d'avance : le jour d'échéance du mois concerné (ex. le 5)
                date_ech = _jour_dans_mois(annee, mois, bail.jour_echeance)
            db.add(Echeance(
                agence_id=agence_id,
                bail_id=bail.id,
                periode=periode,
                montant_du=bail.loyer + bail.charges,
                date_echeance=date_ech,
                date_limite=_date_limite(date_ech, jour_limite),
            ))
            creees += 1
    if creees:
        await db.commit()
    return creees


async def montant_paye_echeance(db: AsyncSession, echeance_id: str) -> int:
    res = await db.execute(
        select(func.coalesce(func.sum(Paiement.montant), 0)).where(
            Paiement.echeance_id == echeance_id,
            Paiement.annule.is_(False),
            Paiement.type == "loyer",
        )
    )
    return int(res.scalar() or 0)


def statut_echeance(montant_du: int, montant_paye: int, date_ech: date, aujourdhui: date | None = None,
                    date_limite: date | None = None) -> str:
    """payé | partiel | en_retard | en_attente (en_retard l'emporte sur partiel).

    date_limite : dernier jour de tolérance (ex. le 10 du mois) — le retard
    commence le lendemain. Sans date_limite, c'est date_ech qui sert de seuil."""
    aujourdhui = aujourdhui or date.today()
    if montant_paye >= montant_du:
        return "paye"
    seuil_retard = date_limite or date_ech
    if aujourdhui > seuil_retard:
        return "en_retard"
    if montant_paye > 0:
        return "partiel"
    return "en_attente"


LIBELLES_STATUT = {
    "paye": "Payé",
    "partiel": "Partiel",
    "en_attente": "En attente",
    "en_retard": "En retard",
}


async def echeances_detail(db: AsyncSession, agence_id: str, *,
                           periode: str | None = None, statut: str | None = None,
                           locataire_id: str | None = None, bail_id: str | None = None,
                           proprietaire_id: str | None = None, unite_id: str | None = None,
                           aujourdhui: date | None = None) -> list[dict]:
    """Vue enrichie des échéances avec locataire, bien, montants et statut calculé."""
    aujourdhui = aujourdhui or date.today()
    paye_sub = (
        select(Paiement.echeance_id, func.sum(Paiement.montant).label("paye"))
        .where(Paiement.annule.is_(False), Paiement.type == "loyer")
        .group_by(Paiement.echeance_id)
        .subquery()
    )
    q = (
        select(Echeance, Bail, Unite, Immeuble, Locataire,
               func.coalesce(paye_sub.c.paye, 0).label("montant_paye"))
        .join(Bail, Echeance.bail_id == Bail.id)
        .join(Unite, Bail.unite_id == Unite.id)
        .join(Immeuble, Unite.immeuble_id == Immeuble.id)
        .join(Locataire, Bail.locataire_id == Locataire.id)
        .outerjoin(paye_sub, paye_sub.c.echeance_id == Echeance.id)
        .where(Echeance.agence_id == agence_id)
    )
    if periode:
        q = q.where(Echeance.periode == periode)
    if locataire_id:
        q = q.where(Bail.locataire_id == locataire_id)
    if bail_id:
        q = q.where(Echeance.bail_id == bail_id)
    if unite_id:
        q = q.where(Bail.unite_id == unite_id)
    if proprietaire_id:
        q = q.where(Immeuble.proprietaire_id == proprietaire_id)
    q = q.order_by(Echeance.periode.desc(), Locataire.nom)
    rows = (await db.execute(q)).all()
    out: list[dict] = []
    for ech, bail, unite, imm, loc, paye in rows:
        paye = int(paye or 0)
        st = statut_echeance(ech.montant_du, paye, ech.date_echeance, aujourdhui, ech.date_limite)
        if statut and statut != st:
            continue
        out.append({
            "id": ech.id, "periode": ech.periode, "periode_libelle": periode_libelle(ech.periode),
            "montant_du": ech.montant_du, "montant_paye": paye,
            "reste": max(0, ech.montant_du - paye), "statut": st,
            "statut_libelle": LIBELLES_STATUT[st],
            "date_echeance": ech.date_echeance.isoformat(),
            "date_limite": ech.date_limite.isoformat() if ech.date_limite else None,
            "bail_id": bail.id, "unite_id": unite.id, "immeuble_id": imm.id,
            "locataire_id": loc.id, "locataire_nom": loc.nom, "locataire_telephone": loc.telephone_whatsapp or loc.telephone,
            "unite_nom": unite.nom, "immeuble_nom": imm.nom, "bien_libelle": f"{unite.nom} — {imm.nom}",
            "loyer": bail.loyer, "charges": bail.charges,
        })
    return out


async def dashboard(db: AsyncSession, agence_id: str, proprietaire_id: str | None = None,
                    aujourdhui: date | None = None) -> dict:
    """Solde du mois + retards (toutes périodes) + occupation (écran d'accueil, F8)."""
    aujourdhui = aujourdhui or date.today()
    await ensure_echeances_agence(db, agence_id)
    periode = periode_courante(aujourdhui)
    ech = await echeances_detail(db, agence_id, periode=periode, proprietaire_id=proprietaire_id, aujourdhui=aujourdhui)
    # les retards portent sur TOUTES les périodes : un loyer de juillet impayé reste en retard en septembre
    retards = await echeances_detail(db, agence_id, statut="en_retard", proprietaire_id=proprietaire_id, aujourdhui=aujourdhui)
    encaisse = sum(e["montant_paye"] for e in ech)
    en_retard = sum(e["reste"] for e in retards)
    en_attente = sum(e["reste"] for e in ech if e["statut"] in ("en_attente", "partiel"))
    # occupation
    q_unites = select(Unite).join(Immeuble, Unite.immeuble_id == Immeuble.id).where(Unite.agence_id == agence_id)
    if proprietaire_id:
        q_unites = q_unites.where(Immeuble.proprietaire_id == proprietaire_id)
    unites = (await db.execute(q_unites)).scalars().all()
    occupees = sum(1 for u in unites if u.statut == "occupe")
    du_jour = [e for e in ech if e["date_echeance"] == date.today().isoformat() and e["statut"] != "paye"]
    return {
        "periode": periode,
        "periode_libelle": periode_libelle(periode),
        "encaisse": encaisse,
        "en_attente": en_attente,
        "en_retard": en_retard,
        "nb_en_retard": len(retards),
        "nb_echeances": len(ech),
        "occupation": {"occupees": occupees, "total": len(unites),
                       "taux": round(occupees / len(unites) * 100) if unites else None},
        "echeances_du_jour": len(du_jour),
    }


def echeancier_caution(bail: Bail, regles: Regles) -> list[dict]:
    """Échéancier de versement de la caution conforme au décret 2023-382 :
    1 mois (loyer) à l'entrée en jouissance, le reliquat étalé sur 12 mois (1/12e par mois).
    Retourne une liste de lignes {libelle, montant, date} — indicatif, jamais bloquant."""
    loyer = bail.loyer or 0
    cible = min(bail.caution or 0, loyer * (regles.caution_max_mois or 2)) if regles.caution_max_mois else (bail.caution or 0)
    if cible <= 0:
        return []
    lignes = [{"libelle": "À l'entrée en jouissance (1 mois)", "montant": min(loyer, cible),
               "date": bail.date_debut.isoformat()}]
    reliquat = cible - min(loyer, cible)
    if reliquat > 0:
        nb = regles.caution_etalee_mois or 12
        part = -(-reliquat // nb)  # arrondi supérieur en entiers FCFA
        for i in range(nb):
            m = min(part, reliquat)
            if m <= 0:
                break
            annee = bail.date_debut.year + (bail.date_debut.month + i) // 12
            mois = (bail.date_debut.month + i) % 12 + 1
            lignes.append({"libelle": f"Étalement {i + 1}/{nb}", "montant": int(m),
                           "date": f"{annee:04d}-{mois:02d}-05"})
            reliquat -= m
    return lignes


async def situation_caution(db: AsyncSession, bail: Bail, regles: Regles | None = None) -> dict:
    """Situation complète de la caution d'un bail : versée, prévue, reste, restitution."""
    versements = (await db.execute(
        select(Paiement).where(Paiement.bail_id == bail.id, Paiement.type == "caution",
                               Paiement.annule.is_(False)))).scalars().all()
    verse = sum(p.montant for p in versements)
    verse = max(0, verse)
    regles = regles or await regles_agence(db, bail.agence_id)
    echeancier = echeancier_caution(bail, regles)
    retenue = bail.caution_retenue or 0
    rembourse_le = bail.caution_rembourse_le
    a_restituer = max(0, verse - retenue)
    # pratique courante : restitution dans le mois qui suit la remise des clés (2 mois si retenues)
    date_limite = None
    if bail.date_fin and not rembourse_le:
        nb_mois = 2 if retenue > 0 else 1
        y, m = (bail.date_fin.year + 1, 1) if bail.date_fin.month + nb_mois > 12 else (bail.date_fin.year, bail.date_fin.month + nb_mois)
        import calendar as _cal
        date_limite = date(y, m, min(bail.date_fin.day, _cal.monthrange(y, m)[1]))
    if rembourse_le or a_restituer == 0:
        statut = "restituee" if rembourse_le else ("aucune" if verse == 0 else "soldee")
    elif verse < (bail.caution or 0):
        statut = "partielle"
    else:
        statut = "a_restituer"
    return {
        "prevue": bail.caution or 0, "versee": verse, "reste_a_verser": max(0, (bail.caution or 0) - verse),
        "retenue": retenue, "retenue_motif": bail.caution_retenue_motif or "",
        "rembourse_le": rembourse_le.isoformat() if rembourse_le else None,
        "a_restituer": a_restituer,
        "date_limite_restitution": date_limite.isoformat() if date_limite else None,
        "en_retard_restitution": bool(date_limite and date_limite < date.today()),
        "statut": statut, "echeancier": echeancier,
    }


async def calculer_notifications(db: AsyncSession, agence_id: str) -> list[dict]:
    """Notifications pour la cloche (actions essentielles) — calculées, jamais stockées."""
    from datetime import timedelta
    aujourdhui = date.today()
    out: list[dict] = []
    regles = await regles_agence(db, agence_id)
    # 1) retards (toutes périodes)
    retards = await echeances_detail(db, agence_id, statut="en_retard")
    if retards:
        total = sum(e["reste"] for e in retards)
        out.append({"cle": "retards", "gravite": "alerte", "nombre": len(retards),
                    "titre": "Loyers en retard",
                    "detail": f"{len(retards)} échéance(s) · {total:,} FCFA à recouvrer".replace(",", " "),
                    "lien": "#/relances"})
    # 2) loyers attendus aujourd'hui / échéances du mois non soldées
    pc = periode_courante()
    ech_mois = await echeances_detail(db, agence_id, periode=pc)
    du_jour = [e for e in ech_mois if e["date_echeance"] == aujourdhui.isoformat() and e["statut"] != "paye"]
    if du_jour:
        out.append({"cle": "attendus_jour", "gravite": "info", "nombre": len(du_jour),
                    "titre": "Loyers attendus aujourd'hui",
                    "detail": f"{len(du_jour)} locataire(s) à encaisser ({sum(e['reste'] for e in du_jour):,} FCFA)".replace(",", " "),
                    "lien": "#/encaisser"})
    # 3) cautions à restituer (baux terminés, caution versée non restituée)
    baux_finis = (await db.execute(
        select(Bail).where(Bail.agence_id == agence_id, Bail.statut == "termine"))).scalars().all()
    cautions = []
    for b in baux_finis:
        sc = await situation_caution(db, b, regles)
        if sc["statut"] == "a_restituer":
            cautions.append((b, sc))
    if cautions:
        en_retard = [x for x in cautions if x[1]["en_retard_restitution"]]
        detail = f"{len(cautions)} caution(s) à restituer"
        if en_retard:
            detail += f" dont {len(en_retard)} au-delà du délai"
        out.append({"cle": "cautions", "gravite": "alerte" if en_retard else "info",
                    "nombre": len(cautions), "titre": "Cautions à restituer", "detail": detail,
                    "lien": "#/biens"})
    # 4) mandats de gestion arrivant à échéance (60 jours) ou expirés
    props = (await db.execute(select(Proprietaire).where(Proprietaire.agence_id == agence_id))).scalars().all()
    mandats = [p for p in props if p.mandat_fin and p.mandat_fin <= aujourdhui + timedelta(days=60)]
    if mandats:
        expires = [p for p in mandats if p.mandat_fin < aujourdhui]
        out.append({"cle": "mandats", "gravite": "alerte" if expires else "info", "nombre": len(mandats),
                    "titre": "Mandats de gestion",
                    "detail": f"{len(mandats)} mandat(s) à renouveler" + (f" dont {len(expires)} expiré(s)" if expires else ""),
                    "lien": "#/rapports"})
    # 5) baux actifs arrivant à échéance dans 60 jours (date_fin connue)
    baux_actifs = (await db.execute(
        select(Bail).where(Bail.agence_id == agence_id, Bail.statut == "actif",
                           Bail.date_fin.is_not(None)))).scalars().all()
    proches = [b for b in baux_actifs if b.date_fin and aujourdhui <= b.date_fin <= aujourdhui + timedelta(days=60)]
    if proches:
        out.append({"cle": "baux_fin", "gravite": "info", "nombre": len(proches),
                    "titre": "Baux arrivant à échéance",
                    "detail": f"{len(proches)} bail(s) se terminent dans les 60 jours",
                    "lien": "#/biens"})
    return out


async def rapport_proprietaire(db: AsyncSession, agence_id: str, proprietaire_id: str, periode: str) -> dict:
    """Loyers encaissés, commission, montant à reverser (F8)."""
    prop = await db.get(Proprietaire, proprietaire_id)
    if not prop or prop.agence_id != agence_id:
        raise KeyError("propriétaire inconnu")
    ech = await echeances_detail(db, agence_id, periode=periode, proprietaire_id=proprietaire_id)
    par_bien: dict[str, dict] = {}
    for e in ech:
        key = e["immeuble_id"]
        b = par_bien.setdefault(key, {
            "immeuble": e["immeuble_nom"], "immeuble_id": e["immeuble_id"],
            "nb_unites": 0, "du": 0, "paye": 0, "reste": 0, "unites": [],
        })
        if e["unite_id"] not in [u["id"] for u in b["unites"]]:
            b["unites"].append({"id": e["unite_id"], "nom": e["unite_nom"]})
            b["nb_unites"] += 1
        b["du"] += e["montant_du"]
        b["paye"] += e["montant_paye"]
        b["reste"] += e["reste"]
    encaisse = sum(e["montant_paye"] for e in ech)
    commission = round(encaisse * (prop.commission_pct or 0) / 100)
    return {
        "periode": periode,
        "periode_libelle": periode_libelle(periode),
        "proprietaire": {"id": prop.id, "nom": prop.nom, "telephone": prop.telephone,
                         "commission_pct": prop.commission_pct,
                         "mandat_debut": prop.mandat_debut.isoformat() if prop.mandat_debut else None,
                         "mandat_fin": prop.mandat_fin.isoformat() if prop.mandat_fin else None},
        "encaisse": encaisse,
        "du": sum(e["montant_du"] for e in ech),
        "reste_a_encaisser": sum(e["reste"] for e in ech),
        "nb_en_retard": sum(1 for e in ech if e["statut"] == "en_retard"),
        "commission": commission,
        "a_reverser": encaisse - commission,
        "biens": list(par_bien.values()),
    }
