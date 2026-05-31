"""
Judicial Case Duration Inference Script.

This script reloads the trained XGBoost multi-class framework and runs 
probabilistic predictive inference on a batch dataset configuration.
"""

import sys
import json  # Added to parse the categorical schema mapping
import numpy as np
import pandas as pd
from pathlib import Path
from xgboost import XGBClassifier

# ============================================================
# PATHS & CONFIGURATION
# ============================================================
# Establish proper directory traversal to look up model artifacts
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_training.prep_for_inference import prep_for_inference

MODEL_DIR = PROJECT_ROOT / "model_training" / "models"
model_file = MODEL_DIR / "case_classifier_xgb_v1.json"
class_names_file = MODEL_DIR / "class_names.npy"
categories_file = MODEL_DIR / "categorical_categories.json"  # Added file path
court_file = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"

# Verify artifacts exist before initializing memory
if not model_file.exists() or not class_names_file.exists() or not categories_file.exists():
    raise FileNotFoundError(
        f"Required model artifacts missing from {MODEL_DIR.as_posix()}. "
        "Please execute your training script first to train, export, and map categories."
    )

# ============================================================
# LOAD MODEL & METADATA
# ============================================================
print("Reloading XGBoost classifier model into memory...")
clf = XGBClassifier()
clf.load_model(str(model_file))

print("Loading operational class mappings...")
class_names = np.load(str(class_names_file), allow_pickle=True).tolist()
print(f"Loaded Target Buckets: {class_names}")

print("Loading categorical feature vocabularies...")  # Loaded categories map
with open(categories_file, "r") as f:
    categorical_categories = json.load(f)

# Define the exact features and order the model was trained on
FEATURES = [
    "court_id", "blocked", "is_appeal", 
    "jury_demand", "quarter_filed", "year_filed",
    "circuit", "level", "is_federal", "jurisdiction", "cause", "nature_of_suit"
]

answered = False
while not answered:
    response = input("Specify the relative path to the chosen dataset in parquet format (right click on the chosen file and choose 'Copy relative path')\n")
    file_path = PROJECT_ROOT / response
    if file_path.exists():
        answered = True
        docket_list = prep_for_inference(file_path, court_file=court_file)
        docket_file = str(file_path).split("\\")[-1]
    else:
        print("The file path has not been recognized. Please, retry")

print("\nParsing raw profile data into structural model inputs...")
df_input = pd.DataFrame(docket_list)

if df_input.empty:
    print("No records found to process.")
    sys.exit(0)

df_input = df_input[FEATURES]
# Reconstruct explicit category shapes for all categorical features
for col, categories in categorical_categories.items():
    if col in df_input.columns:
        cat_dtype = pd.CategoricalDtype(categories=categories, ordered=False)
        df_input[col] = df_input[col].astype(cat_dtype)

# ============================================================
# INFERENCE OPERATIONS
# ============================================================
print("Executing batch probabilistic model inference...")
df_input['is_federal'] = df_input['is_federal'].fillna(False).astype(bool)
clf.set_params(enable_categorical=True) 

# Run predictions for ALL records simultaneously
pred_class_indices = clf.predict(df_input)
predicted_buckets = [class_names[idx] for idx in pred_class_indices]

# Extract prediction probabilities for all records to track confidence scores
probabilities = clf.predict_proba(df_input)
confidence_scores = [prob[idx] * 100 for prob, idx in zip(probabilities, pred_class_indices)]
buckets = {"fast_track" : "x <90",
           "low" : "90<= x <365",
           "avg": "365<= x <730",
           "extended" : "730>="
}
# Create the presentation table by copying features and appending results
df_output = df_input.copy()
df_output['expected_resolution'] = predicted_buckets
for value in buckets:
    df_output.loc[df_output["expected_resolution"] == value, "days_resolution"] = buckets[value]
df_output['confidence_pct'] = confidence_scores


df_output.to_parquet(PROJECT_ROOT/"predictions"/f"predicted_resolution_{docket_file}.parquet", engine = "pyarrow")

# ============================================================
# DISPLAY OPERATIONAL INSIGHTS
# ============================================================
print("\n" + "="*120)
print("                                      BATCH JUDICIAL TIMELINE ASSESSMENT REPORT                                       ")
print("="*120)

# Adjust pandas display parameters to prevent row truncation or line wrapping in the terminal
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.max_rows', None)

# Print out the complete structured table matching all inputs to their expected classes
print(df_output.to_string(index=False))
print("="*120)

# Display a high-level operational summary of the batch run
print("\nPrediction Distribution Summary:")
print(df_output['expected_resolution'].value_counts().to_string())
print("="*120)