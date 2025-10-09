# /app/scripts/seed_click.py

import os
import sys
import json
import uuid
import random # Thêm thư viện random
from datetime import datetime, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras

# Thêm đường dẫn thư mục gốc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.search_constants import SUB_REGION_KEYWORDS
# Thêm hàm remove_vietnamese_diacritics để so sánh tên không dấu
from services.feature_extractor import remove_vietnamese_diacritics

# Tải biến môi trường
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        psycopg2.extras.register_uuid()
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to the database: {e}")
        sys.exit(1)

def get_product_details(cursor, product_ids):
    """Lấy thông tin chi tiết của các sản phẩm từ ID."""
    if not product_ids:
        return {}
    string_ids = [str(pid) for pid in product_ids]
    query = """
    SELECT p."ID", p."Name", pr."SubRegion"
    FROM "Product" p
    LEFT JOIN "Province" pr ON p."ProvinceID" = pr."ID"
    WHERE p."ID"::text = ANY(%s)
    """
    cursor.execute(query, (string_ids,))
    product_map = {}
    for row in cursor.fetchall():
        product_map[row[0]] = {"name": row[1], "sub_region": row[2]}
    return product_map

def generate_clicks():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Lấy tất cả search log chưa có click
        cur.execute("""
            SELECT sl."ID", sl."QueryText", sl."RankedProductIDs"
            FROM "SearchLog" sl
            LEFT JOIN "SearchClickLog" scl ON sl."ID" = scl."SearchID"
            WHERE scl."ID" IS NULL
        """)
        search_logs = cur.fetchall()

        if not search_logs:
            print("Không có search log mới nào cần tạo click giả định.")
            return

        print(f"Tìm thấy {len(search_logs)} search log cần xử lý...")
        clicks_generated = 0

        for log_id, query_text, ranked_ids_data in search_logs:
            query_unaccented = remove_vietnamese_diacritics(query_text)

            if isinstance(ranked_ids_data, str):
                ranked_ids = json.loads(ranked_ids_data)
            else:
                ranked_ids = ranked_ids_data or []

            if not ranked_ids:
                continue

            product_details_map = get_product_details(cur, [uuid.UUID(pid) for pid in ranked_ids])
            product_to_click = None
            click_reason = "Không có quy tắc nào được áp dụng"

            # ======================================================================
            # LOGIC TẠO CLICK MỚI THÔNG MINH HƠN
            # ======================================================================

            # Quy tắc 1: Ưu tiên click vào sản phẩm có tên khớp chính xác (không dấu)
            for pid_str in ranked_ids:
                pid_uuid = uuid.UUID(pid_str)
                product = product_details_map.get(pid_uuid)
                if product:
                    product_name_unaccented = remove_vietnamese_diacritics(product["name"])
                    # Nếu query không dấu là một phần của tên sản phẩm không dấu
                    if query_unaccented in product_name_unaccented:
                        product_to_click = pid_str
                        click_reason = f"Khớp tên không dấu: '{query_unaccented}' in '{product_name_unaccented}'"
                        break

            # Quy tắc 2: Nếu không khớp tên, tìm sản phẩm khớp vùng miền trong top 3
            if not product_to_click:
                detected_sub_region = None
                for sub_region, keywords in SUB_REGION_KEYWORDS.items():
                    # Check cả query có dấu và không dấu
                    if any(keyword in query_text.lower() for keyword in keywords) or any(remove_vietnamese_diacritics(keyword) in query_unaccented for keyword in keywords):
                        detected_sub_region = sub_region
                        break

                if detected_sub_region:
                    for pid_str in ranked_ids[:3]:
                        pid_uuid = uuid.UUID(pid_str)
                        product = product_details_map.get(pid_uuid)
                        if product and product["sub_region"] == detected_sub_region:
                            product_to_click = pid_str
                            click_reason = f"Khớp vùng miền '{detected_sub_region}' trong top 3"
                            break

            # Quy tắc 3 (Mới): Nếu vẫn không tìm thấy, click ngẫu nhiên vào top 2 kết quả đầu tiên
            # Điều này giúp tạo thêm nhãn positive, giả định rằng kết quả đầu thường tốt
            if not product_to_click and ranked_ids:
                 # 30% cơ hội click vào kết quả đầu tiên
                if random.random() < 0.3:
                    product_to_click = ranked_ids[0]
                    click_reason = "Click ngẫu nhiên vào top 1 (giả định kết quả tốt)"

            # ======================================================================

            if product_to_click:
                click_position = ranked_ids.index(product_to_click)
                insert_sql = """
                INSERT INTO "SearchClickLog" ("ID", "SearchID", "ProductID", "ClickPosition", "ClickedAt")
                VALUES (%s, %s, %s, %s, %s)
                """
                cur.execute(insert_sql, (uuid.uuid4(), log_id, uuid.UUID(product_to_click), click_position, datetime.now(timezone.utc)))
                print(f"✅ Đã tạo click cho query '{query_text}' -> ID: {product_to_click} (Lý do: {click_reason})")
                clicks_generated += 1

        conn.commit()
        print(f"\nHoàn tất! Đã tạo thành công {clicks_generated} click giả định.")

    except Exception as e:
        conn.rollback()
        print(f"Đã xảy ra lỗi: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    generate_clicks()