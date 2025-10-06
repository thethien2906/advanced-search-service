from fastapi import FastAPI
from app.api import endpoints

# Create the main FastAPI application instance
app = FastAPI(
    title="Homeland's Finest - Search Service",
    description="The advanced search microservice for the THQN platform.",
    version="1.0.0"
)

# Include the API router from the endpoints module
app.include_router(endpoints.router)