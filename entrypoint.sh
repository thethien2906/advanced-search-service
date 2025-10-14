#!/bin/sh

# Thoát ngay lập tức nếu có lỗi
set -e

echo "--- [ENTRYPOINT] Bắt đầu khởi tạo service ---"

# Bước 1: Chạy script để tạo/cập nhật embedding cho sản phẩm
echo "--- [ENTRYPOINT] Đang chạy script tạo embedding... ---"
python -m app.scripts.seed_data
echo "--- [ENTRYPOINT] Script tạo embedding đã hoàn tất. ---"

# Bước 2: Khởi chạy ứng dụng chính (Kafka worker)
echo "--- [ENTRYPOINT] Đang khởi động Kafka worker... ---"
exec python -m app.kafka_worker