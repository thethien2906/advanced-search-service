# /app/kafka_worker.py
import json
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from app.services.search_service import SearchService
from app.core.config import settings
import uuid
from uuid import UUID
from datetime import datetime, timezone
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Hàm chính để khởi tạo và chạy Kafka worker.
    - Lắng nghe các yêu cầu tìm kiếm từ topic 'search_requests'.
    - Gọi SearchService để xử lý.
    - Gửi kết quả và log đến các topic Kafka tương ứng.
    """
    logger.info("=============================================")
    logger.info("      🚀 Search Worker Starting 🚀")
    logger.info("=============================================")

    # Khởi tạo KafkaConsumer để lắng nghe yêu cầu
    try:
        consumer = KafkaConsumer(
            settings.SEARCH_REQUESTS_TOPIC,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='search-worker-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        logger.info("✅ KafkaConsumer connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect KafkaConsumer: {e}")
        return # Thoát nếu không kết nối được

    # Khởi tạo KafkaProducer để gửi phản hồi
    try:
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8') # Hỗ trợ serialize UUID
        )
        logger.info("✅ KafkaProducer connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect KafkaProducer: {e}")
        return

    # Khởi tạo SearchService để tái sử dụng logic tìm kiếm
    try:
        search_service = SearchService()
        logger.info("✅ SearchService initialized successfully.")
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to initialize SearchService: {e}")
        return

    logger.info("=============================================")
    logger.info("👂 Worker is now listening for messages...")
    logger.info("=============================================")


    # Vòng lặp vô tận để xử lý message
    for message in consumer:
        try:
            request_data = message.value
            query_text = request_data.get("query_text") or ""  # Cho phép None/rỗng, search_service sẽ handle
            request_id = request_data.get("request_id") # Nhận request_id từ message
            user_id = request_data.get("user_id") # Nhận user_id
            limit = request_data.get("limit", 20)

            # [NEW] Lấy loại tìm kiếm (Mặc định là PRODUCT để tương thích ngược)
            search_type = request_data.get("search_type", "PRODUCT").upper()

            # Lấy category_filter_ids từ request (list of UUID strings)
            category_filter_ids = None
            if "category_filter_ids" in request_data and request_data["category_filter_ids"]:
                try:
                    category_filter_ids = [UUID(cid) for cid in request_data["category_filter_ids"]]
                    logger.info(f"📋 Category filters: {len(category_filter_ids)} categories")
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Invalid category_filter_ids format: {e}. Ignoring category filter.")

            # Chỉ validate request_id (bắt buộc), query_text có thể rỗng (search_service sẽ search theo xu hướng)
            if not request_id:
                logger.warning(f"⚠️ Received message with missing 'request_id'. Skipping.")
                continue

            # Log query text hoặc thông báo search theo xu hướng nếu rỗng
            query_display = query_text if query_text.strip() else "[Empty - Trending Search]"
            logger.info(f"📩 Nhận Request | ID: {request_id} | Type: {search_type} | Query: '{query_display}'")

            search_results = []

            # 2. [NEW] Routing Logic
            if search_type == "DOCUMENT":
                # Gọi logic tìm tài liệu
                search_results = search_service.search_documents(query=query_text, limit=limit)
                logger.info(f"📄 Tìm thấy {len(search_results)} tài liệu.")
            else:
                # Gọi logic tìm sản phẩm (Product) - Giữ nguyên logic cũ
                # Có thể dùng search_with_ml hoặc search_semantic tùy cấu hình
                search_results = search_service.search_semantic(query=query_text, limit=limit, category_filter_ids=category_filter_ids)
                logger.info(f"🛍️ Tìm thấy {len(search_results)} sản phẩm.")

            # --- GIAI ĐOẠN 3: GỬI KẾT QUẢ VÀ LOGGING ---

            # 1. Gửi kết quả tìm kiếm vào topic 'search_results'
            result_payload = {
                "request_id": request_id,
                "type": search_type,      # [NEW] Trả về type để client dễ xử lý
                "results": search_results # Đổi key chung là "results" thay vì "products"
            }
            logger.info(f"--- GỬI PAYLOAD LÊN KAFKA (RequestID: {request_id}) ---")
            logger.info(json.dumps(result_payload, default=str, indent=4, ensure_ascii=False))

            # producer.send(settings.SEARCH_RESULTS_TOPIC, value=result_payload)
            future = producer.send(settings.SEARCH_RESULTS_TOPIC, value=result_payload)
            future.add_callback(lambda metadata: logger.info(f"✅ Message sent successfully to topic={metadata.topic}, partition={metadata.partition}, offset={metadata.offset}"))
            future.add_errback(lambda error: logger.error(f"❌ Failed to send message: {error}"))
            logger.info(f"📤 Sent {len(search_results)} results to '{settings.SEARCH_RESULTS_TOPIC}' for RequestID: {request_id}")

            # 2. Gửi dữ liệu log vào topic 'search_logging_events'
            ranked_ids = [result['id'] for result in search_results] 
            log_payload = {
                "search_id": str(uuid.uuid4()),
                "user_id": user_id,
                "query_text": query_text,
                "result_count": len(search_results),
                "ranked_product_ids": ranked_ids,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            producer.send(settings.SEARCH_LOGGING_TOPIC, value=log_payload)
            logger.info(f"📝 Sent log event to '{settings.SEARCH_LOGGING_TOPIC}' for RequestID: {request_id}")

            # Đảm bảo message được gửi đi
            producer.flush()

        except json.JSONDecodeError:
            logger.error("Failed to decode message value. Skipping.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing message: {e}", exc_info=True)


if __name__ == "__main__":
    main()