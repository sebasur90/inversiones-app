"""Elección de pares: industria → tamaño → sector, deduplicación de emisores, ETFs por categoría y
correcciones manuales."""
from app.services.pares_engine import Candidato, deduplicar, elegir_pares


def _c(t, industria="Beverages - Non-Alcoholic", tamano=1e11, sector="Consumo básico", region="EEUU",
       simbolo=None, etf=False, categoria=None):
    return Candidato(ticker_base=t, simbolo_yahoo=simbolo or t, es_etf=etf, sector=sector,
                     industria_raw=industria, categoria=categoria, region=region, tamano_usd=tamano)


KO = _c("KO", tamano=3e11)


def test_misma_industria_y_tamano_parecido():
    universo = [KO, _c("PEP", tamano=2e11), _c("MNST", tamano=6e10), _c("KDP", tamano=4.5e10),
                _c("CELH", tamano=1e10), _c("FIZZ", tamano=3e9), _c("PG", industria="Household", tamano=4e11)]
    g = elegir_pares(KO, universo)
    assert g.pares[0] == "PEP"
    assert "PG" not in g.pares and "KO" not in g.pares
    # En 0,2x-5x sólo entran PEP y MNST, en 0,05x-20x se suma KDP: no llegan a 4, así que se
    # saca el filtro de tamaño y entra toda la industria, ordenada por cercanía de tamaño.
    assert g.pares == ["PEP", "MNST", "KDP", "CELH", "FIZZ"]
    assert g.criterio == "misma industria"


def test_tamano_parecido_cuando_alcanza():
    universo = [KO] + [_c(f"P{i}", tamano=t) for i, t in enumerate((2e11, 4e11, 1e11, 8e10, 1e9))]
    g = elegir_pares(KO, universo)
    assert "P4" not in g.pares and len(g.pares) == 4
    assert g.criterio == "misma industria y tamaño parecido"


def test_sin_suficientes_en_la_industria_completa_con_el_sector():
    universo = [KO, _c("PEP", tamano=2e11), _c("PG", industria="Household", tamano=4e11),
                _c("CL", industria="Household", tamano=7e10), _c("XOM", industria="Oil", sector="Energía")]
    g = elegir_pares(KO, universo)
    assert g.pares[0] == "PEP"
    assert {"PG", "CL"} <= set(g.pares)
    assert "XOM" not in g.pares
    assert "completado con el mismo sector" in g.criterio


def test_penaliza_otra_region():
    ggal = _c("GGAL", industria="Banks - Regional", sector="Financiero", region="Argentina", tamano=6e9)
    universo = [ggal,
                _c("BMA", industria="Banks - Regional", sector="Financiero", region="Argentina", tamano=4e9),
                _c("USB", industria="Banks - Regional", sector="Financiero", region="EEUU", tamano=6.5e9),
                _c("SUPV", industria="Banks - Regional", sector="Financiero", region="Argentina", tamano=1.5e9),
                _c("BBAR", industria="Banks - Regional", sector="Financiero", region="Argentina", tamano=3e9)]
    g = elegir_pares(ggal, universo)
    assert g.pares.index("BMA") < g.pares.index("USB")


def test_mismo_emisor_cuenta_una_vez_y_nunca_es_par_de_si_mismo():
    pbr = _c("PBR", industria="Oil & Gas Integrated", sector="Energía", region="Emergentes")
    universo = [pbr, _c("PETR3", industria="Oil & Gas Integrated", sector="Energía", region="Emergentes", simbolo="PBR"),
                _c("XOM", industria="Oil & Gas Integrated", sector="Energía"),
                _c("CVX", industria="Oil & Gas Integrated", sector="Energía")]
    g = elegir_pares(pbr, universo)
    assert "PETR3" not in g.pares and "PBR" not in g.pares
    d = deduplicar(universo)
    assert [c.ticker_base for c in d if c.simbolo_yahoo == "PBR"] == ["PBR"]


def test_etfs_por_categoria_ordenados_por_aum():
    spy = _c("SPY", etf=True, categoria="Large Blend", industria=None, sector="Diversificado", tamano=8e11)
    universo = [spy, KO,
                _c("IVV", etf=True, categoria="Large Blend", industria=None, sector="Diversificado", tamano=6e11),
                _c("RSP", etf=True, categoria="Large Blend", industria=None, sector="Diversificado", tamano=7e10),
                _c("VIG", etf=True, categoria="Large Blend", industria=None, sector="Diversificado", tamano=9e10),
                _c("QQQ", etf=True, categoria="Large Growth", industria=None, sector="Diversificado", tamano=3e11),
                _c("XLK", etf=True, categoria="Technology", industria=None, sector="Tecnología", tamano=7e10)]
    g = elegir_pares(spy, universo)
    assert g.pares[:3] == ["IVV", "VIG", "RSP"]
    assert "KO" not in g.pares            # una acción nunca es par de un ETF
    assert "QQQ" in g.pares               # completa con mismo sector y región
    assert "XLK" not in g.pares


def test_correcciones_manuales():
    universo = [KO, _c("PEP", tamano=2e11), _c("MNST", tamano=6e10), _c("KDP", tamano=4.5e10),
                _c("CELH", tamano=1e10)]
    g = elegir_pares(KO, universo, agregar=["BUD", "KO"], quitar=["CELH"])
    assert "CELH" not in g.pares and "CELH" in g.automaticos
    assert g.pares[-1] == "BUD"
    assert g.agregados == ["BUD"] and g.quitados == ["CELH"]
    assert "correcciones manuales" in g.criterio


def test_sin_industria_ni_sector_no_hay_pares():
    raro = _c("ZZZ", industria=None, sector=None)
    g = elegir_pares(raro, [raro, KO])
    assert g.pares == [] and g.criterio == ""
