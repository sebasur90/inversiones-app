export interface PasoTour {
  emoji: string
  titulo: string
  texto: string
}

/**
 * Tour de bienvenida: aparece solo la primera vez que se abre la app con datos ya sincronizados
 * (ver `Root` en `App.tsx`) y queda accesible desde Ajustes y el Centro de ayuda ("Ver el tour
 * otra vez"). Es deliberadamente corto: la idea es orientar en 30 segundos, no explicar todo —
 * para el resto está la guía 💡 de cada pantalla y el Centro de ayuda.
 */
export const TOUR_BIENVENIDA: PasoTour[] = [
  {
    emoji: '👋',
    titulo: 'Tu cartera, en una sola app',
    texto:
      'Los datos salen de tu Google Sheet: la app sólo lee y calcula. No opera, no envía órdenes y no toca tu dinero.',
  },
  {
    emoji: '📊',
    titulo: 'Resumen: el punto de partida',
    texto:
      'El número grande es el valor total de tu cartera. Debajo, "Requiere atención" junta lo urgente para que no tengas que revisar pantalla por pantalla.',
  },
  {
    emoji: '🧭',
    titulo: 'La barra de abajo y "Más"',
    texto:
      'Las cuatro pantallas más usadas están siempre a mano. El resto —30 pantallas en total— vive agrupado por tema en "Más", y también se puede buscar con la lupa.',
  },
  {
    emoji: '🔄',
    titulo: 'Cartera, moneda y frescura de los datos',
    texto:
      'Arriba de cada pantalla elegís qué cartera mirar y en qué moneda (USD o ARS). La frase "Datos hace…" te avisa si conviene sincronizar de nuevo.',
  },
  {
    emoji: '💡',
    titulo: 'Cuando algo no se entiende',
    texto:
      'El ícono (i) junto a una métrica explica qué es y cómo se calcula. La franja "💡 Cómo leer esta pantalla" arriba de cada pantalla resume qué estás mirando.',
  },
  {
    emoji: '🎓',
    titulo: 'Centro de ayuda',
    texto:
      'En "Más → Centro de ayuda" hay tutoriales paso a paso, un buscador de todo el glosario y las preguntas más frecuentes. Este tour también está ahí por si lo querés repasar.',
  },
]
