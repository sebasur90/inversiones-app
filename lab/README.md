# Carpeta de trabajo del laboratorio de estrategias

Se monta en `/app/lab` dentro del servicio `lab` de docker-compose (perfil `lab`).

- `*.ipynb` — notebooks, versionados **sin outputs**.
- `estrategias/*.json` — estrategias exportadas; NO se versionan (ver `.gitignore`).

Levantar: `docker compose --profile lab up lab` y abrir http://127.0.0.1:8888

El puerto se publica sólo en `127.0.0.1` (Jupyter corre código arbitrario como root); por eso
va sin token. No cambiar el mapeo `127.0.0.1:8888:8888` de `docker-compose.yml`.
