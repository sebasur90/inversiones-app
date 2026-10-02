/** Prefijo de los cachés de la API que crea el service worker (`public/sw.js`). */
const PREFIJO_CACHE_API = 'inversiones-api-'

/**
 * Borra las respuestas de la API que el service worker guardó para poder abrir sin conexión.
 * Son datos reales de la cartera (patrimonio, posiciones, movimientos) y quedan en Cache Storage
 * sin cifrar, así que el modo privacidad no alcanza si alguien tiene acceso al dispositivo.
 *
 * Se borra desde la ventana y no con un `postMessage` al service worker: Cache Storage es
 * same-origin y compartido entre los dos, y hacerlo acá funciona también cuando no hay un service
 * worker *controlando* la pestaña (primer load, registro viejo, uno esperando activación), que es
 * justo el caso en el que uno quiere purgar.
 *
 * Se matchea por prefijo en vez del nombre exacto porque `sw.js` es JS plano en `public/` y no
 * puede importar de `src/`: así no hay que duplicar la constante, y además se limpian las
 * versiones huérfanas que hayan quedado de un deploy anterior.
 *
 * No toca `inversiones-shell-*`: el shell tiene que sobrevivir para que la app siga abriendo sin
 * conexión, y no contiene datos privados. Tampoco toca el caché en memoria de React Query, que
 * muere al cerrar la pestaña y cuyo borrado dejaría la pantalla en blanco.
 *
 * @returns cuántos cachés borró, o `null` si el navegador no expone Cache Storage.
 */
export async function purgarCacheApi(): Promise<number | null> {
  try {
    if (typeof caches === 'undefined') return null
    const claves = await caches.keys()
    const deApi = claves.filter(k => k.startsWith(PREFIJO_CACHE_API))
    const borrados = await Promise.all(deApi.map(k => caches.delete(k)))
    return borrados.filter(Boolean).length
  } catch {
    // Safari en modo privado y algunas configuraciones bloquean Cache Storage: no hay nada que
    // borrar y tampoco debe tumbar la pantalla de Ajustes.
    return null
  }
}
