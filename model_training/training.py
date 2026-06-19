"""
Survival analysis: predicts time-to-closure for judicial cases.
Uses XGBoost's AFT (Accelerated Failure Time) survival model.

- Closed cases: observed (uncensored) — exact duration known.
- Open cases:   right-censored — we know they lasted at least X days.

Trains on ALL cases from the DuckLake in ./silver/data.
"""

import duckdb
import numpy as np
import sys
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import matplotlib.pyplot as plt
import xgboost as xgb
import random 

# to ensure absolute reproducibility
random.seed(99)
np.random.seed(99)

# ============================================================
# PATHS
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

SILVER_DATA = PROJECT_ROOT / "silver" / "data"

model_output_path = PROJECT_ROOT / "model_training"
model_output_path.mkdir(parents=True, exist_ok=True)

courts_file = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"
if not courts_file.exists():
    if Path("courts_classified.parquet").exists():
        courts_file = Path("courts_classified.parquet")
    else:
        raise FileNotFoundError("Could not locate 'courts_classified.parquet'.")

# ============================================================
# DATA EXTRACTION — reads all parquet files from DuckLake
# ============================================================
print("Connecting to DuckDB...")
con = duckdb.connect()

# Attach the DuckLake (iceberg/parquet catalog in ./silver/data)
silver_glob = SILVER_DATA.as_posix() + "/**/*.parquet"

query = f"""
    WITH court_stats AS (
        SELECT
            court_id,
            AVG(CASE WHEN date_terminated IS NULL THEN 1.0 ELSE 0.0 END) AS court_censoring_rate,
            COUNT(*) AS court_case_volume
        FROM read_parquet('{silver_glob}', hive_partitioning=true, union_by_name=true)
        GROUP BY court_id
    )
    SELECT
        g.court_id,
        g.blocked,
        g.is_appeal,
        g.jury_demand,
        g.quarter_filed,
        CASE
            WHEN g.date_terminated IS NOT NULL
                THEN DATE_DIFF('day', g.date_filed::DATE, g.date_terminated::DATE)
            ELSE DATE_DIFF('day', g.date_filed::DATE, '2026-03-31'::DATE)
        END AS duration_days,
        CASE WHEN g.date_terminated IS NOT NULL THEN 1 ELSE 0 END AS is_closed,
        c.circuit,
        c.level,
        c.is_federal,
        c.jurisdiction,
        cs.court_censoring_rate,
        cs.court_case_volume
    FROM read_parquet('{silver_glob}', hive_partitioning=true, union_by_name=true) g
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

# Recompute court stats from data
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
print(f"  Closed (observed): {df['is_closed'].sum():,} ({100*df['is_closed'].mean():.1f}%)")
print(f"  Open (censored):   {(1-df['is_closed']).sum():,} ({100*(1-df['is_closed']).mean():.1f}%)")

# ============================================================
# SURVIVAL TARGETS
#
# XGBoost AFT expects:
#   y_lower: lower bound of the observed time interval
#   y_upper: upper bound (np.inf for right-censored / open cases)
#
# Closed case: [duration_days, duration_days]   — exact observation
# Open case:   [duration_days, +inf]            — right-censored
# ============================================================
df["y_lower"] = df["duration_days"].astype(float)
df["y_upper"] = np.where(df["is_closed"] == 1, df["duration_days"].astype(float), np.inf)

# ============================================================
# FEATURES & SPLIT
# ============================================================
features = [
    "court_id", "blocked", "is_appeal", "jury_demand",
    "quarter_filed", "circuit", "level", "is_federal", "jurisdiction",
    "court_censoring_rate", "court_case_volume",
]

X = df[features].copy()
y_lower = df["y_lower"].values
y_upper = df["y_upper"].values

for col in X.select_dtypes(include=["object"]).columns:
    X[col] = X[col].astype("category")

# Stratify by a binarised long-case flag so val set has representative mix
strat_flag = (df["duration_days"] >= 365).astype(int)

X_train, X_val, yl_train, yl_val, yu_train, yu_val, strat_train, strat_val = (
    train_test_split(X, y_lower, y_upper, strat_flag,
                     test_size=0.2, random_state=99, stratify=strat_flag)
)

print(f"\nTrain: {len(X_train):,}  |  Val: {len(X_val):,}")

# ============================================================
# DMATRIX  — AFT requires label_lower_bound / label_upper_bound
# ============================================================
dtrain = xgb.DMatrix(X_train, enable_categorical=True)
dtrain.set_float_info("label_lower_bound", yl_train)
dtrain.set_float_info("label_upper_bound", yu_train)

dval = xgb.DMatrix(X_val, enable_categorical=True)
dval.set_float_info("label_lower_bound", yl_val)
dval.set_float_info("label_upper_bound", yu_val)

# ============================================================
# TRAIN — AFT with log-normal distribution
# ============================================================
params = {
    "objective":            "survival:aft",
    "eval_metric":          "aft-nloglik",   # negative log-likelihood (lower = better)
    "aft_loss_distribution": "normal",        # log-normal on the log scale
    "aft_loss_distribution_scale": 1.0,
    "learning_rate":        0.03,
    "max_depth":            5,
    "min_child_weight":     30,
    "tree_method":          "hist",
    "colsample_bytree":     0.8,
    "subsample":            0.8,
    "reg_alpha":            5.0,
    "reg_lambda":           5.0,
    "seed":                 99,
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
# PREDICTIONS
# predict() returns the predicted median survival time (days)
# ============================================================
val_pred_days = bst.predict(dval)      # predicted duration in days

# For secondary binary eval: is predicted duration >= 365?
LONG_THRESHOLD_DAYS = 365
val_pred_long  = (val_pred_days >= LONG_THRESHOLD_DAYS).astype(int)
val_actual_long = (yl_val >= LONG_THRESHOLD_DAYS).astype(int)  # use lower bound for closed

# ROC-AUC on the binary long/not-long question (closed cases only, where ground truth is exact)
closed_mask = np.isfinite(yu_val)
if closed_mask.sum() > 0:
    auc = roc_auc_score(val_actual_long[closed_mask], val_pred_days[closed_mask])
    print(f"\nROC-AUC (closed cases, predicted days vs >=365 label): {auc:.4f}")

# ============================================================
# FEATURE IMPORTANCE
# ============================================================
importance = bst.get_score(importance_type="gain")
importance_sorted = sorted(importance.items(), key=lambda x: x[1], reverse=True)
print("\nFeature importance by gain:")
for feat, score in importance_sorted:
    print(f"  {feat:35s}: {score:.2f}")

# ============================================================
# PLOT 1 — Predicted vs actual duration (closed cases only, log scale)
# ============================================================
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(
    yl_val[closed_mask],
    val_pred_days[closed_mask],
    alpha=0.2, s=5, color="steelblue", label="Closed cases"
)
max_val = max(yl_val[closed_mask].max(), val_pred_days[closed_mask].max())
ax.plot([1, max_val], [1, max_val], "r--", label="Perfect prediction")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("Actual duration (days, log)")
ax.set_ylabel("Predicted median survival (days, log)")
ax.set_title("AFT: Predicted vs Actual Duration (closed cases)")
ax.legend(loc="lower right"); ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(str(model_output_path / "survival_pred_vs_actual.png"), dpi=150)
plt.show()

# ============================================================
# PLOT 2 — Distribution of predicted median survival
# ============================================================
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(np.log1p(val_pred_days), bins=80, color="steelblue", edgecolor="none", alpha=0.7)
ax.axvline(np.log1p(365), color="red", linestyle="--", label="365-day threshold")
ax.set_xlabel("log(1 + predicted days)")
ax.set_ylabel("Count")
ax.set_title("Distribution of Predicted Median Survival (validation set)")
ax.legend(loc="lower right"); ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(str(model_output_path / "survival_pred_distribution.png"), dpi=150)
plt.show()

# ============================================================
# PLOT 3 — Feature importance bar chart
# ============================================================
feat_names, feat_scores = zip(*importance_sorted)
fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(feat_names[::-1], feat_scores[::-1], color="steelblue")
ax.set_xlabel("Gain")
ax.set_title("Feature Importance (gain)")
plt.tight_layout()
plt.savefig(str(model_output_path / "survival_feature_importance.png"), dpi=150)
plt.show()

# ============================================================
# CONCORDANCE INDEX (C-index) 
# Fraction of comparable pairs where higher predicted time → longer actual time
# ============================================================
def concordance_index(event_times, predicted_times, event_observed):
    """Harrell's C-index. event_observed=1 means uncensored."""
    n = len(event_times)
    concordant = 0
    comparable = 0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            # pair (i,j) is comparable only if i had an event
            # and i's event time < j's event time (or j is censored after i)
            if event_observed[i] == 1 and event_times[i] < event_times[j]:
                comparable += 1
                if predicted_times[i] < predicted_times[j]:
                    concordant += 1
                elif predicted_times[i] == predicted_times[j]:
                    concordant += 0.5
    return concordant / comparable if comparable > 0 else float("nan")


# C-index on a random subsample
CINDEX_SAMPLE = min(5_000, closed_mask.sum())
rng = np.random.default_rng(99)
idx = rng.choice(np.where(closed_mask)[0], size=CINDEX_SAMPLE, replace=False)

c_index = concordance_index(
    event_times=yl_val[idx],
    predicted_times=val_pred_days[idx],
    event_observed=np.ones(len(idx)),  # all closed
)
print(f"\nC-index (subsample n={CINDEX_SAMPLE:,}): {c_index:.4f}  "
      f"(0.5 = random, 1.0 = perfect)")

# ============================================================
# SAVE MODEL
# ============================================================
survival_path = model_output_path / "survival_model.ubj"
bst.save_model(str(survival_path))
print(f"\nSurvival model saved to: {survival_path}")