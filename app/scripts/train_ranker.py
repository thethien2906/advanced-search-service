# /app/scripts/train_ranker.py
import os
import sys
import psycopg2
import pandas as pd
import xgboost as xgb
import numpy as np
import json
import uuid
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from typing import List, Set

# Thêm đường dẫn thư mục gốc của ứng dụng vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.feature_extractor import extract_features, remove_vietnamese_diacritics
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
    """Thiết lập và trả về một kết nối đến cơ sở dữ liệu."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        psycopg2.extras.register_uuid() # Đăng ký kiểu dữ liệu UUID
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to the database: {e}")
        sys.exit(1)

def load_all_categories_for_training(conn) -> List[str]:
    """Tải tất cả tên danh mục để sử dụng trong quá trình trích xuất đặc trưng."""
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "Name" FROM "ProductCategory" WHERE "IsActive" = true;')
            # Chuyển đổi tên danh mục sang chữ thường và không dấu để dễ so khớp
            categories = [remove_vietnamese_diacritics(row[0].lower()) for row in cur.fetchall()]
            return categories
    except Exception as e:
        print(f"ERROR: Could not load categories for training: {e}")
        return []

def create_labeled_dataset(conn) -> pd.DataFrame:
    """
    Tạo bộ dữ liệu huấn luyện bằng cách mô phỏng pipeline GĐ 1 + GĐ 2.
    """
    print("Bắt đầu tạo bộ dữ liệu huấn luyện...")

    # 1. Lấy dữ liệu log thô (Gốc và Click)
    sql_logs = """
        SELECT
            sl."QueryText",
            sl."RankedProductIDs",
            scl."ProductID" as "ClickedProductID"
        FROM "SearchLog" sl
        LEFT JOIN "SearchClickLog" scl ON sl."ID" = scl."SearchID"
        WHERE sl."RankedProductIDs" IS NOT NULL AND jsonb_array_length(sl."RankedProductIDs") > 0;
    """
    df_logs = pd.read_sql_query(sql_logs, conn)

    # 2. "Explode" dữ liệu (từ 1 log -> nhiều hàng)
    training_data = []
    all_product_ids_needed: Set[uuid.UUID] = set()

    for _, row in df_logs.iterrows():
        query_text = row["QueryText"]

        try:
            ranked_ids = json.loads(row["RankedProductIDs"])
        except (json.JSONDecodeError, TypeError):
            continue # Bỏ qua nếu JSON không hợp lệ

        clicked_id_str = str(row["ClickedProductID"]) if row["ClickedProductID"] else None

        for product_id_str in ranked_ids:
            try:
                product_id_uuid = uuid.UUID(product_id_str)
                training_data.append({
                    "QueryText": query_text,
                    "ProductID": product_id_uuid,
                    "clicked": 1 if product_id_str == clicked_id_str else 0
                })
                all_product_ids_needed.add(product_id_uuid)
            except ValueError:
                continue # Bỏ qua nếu ID không phải UUID hợp lệ

    if not training_data:
        print("Không có dữ liệu log nào để huấn luyện.")
        return pd.DataFrame()

    df_train = pd.DataFrame(training_data)

    product_ids_list = [str(pid) for pid in all_product_ids_needed]

    # 3. Lấy dữ liệu GĐ 1 (Feature Gốc) cho tất cả sản phẩm
    sql_goc_features = """
        SELECT
            p."ID" as "ProductID",
            p."Name" as "name",
            p."ProductImages" as "product_images",
            s."Status" as "store_status",
            (
                SELECT array_agg(pc."Name")
                FROM "ProductCategory" pc
                WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(p."CategoryID"))
            ) as "category_names",
            pr."RegionSpecified" AS "sub_region_name",
            p."Embedding"
        FROM "Product" p
        LEFT JOIN "Store" s ON p."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON p."ProvinceID" = pr."ID"
        WHERE p."ID"::text = ANY(%(product_ids)s)
    """
    df_goc_features = pd.read_sql_query(sql_goc_features, conn, params={"product_ids": product_ids_list})

    # 4. Lấy dữ liệu GĐ 2 (Feature tổng hợp) cho tất cả sản phẩm
    sql_agg_features = """
        WITH RECURSIVE product_tree AS (
            SELECT "ID", "ParentID", "ID" as "RootID"
            FROM "Product" WHERE "ID"::text = ANY(%(product_ids)s)
            UNION ALL
            SELECT p."ID", p."ParentID", pt."RootID"
            FROM "Product" p JOIN product_tree pt ON p."ParentID" = pt."ID"
        ),
        leaf_skus AS (
            SELECT
                pt."RootID",
                pv."FinalPrice", pv."SaleCount", pv."Rating", pv."ReviewCount"
            FROM product_tree pt
            JOIN "ProductVariant" pv ON pt."ID" = pv."ID"
            JOIN "Product" p_la ON pt."ID" = p_la."ID"
            WHERE
                p_la."ProductType" = 'ProductVariant'
                AND p_la."IsActive" = true
                AND pv."Quantity" > 0
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = pt."ID" AND p_child."ProductType" = 'ProductVariant'
                )
        )
        SELECT
            "RootID" as "ProductID",
            COALESCE(MIN(ls."FinalPrice"), 0) as "price",
            COALESCE(SUM(ls."SaleCount"), 0) as "sale_count",
            COALESCE(AVG(ls."Rating"), 0.0) as "rating",
            COALESCE(SUM(ls."ReviewCount"), 0) as "review_count"
        FROM leaf_skus ls
        GROUP BY "RootID"
    """
    df_agg_features = pd.read_sql_query(sql_agg_features, conn, params={"product_ids": product_ids_list})

    # 5. Lấy feature is_certified
    sql_cert_features = """
        WITH RECURSIVE master_root AS (
            SELECT "ID", "ParentID", "ID" as "RootID"
            FROM "Product" WHERE "ID"::text = ANY(%(product_ids)s)
            UNION ALL
            SELECT p."ID", p."ParentID", mr."RootID"
            FROM "Product" p JOIN master_root mr ON p."ParentID" = mr."ID"
        ),
        l1_root AS (
            SELECT "RootID" as "ProductID", "ID" as "MasterID" FROM master_root WHERE "ParentID" IS NULL
        )
        SELECT
            lr."ProductID",
            EXISTS (SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = lr."MasterID" AND pc."Status" = 'Approved') as "is_certified"
        FROM l1_root lr
    """
    df_cert_features = pd.read_sql_query(sql_cert_features, conn, params={"product_ids": product_ids_list})

    # 6. Gộp tất cả lại
    df_train = df_train.merge(df_goc_features, on="ProductID", how="left")
    df_train = df_train.merge(df_agg_features, on="ProductID", how="left")
    df_train = df_train.merge(df_cert_features, on="ProductID", how="left")

    # Điền các giá trị NA (cho các sản phẩm không có SKU hợp lệ)
    df_train['price'] = df_train['price'].fillna(0)
    df_train['sale_count'] = df_train['sale_count'].fillna(0)
    df_train['rating'] = df_train['rating'].fillna(0.0)
    df_train['review_count'] = df_train['review_count'].fillna(0)
    df_train['is_certified'] = df_train['is_certified'].fillna(False)

    print(f"Tạo xong bộ dữ liệu. Tổng cộng {len(df_train)} hàng huấn luyện.")
    return df_train


def calculate_relevance_score(query_embedding: np.ndarray, product_embedding_str: str) -> float:
    if not product_embedding_str:
        return 0.0
    try:
        # Embedding được lưu dưới dạng chuỗi "[1.2, 3.4, ...]"
        product_embedding = np.array(json.loads(product_embedding_str))
        if product_embedding.shape != query_embedding.shape:
             return 0.0
        # Tính cosine similarity (1 - cosine distance)
        return 1 - cosine(query_embedding, product_embedding)
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def train_xgboost_model(df: pd.DataFrame, all_categories: List[str]):
    if df.empty:
        print("WARNING: Training data is empty. Skipping model training.")
        return

    print("Pre-calculating query embeddings...")
    unique_queries = df["QueryText"].unique()
    query_embeddings = {query: EMBEDDING_MODEL.encode(query, normalize_embeddings=True) for query in unique_queries}

    print("Calculating relevance scores (semantic_similarity) for the dataset...")
    df['relevance_score'] = df.apply(
        lambda row: calculate_relevance_score(query_embeddings[row['QueryText']], row['Embedding']),
        axis=1
    )

    print("Starting feature extraction for the training dataset...")

    feature_vectors = df.apply(
        lambda row: extract_features({
            "relevance_score": row["relevance_score"],
            "name": row["name"],
            "rating": row["rating"],
            "review_count": row["review_count"],
            "sale_count": row["sale_count"],
            "price": row["price"],
            "product_images": row["product_images"],
            "is_certified": row["is_certified"],
            "store_status": row["store_status"],
            "category_names": row["category_names"],
            "sub_region_name": row["sub_region_name"]
        }, row["QueryText"], all_categories),
        axis=1
    )

    X_train = np.array(feature_vectors.tolist())
    y_train = df["clicked"].values

    print(f"Feature matrix shape: {X_train.shape}")
    print(f"Labels shape: {y_train.shape}")

    print(f"Number of clicked items in training data: {np.sum(y_train)}")
    if np.sum(y_train) == 0:
        print("WARNING: No clicks found in the training data. The model may not learn effectively.")
        # Thoát nếu không có dữ liệu dương để tránh lỗi chia cho 0
        return

    # Tính toán tỷ lệ giữa số lượng mẫu âm (0) và mẫu dương (1)
    scale_pos_weight = np.sum(y_train == 0) / np.sum(y_train == 1)
    print(f"Calculated scale_pos_weight: {scale_pos_weight:.2f}")

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_SCHEMA)

    # Thêm tham số scale_pos_weight vào đây
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'logloss',
        'max_depth': 4,
        'eta': 0.1,
        'scale_pos_weight': scale_pos_weight # <-- THAM SỐ QUAN TRỌNG
    }

    print("Training the XGBoost ranker with balanced weights...")
    model = xgb.train(params, dtrain, num_boost_round=100)

    model.save_model(MODEL_OUTPUT_PATH)
    print(f"✅ New ranker model successfully trained and saved to {MODEL_OUTPUT_PATH}")

    try:
        feature_importance = model.get_score(importance_type='gain')
        print("Feature Importance (Gain):", feature_importance)
    except Exception as e:
        print(f"Could not calculate feature importance: {e}")

def main():
    conn = get_db_connection()
    try:
        all_categories = load_all_categories_for_training(conn)
        if not all_categories:
            print("Could not load categories, aborting training.")
            return

        labeled_data = create_labeled_dataset(conn)
        train_xgboost_model(labeled_data, all_categories)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()