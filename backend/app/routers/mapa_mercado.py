"""Mapa de mercado: todos los emisores de renta variable agrupados y coloreados por variación.

Las variaciones salen de una descarga en lote de Yahoo (`services/mapa_mercado_ingesta.py`) que
corre sola después del cierre de EE.UU.; el POST permite dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import MapaMercadoOut
from ..services import mapa_mercado_analytics, mapa_mercado_ingesta

router = APIRouter(prefix="/api/inversiones", tags=["mapa-mercado"])


@router.get("/mapa-mercado", response_model=MapaMercadoOut)
def get_mapa_mercado(db: Session = Depends(get_db)):
    return mapa_mercado_analytics.get_mapa_mercado(db)


def _corrida_en_segundo_plano() -> None:
    db = SessionLocal()
    try:
        mapa_mercado_ingesta.correr(db)
    except Exception:  # pragma: no cover - se loguea dentro; un hilo no puede propagar
        mapa_mercado_ingesta.logger.exception("mapa de mercado: la corrida manual falló")
        db.rollback()
    finally:
        db.close()


@router.post("/mapa-mercado/refrescar", status_code=202)
def refrescar_mapa_mercado():
    """Descarga las variaciones ya mismo. Responde enseguida: son ~460 símbolos y tarda un rato."""
    threading.Thread(target=_corrida_en_segundo_plano, daemon=True, name="mapa-mercado").start()
    return {"resultado": "iniciado"}
