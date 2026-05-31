"""
Judicial Case Duration Inference Script.

This script reloads the trained XGBoost multi-class framework and runs 
probabilistic predictive inference on a sample upcoming case configuration.
"""

import sys
import json  # 1. Added to parse the categorical schema mapping
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

MODEL_DIR = PROJECT_ROOT / "prediction" / "models"
model_file = MODEL_DIR / "case_classifier_xgb_v1.json"
class_names_file = MODEL_DIR / "class_names.npy"
categories_file = MODEL_DIR / "categorical_categories.json"  # 1. Added file path

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

print("Loading categorical feature vocabularies...")  # 2. Loaded categories map
with open(categories_file, "r") as f:
    categorical_categories = json.load(f)

# Define the exact features and order the model was trained on
FEATURES = [
    "court_id", "jurisdiction_type", "blocked", "is_appeal", 
    "jury_demand", "quarter_filed", "year_filed",
    "circuit", "level", "is_federal"
]

# ============================================================
# SAMPLE INCOMING CASENOTE FOR PREDICTION
# ============================================================
sample_case_data = {
    "court_id": "NYSD",              # Southern District of New York
    "jurisdiction_type": "Federal",
    "blocked": False,                # Is the case currently stayed or blocked?
    "is_appeal": False,              # Is this an appellate action or initial filing?
    "jury_demand": True,             # Did the plaintiff request a jury trial?
    "quarter_filed": "q2",
    "year_filed": 2026,
    "circuit": "2",                  # Geographic court metadata
    "level": "state",                # Successfully mapped to the training level vocabulary list!
    "is_federal": True
}

print("\nParsing raw profile data into structural model inputs...")
# Convert single record dictionary into a pandas DataFrame row
df_input = pd.DataFrame([sample_case_data])

# Ensure features are arranged in the precise order specified during training
df_input = df_input[FEATURES]

# 3. REPLACED FIXED ENFORCEMENT: Reconstruct explicit category shapes
for col, categories in categorical_categories.items():
    if col in df_input.columns:
        cat_dtype = pd.CategoricalDtype(categories=categories, ordered=False)
        df_input[col] = df_input[col].astype(cat_dtype)

# ============================================================
# INFERENCE OPERATIONS
# ============================================================
print("Executing probabilistic model inference...")

# 1. Generate the standard discrete prediction (returns integer 0-4)
pred_class_idx = clf.predict(df_input)[0]
predicted_bucket_name = class_names[pred_class_idx]

# 2. Extract soft probability array for comprehensive risk parsing
probabilities = clf.predict_proba(df_input)[0]

# ============================================================
# DISPLAY OPERATIONAL INSIGHTS
# ============================================================
print("\n" + "="*60)
print("             JUDICIAL TIMELINE ASSESSMENT REPORT          ")
print("="*60)
print(f"Assigned Target Classification: Class {pred_class_idx} -> {predicted_bucket_name.upper()}")
print("-"*60)
print("Complete Operational Probability Matrix:")

# Render out clean metrics for software logs or front-end visualization engines
for idx, prob in enumerate(probabilities):
    pct_val = prob * 100
    # Create a simple visual text-based loading bar for contextual visibility
    bar_length = int(pct_val // 5)
    progress_bar = "█" * bar_length + "░" * (20 - bar_length)
    
    print(f"  [{progress_bar}] {class_names[idx]:<12}: {pct_val:6.2f}%")

print("="*60)

if predicted_bucket_name == "extended":
    print("WARNING: This profile matches historical multi-year litigations.")
    print("Recommendation: Prepare for a case longer than 1000 days")
elif predicted_bucket_name == "high_avg":
    print("Case will likely last between 519 and 1000 days")
elif predicted_bucket_name == "low_avg":
    print("Case will likely last between 210 and 518 days")
elif predicted_bucket_name == "low":
    print("Case will likely last between 90 and 209 days")
elif predicted_bucket_name == "fast_track":
    print("INFO: High-speed resolution pattern identified.")
    print("Resolution will most likely take less than 90 days")