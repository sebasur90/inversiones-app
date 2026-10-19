"""Mapa de mercado: todos los emisores de renta variable agrupados y coloreados por variación.

Las variaciones salen de una descarga en lote de Yahoo (`services/mapa_mercado_ingesta.py`) que
corre sola después del cierre de EE.UU.; el POST permite dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import MapaMercadoOut
from ..services import logos, mapa_mercado_analytics, mapa_mercado_ingesta

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


@router.get("/logos/{archivo}")
def get_logo(archivo: str):
    """El logo de un emisor (`/logos/KO.png`). 404 si no hay. Sólo sirve archivos de la carpeta de
    logos: el nombre se valida contra la forma de un `ticker_base`, nunca se arma una ruta con él."""
    base = archivo[:-4] if archivo.lower().endswith(".png") else ""
    destino = logos.ruta(base)
    if destino is None:
        raise HTTPException(status_code=404, detail="Sin logo")
    # Los logos cambian una vez cada tanto: una semana de caché en el navegador alcanza.
    return FileResponse(destino, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
