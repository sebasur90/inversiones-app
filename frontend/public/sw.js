const CACHE_NAME = 'inversiones-shell-v7'
const API_CACHE = 'inversiones-api-v1'
// Logos de las empresas (mapa de mercado). Caché aparte y sin versión atada a la del shell: no son
// datos del usuario, cambian casi nunca y bajarlos de nuevo en cada deploy sería gastar red por nada.
const LOGOS_CACHE = 'inversiones-logos-v1'
const RUTA_LOGOS = '/api/inversiones/logos/'
const APP_SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)))
  self.skipWaiting()
})

// El caché de la API se borra en cada activación de una versión nueva del service worker: son
// respuestas con el patrimonio, las posiciones y los movimientos, y quedan en disco sin cifrar.
// Antes estaba excluido de esta limpieza, así que nunca caducaba. Ajustes tiene además un botón
// para borrarlo a mano (`utils/purgarCacheApi.ts`).
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME && key !== LOGOS_CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  )
})

// Las respuestas de la API se guardan como red de contención: la red manda siempre, pero si
// no hay conexión la app abre con los últimos datos conocidos en vez de una pantalla vacía.
// El chip de frescura del header avisa de cuándo son.
function apiConRespaldo(request) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const copia = response.clone()
        caches.open(API_CACHE).then((cache) => cache.put(request, copia))
      }
      return response
    })
    .catch(() => caches.match(request).then((cached) => cached || Promise.reject(new Error('offline'))))
}

// El shell se sirve de caché y se revalida contra la red por detrás. Sólo se guarda lo que
// respondió bien: antes un chunk inexistente devolvía el index.html del fallback de nginx y
// quedaba cacheado bajo la URL del .js, rompiendo esa pantalla para siempre (la versión del
// caché se subió para purgar lo ya contaminado).
function shellStaleWhileRevalidate(request) {
  return caches.match(request).then((cached) => {
    const network = fetch(request)
      .then((response) => {
        if (response.ok) {
          const copia = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copia))
        }
        return response
      })
      .catch(() => cached)
    return cached || network
  })
}

// Los logos van primero a caché: si ya está, no se pide. Sólo se guarda lo que respondió bien (un
// 404 de "sin logo" no se cachea: el logo puede aparecer cuando la ingesta lo baje).
function logoDesdeCache(request) {
  return caches.match(request).then(
    (cached) =>
      cached ||
      fetch(request).then((response) => {
        if (response.ok) {
          const copia = response.clone()
          caches.open(LOGOS_CACHE).then((cache) => cache.put(request, copia))
        }
        return response
      })
  )
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const { pathname } = new URL(request.url)
  if (pathname.startsWith(RUTA_LOGOS)) {
    event.respondWith(logoDesdeCache(request))
    return
  }
  const esApi = pathname.startsWith('/api/')
  event.respondWith(esApi ? apiConRespaldo(request) : shellStaleWhileRevalidate(request))
})
