import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db, SessionLocal
from .services.cotizaciones import fetch_and_cache_today
from .routers import inversiones, objetivos_inversion


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    db = SessionLocal()
    try:
        await fetch_and_cache_today(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Inversiones API", version="1.0.0", lifespan=lifespan)

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://localhost:80",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inversiones.router)
app.include_router(objetivos_inversion.router)


@app.get("/health")
def health():
    return {"status": "ok"}
