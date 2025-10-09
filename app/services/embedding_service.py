# /app/services/embedding_service.py
from sentence_transformers import SentenceTransformer
import numpy as np
import re
from typing import List
from app.models.pydantic_models import EmbeddingRequest

def remove_vietnamese_diacritics(text: str) -> str:
    """
    Loại bỏ dấu tiếng Việt khỏi một chuỗi văn bản.
    """
    if not text:
        return ""
    text = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', text)
    text = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', text)
    text = re.sub(r'[ìíịỉĩ]', 'i', text)
    text = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', text)
    text = re.sub(r'[ùúụủũưừứựửữ]', 'u', text)
    text = re.sub(r'[ỳýỵỷỹ]', 'y', text)
    text = re.sub(r'[đ]', 'd', text)
    text = re.sub(r'[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ]', 'A', text)
    text = re.sub(r'[ÈÉẸẺẼÊỀẾỆỂỄ]', 'E', text)
    text = re.sub(r'[ÌÍỊỈĨ]', 'I', text)
    text = re.sub(r'[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]', 'O', text)
    text = re.sub(r'[ÙÚỤỦŨƯỪỨỰỬỮ]', 'U', text)
    text = re.sub(r'[ỲÝỴỶỸ]', 'Y', text)
    text = re.sub(r'[Đ]', 'D', text)
    return text

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
        self.max_desc_words = 500
        self.max_story_words = 350
        print(f"Embedding model loaded. Description word limit set to {self.max_desc_words}.")

    def create_embedding(self, data: EmbeddingRequest) -> List[float]:
        """
        Creates a high-quality, normalized embedding from multiple product fields
        by building a contextualized "super document" that includes both accented
        and unaccented versions of the text.
        """
        # 1. Intelligently truncate long text fields
        truncated_description = " ".join(data.product_description.split()[:self.max_desc_words]) if data.product_description else ""
        truncated_product_story = " ".join(data.product_story_detail.split()[:self.max_story_words]) if data.product_story_detail else ""
        truncated_store_story = " ".join(data.store_story_detail.split()[:self.max_story_words]) if data.store_story_detail else ""

        # 2. Build the "super document" with contextual prefixes and weighting
        parts = []

        # --- Emphasize Product Name (Weight x3) ---
        if data.product_name:
            parts.append(f"sản phẩm {data.product_name}")
            parts.append(f"tên {data.product_name}")
            parts.append(data.product_name)

        # --- Emphasize Location (Weight x2) ---
        if data.province_name:
            parts.append(f"tỉnh {data.province_name}")
            parts.append(f"xuất xứ {data.province_name}")
        if data.region_name:
            parts.append(f"vùng miền {data.region_name}")
            parts.append(f"đặc sản {data.region_name}")
        if data.sub_region_name:
            parts.append(f"khu vực {data.sub_region_name}")
            parts.append(f"đặc sản {data.sub_region_name}")

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

        # 3. Join all accented parts into a single text document
        accented_text = ". ".join(filter(None, parts))

        # 4. Create the unaccented version of the document
        unaccented_text = remove_vietnamese_diacritics(accented_text)

        # 5. Combine both versions to create the final super document
        # This teaches the model that "ruou" and "rượu" are semantically linked.
        combined_text = f"{accented_text}. {unaccented_text}"

        # Log the generated document for debugging
        print("--- Generated Super Document for Embedding ---")
        print(combined_text)
        print("---------------------------------------------")

        # 6. Use the pre-loaded model to generate the embedding
        vector = self.model.encode(combined_text)

        # 7. Normalize the vector (L2 normalization)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return [0.0] * len(vector)
        normalized_vector = vector / norm

        return normalized_vector.tolist()