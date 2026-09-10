import type { HelpKey } from './index'

export interface PasoTutorial {
  titulo: string
  detalle: string
  /** Ruta a la que lleva el botón "Ir ahí", si aplica. */
  ruta?: string
  /** Término del glosario que conviene tener a mano en este paso. */
  termino?: HelpKey
}

export interface Tutorial {
  id: string
  titulo: string
  resumen: string
  pasos: PasoTutorial[]
}

/**
 * Recorridos paso a paso para alguien que nunca usó la app. Viven en el Centro de ayuda
 * (`pages/Ayuda.tsx`), pestaña "Tutoriales". No reemplazan la guía 💡 de cada pantalla ni el
 * glosario: son el "hilo conductor" entre varias pantallas para una tarea concreta.
 */
export const TUTORIALES: Tutorial[] = [
  {
    id: 'primeros-pasos',
    titulo: 'Primeros pasos: del Sheet a la app',
    resumen: 'Cómo se conecta tu Google Sheet con lo que ves acá, y qué hacer si algo no aparece.',
    pasos: [
      {
        titulo: 'La app no guarda nada por su cuenta',
        detalle:
          'Todo lo que ves sale de tu Google Sheet: movimientos, instrumentos, objetivos, watchlist. La app lo lee, lo calcula y te lo muestra. Nunca opera ni modifica el Sheet.',
      },
      {
        titulo: 'Sincronizar trae los datos nuevos',
        detalle:
          'Tocá el ícono de sincronizar (arriba a la derecha, o el botón grande si es tu primera vez) cada vez que cambiaste algo en el Sheet y querés verlo reflejado acá.',
      },
      {
        titulo: 'Si algo no aparece, revisá Calidad de datos',
        detalle:
          'Después de sincronizar, si una fila del Sheet tiene un problema (una columna vacía, un formato raro), queda registrado ahí con el detalle de qué fila y qué falló.',
        ruta: '/calidad-datos',
      },
      {
        titulo: 'Elegí cartera y moneda',
        detalle:
          'Arriba de casi toda pantalla podés elegir "Consolidado" o una cartera puntual, y ver los importes en USD o ARS. Es sólo cómo se muestra: no cambia tus datos.',
        ruta: '/resumen',
      },
    ],
  },
  {
    id: 'cuanto-ganaste',
    titulo: 'Entender cuánto ganaste (o perdiste)',
    resumen: 'Por qué hay tres números distintos para "rendimiento", y cuál mirar según la pregunta.',
    pasos: [
      {
        titulo: 'Rendimiento simple: lo más intuitivo',
        detalle:
          'Compara lo que vale hoy contra lo que pusiste, sin importar cuándo. Es el número más fácil de entender, pero no sirve para comparar dos carteras con historiales de distinta duración.',
        termino: 'simple',
      },
      {
        titulo: 'TIR (XIRR): tiene en cuenta el timing',
        detalle:
          'Si aportaste plata en distintos momentos, la TIR pesa cada aporte según cuánto tiempo estuvo invertido. Es la más parecida a una "tasa de interés anual" de tu cartera.',
        termino: 'xirr',
      },
      {
        titulo: 'TWRR: sólo mide la estrategia',
        detalle:
          'Aísla el efecto de tus aportes y retiros: mide cómo le fue a la cartera en sí, como si nunca hubieras metido o sacado plata en el medio. Es lo que se usa para comparar contra un benchmark.',
        termino: 'twr',
      },
      {
        titulo: 'Dónde verlos todos juntos',
        detalle: 'La pantalla Rendimiento los muestra a los tres, lado a lado, en pesos nominales, pesos reales y dólares.',
        ruta: '/rendimiento',
      },
    ],
  },
  {
    id: 'leer-el-riesgo',
    titulo: 'Leer el riesgo sin ser experto',
    resumen: 'Qué mirar primero en la pantalla de Riesgo, sin necesitar saber estadística.',
    pasos: [
      {
        titulo: 'Empezá por el drawdown',
        detalle:
          'Es la pregunta más directa: "¿cuánto llegué a perder en el peor momento?". Un drawdown del 20% significa que en algún punto tu cartera valía 20% menos que su máximo.',
        termino: 'drawdown',
        ruta: '/riesgo',
      },
      {
        titulo: 'La volatilidad es "qué tan movido" fue el camino',
        detalle:
          'No es buena ni mala por sí sola: una cartera puede tener alta volatilidad y aun así terminar arriba. Sirve para saber si vas a poder tolerar los vaivenes.',
        termino: 'volatilidad',
      },
      {
        titulo: 'Sharpe, Sortino y Calmar: ganancia vs. riesgo',
        detalle:
          'Los tres comparan cuánto ganaste contra cuánto riesgo tomaste para lograrlo. Más alto es mejor; no hace falta entender la fórmula para usarlos así.',
        termino: 'sharpe',
      },
      {
        titulo: '"Datos insuficientes" es normal al principio',
        detalle:
          'Estas métricas necesitan varios meses de historial mensual. Con una cartera nueva, es esperable que varias digan eso hasta que pase más tiempo.',
      },
    ],
  },
  {
    id: 'precios-objetivo-y-alertas',
    titulo: 'Precios objetivo, stop-loss y alertas',
    resumen: 'Cómo configurar niveles de precio y qué hace la app cuando el mercado se acerca.',
    pasos: [
      {
        titulo: 'Objetivo y stop-loss se cargan en el Sheet',
        detalle:
          'Por cada ticker (en Posiciones o en Watchlist) podés definir un precio objetivo (dónde te gustaría vender o comprar) y un stop-loss (dónde cortarías la pérdida). Se cargan en la pestaña Instrumentos o Watchlist del Sheet.',
        termino: 'objetivo',
      },
      {
        titulo: 'La app avisa antes de que se cumplan',
        detalle:
          'No hace falta que el precio ya cruzó el nivel: en Ajustes podés definir un umbral (ej. 5%) para que la alerta aparezca un poco antes, con margen para decidir.',
        ruta: '/ajustes',
      },
      {
        titulo: 'Dónde se ven las alertas',
        detalle:
          'En Posiciones, un badge marca cada ticker en alerta y podés filtrar sólo esos. En Watchlist es lo mismo, pero para lo que todavía no tenés y estás por comprar.',
        ruta: '/posiciones',
        termino: 'posiciones_alerta_precio',
      },
    ],
  },
  {
    id: 'rebalancear',
    titulo: 'Cómo rebalancear tu cartera',
    resumen: 'De "está desbalanceada" a "esto es lo que tengo que comprar o vender".',
    pasos: [
      {
        titulo: 'Primero, definí objetivos de peso en el Sheet',
        detalle:
          'En la pestaña Rebalanceo del Sheet definís, por ejes (tipo de activo, sector, etc.), qué porcentaje de tu cartera querés que ocupe cada categoría.',
      },
      {
        titulo: 'Balance de Cartera te muestra la distancia',
        detalle:
          'Cada barra compara tu peso actual contra el objetivo. Lo que está fuera de la tolerancia (definida en el Sheet) es candidato a ajustar.',
        ruta: '/rebalanceo',
        termino: 'rebalanceo',
      },
      {
        titulo: 'Simulá antes de operar',
        detalle:
          'El botón "Simular rebalanceo" calcula, en plata, cuánto comprar o vender de cada cosa para volver al objetivo. No ejecuta nada: es sólo la cuenta.',
      },
    ],
  },
  {
    id: 'simular-escenarios',
    titulo: 'Simular escenarios: el "qué pasaría si"',
    resumen: 'Proyectar tu patrimonio bajo distintos supuestos, sin arriesgar nada real.',
    pasos: [
      {
        titulo: 'Arrancá con los presets',
        detalle:
          'Base, Alcista y Bajista ya vienen armados con supuestos razonables. Es más fácil partir de ahí y ajustar un par de números que empezar de cero.',
        ruta: '/simulador',
      },
      {
        titulo: 'Los parámetros son tus supuestos, no una predicción',
        detalle:
          'Variación esperada del dólar, aporte mensual, si reinvertís dividendos: todo eso lo definís vos. El resultado depende enteramente de esos números.',
        termino: 'escenario_horizonte',
      },
      {
        titulo: 'Compará varios escenarios a la vez',
        detalle: 'Podés tener hasta 6 escenarios abiertos y compararlos lado a lado en la misma tabla, antes de decidir cuál te parece más realista.',
      },
      {
        titulo: 'Guardá los que te sirvan',
        detalle: 'Un escenario guardado queda disponible para volver a cargarlo después, sin tener que rearmarlo.',
      },
    ],
  },
  {
    id: 'analisis-tecnico-en-criollo',
    titulo: 'Análisis técnico, explicado en criollo',
    resumen: 'Qué es un indicador, qué es una estrategia y qué es un backtest, sin jerga previa.',
    pasos: [
      {
        titulo: 'El gráfico de velas es el precio a lo largo del tiempo',
        detalle:
          'Cada vela resume un período (un día, por ejemplo): dónde abrió, dónde cerró, el máximo y el mínimo. Verde si cerró arriba de donde abrió, coral si cerró abajo.',
        ruta: '/analisis-tecnico',
      },
      {
        titulo: 'Un indicador es una cuenta hecha sobre el precio',
        detalle:
          'Por ejemplo, una media móvil es el promedio de los últimos N precios: suaviza el ruido para ver la tendencia. Podés activar varios a la vez y se superponen al gráfico.',
        termino: 'analisis_tecnico_indicadores',
      },
      {
        titulo: 'Una estrategia son reglas de entrada y salida',
        detalle:
          'Por ejemplo: "comprar cuando el precio cruza arriba de su media de 50 días, vender si cae 8% desde la compra". Se arman con un editor visual, sin escribir código.',
        termino: 'analisis_tecnico_estrategias',
      },
      {
        titulo: 'El backtest prueba esa estrategia contra el pasado',
        detalle:
          'Simula cómo le habría ido si la hubieras aplicado durante todo el historial disponible. Es un dato útil, pero no una garantía de resultado futuro: el mercado no se repite igual.',
        termino: 'analisis_tecnico_backtest',
      },
    ],
  },
]
