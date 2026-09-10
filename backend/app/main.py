import faulthandler
import os
import signal
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db
from .routers import inversiones, objetivos_inversion, escenarios, tecnico


def _habilitar_volcado_de_stacks() -> None:
    """Diagnóstico de cuelgues: `docker kill -s USR1 <backend>` imprime en los logs el stack de
    TODOS los threads sin matar el proceso.

    Cuando la app "deja de responder" pero el contenedor sigue arriba, esto dice exactamente en qué
    línea está trabado cada worker (una llamada de red sin timeout, un lock tomado, la DB
    bloqueada). Sin esto sólo se ve un proceso vivo y mudo.

    Quien dispara la señal es `scripts/watchdog.sh` al detectar el cuelgue, sin intervención
    manual. `chain=False` porque no hay otro handler de USR1 que encadenar.
    """
    faulthandler.enable()
    if hasattr(faulthandler, "register"):  # no existe en Windows
        faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True, chain=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup. El MEP y el CER salen del Sheet (tabla IndiceMercado), no de una API externa:
    # el arranque no depende de la red.
    _habilitar_volcado_de_stacks()
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
app.include_router(tecnico.router)


@app.get("/health")
def health():
    return {"status": "ok"}
