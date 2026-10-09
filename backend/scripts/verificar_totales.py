"""Verifica, contra la base real, que todas las pantallas informen el mismo valor de cartera.

La pantalla principal (`get_resumen`) valúa al costo de compra lo que no tiene cotización. Las
pantallas que muestran un total o pesos (Exposición, Descomposición, Rebalanceo, Posiciones)
tienen que hacer lo mismo, o sus porcentajes —y las propuestas de rebalanceo que salen de
ellos— quedan medidos contra un patrimonio recortado.

Los tests cubren la lógica; esto cubre la cartera real, que es donde viven los casos raros
(tickers sin ficha, bonos sin precio, MEP faltante). Corre DENTRO del contenedor:

    docker compose exec backend python -m scripts.verificar_totales
    docker compose exec backend python -m scripts.verificar_totales --cartera "Mi cartera"

Sale con código 1 si encuentra alguna diferencia mayor a la tolerancia.
"""
import argparse
import sys

from app.database import SessionLocal
from app.services.descomposicion_analytics import get_descomposicion
from app.services.inversiones_analytics import (
    get_carteras,
    get_exposicion,
    get_rebalanceo,
    get_rendimiento_por_ticker,
    get_resumen,
)

TOLERANCIA_USD = 0.05


def _comparar(nombre: str, obtenido: float, esperado: float) -> bool:
    diferencia = obtenido - esperado
    ok = abs(diferencia) <= TOLERANCIA_USD
    marca = "ok  " if ok else "DIF "
    print(f"  [{marca}] {nombre:<34} {obtenido:>16,.2f}   dif {diferencia:>14,.2f}")
    return ok


def verificar(cartera: str | None, db) -> bool:
    etiqueta = cartera or "Consolidado"
    resumen = get_resumen(cartera, db)
    esperado = resumen["valor_actual_usd"]
    print(f"\n=== {etiqueta} — valor_actual_usd de la pantalla principal: {esperado:,.2f}")

    todo_ok = True

    exposicion = get_exposicion(cartera, db)
    for eje in exposicion["ejes"]:
        total = sum(it["valor_usd"] for it in eje["items"])
        todo_ok &= _comparar(f"Exposición · eje {eje['eje']}", total, esperado)

    todo_ok &= _comparar("Descomposición", get_descomposicion(cartera, db)["total_usd"], esperado)

    for eje in get_rebalanceo(cartera, db)["ejes"]:
        todo_ok &= _comparar(f"Rebalanceo · eje {eje['eje']}", eje["total_usd"], esperado)

    posiciones = get_rendimiento_por_ticker(cartera, db)
    todo_ok &= _comparar("Posiciones (suma de filas)", sum(p["valor_actual_usd"] for p in posiciones), esperado)

    avisos = exposicion["avisos"]
    if any(avisos.values()):
        print("  Avisos de valuación:")
        for clave, tickers in avisos.items():
            if tickers:
                print(f"    - {clave}: {', '.join(tickers)}")
    else:
        print("  Sin avisos: todas las posiciones tienen cotización y ficha.")

    al_costo = [p["ticker"] for p in posiciones if p.get("valuado_al_costo")]
    if al_costo:
        print(f"  Posiciones valuadas al costo en Posiciones: {', '.join(al_costo)}")

    return todo_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cartera", help="sólo esta cartera (por defecto: Consolidado y todas)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        alcances = [args.cartera] if args.cartera else [None, *get_carteras(db)]
        todo_ok = all(verificar(cartera, db) for cartera in alcances)
    finally:
        db.close()

    print("\nTodo coincide." if todo_ok else "\nHay diferencias: ver las líneas marcadas con DIF.")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
