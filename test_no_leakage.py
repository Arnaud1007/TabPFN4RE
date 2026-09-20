"""
test_no_leakage.py — vérifie que le split ne fuit pas (Day 6).
C'est LE test le plus important : il garantit que le holdout reste séparé.
"""

from data import load_data, get_X_y, make_split


def test_pas_de_ligne_commune():
    """Aucune maison ne doit être à la fois en développement ET en holdout."""
    df = load_data()
    X, y = get_X_y(df)
    X_dev, X_hold, y_dev, y_hold = make_split(X, y)
    dev = set(X_dev.index)
    hold = set(X_hold.index)
    assert dev.isdisjoint(hold)              # zéro maison en commun
    assert len(dev) + len(hold) == len(df)   # aucune maison perdue


def test_split_reproductible():
    """Même graine => exactement le même holdout à chaque fois."""
    df = load_data()
    X, y = get_X_y(df)
    hold_a = make_split(X, y)[1].index.tolist()
    hold_b = make_split(X, y)[1].index.tolist()
    assert hold_a == hold_b


def test_taille_holdout():
    """Le holdout doit faire ~20% des maisons."""
    df = load_data()
    X, y = get_X_y(df)
    X_dev, X_hold, y_dev, y_hold = make_split(X, y)
    assert abs(len(X_hold) - 0.20 * len(df)) < 2
