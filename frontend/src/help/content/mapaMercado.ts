import { HelpContent } from '../types'

export type MapaMercadoHelpKey =
  | 'mapa_que_es'
  | 'mapa_agrupar'
  | 'mapa_tamano'
  | 'mapa_variacion'
  | 'mapa_promedio_grupo'
  | 'mapa_sin_dato'

export const MAPAMERCADO_HELP: Record<MapaMercadoHelpKey, HelpContent> = {
  mapa_que_es: {
    title: 'Mapa de mercado',
    shortDescription: 'Todas las acciones, CEDEARs y ETFs del catálogo de IOL dibujados como rectángulos, agrupados por sector, región, tamaño o tipo y pintados de verde o rojo según cuánto subieron o bajaron.',
    whyItMatters: 'Sirve para dos cosas: ver de un vistazo qué empresas se parecen entre sí (las que comparten grupo) y cuáles se movieron en el período.',
    howToInterpret: 'Un grupo casi todo verde dice que el sector subió entero; uno mezclado, que subieron unas pocas. Tocá el título de un grupo para entrar a sus subgrupos y un rectángulo para ver la ficha de la empresa.',
    limitations: 'No es una recomendación. Que algo esté en rojo no dice que sea barato, ni en verde que esté caro: para eso está Valuación vs. pares.',
  },
  mapa_agrupar: {
    title: 'Agrupar por',
    shortDescription: 'Qué criterio junta a las empresas en un mismo bloque: Sector (y adentro la industria), Región (y adentro el país), Tamaño de empresa o Tipo de instrumento.',
    whyItMatters: 'Cada eje responde una pregunta distinta: "¿quiénes compiten?" (sector), "¿dónde están?" (región), "¿cuánto pesan en el mundo?" (tamaño) o "¿qué tipo de papel es?" (tipo).',
    howItIsCalculated: 'Sale de la misma clasificación que usan el resto de las pantallas: corrección manual, luego la lista de la app, luego Yahoo y por último tu Sheet. Lo que ninguna fuente informa va a "Sin clasificar".',
    example: 'Con Sector, Coca-Cola y PepsiCo quedan juntas en "Consumo defensivo › Bebidas sin alcohol". Con Región, juntas en "EEUU".',
  },
  mapa_tamano: {
    title: 'Tamaño del rectángulo',
    shortDescription: 'Qué hace más grande a un rectángulo: la capitalización de la empresa, cuánto pesa en tu cartera, o nada (todos iguales).',
    whyItMatters: '"Capitalización" muestra qué importa más en el mercado; "Mi cartera" qué importa más para vos; "Parejo" deja ver a todas por igual, útil para contar cuántas subieron y cuántas bajaron sin que las gigantes tapen al resto.',
    howItIsCalculated: 'La capitalización se achata con raíz cuadrada: con la escala real, tres o cuatro gigantes ocuparían casi todo el mapa y el resto serían puntos. Un emisor sin capitalización conocida se dibuja con el tamaño del más chico que sí la tiene. "Mi cartera" usa el porcentaje de cada posición sobre el total consolidado.',
    limitations: 'Al achatar con raíz cuadrada, las proporciones entre empresas no son las reales: sirve para comparar tamaños, no para medirlos.',
  },
  mapa_variacion: {
    title: 'Variación en dólares',
    shortDescription: 'Cuánto subió o bajó el precio en el período, medido en dólares. Para un CEDEAR es lo que se movió la acción en Nueva York, no el CEDEAR en pesos.',
    whyItMatters: 'El CEDEAR en pesos mezcla el movimiento de la empresa con el del dólar. Medido en dólares, el rojo y el verde dicen si la empresa subió o bajó, nada más.',
    howItIsCalculated: 'Último cierre contra el de la rueda anterior (1D) o contra hace 7, 30 y 365 días (1S, 1M, 1A). Las acciones argentinas cotizan en pesos: se pasan a dólares con el MEP de cada fecha. Si falta el MEP, esa acción queda en pesos y la ficha lo avisa.',
    limitations: 'Se actualiza una vez por día, después del cierre de EE.UU. Durante la rueda se ve lo de ayer, no lo de ahora.',
  },
  mapa_promedio_grupo: {
    title: 'Promedio del grupo',
    shortDescription: 'El número que acompaña al título de cada bloque: cuánto se movió el grupo en conjunto.',
    howItIsCalculated: 'Promedio de las variaciones de sus empresas, ponderado por el tamaño elegido: con "Capitalización" las grandes pesan más; con "Parejo", todas igual. Las empresas sin dato no entran al promedio.',
    example: 'Un sector con una gigante que subió 2% y diez chicas que bajaron 1% puede mostrar +0,8% con "Capitalización" y −0,5% con "Parejo". Los dos son ciertos: miden cosas distintas.',
  },
  mapa_sin_dato: {
    title: 'Rectángulos grises',
    shortDescription: 'Emisores que todavía no tienen variación: la descarga no los trajo, Yahoo no los conoce con ese símbolo, o no hay historia suficiente para el período elegido.',
    howToInterpret: 'Gris no es "no se movió": es "no sabemos". Un movimiento nulo se ve en un gris azulado neutro, un poco más claro.',
  },
}
