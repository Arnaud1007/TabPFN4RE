"""
data.py
-------
Chargement des données et découpage (split), en petites fonctions testables.
"""

import pandas as pd
from sklearn.model_selection import train_test_split

DATA_PATH = "ames.csv"
TARGET = "SalePrice"
SEED = 42  # graine fixe = résultats reproductibles


def load_data(path=DATA_PATH):
    """Charge le dataset Ames depuis le CSV et renvoie un tableau pandas."""
    return pd.read_csv(path)


def get_X_y(df, target=TARGET):
    """Sépare les features (X) de la cible (y = prix)."""
    y = df[target]
    X = df.drop(columns=[target])
    return X, y


def make_split(X, y, test_size=0.20, seed=SEED):
    """
    Découpe en développement (80%) et holdout (20%), toujours pareil (graine fixe).
    Renvoie : X_dev, X_hold, y_dev, y_hold.
    Le holdout ne sert QU'à la toute fin du projet.
    """
    return train_test_split(X, y, test_size=test_size, random_state=seed)
