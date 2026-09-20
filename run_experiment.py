"""
run_experiment.py — Day 8
-------------------------
Évalue Dummy et XGBoost en validation croisée 5 plis, avec TOUTES les métriques
(MAE, RMSE, RMSLE, R2) + le temps, et écrit les résultats dans artifacts/.

Réutilise data.py (chargement + split) et evaluate.py (métriques).
Le holdout reste fermé : on ne travaille que sur le développement (80%).

Lancer :
    python run_experiment.py
Crée :
    artifacts/cv_scores.csv   -> le détail par pli
    artifacts/metrics.csv     -> le résumé (moyenne par modèle)
"""

import os
import time
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.dummy import DummyRegressor
from xgboost import XGBRegressor

from data import load_data, get_X_y, make_split, SEED
from evaluate import compute_metrics

# --- Données : on ne garde que le développement (holdout fermé) ---
df = load_data()
X, y = get_X_y(df)
X_dev, X_hold, y_dev, y_hold = make_split(X, y)
print(f"Développement : {len(X_dev)} maisons  |  Holdout (fermé) : {len(X_hold)}")

# --- Préparation leakage-safe pour XGBoost ---
num_cols = X_dev.select_dtypes(include="number").columns.tolist()
cat_cols = [c for c in X_dev.columns if c not in num_cols]
prep = ColumnTransformer([
    ("num", SimpleImputer(strategy="median"), num_cols),
    ("cat", Pipeline([
        ("imp", SimpleImputer(strategy="most_frequent")),
        ("oh", OneHotEncoder(handle_unknown="ignore")),
    ]), cat_cols),
])

# --- Modèles à comparer ---
modeles = {
    "Dummy": DummyRegressor(strategy="mean"),
    "XGBoost": XGBRegressor(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=SEED, n_jobs=-1,
    ),
}

cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
lignes = []  # détail par pli

for nom, modele in modeles.items():
    for i, (tr, va) in enumerate(cv.split(X_dev), start=1):
        Xtr, Xva = X_dev.iloc[tr], X_dev.iloc[va]
        ytr, yva = y_dev.iloc[tr], y_dev.iloc[va]

        pipe = Pipeline([("prep", prep), ("model", modele)])

        t0 = time.perf_counter()
        pipe.fit(Xtr, ytr)
        pred = pipe.predict(Xva)
        duree = time.perf_counter() - t0

        m = compute_metrics(yva, pred)
        m.update({"modele": nom, "pli": i, "temps_s": round(duree, 2)})
        lignes.append(m)

detail = pd.DataFrame(lignes)[
    ["modele", "pli", "mae", "rmse", "rmsle", "r2", "temps_s"]
]

# --- Résumé : moyenne par modèle ---
resume = detail.groupby("modele").mean(numeric_only=True).drop(columns="pli").reset_index()

# --- Sauvegarde ---
os.makedirs("artifacts", exist_ok=True)
detail.to_csv("artifacts/cv_scores.csv", index=False)
resume.to_csv("artifacts/metrics.csv", index=False)

# --- Affichage lisible ---
pd.options.display.float_format = lambda v: f"{v:,.2f}"
print("\n=== Résumé (moyenne sur 5 plis) ===")
for _, r in resume.iterrows():
    print(f"  {r['modele']:8s} | MAE {r['mae']:>10,.0f} $ | RMSE {r['rmse']:>10,.0f} $ "
          f"| RMSLE {r['rmsle']:.3f} | R2 {r['r2']:.3f} | {r['temps_s']:.2f}s / pli")

print("\nFichiers écrits : artifacts/cv_scores.csv (détail) et artifacts/metrics.csv (résumé).")
