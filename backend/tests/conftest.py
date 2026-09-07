"""Configuración compartida de tests.

Fuerza USE_EXTERNAL_APIS a apagado por default para toda la suite: los tests que sí quieren
ejercitar la ruta de `market_data` mockean explícitamente lo que necesitan (nunca deben
depender de la red real), y en docker-compose.yml / docker-compose.corporate.yml el default de
esa variable es `true` — sin este fixture, correr los tests dentro de esos contenedores haría
que `sync_from_sheet` intente pegarle a APIs externas de verdad en cada test.
"""
import importlib

import pytest


from app.services.cache import limpiar_cache

# Los tests conviven con dos identidades de módulo ("app.*" y "backend.app.*") según cómo importe
# cada archivo. Se stubea `yahoo` en las dos que estén cargadas.
_YAHOO_MODS = []
for _n in ("app.services.market_data.yahoo", "backend.app.services.market_data.yahoo"):
    try:
        _YAHOO_MODS.append(importlib.import_module(_n))
    except ImportError:  # pragma: no cover
        pass


@pytest.fixture(autouse=True)
def _sin_apis_externas_por_default(monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "usa_yahoo_real: el test ejercita `market_data.yahoo` directamente; no stubear su red.",
    )


@pytest.fixture(autouse=True)
def _sin_red_yahoo_por_default(request, monkeypatch):
    """yfinance hace su propio HTTP (no pasa por `market_data.client`), así que
    `USE_EXTERNAL_APIS=false` no lo frena. Se stubean sus dos funciones de red para que la
    resolución/backfill del subyacente sea un no-op salvo que el test lo mockee a propósito.
    Los tests de `test_yahoo.py` (marcados `usa_yahoo_real`) quedan exentos."""
    if request.node.get_closest_marker("usa_yahoo_real"):
        return
    for mod in _YAHOO_MODS:
        monkeypatch.setattr(mod, "fetch_info", lambda *a, **k: None)
        monkeypatch.setattr(mod, "fetch_historico_ohlcv", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _cache_limpia():
    """Los analytics cachean por (conexión, sync, fecha). Cada test arranca con la caché
    vacía para que el resultado no dependa de lo que corrió antes."""
    limpiar_cache()
    yield
    limpiar_cache()
