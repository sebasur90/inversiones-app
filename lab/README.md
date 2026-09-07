# Carpeta de trabajo del laboratorio de estrategias

Se monta en `/app/lab` dentro del servicio `lab` de docker-compose (perfil `lab`).

- `*.ipynb` — notebooks, versionados **sin outputs**.
- `estrategias/*.json` — estrategias exportadas; NO se versionan (ver `.gitignore`).

Levantar: `docker compose --profile lab up lab` y abrir http://127.0.0.1:8888
