# Instrucciones del Proyecto

## Comandos de Ejecución

### En ambiente local (sin proxy):
```bash
docker compose up                    # Iniciar proyecto
docker compose down                  # Detener proyecto
docker compose logs -f               # Ver logs
```

### En ambiente corporativo (con proxy):
```bash
# 1. Crear archivo .env.corporate con tus credenciales:
#    cp .env.example .env.corporate
#    # Editar .env.corporate con tu proxy corporativo
#
# 2. Iniciar con la configuración corporativa:
docker compose -f docker-compose.yml -f docker-compose.corporate.yml up
docker compose -f docker-compose.yml -f docker-compose.corporate.yml down
docker compose -f docker-compose.yml -f docker-compose.corporate.yml logs -f
```

O crear alias en `.bashrc` / `.zshrc`:
```bash
alias compose-corp='docker compose -f docker-compose.yml -f docker-compose.corporate.yml'
# Luego usar: compose-corp up
```

### Laboratorio de estrategias (JupyterLab, perfil opcional):
```bash
# No arranca con `docker compose up` normal. Levantarlo aparte:
docker compose --profile lab up lab
# (corporativo)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml --profile lab up lab
```
Abrir **http://127.0.0.1:8888** (el puerto se publica sólo en `127.0.0.1`, por eso va sin token;
Jupyter corre código arbitrario como root). Los notebooks van en `lab/`;
las estrategias exportadas en `lab/estrategias/*.json` (no se versionan). El lab lee la DB de
la app en modo **solo lectura**. Ver `docs/laboratorio-estrategias.md`.

Prueba rápida sin Jupyter (el ejemplo end-to-end):
```bash
docker compose exec backend python -m scripts.lab_ejemplo AAPL
```

## Archivos de Configuración
- **docker-compose.yml** - Versión local (sin proxy)
- **docker-compose.corporate.yml** - Versión corporativa (carga proxy desde .env)
- **.env.corporate** - Variables de proxy (NO commitear, usar .env.example como template)

## Variables de Entorno (Corporativo)
Crear archivo `.env.corporate` basado en `.env.example`:
```
HTTP_PROXY=http://usuario:contraseña@proxy-host:puerto
HTTPS_PROXY=http://usuario:contraseña@proxy-host:puerto
NO_PROXY=localhost,127.0.0.1,...
```

⚠️ **IMPORTANTE**: Nunca commitear archivos `.env` con credenciales reales

## Reglas de Desarrollo
- Toda la aplicación debe correr dentro de los contenedores de Docker.
- No ejecutar scripts de entorno localmente sin pasar por Docker.
- No usar chromium
- **Credenciales y variables sensibles**: Usar `.env` files en `.gitignore`, nunca hardcodear