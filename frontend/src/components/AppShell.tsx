import clsx from 'clsx'
import { ArrowRight, Library, Lightbulb, Settings2, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { api, useQuery } from '../lib/api'
import { prettyModel, prettyVendor } from '../lib/format'
import type { Health } from '../lib/types'
import { Logo } from './Logo'
import { StatusPill } from './StatusPill'

const NAV: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/', label: 'Library', icon: Library },
  { to: '/how-it-works', label: 'How it works', icon: Lightbulb },
  { to: '/settings', label: 'Settings', icon: Settings2 },
]

interface AppShellProps {
  title: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
}

/** The signed-in app frame: sidebar navigation, page header, content. */
export function AppShell({ title, subtitle, actions, children }: AppShellProps) {
  const health = useQuery('health', api.health)

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-white lg:flex">
        <div className="flex h-16 items-center px-5">
          <Logo />
        </div>
        <nav className="flex-1 px-3 pt-3">
          <div className="px-2.5 pb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-3 uppercase">Workspace</div>
          <ul className="space-y-0.5">
            {NAV.map((item) => (
              <li key={item.to}>
                <SideLink {...item} />
              </li>
            ))}
          </ul>
        </nav>
        <SystemCard health={health.data} error={health.error} />
      </aside>

      <div className="sticky top-0 z-30 border-b border-line bg-white/90 backdrop-blur lg:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <Logo />
          <StatusPill health={health.data} error={health.error} />
        </div>
        <nav className="scroll-thin flex gap-1 overflow-x-auto px-3 pb-2">
          {NAV.map((item) => (
            <SideLink key={item.to} {...item} compact />
          ))}
        </nav>
      </div>

      <main className="mx-auto max-w-6xl px-4 pb-16 sm:px-8">
        <header className="flex flex-wrap items-end justify-between gap-4 pt-7 pb-6 lg:pt-10">
          <div className="animate-fade-up">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] text-ink">{title}</h1>
            {subtitle && <p className="mt-1.5 text-[15px] text-ink-2">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </header>
        {children}
      </main>
    </div>
  )
}

function SideLink({ to, label, icon: Icon, compact }: { to: string; label: string; icon: LucideIcon; compact?: boolean }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors',
          compact ? 'px-3 py-1.5' : 'px-2.5 py-2',
          isActive ? 'bg-accent-soft text-accent-ink' : 'text-ink-2 hover:bg-hover hover:text-ink',
        )
      }
    >
      <Icon className="h-[18px] w-[18px]" strokeWidth={1.9} />
      {label}
    </NavLink>
  )
}

function SystemCard({ health, error }: { health?: Health; error?: string }) {
  const ready = health?.livekit_configured
  return (
    <div className="m-3 rounded-xl border border-line bg-subtle p-3.5">
      <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <span className={clsx('h-2 w-2 rounded-full', error ? 'bg-live' : !health ? 'bg-ink-3' : ready ? 'bg-ok' : 'bg-warn')} />
        {error ? 'API offline' : !health ? 'Checking…' : ready ? 'Ready to present' : 'Setup needed'}
      </div>
      {health && (
        <p className="mt-1.5 text-xs leading-relaxed text-ink-2">
          {prettyModel(health.models.llm)} · {prettyVendor(health.models.stt)} · {prettyVendor(health.models.tts)}
        </p>
      )}
      <Link to="/settings" className="mt-2.5 inline-flex items-center gap-1 text-xs font-semibold text-accent hover:text-accent-hover">
        View settings <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}
