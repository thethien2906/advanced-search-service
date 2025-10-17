#!/bin/sh

# Thoát ngay lập tức nếu có lỗi
set -e

echo "--- [ENTRYPOINT] Đang khởi động worker cho: $SERVICE_NAME ---"

if [ "$SERVICE_NAME" = "seeder-worker" ]; then
  exec python -m app.seeder_worker
elif [ "$SERVICE_NAME" = "suggestion-worker" ]; then
  exec python -m app.suggestion_worker
elif [ "$SERVICE_NAME" = "data-collector" ]; then
  exec python -m app.scripts.data_collector
elif [ "$SERVICE_NAME" = "search-service" ]; then
  exec python -m app.search_worker
else
  echo "Lỗi: Biến môi trường SERVICE_NAME không hợp lệ hoặc chưa được đặt: $SERVICE_NAME"
  exit 1
fi