import os
import psycopg2
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")

# Dữ liệu địa danh chuẩn (ID phải khớp với dữ liệu trong seed_data.py)
PROVINCES = [
    (1, 'Thành phố Hà Nội', 'Đồng bằng sông Hồng'),
    (46, 'Tỉnh Thừa Thiên Huế', 'Bắc Trung Bộ'),
    (79, 'Thành phố Hồ Chí Minh', 'Đông Nam Bộ'),
    (66, 'Tỉnh Đắk Lắk', 'Tây Nguyên')
]

DISTRICTS = [
    (1, 'Quận Hoàn Kiếm', 1),
    (474, 'Thành phố Huế', 46),
    (760, 'Quận 1', 79),
    (643, 'Thành phố Buôn Ma Thuột', 66)
]

WARDS = [
    (7, 'Phường Hàng Trống', 1),
    (9078, 'Phường Phú Hội', 474),
    (27883, 'Phường Bến Nghé', 760),
    (24088, 'Phường Thắng Lợi', 643)
]

def seed_locations():
    """Nạp dữ liệu Tỉnh, Quận, Phường vào cơ sở dữ liệu."""
    conn = None
    try:
        print("Connecting to the database...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print("Connection successful.")

        print("Seeding Provinces...")
        cur.executemany('INSERT INTO "Province" ("ID", "Name", "Region") VALUES (%s, %s, %s) ON CONFLICT ("ID") DO NOTHING;', PROVINCES)

        print("Seeding Districts...")
        cur.executemany('INSERT INTO "District" ("ID", "Name", "ProvinceID") VALUES (%s, %s, %s) ON CONFLICT ("ID") DO NOTHING;', DISTRICTS)

        print("Seeding Wards...")
        cur.executemany('INSERT INTO "Ward" ("ID", "Name", "DistrictID") VALUES (%s, %s, %s) ON CONFLICT ("ID") DO NOTHING;', WARDS)

        conn.commit()
        print("\n--- Location seeding complete! ---")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- ERROR: Location seeding failed. ---")
        print(error)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    if not DATABASE_URL:
        print("FATAL: DATABASE_URL environment variable not set.")
    else:
        seed_locations()