# /app/scripts/train_ranker.py
import os
import sys
import psycopg2
import pandas as pd
import xgboost as xgb
import numpy as np
from dotenv import load_dotenv
from typing import List, Dict, Any

# Add the app directory to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.feature_extractor import extract_features, FEATURE_SCHEMA

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
MODEL_OUTPUT_PATH = "app/models/ranker.xgb"

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to the database: {e}")
        sys.exit(1)

def create_labeled_dataset() -> pd.DataFrame:
    """
    Creates a labeled dataset by joining search logs with product and click data.
    """
    print("Connecting to the database to create a labeled dataset...")
    conn = get_db_connection()

    # CORRECTED SQL QUERY: Replaced unnest with jsonb_array_elements_text
    sql_query = """
    WITH SearchResults AS (
        -- Use jsonb_array_elements_text to correctly expand the JSON array of product IDs
        SELECT
            sl."ID" AS "SearchID",
            sl."QueryText",
            value AS "ProductID", -- The expanded product ID is now in the 'value' column
            p."Name" AS "ProductName",
            p."Rating",
            p."ReviewCount",
            p."SaleCount",
            p."CategoryID",
            p."ProductImages",
            pv."BasePrice" AS "price",
            s."Status" AS "StoreStatus",
            EXISTS(SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = p."ID") AS "IsCertified"
        FROM "SearchLog" sl,
        -- This function correctly unnests the JSONB array into text rows
        LATERAL jsonb_array_elements_text(sl."RankedProductIDs")
        -- Join the expanded product ID with the Product table
        JOIN "Product" p ON p."ID" = value::uuid
        JOIN "ProductVariant" pv ON p."ID" = pv."ProductID"
        JOIN "Store" s ON p."StoreID" = s."ID"
    )
    -- Left join with click logs remains the same to create the 'clicked' label
    SELECT
        sr.*,
        CASE WHEN scl."ID" IS NOT NULL THEN 1 ELSE 0 END AS "clicked"
    FROM SearchResults sr
    LEFT JOIN "SearchClickLog" scl
        ON sr."SearchID" = scl."SearchID" AND sr."ProductID"::uuid = scl."ProductID";
    """

    try:
        df = pd.read_sql_query(sql_query, conn)
        print(f"Successfully fetched {len(df)} records for training.")
        return df
    except Exception as e:
        print(f"ERROR: Failed to fetch training data: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def train_xgboost_model(df: pd.DataFrame):
    """
    Trains an XGBoost ranking model from the prepared DataFrame.
    """
    if df.empty:
        print("WARNING: Training data is empty. Skipping model training.")
        return

    print("Starting feature extraction for the training dataset...")

    feature_vectors = df.apply(
        lambda row: extract_features({
            "relevance_score": 0,
            "rating": row["Rating"],
            "review_count": row["ReviewCount"],
            "sale_count": row["SaleCount"],
            "price": row["price"],
            "product_images": row["ProductImages"],
            "is_certified": row["IsCertified"],
            "store_status": row["StoreStatus"],
            "category_id": row["CategoryID"]
        }, row["QueryText"]),
        axis=1
    )

    X_train = np.array(feature_vectors.tolist())
    y_train = df["clicked"].values

    print(f"Feature matrix shape: {X_train.shape}")
    print(f"Labels shape: {y_train.shape}")

    dtrain = xgb.DMatrix(X_train, label=y_train)
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'logloss',
        'max_depth': 4,
        'eta': 0.1
    }

    print("Training the XGBoost ranker...")
    model = xgb.train(params, dtrain, num_boost_round=100)

    model.save_model(MODEL_OUTPUT_PATH)
    print(f"✅ New ranker model successfully trained and saved to {MODEL_OUTPUT_PATH}")

def main():
    """Main function to run the training pipeline."""
    labeled_data = create_labeled_dataset()
    train_xgboost_model(labeled_data)

if __name__ == "__main__":
    main()