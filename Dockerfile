# Dockerfile (Cập nhật)

# Step 1: Start from an official Python base image
FROM python:3.11-slim

# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy the entire app/ directory into the container
COPY ./app /app/app

# --- THAY ĐỔI ĐỂ SỬ DỤNG ENTRYPOINT ---
# Step 5: Sao chép entrypoint script vào container
COPY entrypoint.sh .

# Step 6: Cấp quyền thực thi cho script
RUN chmod +x entrypoint.sh
# --- KẾT THÚC THAY ĐỔI ---

# Step 7: Thiết lập entrypoint để script được chạy khi container khởi động
ENTRYPOINT ["./entrypoint.sh"]