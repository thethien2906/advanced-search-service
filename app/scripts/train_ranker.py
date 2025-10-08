import os
import sys
import psycopg2
import pandas as pd
import xgboost as xgb
import numpy as np
from dotenv import load_dotenv
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine

# Add the app directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.feature_extractor import extract_features
from core.config import settings
from services.search_constants import FEATURE_SCHEMA

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
MODEL_OUTPUT_PATH = "app/models/ranker.xgb"

print("Loading sentence-transformer model for training...")
EMBEDDING_MODEL = SentenceTransformer(settings.MODEL_NAME)
print("Model loaded.")

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

    # CẬP NHẬT: Thêm pr."Name" và pr."Region" vào câu SQL
    sql_query = """
    WITH SearchResults AS (
        SELECT
            sl."ID" AS "SearchID",
            sl."QueryText",
            value AS "ProductID",
            p."Name" AS "ProductName",
            p."Rating",
            p."ReviewCount",
            p."SaleCount",
            p."CategoryID",
            p."ProductImages",
            p."Embedding",
            pv."BasePrice" AS "price",
            s."Status" AS "StoreStatus",
            pr."Name" AS "ProvinceName", -- LẤY TÊN TỈNH
            pr."Region" AS "RegionName",   -- LẤY TÊN VÙNG MIỀN
            EXISTS(SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = p."ID") AS "IsCertified"
        FROM "SearchLog" sl,
        LATERAL jsonb_array_elements_text(sl."RankedProductIDs")
        JOIN "Product" p ON p."ID" = value::uuid
        JOIN "ProductVariant" pv ON p."ID" = pv."ProductID"
        JOIN "Store" s ON p."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON p."ProvinceID" = pr."ID"
    )
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

def calculate_relevance_score(query_embedding: np.ndarray, product_embedding_str: str) -> float:
    # ... (Giữ nguyên hàm này)
    if not product_embedding_str:
        return 0.0
    try:
        product_embedding = np.array(eval(product_embedding_str))
        if product_embedding.shape != query_embedding.shape:
             return 0.0
        return 1 - cosine(query_embedding, product_embedding)
    except:
        return 0.0


def train_xgboost_model(df: pd.DataFrame):
    if df.empty:
        print("WARNING: Training data is empty. Skipping model training.")
        return

    print("Pre-calculating query embeddings...")
    unique_queries = df["QueryText"].unique()
    query_embeddings = {query: EMBEDDING_MODEL.encode(query, normalize_embeddings=True) for query in unique_queries}

    print("Calculating relevance scores for the dataset...")
    df['relevance_score'] = df.apply(
        lambda row: calculate_relevance_score(query_embeddings[row['QueryText']], row['Embedding']),
        axis=1
    )

    print("Starting feature extraction for the training dataset...")

    # ======================================================================
    # SỬA LỖI QUAN TRỌNG TẠI ĐÂY
    # ======================================================================
    feature_vectors = df.apply(
        lambda row: extract_features({
            "relevance_score": row["relevance_score"],
            "rating": row["Rating"],
            "review_count": row["ReviewCount"],
            "sale_count": row["SaleCount"],
            "price": row["price"],
            "product_images": row["ProductImages"],
            "is_certified": row["IsCertified"],
            "store_status": row["StoreStatus"],
            "category_id": row["CategoryID"],
            "province_name": row["ProvinceName"], # THÊM DỮ LIỆU
            "region_name": row["RegionName"]   # THÊM DỮ LIỆU
        }, row["QueryText"]),
        axis=1
    )
    # ======================================================================

    X_train = np.array(feature_vectors.tolist())
    y_train = df["clicked"].values

    print(f"Feature matrix shape: {X_train.shape}")
    print(f"Labels shape: {y_train.shape}")

    print(f"Number of clicked items in training data: {np.sum(y_train)}")
    if np.sum(y_train) == 0:
        print("WARNING: No clicks found in the training data. The model may not learn effectively.")

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_SCHEMA)
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

    feature_importance = model.get_score(importance_type='gain')
    print("Feature Importance (Gain):", feature_importance)

def main():
    labeled_data = create_labeled_dataset()
    train_xgboost_model(labeled_data)

if __name__ == "__main__":
    main()