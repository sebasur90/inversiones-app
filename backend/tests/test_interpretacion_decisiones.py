"""Capa de interpretación del Centro de Decisiones: toda cifra de una frase tiene que salir de los datos."""
from app.services import interpretacion


def test_validar_cifras_acepta_numeros_presentes_y_formatos_locales():
    datos = {"orden": {"puntaje": 62.4}, "vol": 0.253, "precio": 1234.5}
    assert interpretacion.validar_cifras("Puntaje 62,4 y volatilidad 25,3 %", datos) == []
    assert interpretacion.validar_cifras("Precio 1.234,5", datos) == []


def test_validar_cifras_detecta_un_numero_inventado():
    assert interpretacion.validar_cifras("El precio objetivo es 987,6", {"precio": 100.0}) == ["987,6"]


def test_conteos_chicos_no_cuentan_como_cifras():
    assert interpretacion.validar_cifras("3 de 5 dimensiones", {}) == []


def _analisis():
    return {
        "evaluacion": {
            "dimensiones": [{"clave": "fundamentales", "puntaje": 61.7}, {"clave": "valoracion", "puntaje": 44.0}],
            "banderas": [{"texto": "Ingresos cayendo 3,1 % interanual.", "regla": "r"}],
            "orden": {"puntaje": 58.3, "regla": "r"},
        },
        "conclusion": {"titulo": "Ninguna alternativa claramente superior", "regla": "r",
                       "respuestas": {"por_que": "Las diferencias no alcanzan (hace falta ≥ 10 puntos)."}},
        "constantes": [10],
    }


def test_resumen_de_plantillas_es_trazable():
    a = _analisis()
    frases = interpretacion.resumen_validado(a)
    assert len(frases) == 4
    for f in frases:
        assert interpretacion.validar_cifras(f["texto"], a) == []


def test_un_interpretador_que_inventa_queda_filtrado(monkeypatch):
    class Inventa:
        nombre = "x"

        def resumen(self, analisis):
            return [{"texto": "Va a subir 37,5 % el año que viene", "regla": "", "fuentes": []},
                    {"texto": "Orden 58,3", "regla": "", "fuentes": []}]

    monkeypatch.setattr(interpretacion, "interpretador", lambda: Inventa())
    frases = interpretacion.resumen_validado(_analisis())
    assert [f["texto"] for f in frases] == ["Orden 58,3"]


def test_un_interpretador_que_falla_no_rompe(monkeypatch):
    class Falla:
        nombre = "x"

        def resumen(self, analisis):
            raise RuntimeError("proveedor caído")

    monkeypatch.setattr(interpretacion, "interpretador", lambda: Falla())
    assert interpretacion.resumen_validado(_analisis()) == []
