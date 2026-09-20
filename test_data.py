"""
test_data.py — vérifie que le chargement est stable et correct (Day 6).
"""

from data import load_data, get_X_y


def test_forme():
    """Le dataset doit toujours faire 1460 lignes et 81 colonnes."""
    df = load_data()
    assert df.shape == (1460, 81)


def test_deterministe():
    """Charger deux fois donne exactement les mêmes colonnes (reproductible)."""
    df1 = load_data()
    df2 = load_data()
    assert list(df1.columns) == list(df2.columns)
    assert df1.shape == df2.shape


def test_cible_presente():
    """La colonne à prédire (SalePrice) doit exister et sortir de X."""
    df = load_data()
    assert "SalePrice" in df.columns
    X, y = get_X_y(df)
    assert "SalePrice" not in X.columns
    assert len(y) == len(df)
