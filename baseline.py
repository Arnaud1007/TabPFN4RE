"""
baseline.py
-----------
Premier modèle de référence sur Ames (suit ton guide, Semaine 2).

Ce qu'il fait, proprement :
  1. charge ames.csv
  2. met 20% des maisons DE COTE (le "holdout" final) et n'y touche PAS
  3. sur les 80% restants, teste 2 modèles en validation croisée 5 plis :
        - Dummy  : bête, prédit toujours le prix moyen (juste pour comparer)
        - XGBoost: le vrai modèle de référence
  4. affiche l'erreur moyenne (MAE = combien de $ il se trompe en moyenne)
  5. sauvegarde les scores dans cv_scores.csv et les IDs du holdout dans holdout_ids.csv

Le holdout reste FERME : on ne regarde son score que tout à la fin du projet,
une seule fois, quand tous les modèles seront figés. C'est la règle anti-triche.

AVANT de lancer, installe XGBoost (une seule fois) :
    python -m pip install xgboost
Puis :
    python baseline.py
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.dummy import DummyRegressor
from xgboost import XGBRegressor

SEED = 42  # graine fixe = résultats reproductibles

# --- 1. Charger ---
df = pd.read_csv("ames.csv")
y = df["SalePrice"]
X = df.drop(columns=["SalePrice"])
print(f"Données : {len(df)} maisons, {X.shape[1]} features")

# --- 2. Mettre 20% de côté (holdout figé, jamais ouvert ici) ---
X_dev, X_hold, y_dev, y_hold = train_test_split(
    X, y, test_size=0.20, random_state=SEED
)
pd.Series(X_hold.index).to_csv("holdout_ids.csv", index=False, header=["row_id"])
print(f"Développement : {len(X_dev)} maisons  |  Holdout (fermé) : {len(X_hold)}")

# --- 3. Préparer les colonnes (nombres vs catégories) ---
num_cols = X_dev.select_dtypes(include="number").columns.tolist()
cat_cols = [c for c in X_dev.columns if c not in num_cols]

# nombres : remplir les trous par la médiane
# catégories : remplir par la plus fréquente + transformer en 0/1 (one-hot)
prep = ColumnTransformer([
    ("num", SimpleImputer(strategy="median"), num_cols),
    ("cat", Pipeline([
        ("imp", SimpleImputer(strategy="most_frequent")),
        ("oh", OneHotEncoder(handle_unknown="ignore")),
    ]), cat_cols),
])

# validation croisée : 5 plis, mélangés, graine fixe (les MEMES pour les 2 modèles)
cv = KFold(n_splits=5, shuffle=True, random_state=SEED)

def evalue(nom, modele):
    pipe = Pipeline([("prep", prep), ("model", modele)])
    # score = erreur absolue moyenne en $ (on prend l'opposé car sklearn maximise)
    scores = -cross_val_score(pipe, X_dev, y_dev, cv=cv,
                              scoring="neg_mean_absolute_error")
    print(f"  {nom:10s} : MAE moyenne = {scores.mean():8.0f} $   "
          f"(par pli : {', '.join(f'{s:.0f}' for s in scores)})")
    return scores

print("\nValidation croisée 5 plis (erreur = $ d'écart moyen, plus bas = mieux) :")
s_dummy = evalue("Dummy", DummyRegressor(strategy="mean"))
s_xgb = evalue("XGBoost", XGBRegressor(
    n_estimators=400, max_depth=4, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8, random_state=SEED, n_jobs=-1,
))

# --- 5. Sauvegarder les scores ---
pd.DataFrame({
    "pli": range(1, 6),
    "MAE_dummy": s_dummy,
    "MAE_xgboost": s_xgb,
}).to_csv("cv_scores.csv", index=False)

print("\nRésumé :")
print(f"  Le modèle bête se trompe de ~{s_dummy.mean():.0f} $ en moyenne.")
print(f"  XGBoost se trompe de     ~{s_xgb.mean():.0f} $ en moyenne.")
print(f"  => XGBoost fait {100*(1 - s_xgb.mean()/s_dummy.mean()):.0f}% mieux que de deviner la moyenne.")
print("\nScores sauvegardés dans cv_scores.csv. Holdout toujours fermé (holdout_ids.csv).")
