import clsx from 'clsx'
import { AudioLines, Brain, Ear, Info, Radio, ShieldCheck, Workflow, Zap, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { AppShell } from '../components/AppShell'
import { api, useQuery } from '../lib/api'
import { ENGINES } from '../lib/engines'
import { prettyModel, prettyVendor } from '../lib/format'
import type { Engine, Health, Stage } from '../lib/types'

const ENGINE_ICONS: Record<Engine, LucideIcon> = { livekit: Zap, langgraph_pipeline: Workflow }

const STAGES: { stage: Stage; icon: LucideIcon; label: string; detail: string }[] = [
  { stage: 'stt', icon: Ear, label: 'Speech-to-text', detail: 'Turns what you say into text while you talk.' },
  { stage: 'llm', icon: Brain, label: 'Language model', detail: 'Presents, answers and decides when to change slides.' },
  { stage: 'tts', icon: AudioLines, label: 'Voice', detail: "Nova's voice, streamed sentence by sentence." },
]

export function SettingsPage() {
  const health = useQuery('health', api.health)

  return (
    <AppShell title="Settings" subtitle="How this workspace runs Nova.">
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-line bg-white p-4 text-sm text-ink-2 shadow-card">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <p>
          Providers are set by the API keys in <code className="rounded bg-hover px-1 py-0.5 font-mono text-[12.5px] text-ink">backend/.env.local</code>.
          Every provider with a key joins its stage's chain: the first one serves, and the rest take over if it fails.
        </p>
      </div>

      {health.status === 'error' && (
        <p className="rounded-xl border border-line bg-white p-6 text-sm text-ink-2 shadow-card">{health.error}</p>
      )}
      {health.status === 'loading' && <div className="h-64 animate-pulse rounded-2xl border border-line bg-white shadow-card" />}
      {health.data && (
        <div className="space-y-6">
          <Card title="Agent engines" description="Two separate ways to run Nova. Pick one on the start card before each presentation.">
            <ul className="grid gap-3 md:grid-cols-2">
              {health.data.engines.map((engine) => {
                const Icon = ENGINE_ICONS[engine.id]
                return (
                  <li key={engine.id} className="rounded-xl border border-line bg-subtle p-4">
                    <div className="flex items-start justify-between gap-3">
                      <span className="flex items-center gap-2.5">
                        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-accent shadow-xs ring-1 ring-line">
                          <Icon className="h-[18px] w-[18px]" />
                        </span>
                        <span className="text-sm font-semibold text-ink">{engine.name}</span>
                      </span>
                      <span title={engine.available ? undefined : `Needs ${ENGINES[engine.id].needs}`}>
                        <Badge tone={engine.available ? 'ok' : 'warn'}>{engine.available ? 'Available' : 'Needs API keys'}</Badge>
                      </span>
                    </div>
                    <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{ENGINES[engine.id].blurb}</p>
                    <p className="mt-2 text-xs text-ink-3">
                      Model: <span className="font-medium text-ink-2">{prettyModel(engine.llm)}</span>
                    </p>
                  </li>
                )
              })}
            </ul>
          </Card>

          <Card title="AI pipeline" description="The three models behind every reply, in the order they're tried.">
            <ul className="divide-y divide-line">
              {STAGES.map(({ stage, icon: Icon, label, detail }) => (
                <li key={stage} className="grid gap-3 py-4 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:items-center">
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                      <Icon className="h-[18px] w-[18px]" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-ink">{label}</div>
                      <div className="text-[13px] text-ink-2">{detail}</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {health.data.pipeline[stage].map((step, i) => (
                      <Provider key={step.provider} provider={step.provider} model={step.model} primary={i === 0} />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Real-time" description="How audio and conversation flow between your browser and Nova.">
            <Rows health={health.data} />
          </Card>

          <Card title="Presenter" description="How Nova handles your decks.">
            <dl className="divide-y divide-line text-sm">
              <Row label="Name" value="Nova" />
              <Row
                label="Speaker notes"
                value={
                  <span className="inline-flex items-center gap-1.5">
                    <ShieldCheck className="h-4 w-4 text-ok" /> Private: used by Nova, never sent to the browser
                  </span>
                }
              />
              <Row label="Slide changes" value="Automatic: follows your questions, or click any slide" />
            </dl>
          </Card>
        </div>
      )}
    </AppShell>
  )
}

function Rows({ health }: { health: Health }) {
  const cloud = health.livekit.cloud
  return (
    <dl className="divide-y divide-line text-sm">
      <Row
        label="LiveKit server"
        value={
          <span className="inline-flex flex-wrap items-center gap-2">
            <Radio className="h-4 w-4 text-accent" />
            <span className="font-mono text-[12.5px]">{health.livekit.url || 'Not configured'}</span>
            <Badge tone={health.livekit_configured ? 'ok' : 'warn'}>{cloud ? 'LiveKit Cloud' : health.livekit_configured ? 'Local server' : 'Setup needed'}</Badge>
          </span>
        }
      />
      <Row label="Turn detection" value={cloud ? 'LiveKit turn detector (cloud)' : 'Turn-detector model bundled with the SDK'} />
      <Row label="Interruptions" value="Voice-activity barge-in: Nova stops as soon as you speak" />
      <Row label="End of turn" value="0.6 to 1.5 s after you stop talking" />
    </dl>
  )
}

function Provider({ provider, model, primary }: { provider: string; model: string; primary: boolean }) {
  return (
    <div
      className={clsx(
        'flex items-center gap-2 rounded-xl border px-3 py-2',
        primary ? 'border-accent/30 bg-accent-soft/60' : 'border-line bg-subtle',
      )}
    >
      <div className="leading-tight">
        <div className="text-[13px] font-semibold text-ink">{prettyVendor(provider)}</div>
        <div className="font-mono text-[11.5px] text-ink-2">{prettyModel(model)}</div>
      </div>
      <Badge tone={primary ? 'accent' : 'muted'}>{primary ? 'Primary' : 'Fallback'}</Badge>
    </div>
  )
}

function Card({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-white shadow-card">
      <header className="border-b border-line px-6 py-4">
        <h2 className="font-semibold text-ink">{title}</h2>
        <p className="mt-0.5 text-[13px] text-ink-2">{description}</p>
      </header>
      <div className="px-6 py-5">{children}</div>
    </section>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[180px_1fr] sm:items-center">
      <dt className="text-ink-2">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  )
}

function Badge({ tone, children }: { tone: 'ok' | 'warn' | 'accent' | 'muted'; children: ReactNode }) {
  return (
    <span
      className={clsx(
        'rounded-md px-1.5 py-0.5 text-[11px] font-semibold',
        tone === 'ok' && 'bg-ok-soft text-ok',
        tone === 'warn' && 'bg-warn-soft text-warn',
        tone === 'accent' && 'bg-white text-accent ring-1 ring-accent/20',
        tone === 'muted' && 'bg-white text-ink-3 ring-1 ring-line',
      )}
    >
      {children}
    </span>
  )
}
