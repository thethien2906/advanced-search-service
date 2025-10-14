# /app/scripts/seed_data.py
import os
import sys
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv

# Thêm đường dẫn thư mục gốc của ứng dụng vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.embedding_service import EmbeddingService
from app.models.pydantic_models import EmbeddingRequest

# Tải các biến môi trường từ file .env
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Thiết lập và trả về một kết nối đến cơ sở dữ liệu."""
    print("Đang kết nối đến cơ sở dữ liệu...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Kết nối cơ sở dữ liệu thành công.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"LỖI NGHIÊM TRỌNG: Không thể kết nối đến cơ sở dữ liệu: {e}")
        exit(1)

def embed_existing_products():
    """
    Tạo và CẬP NHẬT LẠI embedding cho TẤT CẢ các sản phẩm trong cơ sở dữ liệu
    dựa trên logic mới nhất trong EmbeddingService.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    print("Khởi tạo Dịch vụ Embedding...")
    embedding_service = EmbeddingService()
    print("Dịch vụ đã được khởi tạo.")

    try:
        print("\n--- Bắt đầu quá trình TÁI TẠO Embedding cho toàn bộ sản phẩm ---")

        # Câu truy vấn SQL phức tạp để thu thập tất cả dữ liệu cần thiết
        # **ĐÃ SỬA LỖI:** Xóa bỏ điều kiện 'WHERE p."Embedding" IS NULL' để
        # đảm bảo tất cả sản phẩm đều được xử lý lại.
        sql_query = """
        SELECT
            p."ID" as product_id,
            p."Name" as product_name,
            p."Description" as product_description,
            p."TypeProduct" as product_type_name,
            p."Material" as product_material,
            s."StoreName" as store_name,
            prov."Name" as province_name,
            prov."Region" as region_name,
            prov."RegionSpecified" as sub_region_name,
            ps."Title" as product_story_title,
            (SELECT "ContentData" FROM "ProductStoryContent" WHERE "ProductStoryID" = ps."ID" LIMIT 1) as product_story_detail,
            (SELECT "ContentData" FROM "StoreStoryContent" WHERE "StoreStoryID" = ss."ID" LIMIT 1) as store_story_detail,
            ARRAY(SELECT "VariantName" FROM "ProductVariant" WHERE "ProductID" = p."ID") as variant_names,
            (
                SELECT array_agg(pc."Name")
                FROM "ProductCategory" pc
                WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(p."CategoryID"))
            ) as product_category_names
        FROM "Product" p
        LEFT JOIN "Store" s ON p."StoreID" = s."ID"
        LEFT JOIN "Province" prov ON p."ProvinceID" = prov."ID"
        LEFT JOIN "ProductStory" ps ON p."ID" = ps."ProductID"
        LEFT JOIN "StoreStory" ss ON p."StoreID" = ss."StoreID";
        """

        cur.execute(sql_query)
        products_to_embed = cur.fetchall()

        if not products_to_embed:
            print("Không tìm thấy sản phẩm nào để tạo embedding. Vui lòng kiểm tra dữ liệu.")
            return

        print(f"Tìm thấy {len(products_to_embed)} sản phẩm cần TÁI TẠO embedding...")

        for product_data in products_to_embed:
            product_dict = dict(product_data)
            print(f"Đang xử lý sản phẩm: {product_dict['product_name']} (ID: {product_dict['product_id']})")

            # Tạo đối tượng request cho embedding service
            embedding_request = EmbeddingRequest(
                product_name=product_dict.get('product_name'),
                product_description=product_dict.get('product_description'),
                product_story_title=product_dict.get('product_story_title'),
                product_story_detail=product_dict.get('product_story_detail'),
                product_category_names=product_dict.get('product_category_names'),
                product_type_name=product_dict.get('product_type_name'),
                product_made_by=product_dict.get('product_material'),
                variant_names=product_dict.get('variant_names'),
                store_name=product_dict.get('store_name'),
                store_story_detail=product_dict.get('store_story_detail'),
                province_name=product_dict.get('province_name'),
                region_name=product_dict.get('region_name'),
                sub_region_name=product_dict.get('sub_region_name')
            )

            # Gọi logic create_embedding mới nhất
            embedding_vector = embedding_service.create_embedding(embedding_request)
            embedding_string = str(embedding_vector)

            # Cập nhật sản phẩm với embedding mới
            update_cur = conn.cursor()
            update_cur.execute(
                'UPDATE "Product" SET "Embedding" = %s WHERE "ID" = %s',
                (embedding_string, product_dict['product_id'])
            )
            update_cur.close()

        conn.commit()
        print(f"\n--- Quá trình TÁI TẠO Embedding hoàn tất! Đã cập nhật {len(products_to_embed)} sản phẩm. ---")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- LỖI: Quá trình tạo embedding thất bại. Đang hoàn tác các thay đổi. ---")
        print(error)
        conn.rollback()
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
        print("Đã đóng kết nối cơ sở dữ liệu.")

if __name__ == "__main__":
    psycopg2.extras.register_uuid()
    if not DATABASE_URL:
        print("LỖI NGHIÊM TRỌNG: Biến môi trường DATABASE_URL chưa được thiết lập.")
    else:
        embed_existing_products()