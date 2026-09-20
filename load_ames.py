"""
load_ames.py
------------
Télécharge le dataset Ames Housing (le même que dans ton guide, OpenML id 42165)
et le sauvegarde en CSV pour qu'on travaille dessus.

Lancer ce fichier une seule fois. Il :
  1. télécharge le dataset,
  2. l'enregistre dans  ames.csv,
  3. affiche un résumé (nombre de lignes, prix médian, colonnes intéressantes).

AVANT de lancer, installe les 2 librairies (une seule fois) :
    pip install scikit-learn pandas
Puis :
    python load_ames.py
"""

from sklearn.datasets import fetch_openml
import pandas as pd

print("Téléchargement d'Ames Housing (id 42165)... quelques secondes.")
data = fetch_openml(data_id=42165, as_frame=True, parser="auto")
df = data.frame

# Sauvegarde
df.to_csv("ames.csv", index=False)

# Résumé
print("\n=== OK, dataset chargé et sauvegardé dans ames.csv ===")
print(f"Lignes (maisons)   : {len(df)}")
print(f"Colonnes (features): {df.shape[1] - 1} + 1 cible (SalePrice)")
print(f"Prix médian        : {int(df['SalePrice'].median())} $")
print(f"Prix min / max     : {int(df['SalePrice'].min())} / {int(df['SalePrice'].max())} $")

# Les colonnes 'équipements' que tu voulais absolument garder
envies = {
    "OverallQual": "note de qualité générale (1-10)",
    "GrLivArea":   "surface habitable (sqft)",
    "YearBuilt":   "année de construction",
    "GarageCars":  "nb voitures dans le garage",
    "GarageArea":  "surface garage",
    "PoolArea":    "surface piscine",
    "Fireplaces":  "nb cheminées",
    "TotalBsmtSF": "surface sous-sol",
    "FullBath":    "nb salles de bain",
    "BedroomAbvGr":"nb chambres",
    "LotArea":     "surface terrain",
    "Neighborhood":"quartier",
}
print("\nExemples de colonnes présentes (celles que tu tenais à avoir) :")
for col, desc in envies.items():
    if col in df.columns:
        print(f"   - {col:14s} : {desc}")

print("\nTout est là : prix réel + surface + piscine + garage + qualité + quartier.")
print("C'est exactement le 'combiner les deux' que tu voulais, déjà réuni.")
