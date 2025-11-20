# /app/scripts/seed_documents.py
import os
import sys
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv

# Thêm đường dẫn thư mục gốc của ứng dụng vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.embedding_service import EmbeddingService

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

def embed_existing_documents():
    """
    Tạo và cập nhật embedding cho tất cả các Document trong database.
    Script này nên chạy sau khi cột Embedding đã được thêm vào bảng Document.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    print("Khởi tạo Dịch vụ Embedding...")
    embedding_service = EmbeddingService()
    print("Dịch vụ đã được khởi tạo.")

    try:
        print("\n--- Bắt đầu quá trình TẠO Embedding cho Document ---")

        # Truy vấn tất cả Document
        sql_query = """
        SELECT
            "ID",
            "Title",
            "Content"
        FROM "Document"
        WHERE "IsPublished" = true;
        """

        cur.execute(sql_query)
        docs = cur.fetchall()

        if not docs:
            print("Không tìm thấy Document nào để tạo embedding.")
            return

        print(f"Tìm thấy {len(docs)} Document cần tạo embedding...")

        update_cur = conn.cursor()
        count = 0
        error_count = 0

        for doc in docs:
            doc_dict = dict(doc)
            doc_id = doc_dict['ID']
            doc_title = doc_dict.get('Title') or ""
            doc_content = doc_dict.get('Content') or ""
            
            # Kết hợp Title và Content để tạo ngữ nghĩa đầy đủ
            full_text = f"{doc_title}. {doc_content}".strip()
            
            if not full_text:
                print(f"⚠️ Bỏ qua Document {doc_id}: Không có nội dung.")
                continue

            print(f"Đang xử lý Document: {doc_title[:50]}... (ID: {doc_id})")

            try:
                # Gọi logic create_text_embedding
                embedding_vector = embedding_service.create_text_embedding(full_text)
                embedding_string = str(embedding_vector)

                # Cập nhật Document với embedding mới
                update_cur.execute(
                    'UPDATE "Document" SET "Embedding" = %s WHERE "ID" = %s',
                    (embedding_string, doc_id)
                )
                count += 1

                if count % 10 == 0:
                    print(f"✅ Đã embed {count}/{len(docs)} Document...")

            except Exception as e:
                error_count += 1
                print(f"❌ Lỗi embed Document {doc_id}: {e}")

        conn.commit()
        print(f"\n--- Quá trình TẠO Embedding cho Document hoàn tất! Đã cập nhật {count} Document. ---")
        if error_count > 0:
            print(f"⚠️ Có {error_count} Document gặp lỗi.")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- LỖI: Quá trình tạo embedding thất bại. Đang hoàn tác các thay đổi. ---")
        print(error)
        conn.rollback()
    finally:
        if 'update_cur' in locals() and update_cur is not None:
            update_cur.close()
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
        embed_existing_documents()
