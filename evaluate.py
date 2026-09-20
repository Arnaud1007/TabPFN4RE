"""
evaluate.py
-----------
Les métriques : de combien le modèle se trompe. Fonctions testables.
"""

import numpy as np


def mae(y_true, y_pred):
    """Erreur absolue moyenne (en $). Plus bas = mieux."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    return np.mean(np.abs(y_true - y_pred))


def rmse(y_true, y_pred):
    """Racine de l'erreur quadratique moyenne. Punit plus les gros écarts."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


def rmsle(y_true, y_pred):
    """Comme RMSE mais sur les prix en échelle log (écarts relatifs)."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    y_pred = np.clip(y_pred, 0, None)  # pas de log d'un nombre négatif
    return np.sqrt(np.mean((np.log1p(y_pred) - np.log1p(y_true)) ** 2))


def r2(y_true, y_pred):
    """Part de la variation expliquée. 1 = parfait, 0 = aussi nul que la moyenne."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return 1 - ss_res / ss_tot


def compute_metrics(y_true, y_pred):
    """Renvoie toutes les métriques d'un coup, sous forme de dictionnaire."""
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "rmsle": rmsle(y_true, y_pred),
        "r2": r2(y_true, y_pred),
    }
