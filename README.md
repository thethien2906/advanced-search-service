# advanced-search-service

Đây là một microservice tìm kiếm sản phẩm hiệu suất cao, được xây dựng với kiến trúc hướng sự kiện sử dụng Apache Kafka. Dịch vụ này sử dụng kết hợp tìm kiếm ngữ nghĩa (semantic search) và mô hình học máy (XGBoost) để xếp hạng lại kết quả, nhằm cung cấp các sản phẩm có độ liên quan cao nhất cho người dùng.

## Kiến trúc

Hệ thống được thiết kế theo mô hình Kafka-centric:

* **.NET Service (Gateway):** Đóng vai trò là cổng giao tiếp chính, tiếp nhận yêu cầu tìm kiếm từ client. Thay vì xử lý trực tiếp, nó sẽ tạo một `request_id` và gửi yêu cầu vào topic `search_requests` của Kafka.
* **Python Worker Service (Kafka-centric):** Dịch vụ này (chứa trong project này) lắng nghe topic `search_requests`. Khi nhận được yêu cầu, nó sẽ thực hiện tìm kiếm ngữ nghĩa, xếp hạng lại bằng mô hình ML, và cuối cùng gửi kết quả vào topic `search_results` cùng với `request_id` ban đầu.
* **Kafka:** Đóng vai trò là xương sống giao tiếp, giúp các service giao tiếp bất đồng bộ, tăng khả năng mở rộng và chịu lỗi.