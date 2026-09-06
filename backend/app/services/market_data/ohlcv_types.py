"""Barra cruda compartida entre las fuentes de OHLCV (`analisistecnico`, `iol`), antes de aplicar
factor de escala. `cierre` es el único campo garantizado; el resto degrada a `None` cuando la
fuente no lo trae o resulta inconsistente."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BarraCruda:
    fecha: date
    cierre: float
    apertura: float | None = None
    maximo: float | None = None
    minimo: float | None = None
    volumen: float | None = None
