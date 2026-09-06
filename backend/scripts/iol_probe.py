"""Sondeo manual de la API de IOL: valida los nombres de panel de `market_data/iol.py` contra
una cuenta real y mide el costo en llamadas de un sync completo.

Los nombres de panel en `_PANELES` se fijaron con lo que expone código de terceros -- la
documentación oficial de IOL responde 403 a cualquier cliente que no sea un navegador logueado, así
que no hay forma de confirmarlos sin credenciales reales. Este script se corre UNA VEZ (o cuando
se sospeche que IOL cambió los nombres de panel) para:

  1. Confirmar cuáles de los `_PANELES` candidatos existen y cuántos símbolos trae cada uno.
  2. Contar cuántas llamadas reales consume (para validar el presupuesto de DESARROLLO.md).
  3. Volcar una fila cruda de `seriehistorica` para confirmar los nombres reales de los campos
     OHLCV, que `iol.fetch_historico_ohlcv` hoy resuelve probando varios alias a ciegas
     (`_ALIAS_APERTURA` y hermanos). Con la salida de este paso se pueden fijar los nombres
     correctos y borrar los alias que sobren.

Requiere `credentials/iol.json` ya configurado (ver CREDENTIALS.md). Corre DENTRO del contenedor,
como el resto de la app:

    docker compose up -d backend
    docker compose exec backend python -m scripts.iol_probe

IMPORTANTE: nunca imprime la contraseña ni el bearer token -- sólo status HTTP, cantidad de
`titulos` y hasta 3 símbolos de muestra por panel.
"""
import sys
from datetime import date, timedelta

from app.database import SessionLocal
from app.services.market_data import iol, iol_auth
from app.services.market_data.client import request_json


def _probar_panel(db, instrumento: str, panel: str, pais: str) -> None:
    url = f"{iol_auth.BASE_URL}/Cotizaciones/{instrumento}/{panel}/{pais}"
    token = iol_auth.get_bearer(db)
    if token is None:
        print(f"  {instrumento}/{panel}/{pais}: SIN TOKEN (ver mensajes de error arriba)")
        return
    if not iol_auth.cupo_disponible(db):
        print(f"  {instrumento}/{panel}/{pais}: SIN CUPO, se detiene el sondeo")
        return
    iol_auth.registrar_llamada(db)
    status, body = request_json("GET", url, headers={"Authorization": f"Bearer {token}"})

    if status != 200 or not isinstance(body, dict):
        print(f"  {instrumento}/{panel}/{pais}: HTTP {status} -- no existe o falló")
        return
    titulos = body.get("titulos")
    if not isinstance(titulos, list):
        print(f"  {instrumento}/{panel}/{pais}: HTTP 200 pero sin 'titulos' -- revisar forma de la respuesta")
        return
    muestra = [t.get("simbolo") for t in titulos[:3] if isinstance(t, dict)]
    print(f"  {instrumento}/{panel}/{pais}: OK, {len(titulos)} símbolos (muestra: {muestra})")


def _probar_seriehistorica(db, simbolo: str = "AL30", mercado: str = "bCBA") -> None:
    """Vuelca las claves y una fila cruda de `seriehistorica`, y muestra qué alias de
    `fetch_historico_ohlcv` matchearon. Es la única forma de confirmar los nombres de los campos
    OHLCV sin la documentación oficial (que responde 403)."""
    hasta = date.today() - timedelta(days=1)
    desde = hasta - timedelta(days=10)
    url = (f"{iol_auth.BASE_URL}/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/"
           f"{desde:%Y-%m-%d}/{hasta:%Y-%m-%d}/sinAjustar")

    token = iol_auth.get_bearer(db)
    if token is None:
        print("  SIN TOKEN, se omite el sondeo de seriehistorica")
        return
    if not iol_auth.cupo_disponible(db):
        print("  SIN CUPO, se omite el sondeo de seriehistorica")
        return
    iol_auth.registrar_llamada(db)
    status, body = request_json("GET", url, headers={"Authorization": f"Bearer {token}"})

    if status != 200 or not isinstance(body, list) or not body:
        print(f"  {simbolo}: HTTP {status} o respuesta vacía -- no se pudo inspeccionar la serie")
        return

    fila = next((f for f in body if isinstance(f, dict)), None)
    if fila is None:
        print(f"  {simbolo}: la respuesta no trae filas dict")
        return

    print(f"  {simbolo}: {len(body)} ruedas. Claves de una fila: {sorted(fila.keys())}")
    print(f"  Fila cruda de muestra: {fila}")
    for etiqueta, alias in (
        ("apertura", iol._ALIAS_APERTURA),
        ("maximo", iol._ALIAS_MAXIMO),
        ("minimo", iol._ALIAS_MINIMO),
        ("volumen", iol._ALIAS_VOLUMEN),
    ):
        matcheado = next((a for a in alias if a in fila), None)
        estado = f"'{matcheado}'" if matcheado else "NINGUNO (la barra sale close-only)"
        print(f"    {etiqueta}: {estado}   [alias probados: {list(alias)}]")


def main() -> int:
    # Sesión propia de este script: a diferencia del sync (que reusa una única sesión larga y
    # por eso `iol_auth` no comitea el contador de cupo ahí, ver su docstring), acá no hay una
    # transacción más grande con la que competir -- comiteamos explícitamente para que las
    # llamadas que este sondeo gasta queden contadas aunque el script se corte a mitad de camino.
    db = SessionLocal()
    try:
        if not iol_auth.iol_enabled():
            print("IOL_ENABLED=false -- no hay nada que sondear.")
            return 1
        if iol_auth._leer_credenciales() is None:
            print(f"No se encontraron credenciales en '{iol_auth._credentials_path()}'. "
                  "Configurá credentials/iol.json (ver CREDENTIALS.md) antes de correr esto.")
            return 1

        print("Probando autenticación...")
        token = iol_auth.get_bearer(db)
        db.commit()
        if token is None:
            print("No se pudo autenticar. Revisá usuario/contraseña y que el servicio de API "
                  "esté habilitado en tu cuenta de IOL (Perfil -> API).")
            return 1
        print("Autenticación OK.\n")

        print(f"Probando {len(iol._PANELES)} paneles candidatos:")
        for instrumento, panel, pais in iol._PANELES:
            _probar_panel(db, instrumento, panel, pais)
            db.commit()

        print("\nInspeccionando los campos OHLCV de seriehistorica:")
        _probar_seriehistorica(db)
        db.commit()

        fila = db.get(iol_auth.EstadoApiIol, iol_auth._periodo_actual())
        llamadas = fila.llamadas if fila is not None else 0
        print(f"\nLlamadas consumidas este mes calendario: {llamadas} / {iol_auth._limite_mensual()}")
        print("\nSi algún panel dio HTTP 404, ajustá el nombre en `_PANELES` "
              "(backend/app/services/market_data/iol.py) con lo que haya funcionado acá.")
        print("Si algún campo OHLCV dio 'NINGUNO', agregá el nombre real que aparezca en la fila "
              "cruda a los `_ALIAS_*` del mismo archivo: sin eso las velas de IOL salen close-only.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
