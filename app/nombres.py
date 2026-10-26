"""Conversion d'un montant FCFA en lettres (français) pour les quittances (F6).

Règles appliquées : « vingt » et « cent » prennent un « s » quand ils terminent le nombre
(quatre-vingts, deux cents) mais pas devant « mille » (quatre-vingt mille, deux cent mille).
« mille » est invariable ; « million/milliard » sont des noms (accordés)."""
from __future__ import annotations

_UNITES = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
           "onze", "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZ = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante", 8: "quatre-vingt"}


def _moins_cent(n: int) -> str:
    """1 à 99."""
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    if d in (7, 9):  # soixante-dix… / quatre-vingt-dix…
        base = "soixante" if d == 7 else "quatre-vingt"
        if u == 0:
            return base + "-dix"
        if u == 1 and d == 7:
            return base + " et onze"
        return base + "-" + _UNITES[10 + u]
    base = _DIZ[d]
    if u == 0:
        return "quatre-vingts" if d == 8 else base
    if u == 1 and d != 8:
        return base + " et un"
    return base + "-" + _UNITES[u]


def _moins_mille(n: int) -> str:
    """1 à 999."""
    if n < 100:
        return _moins_cent(n)
    c, reste = divmod(n, 100)
    if c == 1:
        tete = "cent"
    elif reste == 0:
        tete = _UNITES[c] + " cents" if c != 8 else "huit cents"
    else:
        tete = _UNITES[c] + " cent"
    return tete if not reste else f"{tete} {_moins_cent(reste)}"


def _prefixe_mille(n: int) -> str:
    """Forme du multiplicateur devant « mille » : pas de s final (deux cent mille)."""
    s = _moins_mille(n)
    if s.endswith("cents") or s.endswith("quatre-vingts"):
        return s[:-1]
    return s


def en_lettres(n: int) -> str:
    """1250000 -> « un million deux cent cinquante mille »."""
    if n < 0:
        return "moins " + en_lettres(-n)
    if n == 0:
        return "zéro"
    if n < 1000:
        return _moins_mille(n)
    morceaux: list[str] = []
    reste = n
    for valeur, nom in ((1_000_000_000, "milliard"), (1_000_000, "million")):
        q, reste = divmod(reste, valeur)
        if q:
            mot = nom if q == 1 else nom + "s"
            morceaux.append(f"{_moins_mille(q)} {mot}")
    if reste >= 1000:
        q_mille, reste = divmod(reste, 1000)
        morceaux.append("mille" if q_mille == 1 else f"{_prefixe_mille(q_mille)} mille")
    if reste:
        morceaux.append(_moins_mille(reste))
    return " ".join(morceaux)


def montant_fcfa_lettres(n: int) -> str:
    return f"{en_lettres(n)} francs CFA"
