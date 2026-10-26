"""Modèles de données (§6 du cahier des charges).

Conventions clés :
- Tous les identifiants sont des UUID (String 36) générés côté appareil -> mode hors ligne F10.
- Les montants sont des entiers en FCFA (pas de centimes au Sénégal).
- Les paiements ne se suppriment jamais : annulation par écriture motivée (F5/F11).
- `updated_at` sert d'arbitre "dernière version gagne" pour la synchronisation multi-appareils.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def new_uuid() -> str:
    return str(uuid.uuid4())

def utcnow() -> datetime:
    # UTC naïf : SQLite ne conserve pas le fuseau ; tout le code utilise l'UTC serveur.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Agence(Base):
    __tablename__ = "agences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    nom: Mapped[str] = mapped_column(String(200), default="")
    telephone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    adresse: Mapped[str] = mapped_column(String(300), default="")
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tampon_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remuneration_gerant_pct: Mapped[int] = mapped_column(Integer, default=10)  # accord agence-gerant : 10 ou 15 %
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str | None] = mapped_column(ForeignKey("agences.id"), nullable=True)
    proprietaire_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # si rôle propriétaire
    nom: Mapped[str] = mapped_column(String(200), default="")
    telephone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="responsable")  # responsable | employe | proprietaire
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    device_label: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    telephone: Mapped[str] = mapped_column(String(30), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(20), default="login")  # login | inscription
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Regles(Base):
    """Règles locales configurables par agence (F13) — jamais codées en dur."""
    __tablename__ = "regles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), unique=True, index=True)
    caution_max_mois: Mapped[int] = mapped_column(Integer, default=2)          # décret 2023-382
    caution_etalee_mois: Mapped[int] = mapped_column(Integer, default=12)      # reste étalé en 12 fois
    terme_paiement: Mapped[str] = mapped_column(String(10), default="debut")   # debut (d'avance, défaut terrain) | fin (terme échu, décret)
    jour_limite_paiement: Mapped[int] = mapped_column(Integer, default=10)     # retard au-delà du 10 du mois
    frais_agence_max_mois: Mapped[float] = mapped_column(Float, default=0.5)   # ½ mois <= 500 000 FCFA
    revision_periodicite_mois: Mapped[int] = mapped_column(Integer, default=36)
    rappel_enregistrement_jours: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ModeleMessage(Base):
    __tablename__ = "modeles_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="relance")  # relance | quittance | rapport
    contenu: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Proprietaire(Base):
    __tablename__ = "proprietaires"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    telephone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    mode_reversement: Mapped[str] = mapped_column(String(30), default="mensuel")  # mensuel | trimestre | autre
    commission_pct: Mapped[float] = mapped_column(Float, default=0.0)  # % de l'agence sur les loyers
    # Mandat de gestion : contrat agence <-> propriétaire (relation à trois : gérant-agence-propriétaire)
    mandat_debut: Mapped[date | None] = mapped_column(Date, nullable=True)
    mandat_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Immeuble(Base):
    __tablename__ = "immeubles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    proprietaire_id: Mapped[str] = mapped_column(ForeignKey("proprietaires.id"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    adresse: Mapped[str] = mapped_column(String(300), default="")
    quartier: Mapped[str] = mapped_column(String(100), default="")
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Unite(Base):
    """Unité de location : appartement, chambre, local… Un bien seul = un immeuble à 1 unité (F3)."""
    __tablename__ = "unites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    immeuble_id: Mapped[str] = mapped_column(ForeignKey("immeubles.id"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30), default="chambre")  # appartement|maison|chambre|local|bureau
    loyer: Mapped[int] = mapped_column(Integer, default=0)
    charges: Mapped[int] = mapped_column(Integer, default=0)
    statut: Mapped[str] = mapped_column(String(10), default="libre")  # occupe | libre
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Locataire(Base):
    __tablename__ = "locataires"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    telephone: Mapped[str] = mapped_column(String(30), default="")
    telephone_whatsapp: Mapped[str] = mapped_column(String(30), default="")
    piece_identite_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Bail(Base):
    __tablename__ = "baux"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    unite_id: Mapped[str] = mapped_column(ForeignKey("unites.id"), index=True)
    locataire_id: Mapped[str] = mapped_column(ForeignKey("locataires.id"), index=True)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    loyer: Mapped[int] = mapped_column(Integer, default=0)
    charges: Mapped[int] = mapped_column(Integer, default=0)
    jour_echeance: Mapped[int] = mapped_column(Integer, default=5)  # jour du mois
    caution: Mapped[int] = mapped_column(Integer, default=0)
    duree_type: Mapped[str] = mapped_column(String(20), default="triennale")  # triennale | indeterminee | autre
    statut: Mapped[str] = mapped_column(String(10), default="actif")  # actif | termine
    motif_fin: Mapped[str] = mapped_column(Text, default="")
    enregistre_statut: Mapped[str] = mapped_column(String(15), default="non")  # non | en_cours | fait
    enregistre_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Restitution de la caution (décret 2023-382 : 2 mois max, 1 mois à l'entrée puis 1/12e par mois)
    caution_rembourse_le: Mapped[date | None] = mapped_column(Date, nullable=True)
    caution_retenue: Mapped[int] = mapped_column(Integer, default=0)
    caution_retenue_motif: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class LoyerHistorique(Base):
    """Historique du loyer par bail (F13) : montant, date d'effet, motif."""
    __tablename__ = "loyer_historique"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(String(36), index=True)
    bail_id: Mapped[str] = mapped_column(ForeignKey("baux.id"), index=True)
    loyer: Mapped[int] = mapped_column(Integer)
    date_effet: Mapped[date] = mapped_column(Date)
    motif: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Echeance(Base):
    __tablename__ = "echeances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    bail_id: Mapped[str] = mapped_column(ForeignKey("baux.id"), index=True)
    periode: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    montant_du: Mapped[int] = mapped_column(Integer, default=0)
    date_echeance: Mapped[date] = mapped_column(Date)
    date_limite: Mapped[date | None] = mapped_column(Date, nullable=True)  # dernier jour pour payer (ex. le 10)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("bail_id", "periode", name="uq_echeance_bail_periode"),)


class Paiement(Base):
    """Append-only : jamais modifié ni supprimé. Une erreur => écriture d'annulation motivée."""
    __tablename__ = "paiements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    echeance_id: Mapped[str | None] = mapped_column(ForeignKey("echeances.id"), index=True, nullable=True)
    bail_id: Mapped[str] = mapped_column(ForeignKey("baux.id"), index=True)
    type: Mapped[str] = mapped_column(String(15), default="loyer")  # loyer | annulation | caution | frais_agence
    montant: Mapped[int] = mapped_column(Integer)  # négatif pour une écriture d'annulation
    mode: Mapped[str] = mapped_column(String(20), default="wave")  # wave|orange_money|especes|virement|cheque|autre
    date_paiement: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(200), default="")
    motif_annulation: Mapped[str] = mapped_column(Text, default="")
    annule: Mapped[bool] = mapped_column(Boolean, default=False)
    annule_par_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # id de l'écriture d'annulation
    preuve_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    saisi_par: Mapped[str | None] = mapped_column(String(36), nullable=True)  # user_id
    device_id: Mapped[str] = mapped_column(String(100), default="")
    client_uuid: Mapped[str] = mapped_column(String(64), default="", index=True)  # idempotence hors ligne
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Recu(Base):
    __tablename__ = "recus"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    paiement_id: Mapped[str | None] = mapped_column(ForeignKey("paiements.id"), unique=True, nullable=True)
    bail_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="quittance")  # quittance|caution|frais_agence|decharge
    numero: Mapped[str] = mapped_column(String(40), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # lien public de vérification
    fichier_path: Mapped[str] = mapped_column(String(500), default="")
    empreinte: Mapped[str] = mapped_column(String(128), default="")  # sha256 du PDF
    annule: Mapped[bool] = mapped_column(Boolean, default=False)
    contenu: Mapped[str] = mapped_column(Text, default="{}")  # résumé JSON (pour vérification publique)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("agence_id", "numero", name="uq_recu_numero_agence"),)


class CompteurRecu(Base):
    """Numérotation séquentielle par agence et par année : Q-2026-00001."""
    __tablename__ = "compteurs_recu"
    agence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    annee: Mapped[int] = mapped_column(Integer, primary_key=True)
    dernier: Mapped[int] = mapped_column(Integer, default=0)


class Partage(Base):
    """Fichier partageable par lien public (rapports propriétaire notamment)."""
    __tablename__ = "partages"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    agence_id: Mapped[str] = mapped_column(String(36), index=True)
    chemin: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    """Document numérisé rattaché à une fiche (F12)."""
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    attache_type: Mapped[str] = mapped_column(String(20), index=True)  # bail|locataire|unite|immeuble|proprietaire|paiement
    attache_id: Mapped[str] = mapped_column(String(36), index=True)
    type_document: Mapped[str] = mapped_column(String(40), default="autre")
    # bail_signe|piece_identite|titre_propriete|etat_des_lieux|recu_papier|justificatif|facture_travaux|enregistrement|autre
    nom: Mapped[str] = mapped_column(String(300), default="")
    fichier_path: Mapped[str] = mapped_column(String(500))
    mimetype: Mapped[str] = mapped_column(String(100), default="application/pdf")
    poids: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=1)
    saisi_par: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Relance(Base):
    __tablename__ = "relances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str] = mapped_column(ForeignKey("agences.id"), index=True)
    echeance_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    canal: Mapped[str] = mapped_column(String(20), default="whatsapp")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    """Journal d'audit : qui a fait quoi, quand, depuis quel appareil (F11)."""
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agence_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_nom: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[str] = mapped_column(String(60))
    objet_type: Mapped[str] = mapped_column(String(30), default="")
    objet_id: Mapped[str] = mapped_column(String(64), default="")
    objet_libelle: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[str] = mapped_column(Text, default="{}")
    device_id: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


Index("ix_audit_agence_date", AuditLog.agence_id, AuditLog.created_at)
