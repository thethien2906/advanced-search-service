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

class ProductEmbeddingMessage(BaseModel):
    """
    Message structure từ .NET khi staff approve product.
    Kafka topic: embed_product
    """
    product_id: str  # Guid from .NET
    product_name: str
    description: Optional[str] = None
    category_id: str  # Guid from .NET
    category_name: str
    store_id: str  # Guid from .NET
    store_name: str
    price: float
    province_id: int
    province_name: str
    approved_at: str  # ISO timestamp
    approved_by: str  # Staff Guid