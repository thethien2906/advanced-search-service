# /app/models/pydantic_models.py
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class EmbeddingRequest(BaseModel):
    # Product Cốt lõi (7)
    product_name: str
    product_description: Optional[str] = None
    product_type: Optional[str] = None # (Từ Product.ProductType)
    product_material: Optional[str] = None
    product_story_title: Optional[str] = None
    product_story_detail: Optional[str] = None
    hashtag_names: Optional[List[str]] = None

    # Phân loại (2)
    category_name: Optional[str] = None
    parent_category_name: Optional[str] = None

    # Cửa hàng (2)
    store_name: Optional[str] = None
    store_story_detail: Optional[str] = None

    # Vị trí (3)
    province_name: Optional[str] = None
    region_name: Optional[str] = None
    sub_region_name: Optional[str] = None

class EmbeddingResponse(BaseModel): #
    """
    Defines the structure of the embedding API's response.
    """
    embedding: List[float] #