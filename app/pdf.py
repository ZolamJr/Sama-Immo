"""Génération des PDF : quittances, reçus, rapports propriétaire (F6, F8) avec QR de vérification."""
from __future__ import annotations

import hashlib
import io
from datetime import date
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Image, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from .config import FILES_DIR, settings
from .nombres import montant_fcfa_lettres

BLEU = colors.HexColor("#0b5394")
BLEU_CLAIR = colors.HexColor("#eaf3fb")
GRIS = colors.HexColor("#666666")

MENTION = "Document généré par l'application — modèle indicatif. Vérifiable via le QR code."


def _san(s: str) -> str:
    """Helvetica (Latin-1) : remplace les caractères hors Latin-1."""
    remplacements = {"—": "-", "–": "-", "…": "...", "'": "'", "\u2019": "'", "\u00a0": " ",
                     "\u2022": "-", "\u20ac": "EUR"}
    for k, v in remplacements.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _qr_image(url: str, taille: int = 26 * mm):
    img = qrcode.make(url, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=taille, height=taille)


def _img_si_presente(chemin: str | None, largeur: int = 40 * mm, hauteur_max: int = 18 * mm):
    if not chemin:
        return None
    p = Path(chemin)
    if not p.exists():
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(p) as im:
            w, h = im.size
        ratio = w / h
        larg = min(largeur, hauteur_max * ratio)
        return Image(str(p), width=larg, height=larg / ratio)
    except Exception:
        return None


def _entete(story, agence: dict):
    logo = _img_si_presente(agence.get("logo_path"), largeur=20 * mm, hauteur_max=20 * mm)
    coords = Paragraph(
        f"<b>{_san(agence.get('nom', ''))}</b><br/>"
        f"{_san(agence.get('adresse', ''))}<br/>"
        f"Tél : {_san(agence.get('telephone', ''))}"
        + (f"<br/>{_san(agence.get('email', ''))}" if agence.get("email") else ""),
        ParagraphStyle("coords", fontName="Helvetica", fontSize=9, textColor=GRIS, leading=12),
    )
    if logo:
        t = Table([[logo, coords]], colWidths=[24 * mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(t)
    else:
        story.append(coords)
    story.append(Spacer(1, 4 * mm))


def _pied(story, empreinte: str | None, url_verif: str | None):
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=0.6))
    story.append(Spacer(1, 2 * mm))
    lignes = [MENTION]
    if empreinte:
        lignes.append(f"Empreinte SHA-256 : {empreinte[:32]}…")
    if url_verif:
        lignes.append(f"Vérification en ligne : {_san(url_verif)}")
    story.append(Paragraph(
        "<br/>".join(_san(x) for x in lignes),
        ParagraphStyle("pied", fontName="Helvetica", fontSize=7, textColor=GRIS, leading=9, alignment=1),
    ))


def _styles() -> dict:
    base = dict(fontName="Helvetica", fontSize=10, leading=14)
    return {
        "titre": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, textColor=BLEU,
                                alignment=1, spaceAfter=2),
        "sous": ParagraphStyle("s", fontName="Helvetica", fontSize=10, textColor=GRIS, alignment=1),
        "corps": ParagraphStyle("c", **base),
        "gros": ParagraphStyle("g", fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#1a1a1a"),
                               leading=17),
        "italique": ParagraphStyle("i", fontName="Helvetica-Oblique", fontSize=9.5, textColor=GRIS),
        "section": ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=11, textColor=BLEU,
                                  spaceBefore=6, spaceAfter=2),
    }


def _signature_tampon(agence: dict) -> Table | None:
    """Bloc signature du gérant + tampon de l'agence, apposés automatiquement (F6)."""
    sig = _img_si_presente(agence.get("signature_path"), largeur=38 * mm, hauteur_max=14 * mm)
    tampon = _img_si_presente(agence.get("tampon_path"), largeur=30 * mm, hauteur_max=30 * mm)
    if not sig and not tampon:
        return None
    cell_g = [sig] if sig else [Spacer(1, 1)]
    cell_d = [tampon] if tampon else [Spacer(1, 1)]
    t = Table([[cell_g, cell_d]], colWidths=[60 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _build(doc_story, chemin: str) -> str:
    """Construit le PDF et retourne son empreinte SHA-256."""
    FILES_DIR.joinpath("recus").mkdir(parents=True, exist_ok=True)
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        chemin, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="Reçu", author=settings.app_name,
    )
    doc.build(doc_story)
    data = Path(chemin).read_bytes()
    return hashlib.sha256(data).hexdigest()


def generer_recu_pdf(chemin: str, *, recu_type: str, numero: str, url_verif: str,
                     agence: dict, lignes: list[dict], blocs: list, annule: bool = False) -> str:
    """Générateur commun des reçus.
    - lignes : tableau [label, valeur] du détail (loyer/charges/total…)
    - blocs  : paragraphes du corps (déclarations)
    """
    style = _styles()
    story: list = []
    _entete(story, agence)
    titres = {
        "quittance": "QUITTANCE DE LOYER",
        "caution": "REÇU DE CAUTION",
        "frais_agence": "REÇU DE FRAIS D'AGENCE",
        "decharge": "DÉCHARGE DE REMISE DE CLÉS",
        "restitution_caution": "REÇU DE RESTITUTION DE CAUTION",
    }
    story.append(Paragraph(_san(titres.get(recu_type, "REÇU")), style["titre"]))
    story.append(Paragraph(f"N° {_san(numero)} — Émis le {date.today().strftime('%d/%m/%Y')}", style["sous"]))
    story.append(Spacer(1, 5 * mm))
    for b in blocs:
        # les blocs peuvent être du texte simple -> Paragraph avec le style corps
        story.append(Paragraph(b, style["corps"]) if isinstance(b, str) else b)
        story.append(Spacer(1, 3 * mm))
    story.append(Spacer(1, 3 * mm))
    tbl = Table(lignes, colWidths=[65 * mm, None])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), BLEU),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Fait à Dakar, le " + date.today().strftime("%d/%m/%Y")
                           + " — Signature du gérant et tampon :", style["corps"]))
    story.append(Spacer(1, 2 * mm))
    bloc_sig = _signature_tampon(agence)
    if bloc_sig:
        story.append(bloc_sig)
    # QR de vérification à droite du pied
    story.append(Spacer(1, 6 * mm))
    qr = _qr_image(url_verif)
    note = Paragraph("Scanner pour vérifier<br/>l'authenticité du reçu",
                     ParagraphStyle("qr", fontName="Helvetica", fontSize=7, textColor=GRIS, alignment=1, leading=9))
    t = Table([[qr]], colWidths=[30 * mm])
    t.setStyle(TableStyle([("ALIGN", (0, 0), (0, 0), "CENTER")]))
    story.append(Table([[t, note]], colWidths=[34 * mm, None],
                       style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0)])))
    if annule:
        story.insert(2, Paragraph('<font color="#cc0000" size="26"><b>*** ANNULÉ ***</b></font>',
                                  ParagraphStyle("annul", alignment=1, leading=30)))
    # mention légale (§13.2) + lien de vérification en pied de page
    _pied(story, None, url_verif)
    empreinte = _build(story, chemin)
    return empreinte


def generer_rapport_pdf(chemin: str, *, rapport: dict, agence: dict, url_verif: str) -> str:
    style = _styles()
    story: list = []
    _entete(story, agence)
    story.append(Paragraph("RAPPORT DE GESTION", style["titre"]))
    story.append(Paragraph(
        f"{_san(rapport['periode_libelle'])} — Propriétaire : {_san(rapport['proprietaire']['nom'])}",
        style["sous"]))
    story.append(Spacer(1, 5 * mm))
    syn = [
        ["Loyers encaissés", f"{_fmt(rapport['encaisse'])} FCFA"],
        ["Loyers attendus", f"{_fmt(rapport['du'])} FCFA"],
        ["Reste à encaisser", f"{_fmt(rapport['reste_a_encaisser'])} FCFA"],
        [f"Commission agence ({rapport['proprietaire']['commission_pct']}%)", f"{_fmt(rapport['commission'])} FCFA"],
        ["Montant à reverser", f"{_fmt(rapport['a_reverser'])} FCFA"],
    ]
    tbl = Table(syn, colWidths=[80 * mm, None])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (0, -1), BLEU),
        ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    if rapport["biens"]:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("Détail par bien", style["section"]))
        head = [["Bien", "Unités", "Attendu", "Encaissé", "Reste"]]
        rows = [[_san(b["immeuble"]), str(b["nb_unites"]), _fmt(b["du"]), _fmt(b["paye"]), _fmt(b["reste"])]
                for b in rapport["biens"]]
        t2 = Table(head + rows, colWidths=[55 * mm, 16 * mm, 30 * mm, 30 * mm, 30 * mm])
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), BLEU),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t2)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Ce rapport récapitule les encaissements enregistrés pour la période. "
        "Les paiements sont horodatés et ne peuvent pas être supprimés.", style["corps"]))
    _pied(story, None, url_verif)
    return _build(story, chemin)


# ================================================================ Documents de gestion (v1.2)

def _table_generale(head: list, rows: list, largeurs: list, aligns_droite: tuple = ()):
    t = Table([head] + rows, colWidths=largeurs, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), BLEU),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for col in aligns_droite:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _bloc_signature(story, agence: dict):
    """Signature du gérant + tampon, apposés sur les documents de gestion."""
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Fait à Dakar, le " + date.today().strftime("%d/%m/%Y")
                           + " — Le gérant :", _styles()["corps"]))
    bloc = _signature_tampon(agence)
    if bloc:
        story.append(bloc)


def generer_etat_loyers_pdf(chemin: str, *, periode_libelle: str, echeances: list[dict],
                            totaux: dict, agence: dict) -> str:
    """État des loyers du mois (bordereau récapitulatif)."""
    style = _styles()
    story: list = []
    _entete(story, agence)
    story.append(Paragraph("ÉTAT DES LOYERS DU MOIS", style["titre"]))
    story.append(Paragraph(_san(periode_libelle), style["sous"]))
    story.append(Spacer(1, 4 * mm))
    head = ["Locataire", "Bien", "Période", "Dû", "Payé", "Statut"]
    rows = [[_san(e["locataire_nom"]), _san(e["bien_libelle"]), _san(e["periode_libelle"]),
             _fmt(e["montant_du"]), _fmt(e["montant_paye"]), _san(e["statut_libelle"])]
            for e in echeances]
    story.append(_table_generale(head, rows, [34 * mm, 52 * mm, 24 * mm, 22 * mm, 22 * mm, 18 * mm],
                                 aligns_droite=(3, 4)))
    story.append(Spacer(1, 4 * mm))
    syn = [["Total dû", _fmt(totaux["du"]) + " FCFA"],
           ["Total encaissé", _fmt(totaux["paye"]) + " FCFA"],
           ["Reste à encaisser", _fmt(totaux["reste"]) + " FCFA"]]
    t = Table(syn, colWidths=[60 * mm, None])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (0, -1), BLEU),
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    _bloc_signature(story, agence)
    _pied(story, None, None)
    return _build(story, chemin)


def generer_arrieres_pdf(chemin: str, *, retards: list[dict], totaux: int, agence: dict) -> str:
    """État des arriérés : toutes périodes, trié par ancienneté."""
    style = _styles()
    story: list = []
    _entete(story, agence)
    story.append(Paragraph("ÉTAT DES ARRIÉRÉS", style["titre"]))
    story.append(Paragraph(f"Au {date.today().strftime('%d/%m/%Y')} — toutes périodes", style["sous"]))
    story.append(Spacer(1, 4 * mm))
    head = ["Locataire", "Bien", "Période", "En retard depuis", "Reste dû"]
    rows = [[_san(e["locataire_nom"]), _san(e["bien_libelle"]), _san(e["periode_libelle"]),
             _san((e.get("date_limite") or e["date_echeance"])), _fmt(e["reste"])] for e in retards]
    story.append(_table_generale(head, rows, [36 * mm, 52 * mm, 26 * mm, 28 * mm, 26 * mm], aligns_droite=(4,)))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Total à recouvrer : {_fmt(totaux)} FCFA</b>", style["gros"]))
    story.append(Paragraph(
        "Document de travail pour les relances. Chaque relance envoyée est horodatée dans le journal d'activité.",
        style["italique"]))
    _bloc_signature(story, agence)
    _pied(story, None, None)
    return _build(story, chemin)


def generer_recap_locataire_pdf(chemin: str, *, loc: dict, baux: list[dict], paiements: list[dict],
                                agence: dict) -> str:
    """Fiche récapitulative d'un locataire : baux, échéances récentes, paiements."""
    style = _styles()
    story: list = []
    _entete(story, agence)
    story.append(Paragraph("FICHE LOCATAIRE", style["titre"]))
    story.append(Paragraph(_san(loc["nom"]), style["sous"]))
    story.append(Spacer(1, 4 * mm))
    ident = [["Téléphone", _san(loc.get("telephone") or "—")],
             ["WhatsApp", _san(loc.get("telephone_whatsapp") or loc.get("telephone") or "—")]]
    t = Table(ident, colWidths=[40 * mm, None])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (0, -1), BLEU),
                           ("FONTSIZE", (0, 0), (-1, -1), 10), ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BLEU_CLAIR]),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(t)
    for b in baux:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(f"Bail — {_san(b['unite_nom'])} ({_san(b['immeuble_nom'])})", style["section"]))
        lignes = [["Période", f"du {_san(b['date_debut'])}" + (f" au {_san(b['date_fin'])}" if b.get("date_fin") else " (en cours)")],
                  ["Loyer + charges", _fmt(b["loyer"] + b["charges"]) + " FCFA"],
                  ["Caution prévue", _fmt(b.get("caution") or 0) + " FCFA"],
                  ["Statut", _san(b.get("statut_libelle") or b.get("statut") or "")]]
        t2 = Table(lignes, colWidths=[45 * mm, None])
        t2.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (0, -1), BLEU),
                                ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
        story.append(t2)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Derniers paiements", style["section"]))
    head = ["Date", "Type", "Mode", "Montant"]
    rows = []
    for p in paiements[:18]:
        rows.append([_san(p["date"]), _san(p.get("type_libelle") or p.get("type") or ""),
                     _san(p.get("mode_libelle") or p.get("mode") or ""), _fmt(p["montant"])])
    story.append(_table_generale(head, rows, [26 * mm, 34 * mm, 34 * mm, 26 * mm], aligns_droite=(3,)))
    _bloc_signature(story, agence)
    _pied(story, None, None)
    return _build(story, chemin)


def generer_audit_pdf(chemin: str, *, logs: list[dict], agence: dict) -> str:
    """Journal d'activité (extrait) — qui a fait quoi, quand, depuis quel appareil."""
    style = _styles()
    story: list = []
    _entete(story, agence)
    story.append(Paragraph("JOURNAL D'ACTIVITÉ", style["titre"]))
    story.append(Paragraph(f"Extrait des {len(logs)} dernières actions — au {date.today().strftime('%d/%m/%Y')}", style["sous"]))
    story.append(Spacer(1, 4 * mm))
    head = ["Date", "Auteur", "Action", "Objet"]
    rows = []
    for l in logs:
        rows.append([_san((l.get("date") or "")[:16].replace("T", " ")), _san(l.get("user") or "système"),
                     _san(l.get("action") or ""), _san(l.get("objet_libelle") or "")])
    story.append(_table_generale(head, rows, [30 * mm, 34 * mm, 38 * mm, 60 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Chaque action est horodatée et rattachée à son auteur et à son appareil. "
                           "Les paiements ne sont jamais supprimés : toute correction se fait par écriture d'annulation motivée.",
                           style["italique"]))
    _pied(story, None, None)
    return _build(story, chemin)
