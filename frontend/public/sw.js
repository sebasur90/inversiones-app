const CACHE_NAME = 'inversiones-shell-v3'
const API_CACHE = 'inversiones-api-v1'
const APP_SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME && key !== API_CACHE).map((key) => caches.delete(key)))
      )
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

// El shell se sirve de caché y se revalida contra la red por detrás.
function shellStaleWhileRevalidate(request) {
  return caches.match(request).then((cached) => {
    const network = fetch(request)
      .then((response) => {
        const copia = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copia))
        return response
      })
      .catch(() => cached)
    return cached || network
  })
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const esApi = new URL(request.url).pathname.startsWith('/api/')
  event.respondWith(esApi ? apiConRespaldo(request) : shellStaleWhileRevalidate(request))
})
