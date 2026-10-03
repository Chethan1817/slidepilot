import { ArrowRight, Clock3, Layers, Play, Sparkles, Tag, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AgentOrb } from '../components/AgentOrb'
import { AppShell } from '../components/AppShell'
import { buttonClass } from '../components/button-class'
import { SlideView } from '../components/SlideView'
import { api, useQuery } from '../lib/api'
import type { DeckSummary } from '../lib/types'

export function LibraryPage() {
  const decks = useQuery('decks', api.decks)
  const health = useQuery('health', api.health)
  const featured = decks.data?.[0]

  return (
    <AppShell
      title="Library"
      subtitle="Decks Nova can present. Start a live session and talk to it like a person."
      actions={
        featured && (
          <Link to={`/present/${featured.id}`} className={buttonClass('primary')}>
            <Play className="h-4 w-4" /> Start demo
          </Link>
        )
      }
    >
      {health.status === 'error' && (
        <Banner title="The Slidepilot API isn't reachable">
          Start it with <Code>cd backend && uv run uvicorn app.server:app --port 8000</Code>
        </Banner>
      )}
      {health.data && !health.data.livekit_configured && (
        <Banner title="Connect LiveKit to go live">
          Add <Code>LIVEKIT_URL</Code>, <Code>LIVEKIT_API_KEY</Code> and <Code>LIVEKIT_API_SECRET</Code> to{' '}
          <Code>backend/.env.local</Code>. You can still browse every deck.
        </Banner>
      )}

      {decks.status === 'loading' && <FeaturedSkeleton />}
      {decks.status === 'error' && (
        <p className="rounded-xl border border-line bg-white p-6 text-sm text-ink-2 shadow-card">{decks.error}</p>
      )}
      {featured && <FeaturedDeck deck={featured} />}

      {decks.data && (
        <section className="mt-12">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">All decks</h2>
            <span className="text-sm text-ink-3">
              {decks.data.length} {decks.data.length === 1 ? 'deck' : 'decks'}
            </span>
          </div>
          <div className="mt-4 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {decks.data.map((deck) => (
              <DeckCard key={deck.id} deck={deck} />
            ))}
          </div>
        </section>
      )}
    </AppShell>
  )
}

function FeaturedDeck({ deck }: { deck: DeckSummary }) {
  return (
    <section className="animate-fade-up overflow-hidden rounded-2xl border border-line bg-white shadow-card">
      <div className="grid lg:grid-cols-[1.2fr_1fr]">
        <div className="relative border-b border-line bg-canvas p-5 sm:p-8 lg:border-r lg:border-b-0">
          <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:radial-gradient(70%_70%_at_50%_50%,black,transparent)]" />
          <div className="relative overflow-hidden rounded-xl shadow-slide ring-1 ring-black/5">
            <SlideView slide={deck.cover} theme={deck.theme} index={0} total={deck.slide_count} deckTitle={deck.title} />
          </div>
          <div className="absolute bottom-3 left-3 flex items-center gap-2.5 rounded-full border border-line bg-white py-1.5 pr-3.5 pl-1.5 shadow-elevated sm:bottom-5 sm:left-5">
            <AgentOrb state="listening" size={30} />
            <div className="text-[12.5px] leading-tight">
              <div className="font-semibold text-ink">Nova</div>
              <div className="text-ink-2">Ready to present</div>
            </div>
          </div>
        </div>
        <div className="flex flex-col justify-center p-6 sm:p-9">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-ink">
            <Sparkles className="h-3.5 w-3.5" /> Featured demo
          </span>
          <h2 className="mt-4 text-[26px] leading-tight font-semibold tracking-[-0.02em] text-ink">{deck.title}</h2>
          <p className="mt-2.5 text-[15px] leading-relaxed text-ink-2">{deck.description}</p>
          <dl className="mt-6 grid grid-cols-3 gap-3">
            <Fact icon={<Layers className="h-4 w-4" />} label="Slides" value={String(deck.slide_count)} />
            <Fact icon={<Clock3 className="h-4 w-4" />} label="Length" value={`~${deck.minutes} min`} />
            <Fact icon={<Tag className="h-4 w-4" />} label="Topic" value={deck.category} />
          </dl>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link to={`/present/${deck.id}`} className={buttonClass('primary', 'lg')}>
              <Play className="h-4 w-4" /> Start presenting
            </Link>
            <Link to="/how-it-works" className={buttonClass('ghost', 'lg')}>
              How it works <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <p className="mt-5 text-[13px] text-ink-3">Interrupt Nova any time. Just start talking.</p>
        </div>
      </div>
    </section>
  )
}

function Fact({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-subtle px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-xs text-ink-3">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 truncate text-sm font-semibold text-ink">{value}</dd>
    </div>
  )
}

function DeckCard({ deck }: { deck: DeckSummary }) {
  return (
    <Link
      to={`/present/${deck.id}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-elevated focus-visible:outline-2 focus-visible:outline-accent"
    >
      <div className="border-b border-line bg-canvas p-3">
        <div className="overflow-hidden rounded-lg ring-1 ring-black/5">
          <SlideView slide={deck.cover} theme={deck.theme} index={0} total={deck.slide_count} deckTitle={deck.title} thumbnail />
        </div>
      </div>
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded-md bg-accent-soft px-2 py-0.5 font-semibold text-accent-ink">{deck.category}</span>
          <span className="text-ink-3">
            {deck.slide_count} slides · ~{deck.minutes} min
          </span>
        </div>
        <h3 className="mt-3 text-base font-semibold text-ink">{deck.title}</h3>
        <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-2">{deck.description}</p>
        <div className="mt-auto flex items-center justify-between border-t border-line pt-4">
          <span className="flex items-center gap-2 text-xs text-ink-3">
            <AgentOrb state="listening" size={18} /> Presented by Nova
          </span>
          <span className="inline-flex items-center gap-1 text-sm font-semibold text-accent transition-all group-hover:gap-1.5">
            Present <ArrowRight className="h-4 w-4" />
          </span>
        </div>
      </div>
    </Link>
  )
}

function FeaturedSkeleton() {
  return (
    <div className="grid overflow-hidden rounded-2xl border border-line bg-white shadow-card lg:grid-cols-[1.2fr_1fr]">
      <div className="bg-canvas p-8">
        <div className="aspect-video animate-pulse rounded-xl bg-hover" />
      </div>
      <div className="space-y-3 p-9">
        <div className="h-5 w-28 animate-pulse rounded-full bg-hover" />
        <div className="h-7 w-64 animate-pulse rounded bg-hover" />
        <div className="h-4 w-full animate-pulse rounded bg-hover" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-hover" />
      </div>
    </div>
  )
}

function Banner({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6 flex gap-3 rounded-xl border border-warn/25 bg-warn-soft p-4 text-sm">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
      <div>
        <div className="font-semibold text-ink">{title}</div>
        <div className="mt-1 leading-relaxed text-ink-2">{children}</div>
      </div>
    </div>
  )
}

function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-hover px-1 py-0.5 font-mono text-[12.5px] text-ink">{children}</code>
}
