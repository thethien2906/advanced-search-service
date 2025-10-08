import os
import sys
import psycopg2
import json
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
    Tạo và cập nhật embedding cho các sản phẩm trong cơ sở dữ liệu dựa trên
    dữ liệu đã được nạp từ Sample Data.txt.
    """
    conn = get_db_connection()
    # Sử dụng cursor factory để trả về kết quả dưới dạng dictionary
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    print("Khởi tạo Dịch vụ Embedding...")
    embedding_service = EmbeddingService()
    print("Dịch vụ đã được khởi tạo.")

    try:
        print("\n--- Bắt đầu quá trình tạo Embedding cho sản phẩm ---")

        # Câu truy vấn SQL phức tạp để thu thập tất cả dữ liệu cần thiết
        sql_query = """
        SELECT
            p."ID" as product_id,
            p."Name" as product_name,
            p."Description" as product_description,
            p."TypeProduct" as product_type_name,
            p."MadeBy" as product_made_by,
            s."StoreName" as store_name,
            prov."Name" as province_name,
            prov."Region" as region_name,
            ps."Title" as product_story_title,
            -- Lấy nội dung câu chuyện sản phẩm (giả sử chỉ có 1)
            (SELECT "ContentData" FROM "ProductStoryContent" WHERE "ProductStoryID" = ps."ID" LIMIT 1) as product_story_detail,
            -- Lấy nội dung câu chuyện cửa hàng (giả sử chỉ có 1)
            (SELECT "ContentData" FROM "StoreStoryContent" WHERE "StoreStoryID" = ss."ID" LIMIT 1) as store_story_detail,
            -- Tổng hợp tên các biến thể thành một mảng
            ARRAY(SELECT "VariantName" FROM "ProductVariant" WHERE "ProductID" = p."ID") as variant_names,
            -- Tổng hợp tên các danh mục thành một mảng
            (
                SELECT array_agg(pc."Name")
                FROM "ProductCategory" pc
                WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(p."CategoryID"))
            ) as product_category_names
        FROM "Product" p
        LEFT JOIN "Store" s ON p."StoreID" = s."ID"
        LEFT JOIN "Province" prov ON p."ProvinceID" = prov."ID"
        LEFT JOIN "ProductStory" ps ON p."ID" = ps."ProductID"
        LEFT JOIN "StoreStory" ss ON p."StoreID" = ss."StoreID"
        WHERE p."Embedding" IS NULL;
        """

        cur.execute(sql_query)
        products_to_embed = cur.fetchall()

        if not products_to_embed:
            print("Tất cả sản phẩm đã có embedding.")
            return

        print(f"Tìm thấy {len(products_to_embed)} sản phẩm cần tạo embedding...")

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
                product_made_by=product_dict.get('product_made_by'),
                variant_names=product_dict.get('variant_names'),
                store_name=product_dict.get('store_name'),
                store_story_detail=product_dict.get('store_story_detail'),
                province_name=product_dict.get('province_name'),
                region_name=product_dict.get('region_name')
            )

            # Tạo embedding vector
            embedding_vector = embedding_service.create_enhanced_embedding(embedding_request)
            embedding_string = str(embedding_vector)

            # Cập nhật sản phẩm với embedding mới
            update_cur = conn.cursor()
            update_cur.execute(
                'UPDATE "Product" SET "Embedding" = %s WHERE "ID" = %s',
                (embedding_string, product_dict['product_id'])
            )
            update_cur.close()


        conn.commit()
        print(f"\n--- Quá trình tạo Embedding hoàn tất! Đã cập nhật {len(products_to_embed)} sản phẩm. ---")

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
    # Đảm bảo psycopg2.extras được đăng ký
    psycopg2.extras.register_uuid()
    if not DATABASE_URL:
        print("LỖI NGHIÊM TRỌNG: Biến môi trường DATABASE_URL chưa được thiết lập.")
    else:
        embed_existing_products()