# src/api/main.py
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.schemas import DisruptionForecastRequest, DisruptionForecastResponse
from src.api.service import forecast_engine
from src.api.control_tower import router as control_tower_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload ML models during application startup
    try:
        forecast_engine.load_artifacts()
        print("NEXUS ML pipelines loaded successfully into memory.")
    except Exception as e:
        print(f"Failed to load ML artifacts: {e}")
        raise e
    yield


app = FastAPI(
    title="NEXUS Autonomous Control Tower API",
    description="Multi-Agent Supply Chain Disruption Orchestration, Jev Mitigation Scoring, and Human-in-the-Loop Approvals",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Control Tower endpoints
app.include_router(control_tower_router)


@app.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health_check():
    return {
        "status": "online",
        "service": "nexus-control-tower",
        "models_loaded": forecast_engine.mean_pipeline is not None
    }


@app.post(
    "/forecast/disruption",
    response_model=DisruptionForecastResponse,
    status_code=status.HTTP_200_OK,
    tags=["Forecasting Engine"]
)
def evaluate_disruption_forecast(request: DisruptionForecastRequest):
    if not request.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item list for disruption evaluation cannot be empty."
        )
    try:
        response = forecast_engine.predict_disruption(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(e)}"
        )
