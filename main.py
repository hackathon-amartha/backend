from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.chat import router as chat_router

app = FastAPI(
    title="Amartha Hackathon API",
    description="Backend API for Amartha Hackathon",
    version="1.0.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 router
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(chat_router)

app.include_router(api_v1_router)


@app.get("/")
async def root():
    return {"message": "Welcome to Amartha Hackathon API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
