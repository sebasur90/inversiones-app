import { useId } from 'react'

const W = 280
const H = 56

export default function Sparkline({
  data,
  color = '#d8b14a',
  className = 'w-full h-14',
}: {
  data: number[]
  color?: string
  className?: string
}) {
  const gradientId = useId()

  if (data.length < 2) {
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className={className} preserveAspectRatio="none">
        <line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke={color} strokeOpacity={0.3} strokeWidth={2} strokeDasharray="4 5" />
      </svg>
    )
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const step = W / (data.length - 1)
  const points = data.map((v, i) => {
    const x = i * step
    const y = H - 6 - ((v - min) / span) * (H - 12)
    return [x, y] as const
  })

  const line = points.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `0,${H} ${line} ${W},${H}`

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={className} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity={0.32} />
          <stop offset="1" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gradientId})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
