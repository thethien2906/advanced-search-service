# /app/models/pydantic_models.py
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class EmbeddingRequest(BaseModel):
    """
    Defines the final, comprehensive structure for creating a product embedding.
    """
    # Product specific info
    product_name: str
    product_description: str
    product_story_title: Optional[str] = None
    product_story_detail: Optional[str] = None

    # Categorization info
    product_category_names: Optional[List[str]] = None
    product_type_name: Optional[str] = None
    product_made_by: Optional[str] = None
    variant_names: Optional[List[str]] = None

    # Store and Location info
    store_name: Optional[str] = None
    store_story_detail: Optional[str] = None
    province_name: Optional[str] = None
    region_name: Optional[str] = None
    sub_region_name: Optional[str] = None

class EmbeddingResponse(BaseModel): #
    """
    Defines the structure of the embedding API's response.
    """
    embedding: List[float] #