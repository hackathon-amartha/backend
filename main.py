from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import item

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


app.include_router(item.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Amartha Hackathon API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
