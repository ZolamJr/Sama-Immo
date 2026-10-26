"""Sérialisation des modèles vers l'API (dict JSON)."""
from __future__ import annotations

from datetime import date, datetime


def _d(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        # les datetimes base sont en UTC naïf -> suffixe Z pour un parsing JS correct
        return v.isoformat() + ("Z" if not v.isoformat().endswith(("Z", "+00:00")) else "")
    if isinstance(v, date):
        return v.isoformat()
    return v


def serializer(champs: list[str]):
    def _ser(obj) -> dict:
        out = {}
        for c in champs:
            v = getattr(obj, c, None)
            out[c] = _d(v)
        return out

    return _ser


ser_agence = serializer(["id", "nom", "telephone", "email", "adresse", "logo_path", "tampon_path", "created_at"])
ser_user = serializer(["id", "nom", "telephone", "role", "actif", "agence_id", "proprietaire_id", "created_at", "last_login_at"])
ser_proprietaire = serializer(["id", "nom", "telephone", "email", "mode_reversement", "commission_pct",
                               "mandat_debut", "mandat_fin", "created_at", "updated_at"])
ser_immeuble = serializer(["id", "proprietaire_id", "nom", "adresse", "quartier", "photo_path", "created_at", "updated_at"])
ser_unite = serializer(["id", "immeuble_id", "nom", "type", "loyer", "charges", "statut", "notes", "created_at", "updated_at"])
ser_locataire = serializer(["id", "nom", "telephone", "telephone_whatsapp", "piece_identite_path", "notes", "actif", "created_at", "updated_at"])
ser_bail = serializer(["id", "unite_id", "locataire_id", "date_debut", "date_fin", "loyer", "charges",
                       "jour_echeance", "caution", "duree_type", "statut", "motif_fin",
                       "enregistre_statut", "enregistre_date",
                       "caution_rembourse_le", "caution_retenue", "caution_retenue_motif",
                       "created_at", "updated_at"])
ser_paiement = serializer(["id", "echeance_id", "bail_id", "type", "montant", "mode", "date_paiement",
                          "reference", "motif_annulation", "annule", "annule_par_id", "preuve_path",
                          "saisi_par", "client_uuid", "created_at"])
ser_document = serializer(["id", "attache_type", "attache_id", "type_document", "nom", "mimetype", "poids", "pages", "created_at"])
