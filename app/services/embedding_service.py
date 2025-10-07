# /app/services/embedding_service.py
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from app.models.pydantic_models import EnhancedEmbeddingRequest

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
        self.max_desc_words = 200 # Limit the description to 200 words
        print(f"Embedding model loaded. Description word limit set to {self.max_desc_words}.") #

    def create_enhanced_embedding(self, data: EnhancedEmbeddingRequest) -> List[float]:
        """
        Creates a high-quality, normalized embedding from multiple product fields.
        """
        # 1. Intelligently truncate the description
        words = data.product_description.split() #
        truncated_description = " ".join(words[:self.max_desc_words]) #

        # 2. Build the "super document" from available fields
        # A period helps the model distinguish context between parts
        parts = [data.product_name, data.product_story_title, truncated_description] #
        if data.product_category:
            parts.append(f"Danh mục: {data.product_category}") #
        if data.product_type_name:
            parts.append(f"Loại: {data.product_type_name}") #
        if data.product_made_by:
            parts.append(f"Làm từ: {data.product_made_by}") #

        # Remove any empty parts and join them together
        combined_text = ". ".join(filter(None, parts)) #

        # 3. Use the pre-loaded model to generate the embedding
        vector = self.model.encode(combined_text) #

        # 4. Normalize the vector (L2 normalization)
        norm = np.linalg.norm(vector) #
        if norm == 0: # Avoid division by zero
            return [0.0] * len(vector) #
        normalized_vector = vector / norm #

        return normalized_vector.tolist() #