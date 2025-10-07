# /app/models/pydantic_models.py
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    """
    Defines the structure of an incoming search request.
    """
    query_text: str = Field(..., example="Bánh tráng phơi sương")
    user_id: Optional[uuid.UUID] = Field(None, example="123e4567-e89b-12d3-a456-426614174000")
    limit: int = Field(20, gt=0, le=100, example=10)
    filters: Optional[Dict[str, Any]] = Field(None, example={"category_id": "abc-123"})

class ProductResponse(BaseModel):
    """
    Represents a single product item in the search results.
    """
    id: uuid.UUID = Field(..., example="a1b2c3d4-e5f6-7890-1234-567890abcdef")
    name: str = Field(..., example="Mật ong rừng U Minh")
    price: int = Field(..., example=250000)
    rating: float = Field(..., example=4.8)
    review_count: int = Field(..., example=120)
    sale_count: int = Field(..., example=530)
    store_status: str = Field(..., example="Approved")
    is_certified: bool = Field(..., example=True)
    product_images: List[str] = Field(..., example=["https://example.com/image1.jpg"])
    relevance_score: float = Field(..., example=0.92)

class SearchResponse(BaseModel):
    """
    Defines the final structure of the search API's response.
    """
    query: str = Field(..., example="Mật ong")
    total_results: int = Field(..., example=3)
    results: List[ProductResponse]
    processing_time_ms: float = Field(..., example=50.7)



class EnhancedEmbeddingRequest(BaseModel):
    """
    Defines the structured input for creating a product embedding.
    """
    product_name: str #
    product_description: str #
    product_category: Optional[str] = None #
    product_story_title: Optional[str] = None #
    product_made_by: Optional[str] = None #
    product_type_name: Optional[str] = None #
class EmbeddingResponse(BaseModel): #
    """
    Defines the structure of the embedding API's response.
    """
    embedding: List[float] #