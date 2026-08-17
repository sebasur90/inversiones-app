"""Tipos base para la capa de validación."""
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    CRITICO = "critico"
    ADVERTENCIA = "advertencia"
    INFO = "info"


SEVERIDAD_RANK = {"critico": 0, "advertencia": 1, "info": 2}


@dataclass
class ValidationIssue:
    """Un problema detectado durante la validación de una fila o cross-tab."""
    tab: str
    regla: str
    mensaje: str
    impacto: str
    severidad: Severity
    fila: int | None = None
    campo: str | None = None

    def to_dict(self) -> dict:
        return {
            "tab": self.tab,
            "fila": self.fila,
            "campo": self.campo,
            "regla": self.regla,
            "severidad": self.severidad.value,
            "mensaje": self.mensaje,
            "impacto": self.impacto,
        }
