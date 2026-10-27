# Calendario de eventos de mercado (`/eventos`)

Herramienta de investigación para estudiar la relación temporal entre acontecimientos (elecciones,
decisiones de tasas, balances, guerras, aranceles, quiebras, datos macro) y los movimientos de precio de
acciones, CEDEARs, ETFs e índices. Responde preguntas como: qué estaba pasando cuando un ticker se movió
fuerte, qué fechas programadas se vienen para la cartera, cómo reaccionó un activo en eventos parecidos y
cómo lo hizo frente a su índice.

**No es causal ni una recomendación.** La pantalla habla siempre de *comportamiento observado alrededor
del evento*, lista los otros eventos de la misma ventana y compara contra el índice.

Entradas: `Más → Herramientas → Calendario de eventos`, el botón **Eventos** de Análisis técnico y
**Eventos de TICKER** en la ficha de un ticker (abren la pestaña Impacto con ese ticker).

## Fuente de verdad

Nada de esto toca el Google Sheet ni las tablas que vacía su sync. Los eventos, noticias, vínculos y el
estado de las fuentes son tablas propias de la app. Las series que se usan para el análisis son las del
análisis técnico (`serie_ohlcv`) y las de benchmarks (`SPY`, `QQQ`, `^MERV`), separadas de las que
valúan la cartera (`precios_instrumento`).

## Arquitectura

```
backend/app/services/eventos/
├── __init__.py               valores válidos de cada campo (categorías, estados, verificación…)
├── normalizacion_engine.py   Puro. URLs, texto plano, fechas, deduplicación de noticias y eventos
├── clasificacion_engine.py   Puro. Categoría, importancia y confianza por reglas (VERSION_REGLAS)
├── asociacion_engine.py      Puro. Vínculos con instrumentos: directa / sector / país / índice
├── estudio_engine.py         Puro. Rueda de referencia y retornos alrededor del evento
├── importacion.py            Puro. Formato JSON de calendarios (ver abajo)
├── eventos_analytics.py      Adaptador DB. Listado, filtros, ABM, fusión, vínculos, bandeja
├── eventos_sync.py           Adaptador DB. Orquestador: proveedores → normalizar → clasificar → asociar → guardar
├── impacto_analytics.py      Adaptador DB. Serie + marcas, análisis por evento, patrón por categoría
├── catalogo.py + datos/catalogo_historico.json   Semilla curada de eventos pasados
└── proveedores/
    ├── base.py               Interfaz común (ProveedorEventos, NoticiaCruda, EventoCrudo, ResultadoProveedor)
    ├── marketaux.py          Noticias financieras con entidades (clave)
    ├── yahoo_resultados.py   Fechas de balances (sin clave)
    ├── gdelt.py              Acontecimientos globales recientes (sin clave, apagado por default)
    └── importacion.py        Archivos JSON en el volumen de datos
backend/app/routers/eventos.py
frontend/src/pages/CalendarioEventos.tsx + components/eventos/
```

Tablas nuevas (`create_all`, sin migración): `eventos_mercado`, `noticias_mercado`,
`evento_instrumentos`, `estado_fuentes_eventos`. Ninguna tiene FK a tablas del sync: los instrumentos se
vinculan por ticker. **No hay tabla de análisis**: los retornos salen baratos y determinísticos de
`serie_ohlcv`; guardarlos duplicaría datos que se invalidan con cada sync o edición.

### Modelo

- **Evento**: título, descripción, resumen, notas, categoría/subcategoría, `fecha_evento`, `fecha_fin`,
  `hora_evento` + `zona_horaria`, `fecha_publicacion` (UTC, cuándo lo supo el mercado), `precision_fecha`
  (exacta / aproximada / mes / año / desconocida), `programado`, país/región, entidades (empresas,
  organismos, sectores), `importancia` (1–3), `confianza_datos`, `estado` (previsto, confirmado, en
  desarrollo, concluido, cancelado, reprogramado), `verificacion`, `origen` (manual, catálogo, calendario
  oficial, proveedor, importación), proveedor, id externo, fuente y URL, `clave_dedup`,
  `fusionado_en_id`, `fijado`, `descartado`, `campos_editados`, versión y reglas de clasificación.
- **Noticia**: proveedor, medio, URL (y normalizada), título, fragmento en texto plano, idioma, fechas de
  publicación y captura, entidades, categoría sugerida, evento asociado y estado (por revisar / asociada /
  descartada).
- **Vínculo evento–instrumento**: ticker, tipo de relación, justificación escrita, método (manual /
  automático), relevancia 0–1 y estado de revisión (propuesta / confirmada / descartada).

Tres escalas que no se mezclan y ninguna predice la dirección del precio: **importancia** (cuánto suele
mover al mercado), **relevancia** (qué tanto toca a ese ticker) y **confianza de los datos** (evidencia y
certeza de la fecha).

### Lo que hace el usuario manda

- Lo que se edita en un evento importado queda en `campos_editados`: ningún proveedor lo vuelve a pisar.
- Borrar un evento manual lo borra. Borrar uno importado lo deja **descartado** (lápida): si se borrara, la
  próxima sincronización lo recrearía.
- Un vínculo automático descartado queda como lápida: la asociación automática nunca lo revive. Cualquier
  corrección de un vínculo lo vuelve `manual`.
- Fusionar mueve noticias y vínculos al destino; el absorbido queda con `fusionado_en_id` y deja de listarse.

## Fuentes de datos

| Proveedor | Qué trae | Clave | Límites | Por defecto |
|---|---|---|---|---|
| Marketaux | Noticias financieras con tickers, industria, `match_score` y sentimiento | `MARKETAUX_API_TOKEN` | Gratis: 100 consultas/día y **3 noticias por consulta** (Basic: 2.500 y 20). 402 = cupo, 429 = ritmo | Activo si hay token |
| Yahoo Finance (`yfinance`) | Fechas de balances pasadas (con EPS) y la próxima | — | Límite de tasa no documentado: se corta la corrida ante un 429 | Activo |
| GDELT DOC 2.0 | Acontecimientos globales recientes | — | Sólo **últimos 3 meses**; **una consulta cada 5 s por IP** (detrás de un proxy compartido puede dar 429 siempre) | Apagado |
| Archivos de calendarios | Elecciones, reuniones de bancos centrales, calendarios corporativos | — | — | Activo |
| Catálogo histórico | ~45 eventos pasados 2019–2025 con fuente | — | — | Se siembra al arrancar |

Todo se consulta desde el backend: el frontend nunca habla con un proveedor ni ve una clave. Sin claves, la
pantalla funciona igual (eventos manuales, importados, catálogo y balances).

**Marketaux**: cada corrida pide `news/all` por tandas de 5 símbolos del universo (cartera ∪ watchlist),
rotando la tanda entre corridas, con `filter_entities=true`, `group_similar=true`, idiomas en/es y los
últimos 3 días; si queda cupo, una consulta general de macro y política. El token va como parámetro y
`market_data.client.request_json` no loguea los parámetros. El sentimiento se guarda como dato del
proveedor, no como pronóstico.

**GDELT**: sus resultados **siempre** van a la bandeja de revisión: un resultado de búsqueda no es un
acontecimiento verificado. Consultas configurables con `GDELT_CONSULTAS` (separadas por `;`).

**Calendarios oficiales sin API** (Reserva Federal, BCRA, Cámara Nacional Electoral, TSE): en lugar de un
scraper frágil, un archivo JSON. **Ninguna fecha futura vive en el código.**

### Formato de importación

Se lee de `EVENTOS_IMPORTACION_DIR` (default `/app/data/eventos_programados/*.json`, en el volumen del
backend) en cada sincronización, o se sube desde la pantalla (Fuentes → Importar un calendario, o
`POST /api/inversiones/eventos/importar`). Volver a importar actualiza en vez de duplicar (la clave es
`id`, por archivo); los campos corregidos desde la app no se pisan.

```json
{
  "eventos": [
    {
      "id": "fed-2027-01",
      "titulo": "Reunión de política monetaria de la Fed",
      "categoria": "banco_central",
      "fecha": "2027-01-27",
      "hora": "14:00",
      "zona_horaria": "America/New_York",
      "precision": "exacta",
      "estado": "previsto",
      "pais": "Estados Unidos",
      "importancia": 3,
      "url_fuente": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
      "fuente": "Reserva Federal",
      "verificacion": "fuente_oficial",
      "programado": true,
      "tickers": [{"ticker": "SPY", "relacion": "indice", "relevancia": 0.5, "motivo": "Mercado amplio"}]
    }
  ]
}
```

Obligatorios: `id` (letras, números, `. _ : -`), `titulo`, `categoria`, `fecha` (`AAAA-MM-DD`) y
`url_fuente` (`http`/`https`). Opcionales: `fecha_fin`, `hora` (`HH:MM`), `zona_horaria` (IANA),
`precision`, `estado`, `pais`, `region`, `importancia` (1–3), `descripcion`, `fuente`, `verificacion`,
`programado`, `entidades` (`empresas`, `organismos`, `sectores`, `terminos`) y `tickers`. Un ítem inválido
no frena al resto: vuelve en `errores` con su posición.

## Pipeline de noticias

1. Cada proveedor trae lo suyo (sin lock de la base).
2. Normalización: URL canónica (sin tracking, sin `www.`, `https`), texto plano sin HTML, fecha a UTC.
3. Duplicados: mismo id, misma URL o títulos parecidos (Jaccard ≥ 0,6) a menos de 48 h → un grupo.
   Lo ya guardado no se vuelve a guardar.
4. Clasificación por reglas de palabras clave ES/EN (`clasificacion_engine`, con la lista de reglas que
   se aplicaron guardada en el evento).
5. Vínculos: mención fuerte de un instrumento del universo (`match_score ≥ 10` o en el título) →
   directa; según la categoría, sector o país; un acontecimiento global sin país, sólo al índice amplio.
6. **Se incorpora sola** sólo si: categoría clara (confianza no baja), importancia ≥ media y mención
   fuerte de algo que el usuario sigue. Si no, va a **Para revisar**. Si se parece a un evento existente
   de la misma categoría a ±2 días, se suma a ése (y puede subir la verificación a "varias fuentes").
7. Un solo commit, con el lock del sync del Sheet (timeout 300 s).

## Análisis alrededor del evento (`estudio_engine`)

- **Mercado de la serie**: subyacente en USD, SPY y QQQ → Nueva York (cierre 16:00); serie local y Merval
  → BYMA (cierre 17:00). Las ruedas son las fechas con barra: los feriados salen de la propia serie.
- **Cuándo lo supo el mercado**: evento programado → su fecha y hora; si no, la publicación de la noticia
  (UTC); si no, la fecha del evento.
- **Rueda de referencia (T0)**: antes del cierre → esa rueda; después del cierre o día sin rueda → la
  siguiente; sin hora → la del día, con aviso.
- **Retornos** por ventana N ∈ {1, 5, 20} (+60 si alcanza): previo `C[T0−1]/C[T0−1−N]`, rueda
  `C[T0]/C[T0−1]`, posterior `C[T0+N]/C[T0]`, acumulado `C[T0+N]/C[T0−1−N]`. Con las fechas exactas, la
  cantidad de cotizaciones, volatilidad diaria antes/después y volumen relativo cuando hay volumen.
- **Benchmark** en las mismas fechas (tolerancia 3 días) y diferencia en puntos.
- **Faltantes**: un extremo que la serie no cubre queda vacío con su motivo; **nunca** se completa con el
  precio de hoy. Huecos de más de 7 días se avisan.
- **Superpuestos**: otros eventos de importancia ≥ media a ±N ruedas.
- **Patrón por categoría**: mediana del retorno a N ruedas tras los eventos de una categoría contra la de
  todos los tramos de N ruedas de la serie; sin estadísticas con menos de 8 casos.

Series: los CEDEARs usan el subyacente en USD (ajustado por Yahoo); las acciones locales, la serie de
BYMA **sin ajustar** (con aviso `posible_split` si hay un salto). Un ticker fuera de cartera y watchlist
no tiene serie: la pantalla ofrece agregarlo a la watchlist y bajar sus velas (`POST /decisiones/tecnico/{t}/preparar`).

**Eventos futuros**: la serie termina en la última cotización real; el eje se extiende con días hábiles
sin precio hasta el último evento futuro (fondo rayado, "sin cotización").

## Endpoints (`/api/inversiones`)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/eventos` | Listado con filtros combinables (`desde`, `hasta`, `categoria`, `pais`, `ticker`, `sector`, `en_cartera`, `importancia_min`, `verificacion`, `origen`, `proveedor`, `temporalidad`, `q`, `incluir_descartados`, `orden`, `page`, `limite` ≤ 500) |
| GET | `/eventos/opciones` | Valores válidos y los presentes en la base |
| GET | `/eventos/{id}` | Detalle con noticias, vínculos y reglas |
| POST | `/eventos` | Alta manual |
| PATCH | `/eventos/{id}` | Edición parcial (también `fijado`, `descartado`, `instrumentos`) |
| DELETE | `/eventos/{id}` | Manual: 204. Importado: 200 `{"resultado": "descartado"}` |
| POST | `/eventos/{id}/fusionar` | Absorbe el evento en `destino_id` |
| PUT/DELETE | `/eventos/{id}/instrumentos/{ticker}` | Alta/corrección o baja de un vínculo |
| GET | `/eventos/noticias` | Bandeja (`estado=por_revisar`) |
| POST | `/eventos/noticias/{id}/asociar` · `/crear-evento` · `/descartar` | Acciones de la bandeja |
| GET | `/eventos/fuentes` | Estado de cada proveedor (sin secretos) |
| POST | `/eventos/sincronizar` | Corrida manual (202; 409 si ya corre) |
| POST | `/eventos/importar` | Importa el JSON de arriba |
| GET | `/eventos/impacto/universo` | Tickers analizables |
| GET | `/eventos/impacto/{ticker}` | Serie + benchmark + marcas (`futuro=true` sin precio) |
| GET | `/eventos/{id}/analisis` · `/eventos/{id}/analisis/{ticker}` | Comportamiento observado |
| GET | `/eventos/patron/{ticker}?categoria=&n=` | Patrón por categoría |

## Configuración

```
MARKETAUX_API_TOKEN=                      # vacío = sin noticias automáticas
MARKETAUX_MAX_SOLICITUDES_POR_CORRIDA=5
MARKETAUX_LIMITE_DIARIO=90                # el plan gratis da 100
MARKETAUX_ARTICULOS_POR_SOLICITUD=3       # 3 gratis, 20 Basic, 50 Standard
GDELT_ENABLED=false
GDELT_CONSULTAS=                          # opcional, separadas por ;
EVENTOS_RESULTADOS_ENABLED=true
EVENTOS_RESULTADOS_MAX_POR_CORRIDA=25
EVENTOS_IMPORTACION_DIR=/app/data/eventos_programados
EVENTOS_HORAS=9,21                        # todos los días; vacío desactiva; requiere SCHEDULER_ENABLED
EVENTOS_MINUTO=15
```

Las claves van en el `.env` del servidor (gitignored), nunca en el código ni en el frontend. Tras cambiar
una variable: `docker compose up -d --build backend` (o con `-f docker-compose.corporate.yml`).

## Pruebas

`backend/tests/test_eventos_*.py`: CRUD y filtros, normalización y duplicados, clasificación y
asociación, sincronización idempotente con proveedores falsos (errores 402/429/timeout, sin claves, cupo
diario, ediciones y lápidas), parseo de Marketaux/Yahoo/GDELT con respuestas controladas, catálogo e
importación, estudio de eventos (rueda de referencia, ventanas incompletas, huecos, benchmark,
superpuestos) e impacto con eventos futuros sin precio. Ninguno llama a una API real.

## Limitaciones conocidas

- Con el plan gratuito de Marketaux la cobertura de noticias es escasa (3 por consulta).
- GDELT sólo cubre 3 meses y detrás del proxy corporativo responde 429 aunque no se haya consultado.
- Las fechas futuras de elecciones y reuniones de bancos centrales se cargan a mano o por importación.
- La clasificación por palabras clave es simple y auditable; puede errar en noticias ambiguas (por eso
  lo dudoso va a revisión).
- El catálogo histórico es un punto de partida curado a mano, marcado "a revisar".
- La pantalla vive en el ancho móvil de la app (`max-w-md`), también en el escritorio; el calendario es
  mensual con la lista del día debajo (sin vista semanal) y el gráfico no tiene zoom por gestos: el rango
  se elige con los botones.
