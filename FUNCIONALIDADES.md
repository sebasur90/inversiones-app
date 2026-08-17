# Funcionalidades de inversiones-app

Resumen de las pantallas de la app y qué datos/información puede ver el usuario. Generado a partir de una revisión del código (agosto 2026) — si la app cambia, este documento puede quedar desactualizado.

## Origen de datos

La app lee de Google Sheets (pestañas `Movimientos`, `Instrumentos`, `Precios`, `Objetivos`, `Rebalanceo`), con fallback automático a un Excel local si Sheets no está disponible (`USE_LOCAL_SHEET`). Todo se sincroniza a una base local (SQLite). También trae cotizaciones de dólar (MEP/CER) de una API externa (dolarapi.com).

## Navegación

14 pantallas con bottom nav estilo mobile. Soporte para múltiples carteras (más una vista "Consolidado") y toggle de moneda ARS/USD en toda la app.

## Pantallas y qué ve el usuario

- **Resumen** — valor total del patrimonio, KPIs (Invertido, XIRR, TWR), selector de carteras, gráfico cartera vs. benchmarks, top 5 posiciones.
- **Patrimonio** — evolución del valor de mercado vs. capital aportado, línea de máximo histórico (HWM), y eventos clickeables (aportes, retiros, dividendos/cupones) con detalle en modal. Filtros por período (1M–ALL) y vista (ARS nominal, ARS real por CER, USD MEP).
- **Rendimiento** — P&L realizado/no realizado/ingresos; rentabilidad simple, TIR (XIRR) y TWRR en ARS y USD; mapa de calor de rendimiento mensual/anual coloreado por intensidad; comparación vs. benchmarks; P&L por ticker.
- **Balance de Cartera / Rebalanceo** — peso actual vs. objetivo por eje (Cartera, Tipo, Sector), con barras de progreso.
- **Exposición** — composición de la cartera (donut/barras) por Ticker/Tipo/Sector/Mercado.
- **Posiciones / Ticker (detalle)** — tenencias actuales, precio, sparkline histórico, precio objetivo y stop-loss configurados con % de distancia y alertas de "objetivo alcanzado" / "stop loss disparado".
- **Movimientos** — historial de compras, ventas, dividendos, cupones, amortizaciones.
- **Precios** — evolución histórica por ticker (nominal / USD / ajustado por CER).
- **Objetivo** — por cartera: progreso hacia meta en USD, aporte mensual necesario vs. promedio, simulador de interés compuesto, gráfico de aportes.
- **Indicadores Macro** — evolución de CER y MEP.
- **Vencimientos** — calendario de vencimientos de bonos/instrumentos.
- **Comparador** — hasta 5 tickers, series normalizadas a base 100.
- **Comisiones** — desglose por cartera/ticker/mes/año.

## Extras

Glosario financiero integrado (tooltips), modal de resultados de sincronización con Sheets, app instalable como PWA. No tiene exportación (CSV/PDF) ni alertas push.
