"""Configuración compartida de tests.

Fuerza USE_EXTERNAL_APIS a apagado por default para toda la suite: los tests que sí quieren
ejercitar la ruta de `market_data` mockean explícitamente lo que necesitan (nunca deben
depender de la red real), y en docker-compose.yml / docker-compose.corporate.yml el default de
esa variable es `true` — sin este fixture, correr los tests dentro de esos contenedores haría
que `sync_from_sheet` intente pegarle a APIs externas de verdad en cada test.
"""
import pytest


@pytest.fixture(autouse=True)
def _sin_apis_externas_por_default(monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
