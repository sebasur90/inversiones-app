"""Dos clases con el mismo nombre en schemas.py: la segunda pisa a la primera sin avisar
y un endpoint termina validando contra el schema equivocado (pasó con DiagnosticoOut)."""
import ast
from collections import Counter
from pathlib import Path


def test_schemas_no_repite_nombres_de_clase():
    fuente = (Path(__file__).resolve().parent.parent / "app" / "schemas.py").read_text(encoding="utf-8")
    nombres = [n.name for n in ast.parse(fuente).body if isinstance(n, ast.ClassDef)]
    repetidos = sorted(n for n, c in Counter(nombres).items() if c > 1)
    assert not repetidos, f"Clases duplicadas en schemas.py: {repetidos}"
