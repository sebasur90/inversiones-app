"""Catálogo de instrumentos de IOL: descubre todos los tickers (acciones, CEDEARs, bonos, ONs,
letras, FCI, ...) y los guarda en un archivo consultable, marcando qué apareció desde la última
corrida.

Para qué sirve: los nombres de ticker que llegan de la planilla no siempre coinciden con los
símbolos de IOL (sufijos D/C, guiones, ONs con nomenclatura propia). Este script deja un archivo
con el símbolo exacto, la descripción, la moneda y en qué panel vive cada instrumento, para poder
mapear a mano lo que el sync no resuelve solo.

Cómo descubre (no hay endpoint "traeme todo"), todo con llamadas que devuelven listas enteras --
nunca una llamada por ticker:

  1. `GET /{pais}/Titulos/Cotizacion/Instrumentos`          -> 1 llamada (Acciones, Bonos, FCI, ...)
  2. `GET /{pais}/Titulos/Cotizacion/Paneles/{instrumento}` -> 1 por instrumento
  3. `GET /Cotizaciones/{instrumento}/{panel}/{pais}`       -> 1 por panel (docenas de símbolos)
  4. `GET /Titulos/FCI`                                     -> 1 llamada

Los CEDEARs salen del descubrimiento (panel de Acciones). Las ONs y las letras NO: el
descubrimiento no las declara y los paneles "Bonos corporativos en pesos/dólares" que sí declara
vienen vacíos, así que van en `_PANELES_EXTRA` -- confirmados a mano contra la cuenta real
(ObligacionesNegociables/Todas -> 885 símbolos, Letras/Todas -> 154). `Opciones` sí es un
instrumento propio pero se saltea por defecto (son miles de contratos con vencimiento, ruido puro
para mapear tickers de cartera): agregalo con `--incluir Opciones` si alguna vez hace falta. `FCI`
también se saltea en el descubrimiento porque sus paneles de `/Cotizaciones` responden error: los
fondos se bajan con `/Titulos/FCI`, que los trae todos en una sola llamada.

Si (1) o (2) no existen en la cuenta, cae a los paneles candidatos de `market_data/iol.py`, así el
script sigue sirviendo aunque IOL cambie los endpoints de descubrimiento.

PRESUPUESTO DE LLAMADAS: el plan completo son ~60-100 llamadas sobre el cupo mensual bonificado
(25.000; el sync entero gasta ~7 por corrida). El script corta si el plan supera `--max-llamadas`
(default 250) y avisa en vez de gastar: nunca arranca a bajar paneles sin haber mostrado antes
cuántas llamadas va a costar. Con `--dry-run` hace sólo el descubrimiento (~10 llamadas) e imprime
el plan sin bajar ningún panel.

Corre DENTRO del contenedor, como el resto de la app:

    docker compose up -d backend
    docker compose exec backend python -m scripts.iol_catalogo              # catálogo completo
    docker compose exec backend python -m scripts.iol_catalogo --dry-run    # sólo el plan y el costo

El resultado queda en el volumen `backend_data` (sobrevive a `up --build`), en JSON + CSV:

    docker compose cp backend:/app/data/iol_catalogo.json ./
    docker compose cp backend:/app/data/iol_catalogo.csv ./

Re-ejecutable: en cada corrida compara contra el JSON anterior e informa símbolos NUEVOS y
símbolos que DESAPARECIERON, y conserva por símbolo la fecha en que se lo vio por primera vez
(`visto_desde`), de modo que "¿qué tickers nuevos hay?" se responde con una sola corrida.

IMPORTANTE: como el resto del módulo, nunca imprime contraseña ni token -- sólo status y conteos.
"""
import argparse
import csv
import json
import os
import sys
from datetime import date

from app.database import SessionLocal
from app.services.market_data import iol, iol_auth

_SALIDA_DEFAULT = "/app/data/iol_catalogo.json"

# Instrumentos que el descubrimiento trae pero no conviene recorrer por paneles (ver docstring).
_EXCLUIDOS_DEFAULT = ("Opciones", "FCI")

# Paneles que existen pero que el endpoint de descubrimiento NO declara. Se agregan al plan
# siempre; si alguno dejara de existir, devuelve vacío y el resto del catálogo no se ve afectado.
_PANELES_EXTRA = (
    ("ObligacionesNegociables", "Todas", "argentina"),
    ("Letras", "Todas", "argentina"),
    ("Bonos", "Todos", "argentina"),  # catch-all: trae los bonos que no caen en ningún panel
)


class Presupuesto:
    """Cota dura de llamadas de ESTA corrida, encima del cupo mensual que ya controla `iol_auth`.
    El cupo mensual protege la facturación; esto protege contra un descubrimiento que devuelva
    cientos de paneles inesperados y se coma el cupo de un mes en una sola corrida."""

    def __init__(self, maximo: int):
        self.maximo = maximo
        self.usadas = 0

    def hay_lugar(self, n: int = 1) -> bool:
        return self.usadas + n <= self.maximo


def _get(db, presupuesto: Presupuesto, url: str):
    """GET autenticado contando la llamada contra el presupuesto local. `None` si no hay lugar,
    no hay cupo mensual o la petición falló. Comitea para que el contador de cupo quede durable
    aunque el script se corte a mitad (misma razón que en `iol_probe.py`)."""
    if not presupuesto.hay_lugar():
        return None
    presupuesto.usadas += 1
    data = iol_auth.get_autenticado(db, url)
    db.commit()
    return data


def _nombres(data, *claves: str) -> list[str]:
    """Normaliza las respuestas de descubrimiento: IOL devuelve a veces una lista de strings y a
    veces una lista de objetos ({'descripcion': ...} / {'panel': ...}), según el endpoint."""
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str):
            valor = item
        elif isinstance(item, dict):
            valor = next((item[c] for c in claves if item.get(c)), None)
        else:
            valor = None
        if valor and str(valor).strip() not in out:
            out.append(str(valor).strip())
    return out


def _descubrir(db, presupuesto: Presupuesto, paises: list[str], excluidos: set[str]) -> list[tuple[str, str, str]]:
    """Lista de `(instrumento, panel, pais)` a bajar. Si el descubrimiento no está disponible,
    cae a los paneles candidatos ya cableados en `market_data/iol.py`."""
    plan: list[tuple[str, str, str]] = []
    for pais in paises:
        instrumentos = _nombres(
            _get(db, presupuesto, f"{iol_auth.BASE_URL}/{pais}/Titulos/Cotizacion/Instrumentos"),
            "instrumento", "descripcion", "nombre",
        )
        if not instrumentos:
            print(f"  {pais}: el endpoint de instrumentos no respondió; se usan los paneles "
                  "candidatos de market_data/iol.py")
            continue
        omitidos = [i for i in instrumentos if i.lower() in excluidos]
        instrumentos = [i for i in instrumentos if i.lower() not in excluidos]
        print(f"  {pais}: {len(instrumentos)} instrumentos -> {instrumentos}"
              + (f" (omitidos: {omitidos})" if omitidos else ""))
        for instrumento in instrumentos:
            paneles = _nombres(
                _get(db, presupuesto,
                     f"{iol_auth.BASE_URL}/{pais}/Titulos/Cotizacion/Paneles/{instrumento}"),
                "panel", "descripcion", "nombre",
            )
            if not paneles:
                print(f"    {instrumento}: sin paneles declarados (se omite)")
                continue
            print(f"    {instrumento}: {len(paneles)} paneles -> {paneles}")
            for panel in paneles:
                if (instrumento, panel, pais) not in plan:
                    plan.append((instrumento, panel, pais))

    if not plan:
        plan = [t for t in iol._PANELES]
        print(f"  Fallback: {len(plan)} paneles candidatos de market_data/iol.py")

    extra = [t for t in _PANELES_EXTRA if t not in plan]
    if extra:
        print(f"  Paneles extra no declarados por el descubrimiento: "
              f"{[f'{i}/{p}' for i, p, _ in extra]}")
        plan.extend(extra)
    return plan


def _bajar_panel(db, presupuesto: Presupuesto, instrumento: str, panel: str, pais: str) -> list[dict]:
    url = f"{iol_auth.BASE_URL}/Cotizaciones/{instrumento}/{panel}/{pais}"
    data = _get(db, presupuesto, url)
    titulos = data.get("titulos") if isinstance(data, dict) else None
    if not isinstance(titulos, list):
        print(f"  {instrumento}/{panel}/{pais}: sin datos (no existe, sin cupo o falló)")
        return []
    print(f"  {instrumento}/{panel}/{pais}: {len(titulos)} símbolos")
    return [t for t in titulos if isinstance(t, dict)]


def _bajar_fci(db, presupuesto: Presupuesto) -> list[dict]:
    data = _get(db, presupuesto, f"{iol_auth.BASE_URL}/Titulos/FCI")
    if not isinstance(data, list):
        print("  FCI: sin datos (no existe, sin cupo o falló)")
        return []
    print(f"  FCI: {len(data)} símbolos")
    return [t for t in data if isinstance(t, dict)]


def _acumular(catalogo: dict, filas: list[dict], instrumento: str, panel: str, pais: str) -> None:
    """Un mismo símbolo puede aparecer en varios paneles (p.ej. una acción en Merval y en Panel
    General): se guarda una sola entrada con la lista de paneles donde vive."""
    for fila in filas:
        simbolo = str(fila.get("simbolo") or "").strip().upper()
        if not simbolo:
            continue
        titulo = fila.get("titulo") if isinstance(fila.get("titulo"), dict) else {}
        entrada = catalogo.setdefault(simbolo, {
            "simbolo": simbolo,
            "descripcion": "",
            "moneda": "",
            "mercado": "",
            "pais": pais,
            "paneles": [],
        })
        # Los campos descriptivos se toman del primer panel que los traiga: son los mismos para el
        # símbolo, pero no todos los paneles los completan.
        for destino, origen in (("descripcion", "descripcion"), ("moneda", "moneda"), ("mercado", "mercado")):
            if not entrada[destino]:
                valor = fila.get(origen) or titulo.get(origen)
                if valor:
                    entrada[destino] = str(valor).strip()
        etiqueta = f"{instrumento}/{panel}"
        if etiqueta not in entrada["paneles"]:
            entrada["paneles"].append(etiqueta)


def _muestra(simbolos: list[str], tope: int = 40) -> str:
    """Los cambios de una corrida pueden ser miles de símbolos (la primera, o cuando IOL agrega un
    panel entero): se listan los primeros y el resto se consulta en el archivo, que los tiene todos
    con su `visto_desde`."""
    if len(simbolos) <= tope:
        return ", ".join(simbolos)
    return (f"{', '.join(simbolos[:tope])} ... y {len(simbolos) - tope} más "
            "(el archivo los tiene todos, filtrá por `visto_desde`)")


def _leer_anterior(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        instrumentos = data.get("instrumentos")
        return {i["simbolo"]: i for i in instrumentos if isinstance(i, dict) and i.get("simbolo")} \
            if isinstance(instrumentos, list) else {}
    except Exception as exc:
        print(f"No se pudo leer el catálogo anterior '{path}' ({exc}); se trata como primera corrida.")
        return {}


def _escribir(path: str, catalogo: dict, hoy: str, plan: list, presupuesto: Presupuesto) -> None:
    instrumentos = [catalogo[s] for s in sorted(catalogo)]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "generado": hoy,
            "total": len(instrumentos),
            "llamadas_consumidas": presupuesto.usadas,
            "paneles_consultados": [f"{i}/{p}/{q}" for i, p, q in plan],
            "instrumentos": instrumentos,
        }, fh, ensure_ascii=False, indent=2)

    path_csv = os.path.splitext(path)[0] + ".csv"
    with open(path_csv, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["simbolo", "descripcion", "moneda", "mercado", "pais", "paneles", "visto_desde"])
        for i in instrumentos:
            writer.writerow([i["simbolo"], i["descripcion"], i["moneda"], i["mercado"], i["pais"],
                             " | ".join(i["paneles"]), i.get("visto_desde", "")])
    print(f"\nCatálogo escrito en {path} y {path_csv} ({len(instrumentos)} instrumentos).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Catálogo de instrumentos de IOL.")
    parser.add_argument("--salida", default=_SALIDA_DEFAULT,
                        help=f"Archivo JSON de salida (default {_SALIDA_DEFAULT}); el CSV va al lado.")
    parser.add_argument("--paises", default="argentina",
                        help="Países a recorrer, separados por coma (default argentina; "
                             "el otro valor que acepta IOL es estados_Unidos).")
    parser.add_argument("--incluir", default="",
                        help="Instrumentos a NO saltear, separados por coma (por defecto se saltea "
                             f"{', '.join(_EXCLUIDOS_DEFAULT)}).")
    parser.add_argument("--max-llamadas", type=int, default=250,
                        help="Tope de llamadas de esta corrida (default 250). Si el plan lo supera, "
                             "el script se detiene y avisa en vez de gastar cupo.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Sólo descubre instrumentos/paneles e imprime el plan y su costo.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not iol_auth.iol_enabled():
            print("IOL_ENABLED=false -- no hay nada que consultar.")
            return 1
        if iol_auth._leer_credenciales() is None:
            print(f"No se encontraron credenciales en '{iol_auth._credentials_path()}'. "
                  "Configurá credentials/iol.json antes de correr esto.")
            return 1

        presupuesto = Presupuesto(args.max_llamadas)
        print("Autenticando...")
        if iol_auth.get_bearer(db) is None:
            db.commit()
            print("No se pudo autenticar. Revisá usuario/contraseña y que el servicio de API esté "
                  "habilitado en tu cuenta de IOL (Perfil -> API).")
            return 1
        db.commit()
        print("Autenticación OK.\n")

        paises = [p.strip() for p in args.paises.split(",") if p.strip()]
        incluidos = {i.strip().lower() for i in args.incluir.split(",") if i.strip()}
        excluidos = {e.lower() for e in _EXCLUIDOS_DEFAULT} - incluidos
        print("Descubriendo instrumentos y paneles:")
        plan = _descubrir(db, presupuesto, paises, excluidos)

        restantes = len(plan) + 1  # +1 por FCI
        print(f"\nPlan: {len(plan)} paneles + FCI = {restantes} llamadas más "
              f"({presupuesto.usadas} ya usadas en el descubrimiento).")
        if args.dry_run:
            print("--dry-run: no se baja ningún panel.")
            return 0
        if not presupuesto.hay_lugar(restantes):
            print(f"\nDETENIDO: el plan necesita {presupuesto.usadas + restantes} llamadas y el tope "
                  f"es {args.max_llamadas}. Nada se bajó todavía. Revisá el plan de arriba y, si está "
                  f"bien, volvé a correr con --max-llamadas {presupuesto.usadas + restantes + 20}.")
            return 2

        print("\nBajando paneles:")
        catalogo: dict[str, dict] = {}
        for instrumento, panel, pais in plan:
            _acumular(catalogo, _bajar_panel(db, presupuesto, instrumento, panel, pais),
                      instrumento, panel, pais)
        _acumular(catalogo, _bajar_fci(db, presupuesto), "FCI", "Todos", "argentina")

        if not catalogo:
            print("\nNingún panel devolvió símbolos: no se sobrescribe el catálogo anterior.")
            return 1

        hoy = date.today().isoformat()
        anterior = _leer_anterior(args.salida)
        for simbolo, entrada in catalogo.items():
            # `visto_desde` se arrastra del catálogo anterior: así queda registrada la fecha real
            # de alta de cada ticker, no la de la última corrida.
            entrada["visto_desde"] = anterior.get(simbolo, {}).get("visto_desde", hoy)

        nuevos = sorted(set(catalogo) - set(anterior))
        desaparecidos = sorted(set(anterior) - set(catalogo))
        if anterior:
            print(f"\nContra la corrida anterior: {len(nuevos)} nuevos, {len(desaparecidos)} desaparecidos.")
            if nuevos:
                print(f"  NUEVOS: {_muestra(nuevos)}")
            if desaparecidos:
                print(f"  DESAPARECIDOS (deslistados o fuera de panel hoy): {_muestra(desaparecidos)}")
        else:
            print(f"\nPrimera corrida: {len(catalogo)} instrumentos (no hay con qué comparar).")

        _escribir(args.salida, catalogo, hoy, plan, presupuesto)

        fila = db.get(iol_auth.EstadoApiIol, iol_auth._periodo_actual())
        print(f"Llamadas de esta corrida: {presupuesto.usadas}. Cupo mensual usado: "
              f"{fila.llamadas if fila is not None else 0} / {iol_auth._limite_mensual()}.")
        print(f"Para leerlo desde el host: docker compose cp backend:{args.salida} ./")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
