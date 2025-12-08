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
            # Don't use value_deserializer to handle malformed JSON gracefully
            # We'll parse JSON manually in the message loop
            # Fix timeout issues
            max_poll_interval_ms=600000,  # 10 minutes (default: 300000)
            session_timeout_ms=60000,     # 60 seconds (default: 10000)
            heartbeat_interval_ms=10000,  # 10 seconds (default: 3000)
            max_poll_records=10           # Process fewer messages per poll
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
            # Parse JSON manually to handle malformed messages gracefully
            try:
                request_data = json.loads(message.value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
                logger.error(f"❌ Failed to decode message: {e}")
                logger.error(f"   Raw message: {message.value[:200]}...")  # Log first 200 bytes
                logger.warning("⚠️ Skipping malformed message and continuing...")
                continue  # Skip this message and continue with next one
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

            # [NEW] Parse and validate filter parameters
            min_price = request_data.get("min_price")
            max_price = request_data.get("max_price")
            province_filters = request_data.get("province_filters")
            region_filters = request_data.get("region_filters")
            sub_region_filters = request_data.get("sub_region_filters")
            sort_by = request_data.get("sort_by")

            # Validate price filters
            if min_price is not None:
                try:
                    min_price = float(min_price)
                    if min_price < 0:
                        logger.warning(f"⚠️ Invalid min_price (negative): {min_price}. Ignoring.")
                        min_price = None
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Invalid min_price format: {e}. Ignoring.")
                    min_price = None

            if max_price is not None:
                try:
                    max_price = float(max_price)
                    if max_price < 0:
                        logger.warning(f"⚠️ Invalid max_price (negative): {max_price}. Ignoring.")
                        max_price = None
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Invalid max_price format: {e}. Ignoring.")
                    max_price = None

            # Validate price range
            if min_price is not None and max_price is not None and min_price > max_price:
                logger.warning(f"⚠️ min_price ({min_price}) > max_price ({max_price}). Swapping values.")
                min_price, max_price = max_price, min_price

            # Validate sort_by
            valid_sort_values = ["newest", "best-selling", "rating", "price-asc", "price-desc"]
            if sort_by is not None and sort_by not in valid_sort_values:
                logger.warning(f"⚠️ Invalid sort_by value: {sort_by}. Valid values: {valid_sort_values}. Ignoring.")
                sort_by = None

            # Log filter parameters if provided
            if min_price is not None or max_price is not None:
                logger.info(f"💰 Price filter: {min_price} - {max_price}")
            if province_filters:
                logger.info(f"📍 Province filters: {province_filters}")
            if region_filters:
                logger.info(f"🗺️ Region filters: {region_filters}")
            if sub_region_filters:
                logger.info(f"🌏 Sub-region filters: {sub_region_filters}")
            if sort_by:
                logger.info(f"🔄 Sort by: {sort_by}")

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
                search_results = search_service.search_semantic(
                    query=query_text,
                    limit=limit,
                    category_filter_ids=category_filter_ids,
                    min_price=min_price,
                    max_price=max_price,
                    province_filters=province_filters,
                    region_filters=region_filters,
                    sub_region_filters=sub_region_filters,
                    sort_by=sort_by
                )
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

        except Exception as e:
            logger.error(f"An unexpected error occurred while processing message: {e}", exc_info=True)


if __name__ == "__main__":
    main()