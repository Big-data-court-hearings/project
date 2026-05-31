"""
Judicial Case Duration Classification Framework.

This script converts the continuous case duration regression problem into a 
5-class probabilistic classification pipeline using operational buckets, enhanced
with structural and geographical court taxonomies.
"""

import json  
import duckdb
import numpy as np
import pandas as pd
import sys
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from xgboost import XGBClassifier
from sklearn.utils.class_weight import compute_sample_weight

# Setup project root paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Adjust imports to match your project's internal ingestion configuration structure
from ingestion.config import GOLD_PATH

# ============================================================
# PATHS & CONFIGURATION
# ============================================================
gold_file = GOLD_PATH / "database_case_metrics.parquet"
model_output_path = PROJECT_ROOT / "prediction" / "models"
model_output_path.mkdir(parents=True, exist_ok=True)

# Locate the court classification metadata file
courts_file = PROJECT_ROOT / "silver"/ "courts"/"courts_classified.parquet"
if not courts_file.exists():
    # Fallback to look directly in the current working directory if paths differ
    if Path("courts_classified.parquet").exists():
        courts_file = Path("courts_classified.parquet")
    else:
        raise FileNotFoundError(
            f"Could not locate 'courts_classified.parquet' at {courts_file.as_posix()} "
            "or in the current working directory."
        )

# ============================================================
# DATA EXTRACTION & ENGINE CONNECTION (WITH COURT JOIN)
# ============================================================
print("Connecting to DuckDB and extracting closed historical records with court metadata...")
con = duckdb.connect()

# Load all valid closed cases and LEFT JOIN with the court classification table
query = f"""
    SELECT 
        g.court_id, 
        g.nature_of_suit, 
        g.jurisdiction_type, 
        g.cause, 
        g.blocked, 
        g.source, 
        g.is_appeal,
        g.jury_demand,
        g.quarter_filed,
        g.year_filed,
        g.duration_days,
        c.circuit,
        c.level,
        c.is_federal
    FROM read_parquet('{gold_file.as_posix()}') g
    LEFT JOIN read_parquet('{courts_file.as_posix()}') c
      ON g.court_id = c.court_id
    WHERE g.date_terminated IS NOT NULL 
      AND g.date_filed IS NOT NULL
      AND g.duration_days >= 0
"""
df = con.execute(query).df()
print(f"Total raw profiles extracted: {len(df):,}")

# ============================================================
# DYNAMIC THRESHOLD CALCULATION & BUCKETING
# ============================================================
# Compute the true mathematical average duration of the cohort
avg_duration = df["duration_days"].mean()
print(f"Calculated Cohort Mean Duration: {avg_duration:.2f} days.")

print("Mapping continuous duration scales into operational categories...")
# Preserving your exact customized increasing 5-class thresholds
conditions = [
    (df["duration_days"] < 90),
    (df["duration_days"] >= 90) & (df["duration_days"] < 210),
    (df["duration_days"] >= 210) & (df["duration_days"] < avg_duration),
    (df["duration_days"] >= avg_duration) & (df["duration_days"] < 1000),
    (df["duration_days"] >= 1000)
]

# Integer mappings for XGBoost (0-indexed classification targets)
class_labels = [0, 1, 2, 3, 4]
class_names = ["fast_track", "low", "low_avg", "high_avg", "extended"]

df["target_class"] = np.select(conditions, class_labels, default=4)

# Print out class distributions to verify balance
print("\nTarget Class Balances:")
distribution = df["target_class"].value_counts().sort_index()
for idx, count in distribution.items():
    pct = (count / len(df)) * 100
    print(f"  Class {idx} ({class_names[idx]}): {count:,} records ({pct:.2f}%)")

# ============================================================
# FEATURE ENGINEERING & NATIVE CATEGORICAL SETUP
# ============================================================
# Added structural court fields ('circuit', 'level', 'is_federal') into active features
features = [
    "court_id", "jurisdiction_type", "blocked", "is_appeal", 
    "jury_demand", "quarter_filed", "year_filed",
    "circuit", "level", "is_federal"
]

X = df[features].copy()
y = df["target_class"].copy()

# Enforce explicit pandas categorical typing for object/string columns
# This automatically picks up 'circuit' and 'level' so XGBoost processes them natively
categorical_cols = X.select_dtypes(include=['object']).columns.tolist()
for col in categorical_cols:
    X[col] = X[col].astype('category')

# ============================================================
# DATASET SPLIT
# ============================================================
print("\nExecuting randomized dataset split across classification boundaries...")
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

# ============================================================
# MODEL TRAINING WITH MULTI-CLASS PROBABILITIES
# ============================================================
print("\nInitializing native-categorical XGBClassifier fitting operations...")

clf = XGBClassifier(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    objective="multi:softprob",  # Outputs true probabilities for each class bucket
    num_class=5,
    enable_categorical=True,     # Seamlessly processes high-cardinality judicial text identifiers
    tree_method="hist",
    random_state=42,
    early_stopping_rounds=40
)

# Compute inverse frequency sample weights to balance gradients during tree splits
sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)

clf.fit(
    X_train, y_train,
    sample_weight=sample_weights,  # Blocks the model from ignoring minority buckets
    eval_set=[(X_val, y_val)],
    verbose=50
)

# ============================================================
# METRICS EVALUATION
# ============================================================
print("\nGenerating model classification performance report...")
val_preds = clf.predict(X_val)

accuracy = accuracy_score(y_val, val_preds)
print(f"Final Validation Global Accuracy: {accuracy:.4f}")

print("\nDetailed Performance Breakdown:")
print(classification_report(y_val, val_preds, target_names=class_names))

# ============================================================
# EXPORT ARTIFACTS
# ============================================================
print("Exporting classification pipeline artifacts...")
clf.save_model(str(model_output_path / "case_classifier_xgb_v1.json"))
np.save(str(model_output_path / "class_names.npy"), np.array(class_names))

# Extract and save the exact categorical text vocabulary maps
categorical_categories = {
    col: X_train[col].cat.categories.tolist()
    for col in X_train.select_dtypes(include=['category']).columns
}
with open(model_output_path / "categorical_categories.json", "w") as f:
    json.dump(categorical_categories, f, indent=4)
print("Categorical vocabularies successfully archived!")

print("All optimized framework components exported successfully!")