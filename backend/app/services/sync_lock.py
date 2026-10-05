"""Mutex de sincronización, compartido por el endpoint `POST /sync` y el job programado.

Estaba en `routers/inversiones.py` como privado del módulo. Pasó acá cuando el scheduler empezó a
disparar syncs: si el job usara su propio lock, podría arrancar una corrida mientras el usuario
dispara otra desde la app, que es exactamente lo que este lock existe para impedir.
"""
import threading

# Un solo sync a la vez. Dos corridas concurrentes (dos pestañas, `useAutoSync` en dos
# dispositivos, el job y el usuario a la vez) se pisaban: la segunda chocaba con el lock de
# escritura de SQLite y además `iol_auth.iniciar_corrida()` resetea el contador por-corrida del
# sync en vuelo. No bloqueante: encolar sólo alargaría el tiempo con la DB tomada, así que la
# segunda corrida se rechaza (409 en el endpoint, "salteada" en el job).
lock = threading.Lock()
