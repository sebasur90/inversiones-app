"""Laboratorio de estrategias: prototipar en un notebook, exportar el DSL, importarlo a la app.

Vive dentro de `app/` para importar `..services.estrategia_engine` directo (la validación es *la
misma función*, cero drift) y testearse con el pytest existente. `app.main` **no** lo importa, así
que en runtime es peso muerto de riesgo cero. Dependencia estricta: `lab → services`, nunca al
revés.

    from app.lab import Estrategia, ind, precio, entre, todas, alguna, negar
    from app.lab import barras_de_db, barras_de_dataframe, correr_como_la_app
    from app.lab import a_dataframe, comparar_con_mascara
"""
from .builder import (
    Condicion,
    Estrategia,
    EstrategiaInvalida,
    alguna,
    entre,
    ind,
    negar,
    precio,
    todas,
)
from .datos import barras_de_db, barras_de_dataframe, correr_como_la_app
from .evaluacion import ResultadoLab, a_dataframe, comparar_con_mascara

__all__ = [
    "Estrategia", "EstrategiaInvalida", "Condicion",
    "ind", "precio", "entre", "todas", "alguna", "negar",
    "barras_de_db", "barras_de_dataframe", "correr_como_la_app",
    "a_dataframe", "ResultadoLab", "comparar_con_mascara",
]
