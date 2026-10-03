import { useId } from 'react'
import { Link } from 'react-router-dom'

export function LogoMark({ className = 'h-8 w-8' }: { className?: string }) {
  // Unique per instance: a gradient defined inside a hidden copy (e.g. the desktop
  // sidebar on mobile) would leave every other copy without a fill.
  const gradient = useId()
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id={gradient} x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1" />
          <stop offset="1" stopColor="#4338ca" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill={`url(#${gradient})`} />
      <rect x="8" y="11" width="2.6" height="10" rx="1.3" fill="white" />
      <rect x="12.6" y="8" width="2.6" height="16" rx="1.3" fill="white" />
      <rect x="17.2" y="12" width="2.6" height="8" rx="1.3" fill="white" fillOpacity=".85" />
      <rect x="21.8" y="14" width="2.6" height="4" rx="1.3" fill="white" fillOpacity=".7" />
    </svg>
  )
}

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-accent">
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">Slidepilot</span>
    </Link>
  )
}
