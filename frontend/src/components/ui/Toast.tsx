import { useEffect } from 'react'
import { Icon } from '../icons/Icons'

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
    <div className="fixed left-1/2 -translate-x-1/2 bottom-24 z-[60] max-w-[92vw] px-4 py-3 rounded-2xl border shadow-lg flex items-center gap-2 text-caption font-semibold bg-app-surface border-app-border text-app-text">
      <Icon
        name={tone === 'success' ? 'check' : 'alert'}
        className={`w-4 h-4 ${tone === 'success' ? 'text-app-teal' : 'text-app-coral'}`}
      />
      {message}
    </div>
  )
}
