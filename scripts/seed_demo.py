"""Jeu de données de démonstration : agence, propriétaires, immeubles, locataires, baux, échéances, paiements.

Usage :  python3 scripts/seed_demo.py
Le compte de démonstration se connecte avec le téléphone ci-dessous (code OTP affiché à l'écran).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (Agence, Bail, Immeuble, Locataire, LoyerHistorique,  # noqa: E402
                        ModeleMessage, Proprietaire, Regles, Unite, User)
from app.logique import ensure_echeances_agence, regles_agence  # noqa: E402
from app.routers.auth import MODELE_RELANCE_DEFAUT, MODELE_QUITTANCE_DEFAUT  # noqa: E402
from app.security import utc_naif  # noqa: E402

TEL_DEMO = "+221770000000"  # numéro du compte démo


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        existe = (await db.execute(User.__table__.select().where(User.telephone == TEL_DEMO))).first()
        if existe:
            print("Les données de démonstration existent déjà (compte " + TEL_DEMO + ").")
            print("Pour repartir de zéro : rm -f data/app.db puis relancer.")
            return

        agence = Agence(nom="Immo Mermoz Gestion", telephone=TEL_DEMO,
                        email="contact@immermoz.sn", adresse="Cité Mermoz, Dakar")
        db.add(agence)
        await db.flush()
        db.add(Regles(agence_id=agence.id))
        db.add(ModeleMessage(agence_id=agence.id, type="relance", contenu=MODELE_RELANCE_DEFAUT))
        db.add(ModeleMessage(agence_id=agence.id, type="quittance", contenu=MODELE_QUITTANCE_DEFAUT))
        db.add(User(telephone=TEL_DEMO, nom="Moussa Diop", role="responsable", agence_id=agence.id))

        # ---------------- propriétaires
        props = []
        # mandats de gestion : contrat agence <-> propriétaire (v1.2)
        for nom, tel, commission, m_debut, m_fin in [
                ("Ousmane Sow", "+221781112233", 5, date(2024, 1, 15), date(2027, 1, 14)),
                ("Mariama Fall", "+221782223344", 8, date(2023, 6, 1), date(2026, 9, 30))]:
            p = Proprietaire(agence_id=agence.id, nom=nom, telephone=tel, commission_pct=commission,
                             mandat_debut=m_debut, mandat_fin=m_fin)
            db.add(p)
            props.append(p)
        await db.flush()

        # ---------------- immeubles + unités
        imm1 = Immeuble(agence_id=agence.id, proprietaire_id=props[0].id, nom="Immeuble Mermoz",
                        quartier="Mermoz", adresse="Rue 10 x Corniche Ouest")
        imm2 = Immeuble(agence_id=agence.id, proprietaire_id=props[1].id, nom="Villa Almadies",
                        quartier="Almadies", adresse="Route de Ngor")
        db.add(imm1)
        db.add(imm2)
        await db.flush()

        unites = []
        for nom, typ, loyer, charges in [
            ("Appartement B1", "appartement", 350000, 15000),
            ("Appartement B2", "appartement", 300000, 15000),
            ("Chambre 3", "chambre", 90000, 5000),
            ("Local commercial", "local", 450000, 0),
        ]:
            u = Unite(agence_id=agence.id, immeuble_id=imm1.id, nom=nom, type=typ,
                      loyer=loyer, charges=charges)
            db.add(u)
            unites.append(u)
        u5 = Unite(agence_id=agence.id, immeuble_id=imm2.id, nom="Villa complète",
                   type="maison", loyer=700000, charges=25000)
        db.add(u5)
        unites.append(u5)
        await db.flush()

        # ---------------- locataires
        locs = []
        for nom, tel in [("Aïssatou Ndiaye", "772223344"), ("Ibrahima Sarr", "763334455"),
                         ("Fatou Kane", "785556677"), ("Cheikh Gueye", "778889900"),
                         ("Sokhna Diallo", "770112233")]:
            l = Locataire(agence_id=agence.id, nom=nom, telephone="+221" + tel,
                          telephone_whatsapp="+221" + tel)
            db.add(l)
            locs.append(l)
        await db.flush()

        # ---------------- baux (certains anciens, pour voir des retards)
        def bail(unite, loc, mois_passe, loyer, charges, caution=0):
            debut = date.fromordinal(date.today().toordinal() - 30 * mois_passe)
            b = Bail(agence_id=agence.id, unite_id=unite.id, locataire_id=loc.id,
                     date_debut=debut, loyer=loyer, charges=charges, caution=caution)
            db.add(b)
            return b

        b1 = bail(unites[0], locs[0], 8, 350000, 15000, caution=350000)
        b2 = bail(unites[1], locs[1], 5, 300000, 15000, caution=600000)   # caution > 2 mois -> alerte
        b3 = bail(unites[2], locs[2], 14, 90000, 5000)
        b4 = bail(unites[3], locs[3], 3, 450000, 0, caution=900000)      # 2 mois : 1 versé à l'entrée + 1/12e/mois (décret)
        b5 = bail(unites[4], locs[4], 2, 700000, 25000, caution=700000)
        for u in unites:
            u.statut = "occupe"
        # un ancien locataire parti : caution versée non restituée (pour la démo restitution)
        b6 = bail(unites[2], locs[2], 26, 90000, 5000, caution=90000)    # ancien bail de Fatou
        b6.statut = "termine"
        b6.date_fin = date.fromordinal(date.today().toordinal() - 45)
        unites[2].statut = "occupe"  # Fatou a repris la Chambre 3 ensuite (b3)
        await db.flush()
        for b, loyer in [(b1, 350000), (b2, 300000), (b3, 90000), (b4, 450000), (b5, 700000)]:
            db.add(LoyerHistorique(agence_id=agence.id, bail_id=b.id, loyer=loyer,
                                   date_effet=b.date_debut, motif="Bail initial"))
        await db.commit()

        # ---------------- échéances + paiements réalistes
        await ensure_echeances_agence(db, agence.id)
        from app.models import Echeance, Paiement
        from app.services import enregistrer_paiement

        user = (await db.execute(
            User.__table__.select().where(User.telephone == TEL_DEMO))).first()
        user_obj = await db.get(User, user.id)

        echeances = (await db.execute(
            Echeance.__table__.select().where(Echeance.agence_id == agence.id))).all()
        modes = ["wave", "orange_money", "especes", "wave", "virement"]
        i = 0
        for ech in sorted(echeances, key=lambda e: (e.periode, e.bail_id)):
            # scénario réaliste : tout est payé sauf les 2 derniers mois pour 2 locataires
            if ech.periode >= "2026-08" and ech.bail_id in (b3.id, b4.id):
                if ech.periode == "2026-09" and ech.bail_id == b3.id:
                    # un paiement partiel
                    await enregistrer_paiement(db, user_obj, echeance_id=ech.id,
                                               montant=40000, mode="wave",
                                               date_paiement=date.today().isoformat(),
                                               client_uuid=f"seed-part-{ech.id[:8]}")
                continue
            await enregistrer_paiement(db, user_obj, echeance_id=ech.id,
                                       montant=ech.montant_du, mode=modes[i % len(modes)],
                                       date_paiement=ech.date_echeance.isoformat(),
                                       client_uuid=f"seed-{ech.id[:8]}")
            i += 1
        from datetime import timedelta
        # cautions : 1 mois à l'entrée + échéancier 1/12e (décret 2023-382) — b4 (Local commercial)
        for k, montant in enumerate([450000] + [37500] * 11):
            db.add(Paiement(agence_id=agence.id, bail_id=b4.id, type="caution", montant=montant,
                            mode="wave" if k == 0 else "especes",
                            date_paiement=b4.date_debut + timedelta(days=30 * k),
                            reference="Caution " + ("entrée" if k == 0 else f"1/12e {k}/11"),
                            saisi_par=user_obj.id))
        # ancien bail de Fatou : caution intégralement versée, jamais restituée
        db.add(Paiement(agence_id=agence.id, bail_id=b6.id, type="caution", montant=90000,
                        mode="especes", date_paiement=b6.date_debut, reference="Caution entrée",
                        saisi_par=user_obj.id))
        await db.commit()
        print("Données de démonstration créées ✔")
        print(f"Connexion démo : téléphone {TEL_DEMO} (code affiché à l'écran, mode démo).")


if __name__ == "__main__":
    asyncio.run(main())
