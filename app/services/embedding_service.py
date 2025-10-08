# /app/services/embedding_service.py
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from app.models.pydantic_models import EmbeddingRequest

class EmbeddingService:
    """
    Handles the logic for creating enhanced product embeddings using contextual
    prefixes and field weighting to improve semantic relevance.
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
        Creates a high-quality, normalized embedding from multiple product fields
        by building a contextualized "super document".

        This method emphasizes key fields like product name and location by repeating
        them with descriptive prefixes.
        """
        # 1. Intelligently truncate long text fields
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

        # 2. Build the "super document" with contextual prefixes and weighting
        parts = []

        # --- Emphasize Product Name (Weight x3) ---
        if data.product_name:
            parts.append(f"sản phẩm {data.product_name}")
            parts.append(f"tên {data.product_name}")
            parts.append(data.product_name) # Add raw name as well

        # --- Emphasize Location (Weight x2) ---
        if data.province_name:
            parts.append(f"tỉnh {data.province_name}")
            parts.append(f"xuất xứ {data.province_name}")
        if data.region_name:
            parts.append(f"vùng miền {data.region_name}")
            parts.append(f"đặc sản vùng {data.region_name}")
            parts.append(f"đặc sản {data.region_name}")

        # --- Add other fields with single context prefix ---
        if data.product_category_names:
            parts.append(f"danh mục: {', '.join(data.product_category_names)}")

        if truncated_description:
            parts.append(f"mô tả: {truncated_description}")

        if data.product_story_title:
            parts.append(f"câu chuyện: {data.product_story_title}")
        if truncated_product_story:
            parts.append(f"chi tiết câu chuyện: {truncated_product_story}")

        if data.store_name:
            parts.append(f"cửa hàng: {data.store_name}")
        if truncated_store_story:
            parts.append(f"câu chuyện cửa hàng: {truncated_store_story}")

        if data.product_made_by:
            parts.append(f"thành phần chính: {data.product_made_by}")

        if data.variant_names:
            parts.append(f"phiên bản: {', '.join(data.variant_names)}")

        # 3. Join all parts into a single, coherent text document
        combined_text = ". ".join(filter(None, parts))

        # Log the generated document for debugging
        print("--- Generated Super Document for Embedding ---")
        print(combined_text)
        print("---------------------------------------------")

        # 4. Use the pre-loaded model to generate the embedding
        vector = self.model.encode(combined_text)

        # 5. Normalize the vector (L2 normalization)
        norm = np.linalg.norm(vector)
        if norm == 0: # Avoid division by zero
            return [0.0] * len(vector)
        normalized_vector = vector / norm

        return normalized_vector.tolist()