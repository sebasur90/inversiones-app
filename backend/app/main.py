import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db
from .routers import inversiones, objetivos_inversion, escenarios


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup. El MEP y el CER salen del Sheet (tabla IndiceMercado), no de una API externa:
    # el arranque no depende de la red.
    init_db()
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
app.include_router(escenarios.router)


@app.get("/health")
def health():
    return {"status": "ok"}
