import { useEffect } from 'react'

export default function Toast({
  message,
  tone = 'success',
  onDone,
}: {
  message: string | null
  tone?: 'success' | 'error'
  onDone: () => void
}) {
  useEffect(() => {
    if (!message) return
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [message, onDone])

  if (!message) return null

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`animate-toast-in fixed left-1/2 -translate-x-1/2 bottom-24 z-[60] max-w-[92vw] px-4 py-3 rounded-2xl border shadow-lg flex items-center gap-2 text-caption font-semibold bg-app-surface text-app-text ${
        tone === 'success' ? 'border-app-pos/35' : 'border-app-neg/35'
      }`}
    >
      <span aria-hidden="true" className="text-title leading-none">{tone === 'success' ? '✅' : '😕'}</span>
      {message}
    </div>
  )
}
