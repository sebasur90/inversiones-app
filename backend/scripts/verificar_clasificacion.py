"""Compara, contra la base real, la clasificación del Sheet con la clasificación resuelta
(corrección manual > seed > Yahoo > Sheet) antes de prenderla con `CLASIFICACION_AUTO=true`.

Muestra:
1. los tickers de cartera y watchlist cuyo tipo, sector o país cambia, y de qué fuente sale;
2. los pesos de cada eje de Exposición en los dos modos;
3. que el total de cada eje no cambie (la clasificación mueve etiquetas, nunca plata).

Corre DENTRO del contenedor:

    docker compose exec backend python -m scripts.verificar_clasificacion
    docker compose exec backend python -m scripts.verificar_clasificacion --cartera "Mi cartera"

Sale con código 1 si algún total de eje cambia entre los dos modos.
"""
import argparse
import os
import sys

from app.database import SessionLocal
from app.services import clasificacion_analytics
from app.services.cache import limpiar_cache
from app.services.inversiones_analytics import get_exposicion

TOLERANCIA_USD = 0.05


def _exposicion(cartera, db, auto: bool) -> dict:
    os.environ["CLASIFICACION_AUTO"] = "true" if auto else "false"
    limpiar_cache()
    return {eje["eje"]: eje["items"] for eje in get_exposicion(cartera, db)["ejes"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cartera", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=== Tickers cuya clasificación cambia")
        difs = clasificacion_analytics.diferencias(db)
        if not difs:
            print("  (ninguno)")
        for d in difs:
            donde = "cartera" if d["en_cartera"] else "watchlist"
            partes = [f"{c}: {v['antes']!r} -> {v['despues']!r} ({v['fuente'] or 'sin dato'})"
                      for c, v in d["cambios"].items()]
            print(f"  {d['ticker']:<8} [{donde}] región={d['region']!r}  " + "; ".join(partes))

        original = os.environ.get("CLASIFICACION_AUTO")
        sheet = _exposicion(args.cartera, db, auto=False)
        auto = _exposicion(args.cartera, db, auto=True)
        if original is None:
            os.environ.pop("CLASIFICACION_AUTO", None)
        else:
            os.environ["CLASIFICACION_AUTO"] = original

        todo_ok = True
        for eje in sorted(set(sheet) | set(auto)):
            a, b = sheet.get(eje, []), auto.get(eje, [])
            total_a = sum(it["valor_usd"] for it in a)
            total_b = sum(it["valor_usd"] for it in b)
            ok = abs(total_a - total_b) <= TOLERANCIA_USD
            todo_ok &= ok
            print(f"\n=== Eje {eje}: total Sheet {total_a:,.2f} / resuelto {total_b:,.2f} [{'ok' if ok else 'DIF'}]")
            pesos_a = {it["etiqueta"]: it["porcentaje"] for it in a}
            pesos_b = {it["etiqueta"]: it["porcentaje"] for it in b}
            for etiqueta in sorted(set(pesos_a) | set(pesos_b), key=lambda e: -max(pesos_a.get(e, 0), pesos_b.get(e, 0))):
                pa, pb = pesos_a.get(etiqueta, 0.0), pesos_b.get(etiqueta, 0.0)
                marca = "" if abs(pa - pb) < 0.01 else "  <-"
                print(f"  {etiqueta:<28} {pa:>7.2f}%  {pb:>7.2f}%{marca}")
        return 0 if todo_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
