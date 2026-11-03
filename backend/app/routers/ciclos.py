"""Ciclos de mercado: rotación relativa, rendimientos, relaciones y cruce con la cartera.

Las series salen de una descarga en lote de Yahoo (`services/ciclos_ingesta.py`) que corre sola
después del cierre; el POST permite dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import CiclosCatalogoOut, CiclosEstadoOut
from ..services import ciclos_catalogo, ciclos_ingesta

router = APIRouter(prefix="/api/inversiones", tags=["ciclos"])


def _pertenencia(g: ciclos_catalogo.Grupo) -> dict[str, list[str]]:
    """Cómo decide la app qué parte de la cartera pertenece al grupo (para mostrar la regla)."""
    out = {f"exacta_{eje}": list(valores) for eje, valores in g.eje_cartera}
    out.update({k: list(v) for k, v in g.cartera.items() if v})
    return out


@router.get("/ciclos/catalogo", response_model=CiclosCatalogoOut)
def get_catalogo():
    cat = ciclos_catalogo.cargar()
    return {
        "version": cat.version,
        "grupos": [
            {**{k: getattr(g, k) for k in (
                "id", "nombre", "tipo", "padre", "descripcion", "proxy", "benchmark", "moneda", "region",
                "fuente", "tipo_rendimiento", "activo", "exclusivo", "es_benchmark", "lista_curada", "nota",
            )}, "vistas": list(g.vistas), "pertenencia": _pertenencia(g)}
            for g in cat.grupos.values()
        ],
        "periodos": cat.periodos,
        "errores": cat.errores,
    }


@router.get("/ciclos/estado", response_model=CiclosEstadoOut)
def get_estado(db: Session = Depends(get_db)):
    simbolos = ciclos_ingesta.estado(db)
    con_datos = sum(1 for s in simbolos if s["n_barras"] > 0)
    return {
        "simbolos": simbolos,
        "con_datos": con_datos,
        "sin_datos": len(simbolos) - con_datos,
        "desactualizados": sum(1 for s in simbolos if s["desactualizado"]),
    }


def _corrida_en_segundo_plano() -> None:
    db = SessionLocal()
    try:
        ciclos_ingesta.correr(db)
    except Exception:  # pragma: no cover - se loguea dentro; un hilo no puede propagar
        ciclos_ingesta.logger.exception("ciclos: la corrida manual falló")
        db.rollback()
    finally:
        db.close()


@router.post("/ciclos/refrescar", status_code=202)
def refrescar_ciclos():
    """Descarga las series ya mismo. Responde enseguida: la primera vez baja ~20 años de ~60 símbolos."""
    threading.Thread(target=_corrida_en_segundo_plano, daemon=True, name="ciclos").start()
    return {"resultado": "iniciado"}
