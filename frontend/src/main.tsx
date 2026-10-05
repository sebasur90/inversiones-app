import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import dayjs from 'dayjs'
import 'dayjs/locale/es'
import App from './App'
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import './index.css'
import { aplicarEscalaTexto, escalaTextoGuardada } from './utils/escalaTexto'

// La app es toda en español: sin esto dayjs formatea los meses en inglés ("October 2027").
// `utils/fechas.ts` lo repite para no depender del orden de evaluación de los módulos.
dayjs.locale('es')

// Antes del primer render: si no, el texto arranca en tamaño normal y salta al elegido.
aplicarEscalaTexto(escalaTextoGuardada())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
  })
}
