"""Tests del scheduler: parseo de la configuración y gating.

No se arranca APScheduler de verdad: lo que puede fallar en silencio y dejar el job corriendo a una
hora equivocada es el parseo de `REFRESCO_HORAS`, y eso es lo que se prueba.
"""
import pytest

from app.services import scheduler


# --- Gating ------------------------------------------------------------------------------------

def test_deshabilitado_por_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    assert scheduler.habilitado() is False


@pytest.mark.parametrize("valor", ["true", "True", "1", "yes"])
def test_se_habilita_con_los_valores_esperados(monkeypatch, valor):
    monkeypatch.setenv("SCHEDULER_ENABLED", valor)
    assert scheduler.habilitado() is True


@pytest.mark.parametrize("valor", ["false", "0", "no", "", "cualquiera"])
def test_cualquier_otro_valor_lo_deja_apagado(monkeypatch, valor):
    monkeypatch.setenv("SCHEDULER_ENABLED", valor)
    assert scheduler.habilitado() is False


def test_iniciar_no_hace_nada_si_esta_deshabilitado(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    scheduler.iniciar()
    assert scheduler._scheduler is None


# --- Horas del refresco ------------------------------------------------------------------------

def test_default_cubre_la_rueda_cada_dos_horas(monkeypatch):
    monkeypatch.delenv("REFRESCO_HORAS", raising=False)
    assert scheduler._horas_refresco() == "11,13,15,17"


def test_lista_propia(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", "10,12,14,16,18")
    assert scheduler._horas_refresco() == "10,12,14,16,18"


def test_se_ordena_y_deduplica(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", "17,11,13,11")
    assert scheduler._horas_refresco() == "11,13,17"


def test_tolera_espacios(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", " 11 , 13 ")
    assert scheduler._horas_refresco() == "11,13"


def test_vacio_desactiva_el_refresco(monkeypatch):
    """Apagar el job liviano sin tocar el de cierre."""
    monkeypatch.setenv("REFRESCO_HORAS", "")
    assert scheduler._horas_refresco() == ""


def test_valor_no_numerico_cae_al_default_entero(monkeypatch):
    """No se programa "la mitad" de la lista: o la lista pedida, o el default."""
    monkeypatch.setenv("REFRESCO_HORAS", "11,trece,15")
    assert scheduler._horas_refresco() == scheduler.HORAS_REFRESCO_DEFAULT


def test_hora_fuera_de_rango_cae_al_default(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", "11,99")
    assert scheduler._horas_refresco() == scheduler.HORAS_REFRESCO_DEFAULT


def test_hora_negativa_cae_al_default(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", "-1")
    assert scheduler._horas_refresco() == scheduler.HORAS_REFRESCO_DEFAULT


def test_solo_comas_equivale_a_vacio(monkeypatch):
    monkeypatch.setenv("REFRESCO_HORAS", ",,")
    assert scheduler._horas_refresco() == ""


# --- Enteros del entorno -----------------------------------------------------------------------

def test_entero_env_usa_el_default_si_no_esta(monkeypatch):
    monkeypatch.delenv("SCHEDULER_HORA", raising=False)
    assert scheduler._entero_env("SCHEDULER_HORA", 18, 0, 23) == 18


def test_entero_env_rechaza_fuera_de_rango(monkeypatch):
    monkeypatch.setenv("SCHEDULER_HORA", "25")
    assert scheduler._entero_env("SCHEDULER_HORA", 18, 0, 23) == 18


def test_entero_env_rechaza_no_numerico(monkeypatch):
    monkeypatch.setenv("SCHEDULER_MINUTO", "y media")
    assert scheduler._entero_env("SCHEDULER_MINUTO", 30, 0, 59) == 30


# --- Los jobs nunca lanzan ---------------------------------------------------------------------

def test_refresco_con_el_lock_tomado_igual_evalua_alertas(monkeypatch):
    """Si el usuario está sincronizando, se saltea el refresco pero no el aviso."""
    from app.services import sync_lock

    llamado = {"alertas": 0}
    monkeypatch.setattr(scheduler, "_evaluar_alertas", lambda: llamado.__setitem__("alertas", 1))

    assert sync_lock.lock.acquire(blocking=False)
    try:
        scheduler.correr_refresco_y_alertas()
    finally:
        sync_lock.lock.release()

    assert llamado["alertas"] == 1


def test_un_refresco_que_falla_no_propaga_la_excepcion(monkeypatch):
    from app.services import refresco_precios

    def explota(db):
        raise RuntimeError("IOL caído")

    monkeypatch.setattr(refresco_precios, "refrescar", explota)
    monkeypatch.setattr(scheduler, "_evaluar_alertas", lambda: None)

    scheduler.correr_refresco_y_alertas()  # no debe lanzar
