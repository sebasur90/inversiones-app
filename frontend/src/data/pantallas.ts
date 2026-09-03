import type { IconName } from '../components/icons/Icons'

export type PantallaItem = { to: string; label: string; desc: string; icon: IconName }
export type GrupoPantallas = { titulo: string; items: PantallaItem[] }

// Índice de las pantallas a las que no se llega desde el bottom nav. Lo consumen el menú "Más"
// (agrupado por tema) y el buscador global (aplanado). Las cuatro pantallas del nav — Resumen,
// Posiciones, Rendimiento y Movimientos — no están acá: se listan aparte en PANTALLAS_NAV.
export const GRUPOS_PANTALLAS: GrupoPantallas[] = [
  {
    titulo: 'Cartera',
    items: [
      { to: '/watchlist', label: 'Watchlist', desc: 'Instrumentos a seguir y su distancia al precio de compra', icon: 'target' },
      { to: '/patrimonio', label: 'Patrimonio', desc: 'Evolución del valor vs. capital aportado, con aportes y retiros', icon: 'trend' },
      { to: '/exposicion', label: 'Exposición', desc: 'Composición por ticker, tipo, sector y mercado', icon: 'pie' },
      { to: '/rebalanceo', label: 'Balance de cartera', desc: 'Peso actual vs. objetivo por eje', icon: 'scale' },
      { to: '/objetivo', label: 'Objetivo', desc: 'Progreso hacia la meta y aporte mensual necesario', icon: 'target' },
      { to: '/precios', label: 'Precios', desc: 'Evolución histórica por ticker', icon: 'trend' },
      { to: '/vencimientos', label: 'Vencimientos', desc: 'Calendario de vencimientos de bonos', icon: 'alert' },
      { to: '/flujo-caja', label: 'Flujo de caja proyectado', desc: 'Cupones y amortizaciones a cobrar mes a mes', icon: 'trend' },
      { to: '/comisiones', label: 'Comisiones', desc: 'Desglose por cartera, ticker, mes y año', icon: 'scale' },
      { to: '/vista-fiscal', label: 'Vista fiscal por año', desc: 'Realizado, dividendos/cupones y comisiones por año calendario', icon: 'scale' },
    ],
  },
  {
    titulo: 'Rendimiento y riesgo',
    items: [
      { to: '/riesgo', label: 'Riesgo', desc: 'Drawdown, volatilidad, Sharpe, Sortino, Calmar', icon: 'trend' },
      { to: '/performance-relativa', label: 'Performance relativa', desc: 'Cartera vs. un benchmark: alpha, beta, tracking error', icon: 'up' },
      { to: '/benchmarks-comparacion', label: 'Comparar benchmarks', desc: 'Varios benchmarks y tickers a la vez', icon: 'pie' },
      { to: '/contribucion', label: 'Contribución', desc: 'Qué aportó cada posición, concentración y correlaciones', icon: 'pie' },
    ],
  },
  {
    titulo: 'Herramientas',
    items: [
      { to: '/simulador', label: 'Simulador', desc: 'Escenarios "¿qué pasaría si…?"', icon: 'edit' },
      { to: '/comparar', label: 'Comparador', desc: 'Hasta 5 tickers, series normalizadas', icon: 'search' },
    ],
  },
  {
    titulo: 'Sistema',
    items: [
      { to: '/diagnostico', label: 'Diagnóstico', desc: 'Score de salud de la cartera y hallazgos', icon: 'check' },
      { to: '/calidad-datos', label: 'Calidad de datos', desc: 'Estado del último sync y problemas detectados', icon: 'info' },
      { to: '/indicadores', label: 'Indicadores macro', desc: 'CER, MEP, riesgo país e inflación mensual', icon: 'trend' },
      { to: '/ajustes', label: 'Ajustes', desc: 'Moneda, sincronización automática y tamaño de texto', icon: 'edit' },
    ],
  },
]

// Las del bottom nav: no aparecen en "Más" pero sí tienen que ser buscables.
export const PANTALLAS_NAV: PantallaItem[] = [
  { to: '/resumen', label: 'Resumen', desc: 'Valor total, KPIs y qué requiere atención', icon: 'home' },
  { to: '/posiciones', label: 'Posiciones', desc: 'Tenencias actuales con precio y objetivo/stop-loss', icon: 'list' },
  { to: '/rendimiento', label: 'Rendimiento', desc: 'P&L, TIR, TWRR y mapa de calor mensual', icon: 'up' },
  { to: '/movimientos', label: 'Movimientos', desc: 'Compras, ventas, dividendos, cupones y amortizaciones', icon: 'list' },
]

export const TODAS_LAS_PANTALLAS: PantallaItem[] = [
  ...PANTALLAS_NAV,
  ...GRUPOS_PANTALLAS.flatMap(g => g.items),
]
