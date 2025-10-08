# /app/services/embedding_service.py
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
# Giả sử pydantic_models.py đã được cập nhật với class mới
from app.models.pydantic_models import EmbeddingRequest

class EmbeddingService:
    """
    Handles the logic for creating enhanced product embeddings.
    """
    def __init__(self):
        """
        Initializes the service and loads the embedding model once.
        """
        # The model is loaded a single time when the service starts
        self.model = SentenceTransformer('bkai-foundation-models/vietnamese-bi-encoder')
        self.max_desc_words = 200
        self.max_story_words = 150
        print(f"Embedding model loaded. Description word limit set to {self.max_desc_words}.")

    def create_embedding(self, data: EmbeddingRequest) -> List[float]:
        """
        Creates a high-quality, normalized embedding from multiple product fields.
        """
        # 1. Intelligently truncate the description and story fields
        truncated_description = ""
        if data.product_description:
            words = data.product_description.split()
            truncated_description = " ".join(words[:self.max_desc_words])

        truncated_product_story = ""
        if data.product_story_detail:
            words = data.product_story_detail.split()
            truncated_product_story = " ".join(words[:self.max_story_words])

        truncated_store_story = ""
        if data.store_story_detail:
            words = data.store_story_detail.split()
            truncated_store_story = " ".join(words[:self.max_story_words])

        # 2. Build the "super document" from all available fields
        # A period helps the model distinguish context between parts
        parts = [
            data.product_name,
            truncated_description,
            data.product_story_title,
            truncated_product_story
        ]

        # Thêm thông tin cửa hàng và triết lý
        if data.store_name:
            parts.append(f"Cửa hàng: {data.store_name}")
        if truncated_store_story:
            parts.append(f"Câu chuyện cửa hàng: {truncated_store_story}")

        # Thêm thông tin phân loại (xử lý dạng list)
        if data.product_category_names:
            parts.append(f"Danh mục: {', '.join(data.product_category_names)}")
        if data.product_type_name:
            parts.append(f"Loại: {data.product_type_name}")

        # Thêm thông tin nguồn gốc và địa lý
        if data.product_made_by:
            parts.append(f"Làm từ: {data.product_made_by}")
        if data.province_name:
            parts.append(f"Tỉnh: {data.province_name}")
        if data.region_name:
            parts.append(f"Vùng miền: {data.region_name}")

        # Thêm thông tin biến thể (xử lý dạng list)
        if data.variant_names:
            parts.append(f"Phiên bản: {', '.join(data.variant_names)}")

        # Remove any empty parts and join them together
        combined_text = ". ".join(filter(None, parts))
        print(f"Generated Super Document: {combined_text}")

        # 3. Use the pre-loaded model to generate the embedding
        vector = self.model.encode(combined_text)

        # 4. Normalize the vector (L2 normalization)
        norm = np.linalg.norm(vector)
        if norm == 0: # Avoid division by zero
            return [0.0] * len(vector)
        normalized_vector = vector / norm

        return normalized_vector.tolist()