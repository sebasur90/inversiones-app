"""Informe de cobertura REAL de los proxies de «Ciclos de mercado» antes de habilitarlos.

Por cada símbolo del catálogo muestra desde cuándo hay datos, hasta cuándo, cuántas barras, el mayor
hueco entre fechas y qué horizontes (1A/3A/5A/10A) quedan cubiertos. Lo que no baja se marca en el
JSON con `activo: false` y una `nota`; nunca se completa con estimaciones.

Corre DENTRO del contenedor (con el proxy corporativo si corresponde):

    docker compose exec backend python -m scripts.verificar_ciclos
    docker compose exec backend python -m scripts.verificar_ciclos --sin-bajar     # sólo lo ya guardado
    docker compose exec backend python -m scripts.verificar_ciclos --inactivos     # prueba también los `activo: false`

`--inactivos` baja esos símbolos sólo para el informe: no escribe nada en la base.
Sale con código 1 si algún grupo activo se queda sin datos.
"""
import argparse
import sys
from datetime import date, timedelta

from app.database import Base, BarraOHLCV, SessionLocal, engine
from app.services import benchmarks, ciclos_catalogo, ciclos_ingesta
from app.services.market_data import yahoo

HORIZONTES = (("1A", 365), ("3A", 3 * 365), ("5A", 5 * 365), ("10A", 10 * 365))
HUECO_ALERTA_DIAS = 10


def _resumen(fechas: list[date], hoy: date) -> dict:
    if not fechas:
        return {"n": 0}
    fechas = sorted(set(fechas))
    huecos = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    return {
        "n": len(fechas), "desde": fechas[0], "hasta": fechas[-1],
        "hueco": max(huecos) if huecos else 0,
        "horizontes": [nombre for nombre, dias in HORIZONTES if fechas[0] <= hoy - timedelta(days=dias + 10)],
    }


def _linea(simbolo: str, r: dict, extra: str = "") -> str:
    if not r["n"]:
        return f"  {simbolo:<12} SIN DATOS {extra}"
    marca = " ⚠ hueco" if r["hueco"] > HUECO_ALERTA_DIAS else ""
    return (f"  {simbolo:<12} {r['desde']} → {r['hasta']}  {r['n']:>6} barras  "
            f"hueco máx {r['hueco']:>3} d  cubre {','.join(r['horizontes']) or '—'}{marca} {extra}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sin-bajar", action="store_true", help="no descarga: informa lo ya guardado")
    parser.add_argument("--inactivos", action="store_true", help="prueba también los grupos con `activo: false`")
    args = parser.parse_args()

    hoy = date.today()
    cat = ciclos_catalogo.cargar()
    for e in cat.errores:
        print(f"CATÁLOGO: {e}")
    print(f"Catálogo v{cat.version}: {len(cat.grupos)} grupos ({len(cat.activos())} activos).")

    # Las tablas las crea la app al arrancar (`create_all`, sólo agrega las que faltan); acá se garantiza que
    # existan por si se corre antes de levantarla.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if not args.sin_bajar:
            print("Descargando (la primera vez baja ~20 años de cada símbolo)...")
            print(" ", ciclos_ingesta.correr(db))

        simbolos = cat.simbolos()
        sin_datos = []
        print("\nSímbolos activos:")
        for s in sorted(simbolos):
            fechas = [f for (f,) in db.query(BarraOHLCV.fecha).filter(BarraOHLCV.ticker == benchmarks.clave(s))]
            r = _resumen(fechas, hoy)
            est = next((x for x in ciclos_ingesta.estado(db, hoy) if x["simbolo"] == s), None)
            extra = f"[{simbolos[s].rol}, {simbolos[s].moneda}]" + (" DESACTUALIZADO" if est and est["desactualizado"] else "")
            print(_linea(s, r, extra))
            if not r["n"]:
                sin_datos.append(s)

        faltan = [g.id for g in cat.activos() if g.proxy in sin_datos]
        if args.inactivos:
            pendientes = [g for g in cat.grupos.values() if not g.activo and g.proxy]
            print("\nGrupos inactivos (prueba en memoria, no se guarda):")
            for g in pendientes:
                datos, _ = yahoo.fetch_cierres_lote([g.proxy], date(2005, 1, 1), hoy)
                serie = datos.get(g.proxy, [])
                print(_linea(g.proxy, _resumen([f for f, _ in serie], hoy), f"({g.id})"))

        print()
        if faltan:
            print("GRUPOS ACTIVOS SIN DATOS (ponerlos en `activo: false` con una nota): " + ", ".join(faltan))
            return 1
        print("Todos los grupos activos tienen datos.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
