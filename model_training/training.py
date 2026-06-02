"""
Binary classifier: predicts whether a judicial case will be long (>=365 days) or not.
Trains on ALL cases (closed + open), using actual duration for closed and
elapsed days as a lower bound signal for open cases.
"""

import duckdb
import numpy as np
import pandas as pd
import sys
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                             roc_auc_score, RocCurveDisplay)
import matplotlib.pyplot as plt
import seaborn as sns
import xgboost as xgb

LONG_CASE_THRESHOLD = 0.34

# ============================================================
# PATHS
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ingestion.config import GOLD_PATH

gold_file        = GOLD_PATH / "database_case_metrics.parquet"
model_output_path = PROJECT_ROOT / "model_training" / "models"
model_output_path.mkdir(parents=True, exist_ok=True)

courts_file = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"
if not courts_file.exists():
    if Path("courts_classified.parquet").exists():
        courts_file = Path("courts_classified.parquet")
    else:
        raise FileNotFoundError("Could not locate 'courts_classified.parquet'.")

# ============================================================
# DATA EXTRACTION — same query as baseline
# ============================================================
print("Connecting to DuckDB...")
con = duckdb.connect()

query = f"""
    WITH court_stats AS (
        SELECT
            court_id,
            AVG(CASE WHEN date_terminated IS NULL THEN 1.0 ELSE 0.0 END) AS court_censoring_rate,
            COUNT(*) AS court_case_volume
        FROM read_parquet('{gold_file.as_posix()}')
        GROUP BY court_id
    )
    SELECT
        g.court_id,
        g.blocked,
        g.is_appeal,
        g.jury_demand,
        g.quarter_filed,
        CASE
            WHEN g.date_terminated IS NOT NULL THEN g.duration_days
            ELSE DATE_DIFF('day', g.date_filed::DATE, '2026-03-31'::DATE)
        END AS duration_days,
        CASE WHEN g.date_terminated IS NOT NULL THEN 1 ELSE 0 END AS is_closed,
        c.circuit,
        c.level,
        c.is_federal,
        c.jurisdiction,
        cs.court_censoring_rate,
        cs.court_case_volume
    FROM read_parquet('{gold_file.as_posix()}') g
    LEFT JOIN read_parquet('{courts_file.as_posix()}') c ON g.court_id = c.court_id
    LEFT JOIN court_stats cs ON g.court_id = cs.court_id
    WHERE g.date_filed IS NOT NULL
    AND YEAR(g.date_filed::DATE) >= 2020
    AND YEAR(g.date_filed::DATE) < 2026
    AND c.jurisdiction NOT IN ('FS')
    AND g.court_id NOT IN ('texcrimapp')
    AND (c.circuit IS NULL OR c.circuit NOT IN ('20'))
    AND (g.date_terminated IS NULL OR g.date_filed::DATE <= g.date_terminated::DATE)
    
"""
df = con.execute(query).df()
df["duration_days"] = df["duration_days"].clip(lower=1)

# Recompute court stats from data (same as baseline)
court_agg = (
    df.groupby("court_id")
    .agg(
        court_censoring_rate=("is_closed", lambda x: 1 - x.mean()),
        court_case_volume=("is_closed", "count"),
    )
    .reset_index()
)

court_stats_path = model_output_path / "court_stats.parquet"
court_agg.to_parquet(court_stats_path, index=False)
print(f"Court stats saved to: {court_stats_path}")

df = df.drop(columns=["court_censoring_rate", "court_case_volume"])
df = df.merge(court_agg, on="court_id", how="left")

print(f"Total records: {len(df):,}")

# ============================================================
# BINARY TARGET
# Closed cases: label = 1 if actual duration >= 365
# Open cases:   label = 1 if elapsed days already >= 365 (certain longs),
#               drop ambiguous open cases with elapsed < 365 (we can't know)
# ============================================================
closed_df = df[df["is_closed"] == 1].copy()
closed_df["is_long"] = (closed_df["duration_days"] >= 365).astype(int)

open_df = df[df["is_closed"] == 0].copy()
# Only keep open cases already past 365 days — these are definitely long
open_certain = open_df[open_df["duration_days"] >= 365].copy()
open_certain["is_long"] = 1

train_df = pd.concat([closed_df, open_certain], ignore_index=True)

print(f"\nTraining set: {len(train_df):,} cases")
print(f"  Long (>=365d): {train_df['is_long'].sum():,} ({100*train_df['is_long'].mean():.1f}%)")
print(f"  Not long:      {(1-train_df['is_long']).sum():,} ({100*(1-train_df['is_long']).mean():.1f}%)")

# ============================================================
# FEATURES & SPLIT
# ============================================================
features = [
    "court_id", "blocked", "is_appeal", "jury_demand",
    "quarter_filed", "circuit", "level", "is_federal", "jurisdiction",
    "court_censoring_rate", "court_case_volume",
]

X = train_df[features].copy()
y = train_df["is_long"].values

for col in X.select_dtypes(include=["object"]).columns:
    X[col] = X[col].astype("category")

X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Class imbalance: weight the long class proportionally
neg = (y_train == 0).sum()
pos = (y_train == 1).sum()
scale_pos_weight = neg / pos
print(f"\nscale_pos_weight: {scale_pos_weight:.2f}  (neg={neg:,} / pos={pos:,})")

# ============================================================
# TRAIN
# ============================================================
dtrain = xgb.DMatrix(X_train, label=y_train, enable_categorical=True)
dval   = xgb.DMatrix(X_val,   label=y_val,   enable_categorical=True)

params = {
    "objective":        "binary:logistic",
    "eval_metric":      "auc",
    "learning_rate":    0.03,
    "max_depth":        5,
    "min_child_weight": 30,
    "tree_method":      "hist",
    "colsample_bytree": 0.8,
    "subsample":        0.8,
    "reg_alpha":        5.0,
    "reg_lambda":       5.0,
    "scale_pos_weight": scale_pos_weight,
    "seed":             42,
}

bst = xgb.train(
    params=params,
    dtrain=dtrain,
    num_boost_round=1000,
    evals=[(dtrain, "train"), (dval, "val")],
    early_stopping_rounds=50,
    verbose_eval=50,
)

# ============================================================
# EVALUATION
# ============================================================
val_proba = bst.predict(dval)
val_pred  = (val_proba >= LONG_CASE_THRESHOLD).astype(int)

print(f"\nClassification Report (threshold={LONG_CASE_THRESHOLD}):")
print(classification_report(y_val, val_pred, target_names=["not long", "long"]))
print(f"ROC-AUC: {roc_auc_score(y_val, val_proba):.4f}")

# Feature importance
importance = bst.get_score(importance_type="gain")
importance_sorted = sorted(importance.items(), key=lambda x: x[1], reverse=True)
print("\nFeature importance by gain:")
for feat, score in importance_sorted:
    print(f"  {feat:35s}: {score:.2f}")

# ============================================================
# CONFUSION MATRIX
# ============================================================
cm     = confusion_matrix(y_val, val_pred)
cm_pct = cm.astype(float) / cm.sum(axis=1, keepdims=True) * 100

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=axes[0],
            xticklabels=["not long", "long"], yticklabels=["not long", "long"])
axes[0].set_title("Confusion Matrix (counts)")
axes[0].set_xlabel("Predicted"); axes[0].set_ylabel("Actual")

sns.heatmap(cm_pct, annot=True, fmt=".1f", cmap="Blues", ax=axes[1],
            xticklabels=["not long", "long"], yticklabels=["not long", "long"])
axes[1].set_title("Confusion Matrix (% of actual)")
axes[1].set_xlabel("Predicted"); axes[1].set_ylabel("Actual")

plt.tight_layout()
plt.savefig(str(model_output_path / "binary_confusion_matrix.png"), dpi=150)
plt.show()

# ============================================================
# THRESHOLD TUNING
# ============================================================
thresholds = np.arange(0.1, 0.91, 0.02)
results = []
for t in thresholds:
    pred = (val_proba >= t).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_val, pred).ravel()
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1        = 2*precision*recall / (precision+recall) if (precision+recall) > 0 else 0
    results.append({"threshold": t, "precision": precision, "recall": recall, "f1": f1})

res_df = pd.DataFrame(results)
best   = res_df.loc[res_df["f1"].idxmax()]

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(res_df["threshold"], res_df["recall"],    label="Recall (long)",    color="steelblue")
ax.plot(res_df["threshold"], res_df["precision"], label="Precision (long)", color="darkorange")
ax.plot(res_df["threshold"], res_df["f1"],        label="F1",               color="green", linestyle="--")
ax.axvline(0.5,              color="red",   linestyle=":",  label="Default (0.5)")
ax.axvline(best["threshold"], color="purple", linestyle="--", label=f"Best F1 ({best['threshold']:.2f})")
ax.set_xlabel("Probability threshold")
ax.set_ylabel("Score")
ax.set_title("Binary threshold tuning (probability-based)")
ax.legend(); ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(str(model_output_path / "binary_threshold_tuning.png"), dpi=150)
plt.show()

print(f"\nBest F1 threshold: {best['threshold']:.2f} — "
      f"Precision: {best['precision']:.3f} | Recall: {best['recall']:.3f} | F1: {best['f1']:.3f}")

# ============================================================
# SAVE
# ============================================================
binary_path = model_output_path / "binary_model.ubj"
bst.save_model(str(binary_path))
print(f"\nBinary model saved to: {binary_path}")