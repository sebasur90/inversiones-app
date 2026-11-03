"""Ciclos de mercado: rotación relativa, rendimientos, relaciones y cruce con la cartera.

Las series salen de una descarga en lote de Yahoo (`services/ciclos_ingesta.py`) que corre sola
después del cierre; el POST permite dispararla a mano. Todo lo que cruza con la cartera tiene su par
`/carteras/{nombre}/...` y `/consolidado/...`, como el resto de la API.
"""
import threading
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import MovimientoInversion, SessionLocal, get_db
from ..schemas import (
    CiclosCarteraOut, CiclosCatalogoOut, CiclosComparacionOut, CiclosCorrelacionesOut, CiclosDesfasesOut,
    CiclosDetalleOut, CiclosEfectividadOut, CiclosEstadoOut, CiclosInstrumentosOut, CiclosPaisOut, CiclosPanoramaOut,
    CiclosSenalesOut, CiclosSimulacionOut, CiclosSimularIn, CiclosTasasOut,
)
from ..services import (
    ciclos_analytics, ciclos_avisos, ciclos_cartera, ciclos_catalogo, ciclos_efectividad, ciclos_engine, ciclos_historial, ciclos_ingesta,
    ciclos_senales_engine, ciclos_tasas,
)

router = APIRouter(prefix="/api/inversiones", tags=["ciclos"])


def _cartera(nombre: Optional[str], db: Session) -> Optional[str]:
    if not nombre:
        return None
    if not db.query(MovimientoInversion.id).filter(MovimientoInversion.cartera == nombre).first():
        raise HTTPException(status_code=404, detail=f"Cartera '{nombre}' no encontrada")
    return nombre


def _ids(texto: Optional[str]) -> Optional[tuple]:
    if texto is None:
        return None
    return tuple(i.strip() for i in texto.split(",") if i.strip())


def _llamar(fn, *args, **kwargs):
    """Errores de validación → 422; grupo, período o benchmark inexistente → 404."""
    try:
        return fn(*args, **kwargs)
    except ciclos_analytics.NoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Catálogo y datos ────────────────────────────────────────────────────────

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
        "comparaciones": cat.comparaciones,
        "pares_desfase": cat.pares_desfase,
        "tasas": [{"id": t.id, "nombre": t.nombre, "simbolo": t.simbolo, "plazo_meses": t.plazo_meses, "descripcion": t.descripcion,
                   "fuente": t.fuente, "activo": t.activo} for t in cat.tasas.values()],
        "pendientes_curva": cat.pendientes_curva,
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
    else:
        ciclos_avisos.correr(db)
    finally:
        db.close()


@router.post("/ciclos/refrescar", status_code=202)
def refrescar_ciclos():
    """Descarga las series ya mismo. Responde enseguida: la primera vez baja ~20 años de ~60 símbolos."""
    threading.Thread(target=_corrida_en_segundo_plano, daemon=True, name="ciclos").start()
    return {"resultado": "iniciado"}


# ── Panorama y detalle ──────────────────────────────────────────────────────

@router.get("/ciclos/panorama", response_model=CiclosPanoramaOut)
def get_panorama(
    tipo: str = Query("sector", max_length=20), benchmark: Optional[str] = Query(None, max_length=60),
    moneda: str = Query("USD", max_length=3), periodo: str = Query("6M", max_length=3),
    grupos: Optional[str] = Query(None, max_length=1000),
    ventana: int = Query(ciclos_engine.VENTANA_RRG, ge=3, le=52), cola: int = Query(ciclos_engine.COLA_DEFECTO, ge=1, le=52),
    db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.panorama, db, tipo, benchmark, moneda, periodo, _ids(grupos), ventana, cola)


@router.get("/ciclos/grupos/{grupo_id}", response_model=CiclosDetalleOut)
def get_detalle(
    grupo_id: str, benchmark: Optional[str] = Query(None, max_length=60), moneda: str = Query("USD", max_length=3),
    horizonte: Optional[str] = Query("3A", max_length=3), desde: Optional[date] = None, hasta: Optional[date] = None,
    periodo_id: Optional[str] = Query(None, max_length=60), con: Optional[str] = Query(None, max_length=500),
    ventana: int = Query(ciclos_engine.VENTANA_RRG, ge=3, le=52), db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.detalle, db, grupo_id, benchmark=benchmark, moneda=moneda, horizonte=horizonte,
                   desde=desde, hasta=hasta, periodo_id=periodo_id, con=_ids(con) or (), ventana=ventana)


@router.get("/ciclos/tasas", response_model=CiclosTasasOut)
def get_tasas(anios: int = Query(5), db: Session = Depends(get_db)):
    """Tasas del Tesoro de EE.UU.: nivel, cambios en puntos porcentuales, curva y pendientes. Describe; no pronostica."""
    return _llamar(ciclos_tasas.panorama, db, anios=anios)


@router.get("/ciclos/grupos/{grupo_id}/efectividad", response_model=CiclosEfectividadOut)
def get_efectividad(
    grupo_id: str, alcance: str = Query("grupo", max_length=10), benchmark: Optional[str] = Query(None, max_length=60),
    db: Session = Depends(get_db),
):
    """Qué pasó con el rendimiento relativo después de cada estado del ciclo, de este grupo o de todos los de su tipo.
    Describe el pasado con las series completas; no es una predicción ni una recomendación."""
    return _llamar(ciclos_efectividad.efectividad, db, grupo_id, alcance=alcance, benchmark=benchmark)


@router.get("/ciclos/grupos/{grupo_id}/senales", response_model=CiclosSenalesOut)
def get_senales(grupo_id: str, benchmark: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db)):
    """Cambios de estado confirmados de un grupo, sobre el historial semanal guardado. Sólo informa: no avisa ni recomienda."""
    cat = ciclos_catalogo.cargar()
    g = _llamar(ciclos_analytics._grupo, cat, grupo_id)
    b = _llamar(ciclos_analytics._benchmark_efectivo, cat, g, benchmark)
    res = ciclos_senales_engine.detectar(ciclos_historial.historial_de(db, g.id, b.id)) if b else ciclos_senales_engine.detectar([])
    return {
        "grupo_id": g.id, "benchmark_id": b.id if b else None, **res,
        "aviso": "Describe cambios ocurridos con los datos guardados; no es una predicción ni una recomendación.",
    }


@router.get("/ciclos/paises/{grupo_id}", response_model=CiclosPaisOut)
def get_pais(
    grupo_id: str, meses: int = Query(12), benchmark: Optional[str] = Query(None, max_length=60),
    moneda: str = Query("USD", max_length=3), db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.pais, db, grupo_id, meses=meses, benchmark=benchmark, moneda=moneda)


# ── Relaciones ──────────────────────────────────────────────────────────────

@router.get("/ciclos/relaciones/correlaciones", response_model=CiclosCorrelacionesOut)
def get_correlaciones(
    ids: Optional[str] = Query(None, max_length=1000), periodo: str = Query("1A", max_length=3),
    frecuencia: Optional[str] = Query(None, max_length=10), db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.correlaciones, db, ids=_ids(ids), periodo=periodo, frecuencia=frecuencia)


@router.get("/ciclos/relaciones/desfases", response_model=CiclosDesfasesOut)
def get_desfases(
    a: str = Query(..., max_length=60), b: str = Query(..., max_length=60), meses: int = Query(36),
    db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.desfases, db, a=a, b=b, meses=meses)


@router.get("/ciclos/relaciones/comparacion", response_model=CiclosComparacionOut)
def get_comparacion(
    ids: str = Query(..., max_length=1000), benchmark: Optional[str] = Query(None, max_length=60),
    moneda: str = Query("USD", max_length=3), desde: Optional[date] = None, hasta: Optional[date] = None,
    periodo_id: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db),
):
    return _llamar(ciclos_analytics.comparacion, db, ids=_ids(ids) or (), benchmark=benchmark, moneda=moneda,
                   desde=desde, hasta=hasta, periodo_id=periodo_id)


# ── Mi cartera ──────────────────────────────────────────────────────────────

def _exposicion(cartera: Optional[str], benchmark: Optional[str], db: Session) -> dict:
    return _llamar(ciclos_cartera.exposicion, cartera, db, benchmark)


@router.get("/carteras/{nombre}/ciclos/cartera", response_model=CiclosCarteraOut)
def get_cartera_ciclos(nombre: str, benchmark: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db)):
    return _exposicion(_cartera(nombre, db), benchmark, db)


@router.get("/consolidado/ciclos/cartera", response_model=CiclosCarteraOut)
def get_consolidado_ciclos(benchmark: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db)):
    return _exposicion(None, benchmark, db)


@router.get("/carteras/{nombre}/ciclos/grupos/{grupo_id}/instrumentos", response_model=CiclosInstrumentosOut)
def get_instrumentos_cartera(
    nombre: str, grupo_id: str, benchmark: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db),
):
    return _llamar(ciclos_cartera.instrumentos_de_grupo, _cartera(nombre, db), db, grupo_id, benchmark)


@router.get("/consolidado/ciclos/grupos/{grupo_id}/instrumentos", response_model=CiclosInstrumentosOut)
def get_instrumentos_consolidado(grupo_id: str, benchmark: Optional[str] = Query(None, max_length=60), db: Session = Depends(get_db)):
    return _llamar(ciclos_cartera.instrumentos_de_grupo, None, db, grupo_id, benchmark)


def _simular(cartera: Optional[str], body: CiclosSimularIn, db: Session) -> dict:
    return _llamar(ciclos_cartera.simular_rotacion, cartera, db, body.origen, body.destino, body.pct, body.benchmark)


@router.post("/carteras/{nombre}/ciclos/simular", response_model=CiclosSimulacionOut)
def simular_cartera(nombre: str, body: CiclosSimularIn, db: Session = Depends(get_db)):
    """Cómo quedaría la mezcla al trasladar un % de la cartera de un grupo a otro. No guarda nada."""
    return _simular(_cartera(nombre, db), body, db)


@router.post("/consolidado/ciclos/simular", response_model=CiclosSimulacionOut)
def simular_consolidado(body: CiclosSimularIn, db: Session = Depends(get_db)):
    return _simular(None, body, db)
