"""Legacy molecular-screening workflow, retained for audit and migration.

This script is exploratory. QED is directly computable from molecular structure
with RDKit; the XGBoost model below is therefore a surrogate-model benchmark,
not a clinical predictor and not evidence of pharmacological efficacy, safety,
or biological activity.
"""

from __future__ import annotations

from datetime import datetime
import json
import multiprocessing
import os
import shutil
import sys

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from joblib import Parallel, delayed
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem, FilterCatalog, QED
from rdkit.Chem.Scaffolds import MurckoScaffold
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import GroupShuffleSplit

RDLogger.DisableLog("rdApp.*")

PASTA_MODELOS = "modelos_ia_farma"
PASTA_EXPORTACAO = "csv_elite_farma"
CAMINHO_CSV = "BASE_ORACULO_FARMACIA_ADMET.csv"
METADADOS_PATH = os.path.join(PASTA_MODELOS, "metadados_farma_admet.json")

os.makedirs(PASTA_MODELOS, exist_ok=True)
os.makedirs(PASTA_EXPORTACAO, exist_ok=True)
NUM_CORES = multiprocessing.cpu_count()

COLUNAS_NUMERICAS = [
    "Peso_Molar",
    "LogP",
    "TPSA",
    "PHARMA_Qtd_O",
    "PHARMA_Qtd_N",
    "PHARMA_Qtd_F",
    "ADMET_FractionCSP3",
    "ADMET_RotatableBonds",
    "ADMET_AromaticRings",
    "ADMET_HDonors",
    "ADMET_HAcceptors",
]

SCIENTIFIC_NOTICE = (
    "QED is a directly computable RDKit descriptor. The ML model in this legacy "
    "workflow is evaluated only as a surrogate under a scaffold-group holdout. "
    "Its metrics are not clinical confidence and do not establish efficacy, safety, "
    "ADMET performance, or experimental validation."
)


def _gerar_fp_unico(args):
    idx, smiles = args
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
        arr = np.zeros((2048,), dtype=np.float32)
        DataStructs.ConvertToNumpyArray(fp, arr)
        return idx, arr
    except Exception:
        return None


def smiles_para_fingerprint(smiles_series):
    resultados = Parallel(n_jobs=-1, batch_size="auto")(
        delayed(_gerar_fp_unico)(item) for item in enumerate(smiles_series)
    )
    fps, indices_validos = [], []
    for res in resultados:
        if res is not None:
            indices_validos.append(res[0])
            fps.append(res[1])
    return np.asarray(fps), indices_validos


def _scaffold_group(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES in scaffold split: {smiles!r}")
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    if scaffold:
        return f"MURCKO::{scaffold}"
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    return f"ACYCLIC::{canonical}"


def _scaffold_holdout(valid_df: pd.DataFrame):
    groups = valid_df["SMILES"].map(_scaffold_group).to_numpy()
    if len(set(groups)) < 2:
        raise ValueError("at least two structural groups are required for scaffold holdout")

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(splitter.split(np.zeros(len(valid_df)), groups=groups))
    train_groups = set(groups[train_idx])
    test_groups = set(groups[test_idx])
    overlap = train_groups & test_groups
    if overlap:
        raise RuntimeError(f"scaffold leakage detected: {len(overlap)} overlapping groups")
    return train_idx, test_idx, groups


def carregar_metadados():
    if os.path.exists(METADADOS_PATH):
        with open(METADADOS_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "tamanho_ultimo_treino": 0,
        "complexidade_modelo": 200,
        "validation": None,
    }


def salvar_metadados(tamanho, n_estimators, validation):
    payload = {
        "tamanho_ultimo_treino": int(tamanho),
        "complexidade_modelo": int(n_estimators),
        "validation": validation,
        "scientific_notice": SCIENTIFIC_NOTICE,
    }
    with open(METADADOS_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def treinar_oraculo_farmaceutico():
    print("\n" + "=" * 85)
    print("LEGACY QED SURROGATE BENCHMARK")
    print("=" * 85)
    print(SCIENTIFIC_NOTICE)

    if not os.path.exists(CAMINHO_CSV):
        print(f"[FAIL] Dataset not found: {CAMINHO_CSV}")
        return

    colunas_leitura = ["SMILES", "Score_QED"] + COLUNAS_NUMERICAS
    df = pd.read_csv(CAMINHO_CSV, usecols=colunas_leitura, low_memory=False)
    df = df.dropna(subset=["SMILES", "Score_QED"]).copy()
    for col in COLUNAS_NUMERICAS + ["Score_QED"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=COLUNAS_NUMERICAS + ["Score_QED"]).copy()

    tamanho_atual = len(df)
    if tamanho_atual < 10:
        print("[FAIL] Insufficient valid rows for a held-out structural evaluation.")
        return

    metadados = carregar_metadados()
    n_estimators = int(metadados.get("complexidade_modelo", 200))
    tamanho_treino = min(150000, tamanho_atual)
    df_treino = df.sample(n=tamanho_treino, random_state=42).reset_index(drop=True)

    X_fp, idx_validos = smiles_para_fingerprint(df_treino["SMILES"])
    if not idx_validos:
        print("[FAIL] No valid molecular structures were featurized.")
        return

    valid_df = df_treino.iloc[idx_validos].reset_index(drop=True)
    X_tabular = valid_df[COLUNAS_NUMERICAS].to_numpy(dtype=float)
    X_final = np.hstack((X_fp, X_tabular))
    y_final = valid_df["Score_QED"].to_numpy(dtype=float)

    train_idx, test_idx, groups = _scaffold_holdout(valid_df)
    X_tr, X_te = X_final[train_idx], X_final[test_idx]
    y_tr, y_te = y_final[train_idx], y_final[test_idx]

    modelo_qed = xgb.XGBRegressor(
        n_estimators=n_estimators,
        max_depth=7,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,
        random_state=42,
    )
    modelo_qed.fit(X_tr, y_tr)
    pred = modelo_qed.predict(X_te)

    validation = {
        "split": "scaffold_group_holdout",
        "seed": 42,
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "train_groups": int(len(set(groups[train_idx]))),
        "test_groups": int(len(set(groups[test_idx]))),
        "group_overlap": 0,
        "mae": float(mean_absolute_error(y_te, pred)),
        "rmse": float(root_mean_squared_error(y_te, pred)),
        "r2": float(r2_score(y_te, pred)),
        "interpretation": "surrogate-model metrics only; not clinical confidence",
    }

    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_farma_admet_qed.pkl")
    joblib.dump(modelo_qed, caminho_modelo)
    salvar_metadados(tamanho_atual, n_estimators, validation)

    print("\nSurrogate model trained and evaluated on held-out structural groups.")
    print(f"MAE : {validation['mae']:.6f}")
    print(f"RMSE: {validation['rmse']:.6f}")
    print(f"R²  : {validation['r2']:.6f}")
    print("These values describe this held-out surrogate benchmark only.")


def _build_structural_alert_catalog():
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
    return FilterCatalog.FilterCatalog(params)


def _direct_qed(smiles: str) -> float:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return float("nan")
    return float(QED.qed(mol))


def rodar_triagem_automatica():
    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_farma_admet_qed.pkl")
    if not os.path.exists(caminho_modelo):
        print("[FAIL] Train the legacy QED surrogate first.")
        return

    print("\n" + "=" * 85)
    print("LEGACY MOLECULAR QED SCREENING")
    print("=" * 85)
    print(SCIENTIFIC_NOTICE)
    limite_podio = int(input("How many molecules should be retained? [100]: ") or 100)
    modelo_qed = joblib.load(caminho_modelo)
    catalogo_alertas = _build_structural_alert_catalog()

    def sem_alerta_estrutural(smiles):
        mol = Chem.MolFromSmiles(smiles)
        return bool(mol is not None and not catalogo_alertas.HasMatch(mol))

    top = pd.DataFrame()
    total_processado = 0

    for chunk in pd.read_csv(CAMINHO_CSV, chunksize=100000, low_memory=False):
        chunk = chunk.dropna(subset=["SMILES"]).copy()
        if "PHARMA_Lipinski_Pass" in chunk.columns:
            chunk = chunk[chunk["PHARMA_Lipinski_Pass"] == 1]
        if chunk.empty:
            continue

        for col in COLUNAS_NUMERICAS:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        chunk = chunk.dropna(subset=COLUNAS_NUMERICAS)
        if chunk.empty:
            continue

        X_chunk_fp, idx_v = smiles_para_fingerprint(chunk["SMILES"])
        if not idx_v:
            continue
        chunk_v = chunk.iloc[idx_v].copy()
        X_chunk_tab = chunk_v[COLUNAS_NUMERICAS].to_numpy(dtype=float)
        X_chunk_final = np.hstack((X_chunk_fp, X_chunk_tab))

        chunk_v["ML_Pred_QED"] = np.clip(modelo_qed.predict(X_chunk_final), 0.0, 1.0)
        chunk_v["QED_Direct_RDKit"] = chunk_v["SMILES"].map(_direct_qed)
        chunk_v = chunk_v.dropna(subset=["QED_Direct_RDKit"])

        candidates = chunk_v.nlargest(limite_podio * 2, "QED_Direct_RDKit")
        candidates = candidates[candidates["SMILES"].apply(sem_alerta_estrutural)]
        top = (
            pd.concat([top, candidates], ignore_index=True)
            .sort_values(by="QED_Direct_RDKit", ascending=False)
            .head(limite_podio)
        )

        total_processado += len(chunk)
        sys.stdout.write(f"\rProcessed molecular records: {total_processado}")
        sys.stdout.flush()

    print("\n\nTop molecules are ranked by direct RDKit QED, not by the ML surrogate.")
    for _, row in top.head(10).iterrows():
        print(
            f"ID: {row.get('ID', 'N/A')} | direct QED: {row['QED_Direct_RDKit']:.4f} "
            f"| surrogate QED: {row['ML_Pred_QED']:.4f} | SMILES: {row['SMILES'][:40]}..."
        )

    nome_arq = "RANKING_MOLECULAR_QED.csv"
    caminho_saida = os.path.join(PASTA_EXPORTACAO, nome_arq)
    if os.path.exists(caminho_saida):
        backup = os.path.join(
            PASTA_EXPORTACAO,
            f"BKP_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nome_arq}",
        )
        shutil.copy2(caminho_saida, backup)

    top.to_csv(caminho_saida, index=False, encoding="utf-8")
    print(f"Computational screening table exported to: {caminho_saida}")


def painel_controle_principal():
    while True:
        metadados = carregar_metadados()
        validation = metadados.get("validation") or {}
        print("\n" + "=" * 70)
        print("LEGACY MOLECULAR QED SURROGATE")
        print("=" * 70)
        if validation:
            print(
                "Last scaffold holdout: "
                f"MAE={validation.get('mae', float('nan')):.4f} | "
                f"RMSE={validation.get('rmse', float('nan')):.4f} | "
                f"R²={validation.get('r2', float('nan')):.4f}"
            )
        print("1) Train/evaluate QED surrogate")
        print("2) Run molecular QED screening")
        print("3) Exit")

        opcao = input("Choose 1-3: ").strip()
        if opcao == "1":
            treinar_oraculo_farmaceutico()
        elif opcao == "2":
            rodar_triagem_automatica()
        elif opcao == "3":
            return


if __name__ == "__main__":
    painel_controle_principal()
