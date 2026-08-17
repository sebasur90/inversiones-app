"""Lectura de las pestañas del Google Sheet de inversiones (cuenta de servicio) o Excel local."""
import os
import pandas as pd
from dataclasses import dataclass
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SPREADSHEET_ID = "1c-dr1C793IVSNzfQZATf01kg2TCPO7nSjYoVKJBtxks"


@dataclass
class TabRaw:
    presente: bool
    header: list[str]
    rows: list[tuple[int, dict]]
    error_lectura: str | None = None

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


def _fetch_from_excel() -> dict[str, TabRaw]:
    """Lee datos desde archivo Excel local."""
    excel_path = _get_excel_path()
    if not os.path.isfile(excel_path):
        raise SheetsClientError(
            f"Archivo Excel no encontrado en '{excel_path}'. "
            f"Coloca 'sheet_inversiones.xlsx' en la carpeta 'sheet_local/'."
        )

    result: dict[str, TabRaw] = {}
    try:
        excel_file = pd.ExcelFile(excel_path)
        for tab in SHEET_TABS:
            if tab not in excel_file.sheet_names:
                result[tab] = TabRaw(presente=False, header=[], rows=[])
            else:
                try:
                    df = pd.read_excel(excel_path, sheet_name=tab)
                    values = [df.columns.tolist()] + df.values.tolist()
                    # Convertir NaN a vacío para evitar 'nan' en string
                    rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
                    header = df.columns.tolist() if hasattr(df, 'columns') else []
                    result[tab] = TabRaw(presente=True, header=header, rows=rows)
                except Exception as exc:
                    result[tab] = TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

        # Agregar pestañas opcionales
        for opt_tab in [OBJETIVOS_TAB, REBALANCEO_TAB, BENCHMARKS_TAB, CONFIGURACION_TAB]:
            if opt_tab not in excel_file.sheet_names:
                result[opt_tab] = TabRaw(presente=False, header=[], rows=[])
            else:
                try:
                    df = pd.read_excel(excel_path, sheet_name=opt_tab)
                    values = [df.columns.tolist()] + df.values.tolist()
                    rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
                    header = df.columns.tolist() if hasattr(df, 'columns') else []
                    result[opt_tab] = TabRaw(presente=True, header=header, rows=rows)
                except Exception as exc:
                    result[opt_tab] = TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))
    except SheetsClientError:
        raise
    except Exception as exc:
        raise SheetsClientError(f"Error leyendo Excel: {exc}") from exc

    return result


def fetch_sheet_data() -> dict[str, TabRaw]:
    """Lee las 3 pestañas obligatorias + 4 opcionales del Sheet (Excel o Google Sheets).

    Devuelve {pestaña: TabRaw}. No lanza por una sola pestaña obligatoria faltante;
    solo lanza por falla total (credenciales ausentes, archivo Excel ausente, error de servicio).
    La distinción "presente vs error_lectura" permite detectar tab missing vs read failure.
    """
    if _is_local_env():
        return _fetch_from_excel()

    service = _get_service()
    result: dict[str, TabRaw] = {}

    try:
        for tab in SHEET_TABS:
            try:
                resp = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=SPREADSHEET_ID, range=tab)
                    .execute()
                )
                rows = _rows_to_dicts(resp.get("values", []))
                header = resp.get("values", [None])[0] if resp.get("values") else []
                result[tab] = TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
            except Exception as exc:
                message = str(exc)
                # Rango/tab inexistente típicamente da 400 con "Unable to parse range"
                if "400" in message and "Unable to parse range" in message:
                    result[tab] = TabRaw(presente=False, header=[], rows=[])
                else:
                    # Cualquier otro error (permisos, 5xx, red) → presente pero con error
                    result[tab] = TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

        # Agregar pestañas opcionales
        for opt_tab in [OBJETIVOS_TAB, REBALANCEO_TAB, BENCHMARKS_TAB, CONFIGURACION_TAB]:
            try:
                resp = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=SPREADSHEET_ID, range=opt_tab)
                    .execute()
                )
                rows = _rows_to_dicts(resp.get("values", []))
                header = resp.get("values", [None])[0] if resp.get("values") else []
                result[opt_tab] = TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
            except Exception as exc:
                message = str(exc)
                if "400" in message and "Unable to parse range" in message:
                    result[opt_tab] = TabRaw(presente=False, header=[], rows=[])
                else:
                    result[opt_tab] = TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))
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

    return result


def fetch_objetivos_tab() -> TabRaw:
    """Lee la pestaña Objetivos de forma aislada del resto del Sheet.

    Devuelve TabRaw distinguiendo tab no presente vs error de lectura.
    """
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return TabRaw(presente=False, header=[], rows=[])
        try:
            excel_file = pd.ExcelFile(excel_path)
            if OBJETIVOS_TAB not in excel_file.sheet_names:
                return TabRaw(presente=False, header=[], rows=[])
            df = pd.read_excel(excel_path, sheet_name=OBJETIVOS_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
            header = df.columns.tolist() if hasattr(df, 'columns') else []
            return TabRaw(presente=True, header=header, rows=rows)
        except Exception as exc:
            return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=OBJETIVOS_TAB)
            .execute()
        )
        rows = _rows_to_dicts(resp.get("values", []))
        header = resp.get("values", [None])[0] if resp.get("values") else []
        return TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
    except Exception as exc:
        message = str(exc)
        if "400" in message and "Unable to parse range" in message:
            return TabRaw(presente=False, header=[], rows=[])
        return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))


def fetch_rebalanceo_tab() -> TabRaw:
    """Lee la pestaña Rebalanceo de forma aislada del resto del Sheet."""
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return TabRaw(presente=False, header=[], rows=[])
        try:
            excel_file = pd.ExcelFile(excel_path)
            if REBALANCEO_TAB not in excel_file.sheet_names:
                return TabRaw(presente=False, header=[], rows=[])
            df = pd.read_excel(excel_path, sheet_name=REBALANCEO_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
            header = df.columns.tolist() if hasattr(df, 'columns') else []
            return TabRaw(presente=True, header=header, rows=rows)
        except Exception as exc:
            return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=REBALANCEO_TAB)
            .execute()
        )
        rows = _rows_to_dicts(resp.get("values", []))
        header = resp.get("values", [None])[0] if resp.get("values") else []
        return TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
    except Exception as exc:
        message = str(exc)
        if "400" in message and "Unable to parse range" in message:
            return TabRaw(presente=False, header=[], rows=[])
        return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))


def fetch_benchmarks_tab() -> TabRaw:
    """Lee la pestaña Benchmarks de forma aislada del resto del Sheet."""
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return TabRaw(presente=False, header=[], rows=[])
        try:
            excel_file = pd.ExcelFile(excel_path)
            if BENCHMARKS_TAB not in excel_file.sheet_names:
                return TabRaw(presente=False, header=[], rows=[])
            df = pd.read_excel(excel_path, sheet_name=BENCHMARKS_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
            header = df.columns.tolist() if hasattr(df, 'columns') else []
            return TabRaw(presente=True, header=header, rows=rows)
        except Exception as exc:
            return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=BENCHMARKS_TAB)
            .execute()
        )
        rows = _rows_to_dicts(resp.get("values", []))
        header = resp.get("values", [None])[0] if resp.get("values") else []
        return TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
    except Exception as exc:
        message = str(exc)
        if "400" in message and "Unable to parse range" in message:
            return TabRaw(presente=False, header=[], rows=[])
        return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))


def fetch_configuracion_tab() -> TabRaw:
    """Lee la pestaña Configuracion de forma aislada del resto del Sheet."""
    if _is_local_env():
        excel_path = _get_excel_path()
        if not os.path.isfile(excel_path):
            return TabRaw(presente=False, header=[], rows=[])
        try:
            excel_file = pd.ExcelFile(excel_path)
            if CONFIGURACION_TAB not in excel_file.sheet_names:
                return TabRaw(presente=False, header=[], rows=[])
            df = pd.read_excel(excel_path, sheet_name=CONFIGURACION_TAB)
            values = [df.columns.tolist()] + df.values.tolist()
            rows = _rows_to_dicts([['' if pd.isna(v) else str(v) for v in row] for row in values])
            header = df.columns.tolist() if hasattr(df, 'columns') else []
            return TabRaw(presente=True, header=header, rows=rows)
        except Exception as exc:
            return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))

    try:
        service = _get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=CONFIGURACION_TAB)
            .execute()
        )
        rows = _rows_to_dicts(resp.get("values", []))
        header = resp.get("values", [None])[0] if resp.get("values") else []
        return TabRaw(presente=True, header=[str(h).strip() for h in header] if header else [], rows=rows)
    except Exception as exc:
        message = str(exc)
        if "400" in message and "Unable to parse range" in message:
            return TabRaw(presente=False, header=[], rows=[])
        return TabRaw(presente=True, header=[], rows=[], error_lectura=str(exc))
