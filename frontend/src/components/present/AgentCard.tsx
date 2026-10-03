import type { AgentState, TrackReference } from '@livekit/components-react'
import clsx from 'clsx'
import { ENGINES } from '../../lib/engines'
import type { Engine } from '../../lib/types'
import { LiveAgentOrb, VoiceBars } from './LiveAgent'

interface AgentCardProps {
  state: AgentState
  track?: TrackReference
  status: string
  latencyMs: number | null
  slideLabel: string
  modeLabel: string
  engine: Engine
}

export function AgentCard({ state, track, status, latencyMs, slideLabel, modeLabel, engine }: AgentCardProps) {
  return (
    <div className="border-b border-line p-4">
      <div className="flex items-center gap-3.5">
        <LiveAgentOrb state={state} track={track} size={48} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-ink">Nova</span>
            <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide text-accent-ink uppercase">
              AI presenter
            </span>
            <span title="Agent engine" className="truncate rounded-md border border-line bg-white px-1.5 py-0.5 text-[10.5px] font-semibold text-ink-2">
              {ENGINES[engine].name}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-[13px] text-ink-2">
            <VoiceBars track={track} active={state === 'speaking'} />
            <span className="truncate">{status}</span>
          </div>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2">
        <Metric
          label="Response"
          value={latencyMs ? `${(latencyMs / 1000).toFixed(1)} s` : '—'}
          hint="Time from when you stop talking to Nova's first word"
          tone={latencyMs ? (latencyMs < 1300 ? 'good' : latencyMs < 2500 ? 'ok' : 'slow') : undefined}
        />
        <Metric label="Slide" value={slideLabel} />
        <Metric label="Mode" value={modeLabel} />
      </dl>
    </div>
  )
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'good' | 'ok' | 'slow' }) {
  return (
    <div title={hint} className="rounded-xl border border-line bg-subtle px-2.5 py-2">
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd
        className={clsx(
          'mt-0.5 truncate text-[13px] font-semibold tabular-nums',
          !tone && 'text-ink',
          tone === 'good' && 'text-ok',
          tone === 'ok' && 'text-warn',
          tone === 'slow' && 'text-live',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
