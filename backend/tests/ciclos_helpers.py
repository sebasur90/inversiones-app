"""Catálogo y series sintéticas compartidos por los tests de Ciclos de mercado (analytics, cartera y router).

Todo es de juguete y de resultado conocido: nada se parece a un dato real. Las series terminan siempre el viernes
anterior a hoy, así que ningún test depende de en qué día se corra (nunca quedan «desactualizadas»).
"""
import json
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, BarraOHLCV, ClasificacionAuto, IndiceMercado, InstrumentoInversion, MovimientoInversion, PrecioInstrumento,
)
from app.services import clasificacion_analytics as clasif
from app.services.cache import limpiar_cache

SEMANAS = 170           # ~3,3 años: cubre 3A pero no 5A
GRUPOS = [
    {"id": "estados-unidos", "nombre": "Estados Unidos", "tipo": "region", "vistas": ["region", "pais"], "proxy": "SPY",
     "es_benchmark": True, "benchmark": None, "region": "EEUU",
     "eje_cartera": [{"eje": "region", "valores": ["EEUU"]}, {"eje": "pais", "valores": ["Estados Unidos"]}]},
    {"id": "global", "nombre": "Global", "tipo": "region", "proxy": "ACWI", "es_benchmark": True, "benchmark": None,
     "region": "Global", "eje_cartera": [{"eje": "region", "valores": ["Global"]}]},
    {"id": "tecnologia", "nombre": "Tecnología", "tipo": "sector", "proxy": "XLK", "region": "EEUU",
     "eje_cartera": [{"eje": "sector", "valores": ["Tecnología"]}]},
    {"id": "salud", "nombre": "Salud", "tipo": "sector", "proxy": "XLV", "region": "EEUU",
     "eje_cartera": [{"eje": "sector", "valores": ["Salud"]}]},
    {"id": "energia", "nombre": "Energía", "tipo": "sector", "proxy": "XLE", "region": "EEUU",
     "eje_cartera": [{"eje": "sector", "valores": ["Energía"]}]},
    {"id": "consumo-basico", "nombre": "Consumo básico", "tipo": "sector", "proxy": "XLP", "region": "EEUU",
     "eje_cartera": [{"eje": "sector", "valores": ["Consumo básico"]}]},
    {"id": "semiconductores", "nombre": "Semiconductores", "tipo": "industria", "padre": "tecnologia", "proxy": "SMH",
     "region": "EEUU", "cartera": {"industria": ["Semiconductores"]}},
    {"id": "inteligencia-artificial", "nombre": "Inteligencia artificial", "tipo": "tema", "proxy": "AIQ", "lista_curada": True,
     "cartera": {"industria": ["Semiconductores"], "tickers": ["NVDA"]}, "nota": "lista curada"},
    {"id": "commodities-amplios", "nombre": "Commodities amplios", "tipo": "commodity", "proxy": "DBC",
     "nota": "ETF de futuros: incluye el efecto del roll."},
    {"id": "oro", "nombre": "Oro", "tipo": "commodity", "vistas": ["commodity", "activo"], "padre": "commodities-amplios",
     "proxy": "GLD", "cartera": {"tickers": ["GLD"]}},
    {"id": "europa", "nombre": "Europa", "tipo": "region", "vistas": ["region", "pais"], "proxy": "VGK",
     "exclusivo": True, "eje_cartera": [{"eje": "pais", "valores": ["Alemania"]}]},
    {"id": "brasil", "nombre": "Brasil", "tipo": "pais", "proxy": "EWZ", "region": "Emergentes",
     "eje_cartera": [{"eje": "pais", "valores": ["Brasil"]}],
     "indice_local": {"simbolo": "^BVSP", "moneda": "BRL"}, "fx": {"simbolo": "BRL=X", "cotizacion": "local_por_usd"}},
    {"id": "argentina", "nombre": "Argentina", "tipo": "pais", "vistas": ["pais", "region"], "proxy": "ARGT", "region": "Argentina",
     "eje_cartera": [{"eje": "pais", "valores": ["Argentina"]}, {"eje": "region", "valores": ["Argentina"]}],
     "indice_local": {"simbolo": "^MERV", "moneda": "ARS"}, "fx": {"simbolo": None, "cotizacion": "mep"}},
    {"id": "emergentes", "nombre": "Mercados emergentes", "tipo": "region", "proxy": "EEM", "region": "Emergentes",
     "eje_cartera": [{"eje": "region", "valores": ["Emergentes"]}]},
    {"id": "apagado", "nombre": "Apagado", "tipo": "commodity", "proxy": "ALI=F", "activo": False},
]
DOC = {
    "version": 1,
    "defecto_por_tipo": {
        "sector": {"benchmark": "estados-unidos", "exclusivo": True}, "industria": {"benchmark": "estados-unidos"},
        "tema": {"benchmark": "estados-unidos"}, "commodity": {"benchmark": "global"}, "region": {"benchmark": "global"},
        "pais": {"benchmark": "global", "exclusivo": True}, "activo": {"benchmark": "global"},
    },
    "comparaciones": [{"id": "eeuu-europa", "nombre": "EE.UU. vs. Europa", "grupos": ["estados-unidos", "europa"]}],
    "pares_desfase": [{"id": "oro-acciones", "nombre": "Oro → acciones", "grupos": ["oro", "global"]}],
    "grupos": GRUPOS,
}


def escribir_catalogo(tmp_path, monkeypatch, doc=None):
    ruta = tmp_path / "grupos.json"
    ruta.write_text(json.dumps(doc or DOC), encoding="utf-8")
    ruta_p = tmp_path / "periodos.json"
    # El período de prueba es relativo a hoy: con fechas fijas dejaría de caer dentro de las series.
    periodos = {"periodos": [{"id": "tramo", "nombre": "Un tramo", "desde": (fin() - timedelta(days=300)).isoformat(),
                              "hasta": (fin() - timedelta(days=100)).isoformat()}]}
    ruta_p.write_text(json.dumps(periodos), encoding="utf-8")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(ruta))
    monkeypatch.setenv("CICLOS_PERIODOS_FILE", str(ruta_p))


def fin() -> date:
    """El viernes anterior a hoy."""
    d = date.today() - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def lunes_inicial(semanas: int = SEMANAS) -> date:
    return fin() - timedelta(days=4) - timedelta(days=7 * (semanas - 1))


def dias_habiles(semanas: int = SEMANAS) -> list[date]:
    d0 = lunes_inicial(semanas)
    return [d0 + timedelta(days=7 * w + i) for w in range(semanas) for i in range(5)]


def benchmark(tasa: float = 0.0004, semanas: int = SEMANAS) -> list[tuple[date, float]]:
    return [(d, 100.0 * (1 + tasa) ** k) for k, d in enumerate(dias_habiles(semanas))]


def crece(g: float, n: int, desde: float = 1.0) -> list[float]:
    return [desde * g ** i for i in range(1, n + 1)]


def perfil(*tramos, semanas: int = SEMANAS) -> list[float]:
    """Relación grupo/benchmark semana a semana: tramos ("plano", n) o ("crece", g, n), rellenando al principio con 1.0."""
    rs: list[float] = []
    nivel = 1.0
    for t in tramos:
        if t[0] == "plano":
            rs += [nivel] * t[1]
        else:
            rs += crece(t[1], t[2], nivel)
            nivel = rs[-1]
    return [1.0] * (semanas - len(rs)) + rs


def con_rs(bench, rs: list[float]) -> list[tuple[date, float]]:
    """Serie diaria tal que (último día de cada semana) grupo/benchmark = `rs[semana]`."""
    d0 = bench[0][0]
    return [(d, v * rs[(d - d0).days // 7]) for d, v in bench]


PERFILES = {
    "leading": lambda: perfil(("plano", SEMANAS - 20), ("crece", 1.015, 20)),
    "lagging": lambda: perfil(("plano", SEMANAS - 20), ("crece", 0.985, 20)),
    "weakening": lambda: perfil(("plano", SEMANAS - 46), ("crece", 1.015, 40), ("plano", 6)),
    "improving": lambda: perfil(("plano", SEMANAS - 46), ("crece", 0.985, 40), ("plano", 6)),
}


def cargar_series(db, series: dict[str, list[tuple[date, float]]], moneda: str = "USD") -> None:
    filas = [{"ticker": f"{simbolo}@BENCH", "fecha": f, "cierre": c, "moneda": moneda, "fuente": "yahoo"}
             for simbolo, serie in series.items() for f, c in serie]
    db.bulk_insert_mappings(BarraOHLCV, filas)
    db.commit()


def series_basicas(estados: dict[str, str] | None = None) -> dict[str, list[tuple[date, float]]]:
    """SPY y ACWI planos-ish y los cuatro sectores en el estado de rotación que se pida."""
    estados = estados or {"XLK": "leading", "XLV": "lagging", "XLE": "weakening", "XLP": "improving"}
    spy, acwi = benchmark(0.0004), benchmark(0.0003)
    out = {"SPY": spy, "ACWI": acwi}
    for simbolo, estado in estados.items():
        out[simbolo] = con_rs(spy, PERFILES[estado]())
    return out


# -- cartera de juguete --------------------------------------------------------------------------

def inst(db, ticker, sector, pais, tipo="Accion", moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="NYSE", moneda=moneda,
                                sector=sector, pais=pais))


def pos(db, ticker, cantidad, precio, cartera="Principal", moneda="USD", con_precio=True):
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera=cartera, ticker=ticker, tipo_movimiento="compra",
                               cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0))
    if con_precio:
        db.add(PrecioInstrumento(fecha=date(2024, 6, 1), ticker=ticker, precio=precio, moneda=moneda))


def auto(db, base, sector, industria, nombre=None, pais="Estados Unidos", region="EEUU"):
    db.add(ClasificacionAuto(ticker_base=base, simbolo_yahoo=base, estado="ok", tipo="Acción", nombre=nombre or base,
                             quote_type="EQUITY", sector=sector, industria=industria, industria_raw=industria, pais=pais,
                             region=region, intentos_fallidos=0, fecha_fundamentales=date.today()))


TOTAL_CARTERA = 2900.0


def cartera_de_prueba(tmp_path, monkeypatch):
    """Catálogo y series de prueba más una cartera «Principal» de 2.900 USD: MSFT 1000 y NVDA 500 (tecnología), KO 700
    (un CEDEAR en dólares y su variante en pesos), GLD 200, GGAL 200 (financiero, Argentina) y NOSEC 300 (sin sector ni país).
    Devuelve la fábrica de sesiones."""
    escribir_catalogo(tmp_path, monkeypatch)
    monkeypatch.setattr(clasif, "cargar_catalogo", lambda: [
        {"simbolo": "KO", "descripcion": "COCA COLA", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "KOD", "descripcion": "COCA COLA", "moneda": "USD", "tipo": "CEDEAR"},
    ])
    monkeypatch.setattr(clasif, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    auto(db, "MSFT", "Tecnología", "Software de infraestructura", "Microsoft")
    auto(db, "NVDA", "Tecnología", "Semiconductores", "NVIDIA")
    auto(db, "KO", "Consumo básico", "Bebidas sin alcohol", "Coca-Cola")
    inst(db, "MSFT", "Tecnología", "Estados Unidos")
    inst(db, "NVDA", "Tecnología", "Estados Unidos")
    inst(db, "KOD", "Consumo básico", "Estados Unidos", tipo="CEDEAR")
    inst(db, "KO", "Consumo básico", "Estados Unidos", tipo="CEDEAR", moneda="ARS")
    inst(db, "GLD", "Materias primas", "Estados Unidos", tipo="CEDEAR")
    inst(db, "NOSEC", None, None)
    inst(db, "GGAL", "Financiero", "Argentina")
    db.commit()
    pos(db, "MSFT", 10, 100.0)                       # 1000
    pos(db, "NVDA", 5, 100.0)                        # 500
    pos(db, "KOD", 10, 50.0)                         # 500
    pos(db, "KO", 4, 50_000.0, moneda="ARS")         # 200 USD al MEP de 1000
    pos(db, "GLD", 2, 100.0)                         # 200
    pos(db, "NOSEC", 3, 100.0)                       # 300
    pos(db, "GGAL", 4, 50.0)                         # 200
    db.commit()
    cargar_series(db, series_basicas())
    db.close()
    limpiar_cache()
    return Sesion
