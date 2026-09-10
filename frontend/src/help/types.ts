export interface HelpContent {
  title: string
  shortDescription: string
  whyItMatters?: string
  howItIsCalculated?: string
  howToInterpret?: string
  example?: string
  limitations?: string
  relatedTerms?: string[]
}

/**
 * Guía de una pantalla entera, no de un término suelto. `HelpContent` responde "¿qué es esta
 * métrica?"; esto responde "entré acá, ¿qué estoy mirando y qué hago con esto?".
 *
 * El texto va en criollo y en segunda persona: el lector no sabe qué es una TIR.
 */
export interface GuiaPantalla {
  /** Una frase: qué es esta pantalla. Sin jerga. */
  queEs: string
  /** Qué significa lo que se ve en la pantalla. 2 a 4 bullets. */
  comoLeerla: string[]
  /** Qué hacer con esa información. Accionable, opcional. */
  queHacer?: string[]
  /** Malentendido frecuente o advertencia. Se muestra destacado. */
  ojo?: string
  /** Términos del glosario que conviene tener a mano acá (claves de `HELP`). */
  terminos?: string[]
}
