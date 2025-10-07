import os
import psycopg2
import uuid
import random
import json
from sentence_transformers import SentenceTransformer
from faker import Faker
from dotenv import load_dotenv

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
NUM_SELLERS = 5
NUM_PRODUCTS = 30

# --- SAMPLE DATA ---
SAMPLE_PRODUCTS_DATA = [
    {"name": "Mật ong rừng U Minh Hạ nguyên chất", "desc": "Mật ong tự nhiên thu hoạch từ hoa tràm trong rừng U Minh, có màu vàng sẫm và hương thơm đặc trưng.", "category": "Thực phẩm"},
    {"name": "Bộ ấm trà gốm sứ Bát Tràng men lam", "desc": "Sản phẩm thủ công từ làng gốm Bát Tràng, họa tiết hoa sen vẽ tay tinh xảo. Thích hợp làm quà tặng.", "category": "Thủ công mỹ nghệ"},
    {"name": "Nước mắm cốt cá cơm Phú Quốc", "desc": "Nước mắm truyền thống 40 độ đạm, ủ chượp tự nhiên trong thùng gỗ, hương vị đậm đà.", "category": "Thực phẩm"},
    {"name": "Trà sen Tây Hồ ướp tự nhiên", "desc": "Trà xanh Thái Nguyên được ướp trong bông hoa sen tươi của Hồ Tây, hương thơm thanh khiết.", "category": "Thực phẩm"},
    {"name": "Lụa tơ tằm Vạn Phúc Hà Đông", "desc": "Khăn choàng lụa tơ tằm 100% từ làng lụa Vạn Phúc, mềm mại và óng ả.", "category": "Thời trang"},
    {"name": "Tranh Đông Hồ 'Đám cưới chuột'", "desc": "Tranh dân gian in trên giấy điệp, thể hiện nét văn hóa độc đáo của Việt Nam.", "category": "Thủ công mỹ nghệ"},
    {"name": "Cà phê Robusta rang mộc Cầu Đất", "desc": "Hạt cà phê Robusta từ vùng Cầu Đất, Đà Lạt. Vị đậm, đắng nhẹ, hương thơm nồng nàn.", "category": "Thực phẩm"},
    {"name": "Nón lá bài thơ Huế", "desc": "Nón lá truyền thống của Huế, có hình ảnh cầu Tràng Tiền và các câu thơ được lồng ghép tinh tế.", "category": "Thủ công mỹ nghệ"},
    {"name": "Bánh Pía Sóc Trăng nhân sầu riêng trứng muối", "desc": "Đặc sản Sóc Trăng với lớp vỏ mỏng, nhân sầu riêng béo ngậy và trứng muối đậm đà.", "category": "Thực phẩm"},
    {"name": "Túi cói thủ công họa tiết thổ cẩm", "desc": "Túi xách làm từ sợi cói tự nhiên, trang trí bằng vải thổ cẩm dệt tay.", "category": "Thời trang"},
    {"name": "Tượng Phật Di Lặc bằng gỗ hương", "desc": "Tượng gỗ điêu khắc tinh xảo, mang lại may mắn và tài lộc.", "category": "Thủ công mỹ nghệ"},
    {"name": "Rượu mơ Yên Tử", "desc": "Rượu được ngâm từ quả mơ vàng của vùng núi Yên Tử, có vị chua ngọt, tốt cho sức khỏe.", "category": "Thực phẩm"},
    {"name": "Đèn lồng Hội An trang trí", "desc": "Đèn lồng vải lụa nhiều màu sắc, biểu tượng của phố cổ Hội An.", "category": "Thủ công mỹ nghệ"},
    {"name": "Thịt trâu gác bếp Tây Bắc", "desc": "Đặc sản của người Thái đen, thịt trâu được tẩm ướp gia vị mắc khén và hun khói trên bếp củi.", "category": "Thực phẩm"},
    {"name": "Vòng tay trầm hương tự nhiên", "desc": "Vòng tay làm từ gỗ trầm hương, mùi thơm nhẹ nhàng giúp thư giãn tinh thần.", "category": "Trang sức"},
]

def get_db_connection():
    """Establishes a connection to the database."""
    print("Connecting to the database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        # --- CHANGE 1: The following lines are now removed ---
        # from pgvector.psycopg2 import register_vector
        # register_vector(conn)
        print("Database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to database: {e}")
        exit(1)

def generate_embeddings(model, texts):
    """Generates normalized embeddings for a list of texts."""
    print(f"Generating embeddings for {len(texts)} texts...")
    embeddings = model.encode(texts, normalize_embeddings=True)
    print("Embeddings generated.")
    return embeddings

def seed_database():
    """Main function to clear existing data and seed new data."""
    conn = get_db_connection()
    cur = conn.cursor()
    fake = Faker('vi_VN')

    print(f"Loading sentence-transformer model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    print("Model loaded.")

    try:
        print("\n--- Starting Database Seeding ---")
        print("Cleaning up old data...")
        tables_to_clear = [
            "ProductCertificate", "InventoryProduct", "ProductVariant",
            "Product", "Store", "Seller", "User"
        ]
        for table in tables_to_clear:
            cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
        print("Cleanup complete.")

        admin_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        # Generate a simple 10-digit phone number
        phone_number = f"09{random.randint(10000000, 99999999)}"

        cur.execute(
            'INSERT INTO "User" ("ID", "Email", "Password", "PhoneNumber", "Role", "FirstName", "LastName") VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (user_id, fake.email(), 'hashed_password', phone_number, 'Seller', fake.first_name(), fake.last_name())
        )

        print(f"Creating {NUM_SELLERS} sellers and stores...")
        store_ids = []
        for i in range(NUM_SELLERS):
            # FIX 1: Create a unique user_id at the start of the loop
            user_id = str(uuid.uuid4())

            # FIX 2: Generate a simple 10-digit phone number that fits VARCHAR(20)
            phone_number = f"09{random.randint(10000000, 99999999)}"

            # Create User record with the corrected variables
            cur.execute(
                'INSERT INTO "User" ("ID", "Email", "Password", "PhoneNumber", "Role", "FirstName", "LastName") VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (user_id, fake.email(), 'hashed_password', phone_number, 'Seller', fake.first_name(), fake.last_name())
            )

            # Create Seller record
            cur.execute(
                'INSERT INTO "Seller" ("UserID", "BusinessName") VALUES (%s, %s)',
                (user_id, fake.company())
            )

            # Create Store record
            store_id = str(uuid.uuid4())
            store_status = 'Approved' if random.random() < 0.8 else 'Pending'
            approved_by = admin_id if store_status == 'Approved' else None
            cur.execute(
                'INSERT INTO "Store" ("ID", "SellerID", "StoreName", "Province", "District", "Ward", "ProvinceID", "WardID", "Status", "ApprovedBy") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (store_id, user_id, f"Cửa hàng {fake.last_name()}", "Thành phố Hồ Chí Minh", "Quận 1", "Phường Bến Nghé", 79, 27883, store_status, approved_by)
            )
            store_ids.append(store_id)
        print("Sellers and stores created.")

        print(f"Preparing {NUM_PRODUCTS} products for insertion...")
        products_to_insert = []
        texts_for_embedding = []
        for i in range(NUM_PRODUCTS):
            product_template = random.choice(SAMPLE_PRODUCTS_DATA)
            product_name = f"{product_template['name']} - Mẫu #{i+1}"
            product_desc = product_template['desc']
            texts_for_embedding.append(f"{product_name}. {product_desc}")
            products_to_insert.append({
                "id": str(uuid.uuid4()),
                "store_id": random.choice(store_ids),
                "name": product_name,
                "description": product_desc,
                "images": json.dumps([f"https://picsum.photos/seed/{i+1}/400/300"]),
                "category_id": json.dumps([str(uuid.uuid4())]),
                "is_active": random.random() < 0.9,
            })

        embeddings = generate_embeddings(model, texts_for_embedding)

        print("Inserting products, variants, and inventory...")
        for i, product in enumerate(products_to_insert):

            # --- CHANGE 2: Manually convert the embedding to a string ---
            embedding_string = str(embeddings[i].tolist())

            cur.execute(
                'INSERT INTO "Product" ("ID", "StoreID", "Name", "Description", "ProductImages", "CategoryID", "IsActive", "Embedding") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (product['id'], product['store_id'], product['name'], product['description'], product['images'], product['category_id'], product['is_active'], embedding_string) # Pass the string here
            )
            variant_id = str(uuid.uuid4())
            price = random.randint(50, 1000) * 1000
            cur.execute(
                'INSERT INTO "ProductVariant" ("ID", "ProductID", "VariantName", "Length", "Width", "Height", "Weight", "BasePrice", "commission", "FinalPrice") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (variant_id, product['id'], 'Default', 10, 10, 10, 200, price, int(price * 0.1), int(price * 1.1))
            )
            quantity = random.randint(10, 100) if random.random() < 0.85 else 0
            cur.execute(
                'INSERT INTO "InventoryProduct" ("ProductVariantID", "Quantity") VALUES (%s, %s)',
                (variant_id, quantity)
            )
            if random.random() < 0.5:
                cur.execute(
                    'INSERT INTO "ProductCertificate" ("ProductID", "ImageURL", "Status", "ReviewedByStaffID") VALUES (%s, %s, %s, %s)',
                    (product['id'], f"https://example.com/cert/{product['id']}.pdf", 'Approved', None)
                )

        conn.commit()
        print("\n--- Seeding Complete! ---")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- ERROR: Seeding failed. Rolling back changes. ---")
        print(error)
        conn.rollback()
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    if not DATABASE_URL:
        print("FATAL: DATABASE_URL environment variable not set.")
    else:
        seed_database()