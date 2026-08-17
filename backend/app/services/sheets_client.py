"""Lectura de las pestañas del Google Sheet de inversiones (cuenta de servicio) o Excel local."""
import os
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SPREADSHEET_ID = "1c-dr1C793IVSNzfQZATf01kg2TCPO7nSjYoVKJBtxks"

SHEET_TABS = ("Movimientos", "Instrumentos", "Precios")

OBJETIVOS_TAB = "Objetivos"

REBALANCEO_TAB = "Rebalanceo"

BENCHMARKS_TAB = "Benchmarks"

CONFIGURACION_TAB = "Configuracion"


class SheetsClientError(Exception):
    pass


def _credentials_path() -> str:
    return os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "google-service-account.json"),
    )


def _get_service():
    path = _credentials_path()
    if not os.path.isfile(path):
        raise SheetsClientError(
            f"No se encontraron las credenciales de la cuenta de servicio en '{path}'. "
            "Configurá GOOGLE_SERVICE_ACCOUNT_FILE o colocá el archivo en backend/data/google-service-account.json."
        )
    try:
        credentials = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        return build("sheets", "v4", credentials=credentials)
    except Exception as exc:
        raise SheetsClientError(f"Credenciales de Google inválidas: {exc}") from exc


def _is_local_env() -> bool:
    """Detecta si se debe usar archivo Excel local en lugar de Google Sheets."""
    use_local = os.getenv("USE_LOCAL_SHEET", "false").lower() in ("true", "1", "yes")
    return use_local


def _get_excel_path() -> str:
    """Retorna la ruta del archivo Excel local."""
    return os.path.join(os.path.dirname(__file__), "..", "..", "sheet_local", "sheet_inversiones.xlsx")


def _rows_to_dicts(values: list[list[str]]) -> list[tuple[int, dict]]:
    """Devuelve [(nro_fila_planilla, fila_como_dict)], saltando filas totalmente vacías."""
    if not values:
        return []
    header = [h.strip() for h in values[0]]
    rows = []
    for offset, raw_row in enumerate(values[1:]):
        row = {}
        for i, col in enumerate(header):
            cell = raw_row[i] if i < len(raw_row) else ""
            row[col] = cell.strip() if isinstance(cell, str) else cell
        if any(str(v).strip() for v in row.values()):
            rows.append((offset + 2, row))
    return rows


def _fetch_from_excel() -> dict[str, list[tuple[int, dict]]]:
    """Lee datos desde archivo Excel local."""
    excel_path = _get_excel_path()
    if not os.path.isfile(excel_path):
        raise SheetsClientError(
            f"Archivo Excel no encontrado en '{excel_path}'. "
            f"Coloca 'sheet_inversiones.xlsx' en la carpeta 'sheet_local/'."
        )

    result: dict[str, list[tuple[int, dict]]] = {}
    try:
        excel_file = pd.ExcelFile(excel_path)
        for tab in SHEET_TABS:
            if tab not in excel_file.sheet_names:
                raise SheetsClientError(f"Pestaña '{tab}' no encontrada en Excel. Pestañas disponibles: {excel_file.sheet_names}")

            df = pd.read_excel(excel_path, sheet_name=tab)
            values = [df.columns.tolist()] + df.values.tolist()
            result[tab] = _rows_to_dicts([[str(v) for v in row] for row in values])
    except SheetsClientError:
        raise
    except Exception as exc:
        raise SheetsClientError(f"Error leyendo Excel: {exc}") from exc

    return result


def fetch_sheet_data() -> dict[str, list[tuple[int, dict]]]:
    """Lee las 3 pestañas del Sheet (Excel local o Google Sheets) y devuelve {pestaña: [(nro_fila, fila_como_dict)]}."""
    if _is_local_env():
        return _fetch_from_excel()

    service = _get_service()
    result: dict[str, list[tuple[int, dict]]] = {}
    try:
        for tab in SHEET_TABS:
            resp = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=SPREADSHEET_ID, range=tab)
                .execute()
            )
            result[tab] = _rows_to_dicts(resp.get("values", []))
    except SheetsClientError:
        raise
    except Exception as exc:
        message = str(exc)
        if "PERMISSION_DENIED" in message or "403" in message:
            raise SheetsClientError(
                "El Sheet no está compartido con la cuenta de servicio. "
                "Compartilo (acceso de lectura) con el email que figura en el archivo de credenciales."
            ) from exc
        raise SheetsClientError(f"Error leyendo el Google Sheet: {exc}") from exc

    faltantes = [tab for tab in SHEET_TABS if not result.get(tab)]
    if len(faltantes) == len(SHEET_TABS):
        raise SheetsClientError("El Sheet está vacío o no se encontraron las pestañas Movimientos/Instrumentos/Precios.")

    return result


def fetch_objetivos_tab() -> list[tuple[int, dict]]:
    """Lee la pestaña Objetivos de forma aislada del resto del Sheet.

    A diferencia de fetch_sheet_data(), es tolerante a que la pestaña todavía no exista
    (el usuario puede no haberla creado aún): devuelve [] en vez de romper el sync completo.
    """
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return []
        try:
            excel_file = pd.ExcelFile(excel_path)
            if OBJETIVOS_TAB not in excel_file.sheet_names:
                return []
            df = pd.read_excel(excel_path, sheet_name=OBJETIVOS_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            return _rows_to_dicts([[str(v) for v in row] for row in values])
        except Exception:
            return []

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=OBJETIVOS_TAB)
            .execute()
        )
        return _rows_to_dicts(resp.get("values", []))
    except Exception:
        return []


def fetch_rebalanceo_tab() -> list[tuple[int, dict]]:
    """Lee la pestaña Rebalanceo de forma aislada del resto del Sheet.

    Igual que fetch_objetivos_tab(): tolerante a que la pestaña todavía no exista,
    devuelve [] en vez de romper el sync completo.
    """
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return []
        try:
            excel_file = pd.ExcelFile(excel_path)
            if REBALANCEO_TAB not in excel_file.sheet_names:
                return []
            df = pd.read_excel(excel_path, sheet_name=REBALANCEO_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            return _rows_to_dicts([[str(v) for v in row] for row in values])
        except Exception:
            return []

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=REBALANCEO_TAB)
            .execute()
        )
        return _rows_to_dicts(resp.get("values", []))
    except Exception:
        return []


def fetch_benchmarks_tab() -> list[tuple[int, dict]]:
    """Lee la pestaña Benchmarks (Fecha | Benchmark | Valor) de forma aislada del resto del Sheet.

    Igual que fetch_objetivos_tab()/fetch_rebalanceo_tab(): tolerante a que la pestaña
    todavía no exista, devuelve [] en vez de romper el sync completo.
    """
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return []
        try:
            excel_file = pd.ExcelFile(excel_path)
            if BENCHMARKS_TAB not in excel_file.sheet_names:
                return []
            df = pd.read_excel(excel_path, sheet_name=BENCHMARKS_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            return _rows_to_dicts([[str(v) for v in row] for row in values])
        except Exception:
            return []

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=BENCHMARKS_TAB)
            .execute()
        )
        return _rows_to_dicts(resp.get("values", []))
    except Exception:
        return []


def fetch_configuracion_tab() -> list[tuple[int, dict]]:
    """Lee la pestaña Configuracion (Cartera | Benchmark | Rendimiento Objetivo | Peso Máximo |
    Peso Mínimo | Tolerancia) de forma aislada del resto del Sheet.

    Igual que fetch_objetivos_tab()/fetch_rebalanceo_tab()/fetch_benchmarks_tab(): tolerante a
    que la pestaña todavía no exista, devuelve [] en vez de romper el sync completo.
    """
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return []
        try:
            excel_file = pd.ExcelFile(excel_path)
            if CONFIGURACION_TAB not in excel_file.sheet_names:
                return []
            df = pd.read_excel(excel_path, sheet_name=CONFIGURACION_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            return _rows_to_dicts([[str(v) for v in row] for row in values])
        except Exception:
            return []

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=CONFIGURACION_TAB)
            .execute()
        )
        return _rows_to_dicts(resp.get("values", []))
    except Exception:
        return []
