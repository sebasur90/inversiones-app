"""Ejemplo end-to-end del laboratorio de estrategias, sin infraestructura nueva: arma la
estrategia "mínimo histórico" con el builder, la evalúa sobre la serie real de un ticker, la
corre *como la corre la app* y escribe el JSON exportable.

Sirve para validar el builder (fase 5) antes de que exista el servicio Docker, y como referencia
del flujo que después se hace en el notebook.

Corre DENTRO del contenedor, como el resto de la app:

    docker compose up -d backend
    docker compose exec backend python -m scripts.lab_ejemplo AAPL
    docker compose exec backend python -m scripts.lab_ejemplo AAPL --variante subyacente --desde 2015-01-01

El JSON queda en `/app/lab/estrategias/` (montado en `./lab/estrategias/` con el servicio `lab`)
o, si esa carpeta no existe, en el directorio actual.
"""
import argparse
import sys
from pathlib import Path

from app.lab import Estrategia, ind, barras_de_db, correr_como_la_app


def construir_estrategia() -> Estrategia:
    canal = ind.EXTREMOS(ventana=0)  # 0 = histórico acumulado
    return (
        Estrategia("Mínimo histórico", descripcion="Compra a <=1% del mínimo histórico, vende a <=1% del máximo.")
        .comprar(canal.dist_min_pct <= 1.0)
        .vender(canal.dist_max_pct >= -1.0)
        .riesgo(stop_loss_pct=20)
        .ejecucion(comision_pct=0.6, precio_ejecucion="apertura_siguiente", demora_barras=1)
    )


def _destino_json(nombre_archivo: str) -> Path:
    preferido = Path("/app/lab/estrategias")
    carpeta = preferido if preferido.is_dir() else Path.cwd()
    return carpeta / nombre_archivo


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Ejemplo del laboratorio de estrategias.")
    parser.add_argument("ticker", help="ticker de la cartera o watchlist (p.ej. AAPL)")
    parser.add_argument("--desde", default="2015-01-01", help="fecha de inicio del análisis (YYYY-MM-DD)")
    parser.add_argument("--hasta", default=None, help="fecha de fin (YYYY-MM-DD); default: hoy")
    parser.add_argument("--variante", default="local", choices=["local", "subyacente"])
    args = parser.parse_args(argv)

    est = construir_estrategia()
    print("DSL:")
    print(est.a_json())
    print()

    barras = barras_de_db(args.ticker, desde=args.desde, hasta=args.hasta, variante=args.variante)
    if len(barras) < 2:
        print(f"Sin serie suficiente para {args.ticker!r} (variante {args.variante}).", file=sys.stderr)
        return 1
    print(f"{len(barras)} barras entre {barras[0].fecha} y {barras[-1].fecha} (variante {args.variante}).")
    print()

    df = est.dataframe(barras)
    print("df.tail():")
    print(df.tail())
    print()

    res = correr_como_la_app(args.ticker, est, desde=args.desde, hasta=args.hasta, variante=args.variante)
    m = res["metricas"]
    print("Métricas (como la app):")
    for clave in ("estado", "retorno_total_pct", "retorno_buy_hold_pct", "exceso_vs_buy_hold_pp",
                  "operaciones", "operaciones_cerradas", "win_rate_pct", "profit_factor",
                  "max_drawdown_pct", "exposicion_pct"):
        print(f"  {clave:24} {m.get(clave)}")
    print()
    print(f"Operaciones ({len(res['operaciones'])}):")
    for o in res["operaciones"]:
        print(f"  {o['fecha_entrada']} -> {o['fecha_salida'] or '(abierta)':12} "
              f"{o['retorno_neto_pct']:+7.2f}%  {o['motivo_salida'] or ''}")
    print()

    destino = _destino_json("estrategia-minimo-historico.json")
    est.ticker = None  # la lógica es reusable en cualquier activo
    est.variante = args.variante
    est.exportar(destino)
    print(f"JSON exportado en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
