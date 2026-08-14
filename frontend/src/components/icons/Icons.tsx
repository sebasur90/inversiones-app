export type IconName =
  | 'home'
  | 'pie'
  | 'list'
  | 'target'
  | 'sync'
  | 'search'
  | 'chevron'
  | 'up'
  | 'down'
  | 'close'
  | 'back'
  | 'edit'
  | 'trash'
  | 'plus'
  | 'lock'
  | 'check'
  | 'alert'
  | 'download'
  | 'trend'
  | 'info'
  | 'scale'

export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <defs>
        <symbol id="i-home" viewBox="0 0 24 24">
          <path d="M4 11L12 4l8 7" />
          <path d="M6 10v9h5v-6h2v6h5v-9" />
        </symbol>
        <symbol id="i-pie" viewBox="0 0 24 24">
          <path d="M12 3v9l7 4A9 9 0 1 0 12 3z" />
        </symbol>
        <symbol id="i-list" viewBox="0 0 24 24">
          <line x1="4" y1="6" x2="20" y2="6" />
          <line x1="4" y1="12" x2="20" y2="12" />
          <line x1="4" y1="18" x2="20" y2="18" />
        </symbol>
        <symbol id="i-target" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="4.5" />
          <circle cx="12" cy="12" r="1" />
        </symbol>
        <symbol id="i-sync" viewBox="0 0 24 24">
          <path d="M4 4v6h6" />
          <path d="M20 20v-6h-6" />
          <path d="M5.5 15a8 8 0 0013.5 3.5M18.5 9A8 8 0 005 5.5" />
        </symbol>
        <symbol id="i-search" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="6.5" />
          <line x1="20" y1="20" x2="16" y2="16" />
        </symbol>
        <symbol id="i-chevron" viewBox="0 0 24 24">
          <path d="M6 9l6 6 6-6" />
        </symbol>
        <symbol id="i-up" viewBox="0 0 24 24">
          <path d="M7 17L17 7" />
          <path d="M7 7h10v10" />
        </symbol>
        <symbol id="i-down" viewBox="0 0 24 24">
          <path d="M7 7l10 10" />
          <path d="M17 7v10H7" />
        </symbol>
        <symbol id="i-close" viewBox="0 0 24 24">
          <line x1="6" y1="6" x2="18" y2="18" />
          <line x1="18" y1="6" x2="6" y2="18" />
        </symbol>
        <symbol id="i-back" viewBox="0 0 24 24">
          <path d="M15 5l-7 7 7 7" />
        </symbol>
        <symbol id="i-edit" viewBox="0 0 24 24">
          <path d="M4 20h4L18.5 9.5a2.1 2.1 0 00-3-3L5 17v3z" />
        </symbol>
        <symbol id="i-trash" viewBox="0 0 24 24">
          <path d="M5 7h14" />
          <path d="M9 7V5h6v2" />
          <path d="M7 7l1 13h8l1-13" />
        </symbol>
        <symbol id="i-plus" viewBox="0 0 24 24">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </symbol>
        <symbol id="i-lock" viewBox="0 0 24 24">
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V7a4 4 0 018 0v4" />
        </symbol>
        <symbol id="i-check" viewBox="0 0 24 24">
          <path d="M5 13l4 4L19 7" />
        </symbol>
        <symbol id="i-alert" viewBox="0 0 24 24">
          <path d="M12 4l9 16H3z" />
          <line x1="12" y1="10" x2="12" y2="14" />
          <line x1="12" y1="17" x2="12" y2="17.01" />
        </symbol>
        <symbol id="i-download" viewBox="0 0 24 24">
          <path d="M12 4v11" />
          <path d="M7 11l5 5 5-5" />
          <path d="M5 20h14" />
        </symbol>
        <symbol id="i-trend" viewBox="0 0 24 24">
          <polyline points="3 17 8 11 13 14 21 6" />
          <polyline points="17 6 21 6 21 10" />
        </symbol>
        <symbol id="i-info" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="9" />
          <line x1="12" y1="11" x2="12" y2="16" />
          <line x1="12" y1="8" x2="12" y2="8.01" />
        </symbol>
        <symbol id="i-scale" viewBox="0 0 24 24">
          <line x1="12" y1="3" x2="12" y2="21" />
          <line x1="5" y1="7" x2="19" y2="7" />
          <path d="M5 7l-3 6a3 3 0 006 0z" />
          <path d="M19 7l-3 6a3 3 0 006 0z" />
          <line x1="8" y1="21" x2="16" y2="21" />
        </symbol>
      </defs>
    </svg>
  )
}

export function Icon({ name, className = 'w-[18px] h-[18px]' }: { name: IconName; className?: string }) {
  return (
    <svg
      className={`${className} stroke-current fill-none shrink-0`}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <use href={`#i-${name}`} />
    </svg>
  )
}
