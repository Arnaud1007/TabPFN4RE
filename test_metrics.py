"""
test_metrics.py — vérifie que les métriques calculent juste (Day 6).
On teste sur des petits exemples où on connaît la réponse à la main.
"""

import numpy as np
from evaluate import mae, rmse, compute_metrics


def test_mae_connu():
    """Erreurs 10, 10, 0 -> moyenne = 20/3."""
    y = np.array([100, 200, 300])
    p = np.array([110, 190, 300])
    assert abs(mae(y, p) - 20 / 3) < 1e-9


def test_rmse_connu():
    """Erreurs 3 et 4 -> racine de (9+16)/2 = racine de 12.5."""
    y = np.array([0, 0])
    p = np.array([3, 4])
    assert abs(rmse(y, p) - 12.5 ** 0.5) < 1e-9


def test_prediction_parfaite():
    """Si on prédit pile juste : erreur nulle et R2 = 1."""
    y = np.array([1.0, 2.0, 3.0])
    m = compute_metrics(y, y)
    assert m["mae"] == 0
    assert abs(m["r2"] - 1.0) < 1e-9


def test_schema():
    """La sortie doit contenir les 4 métriques attendues (schéma des résultats)."""
    y = np.array([1.0, 2.0, 3.0])
    p = np.array([1.5, 2.0, 2.5])
    m = compute_metrics(y, p)
    for cle in ("mae", "rmse", "rmsle", "r2"):
        assert cle in m
