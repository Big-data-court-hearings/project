"""
Judicial Case Duration Inference Script - Binary Classification Edition.

This script reloads the trained XGBoost binary classifier and predicts
whether a judicial case is likely to be long (>=365 days) or not.
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
import xgboost as xgb

# ============================================================
# PATHS & CONFIGURATION
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_training.prep_for_inference import prep_for_inference

MODEL_DIR        = PROJECT_ROOT / "model_training" / "models"
model_file       = MODEL_DIR / "binary_model.ubj"
court_stats_file = MODEL_DIR / "court_stats.parquet"
court_file       = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"

# Decision threshold tuned for high recall on long cases
LONG_CASE_THRESHOLD = 0.34

for path in [model_file, court_stats_file]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required artifact missing: {path.as_posix()}. "
            "Please run the training script first."
        )

# ============================================================
# LOAD MODEL
# ============================================================
print("Loading binary classifier...")
bst = xgb.Booster()
bst.load_model(str(model_file))

FEATURES = [
    "court_id", "blocked", "is_appeal", "jury_demand",
    "quarter_filed", "circuit", "level", "is_federal", "jurisdiction",
    "court_censoring_rate", "court_case_volume",
]

# ============================================================
# INPUT
# ============================================================
answered = False
while not answered:
    response = input("Specify the relative path to the chosen dataset in parquet format:\n")
    file_path = PROJECT_ROOT / response
    if file_path.exists():
        answered = True
        docket_list = prep_for_inference(
            file_path,
            court_file=court_file,
            court_stats_file=court_stats_file,
        )
        docket_file = file_path.name
    else:
        print("The file path has not been recognized. Please, retry")

print("\nParsing raw profile data into structural model inputs...")
df_input = pd.DataFrame(docket_list)

if df_input.empty:
    print("No records found to process.")
    sys.exit(0)

df_input = df_input[FEATURES].copy()

for col in df_input.select_dtypes(include=["object"]).columns:
    df_input[col] = df_input[col].astype("category")

df_input["is_federal"] = df_input["is_federal"].fillna(False).astype(bool)

# ============================================================
# INFERENCE
# ============================================================
print("Running binary classification inference...")

dmatrix_inference = xgb.DMatrix(df_input, enable_categorical=True)
predicted_proba   = bst.predict(dmatrix_inference)
predicted_label   = (predicted_proba >= LONG_CASE_THRESHOLD).astype(int)

# ============================================================
# OUTPUT
# ============================================================
df_output = df_input.copy()
df_output["long_case_probability"] = np.round(predicted_proba, 4)
df_output["predicted_long"]        = predicted_label
df_output["predicted_class"]       = np.where(predicted_label == 1, "LONG (>=365d)", "NOT LONG (<365d)")

output_parquet_path = PROJECT_ROOT / "predictions" / f"binary_{docket_file}"
output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
df_output.to_parquet(output_parquet_path, engine="pyarrow", index=False)

# ============================================================
# REPORT
# ============================================================
print("\n" + "="*120)
print("                              BATCH JUDICIAL CASE DURATION CLASSIFICATION REPORT")
print("="*120)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)
pd.set_option("display.max_rows", None)

print(df_output.to_string(index=False))
print("="*120)

n_long     = predicted_label.sum()
n_not_long = len(predicted_label) - n_long
print(f"\nSummary: {n_long} cases flagged as LONG ({100*n_long/len(predicted_label):.1f}%) | "
      f"{n_not_long} NOT LONG ({100*n_not_long/len(predicted_label):.1f}%)")
print(f"Decision threshold: {LONG_CASE_THRESHOLD} (tuned for high recall on long cases)")
print(f"\nPredictions saved to: {output_parquet_path.as_posix()}")
