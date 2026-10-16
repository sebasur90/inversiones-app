"""Backtest point-in-time: entradas a un estado, retornos posteriores, muestra mínima."""
from datetime import date, timedelta

import pytest

from app.services import historial_engine as he

D0 = date(2026, 1, 5)


def foto(ticker, fecha, valuacion, version=2, id=0, calidad="Sólida"):
    return {
        "id": id, "ticker_base": ticker, "fecha": fecha, "version_diagnostico": version,
        "estados": {
            "valuacion": {"estado": valuacion, "nivel": "neutro"},
            "calidad": {"estado": calidad, "nivel": "bien"},
            "crecimiento": {"estado": "No aplica", "nivel": "no_aplica"},
        },
    }


def semanal(inicio: date, n: int, p0=100.0, paso=1.0):
    return [(inicio + timedelta(weeks=i), p0 + paso * i) for i in range(n)]


def test_cuenta_entradas_a_un_estado_no_cada_foto():
    filas = [
        foto("A", D0, "Barata", id=1),
        foto("A", D0 + timedelta(days=10), "Barata", id=2),            # igual: no es una entrada
        foto("A", D0 + timedelta(days=20), "Cara", id=3),              # cambia: entrada
        foto("A", D0 + timedelta(days=30), "Barata", id=4),            # vuelve: entrada
    ]
    ev = [(e["dimension"], e["estado"], e["fecha"]) for e in he.entradas_a_estado(filas) if e["dimension"] == "valuacion"]
    assert [x[1] for x in ev] == ["Barata", "Cara", "Barata"]
    assert len([e for e in he.entradas_a_estado(filas) if e["dimension"] == "calidad"]) == 1     # calidad no cambió


def test_estados_no_aplica_o_sin_datos_no_son_eventos():
    ev = he.entradas_a_estado([foto("A", D0, "Barata")])
    assert "crecimiento" not in {e["dimension"] for e in ev}


def test_un_cambio_de_version_empieza_un_evento_nuevo_y_no_se_mezcla():
    filas = [foto("A", D0, "Barata", version=2, id=1), foto("A", D0 + timedelta(days=10), "Barata", version=3, id=2)]
    ev = [e for e in he.entradas_a_estado(filas) if e["dimension"] == "valuacion"]
    assert [e["version"] for e in ev] == [2, 3]            # el mismo estado en otra versión cuenta como entrada nueva


def test_retorno_a_30_dias_con_la_serie():
    serie = {"A": semanal(D0 - timedelta(weeks=2), 40, 100.0, 1.0)}
    ev = [{"ticker_base": "A", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2}]
    r = he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=400))
    celda = r["estados"][0]
    # cierre en D0 = 102; 30 días después (D0+30) → primer cierre ≥ esa fecha: semana 6 = 108 → +5,88 %
    assert celda["eventos"] == 1 and celda["horizontes"]["30"]["n"] == 1
    assert celda["horizontes"]["30"]["suficiente"] is False and celda["horizontes"]["30"]["mediana"] is None


def test_con_30_eventos_se_muestran_estadisticas():
    serie = {f"T{i}": semanal(D0 - timedelta(weeks=1), 60, 100.0, 1.0) for i in range(30)}
    ev = [{"ticker_base": f"T{i}", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2} for i in range(30)]
    r = he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=500))
    h30 = r["estados"][0]["horizontes"]["30"]
    assert h30["suficiente"] is True and h30["n"] == 30 and h30["positivos_pct"] == 100.0
    assert h30["mediana"] == pytest.approx(r["base"]["30"]["mediana"]) and h30["mediana"] > 0
    assert r["suficiente"] is True


def test_un_horizonte_que_todavia_no_ocurrio_no_cuenta():
    serie = {"A": semanal(D0 - timedelta(weeks=1), 60)}
    ev = [{"ticker_base": "A", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2}]
    r = he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=40))
    h = r["estados"][0]["horizontes"]
    assert h["30"]["n"] == 1 and h["90"]["n"] == 0 and h["180"]["n"] == 0


def test_si_la_serie_no_llega_no_se_rellena():
    serie = {"A": semanal(D0 - timedelta(weeks=1), 4)}                 # termina a las 3 semanas
    ev = [{"ticker_base": "A", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2}]
    r = he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=400))
    assert r["estados"] == [] or all(c["n"] == 0 for c in r["estados"][0]["horizontes"].values())


def test_sin_eventos_ni_series_devuelve_muestra_insuficiente():
    r = he.retornos_posteriores([], {})
    assert r["suficiente"] is False and r["estados"] == [] and r["eventos_totales"] == 0 and r["limites"]


def test_estados_de_versiones_distintas_van_en_celdas_distintas():
    serie = {"A": semanal(D0 - timedelta(weeks=1), 60), "B": semanal(D0 - timedelta(weeks=1), 60)}
    ev = [
        {"ticker_base": "A", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2},
        {"ticker_base": "B", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 3},
    ]
    r = he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=400))
    assert sorted(c["version"] for c in r["estados"]) == [2, 3]


def test_determinista():
    serie = {"A": semanal(D0 - timedelta(weeks=1), 60)}
    ev = [{"ticker_base": "A", "fecha": D0, "dimension": "valuacion", "estado": "Barata", "version": 2}]
    assert he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=400)) == he.retornos_posteriores(ev, serie, hoy=D0 + timedelta(days=400))
