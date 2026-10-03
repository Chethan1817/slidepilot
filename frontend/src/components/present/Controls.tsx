import { useLocalParticipant, useTrackVolume, type TrackReference } from '@livekit/components-react'
import clsx from 'clsx'
import { ChevronLeft, ChevronRight, Mic, MicOff, Pause, Play, RotateCcw } from 'lucide-react'
import { Track } from 'livekit-client'
import type { Deck, PresentMode } from '../../lib/types'
import { Button, IconButton } from '../Button'
import { SlideView } from '../SlideView'

interface RailProps {
  deck: Deck
  current: number
  disabled: boolean
  speaking: boolean
  onSelect: (index: number) => void
}

export function ThumbnailRail({ deck, current, disabled, speaking, onSelect }: RailProps) {
  return (
    <div className="scroll-thin flex shrink-0 gap-3 overflow-x-auto px-4 pt-2 pb-3 sm:justify-center sm:px-10">
      {deck.slides.map((slide, i) => (
        <button
          key={slide.id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(i)}
          aria-label={`Slide ${i + 1}: ${slide.title}`}
          aria-current={i === current ? 'true' : undefined}
          className="group w-[116px] shrink-0 text-left disabled:cursor-not-allowed sm:w-[126px]"
        >
          <div
            className={clsx(
              'relative overflow-hidden rounded-lg bg-white shadow-xs transition',
              i === current
                ? 'ring-2 ring-accent ring-offset-2 ring-offset-canvas'
                : 'ring-1 ring-line group-hover:ring-line-strong group-hover:shadow-card',
            )}
          >
            <SlideView slide={slide} theme={deck.theme} index={i} total={deck.slides.length} deckTitle={deck.title} thumbnail />
            {i === current && speaking && (
              <span className="absolute top-1.5 right-1.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-white shadow-xs">
                <span className="h-1.5 w-1.5 animate-blink rounded-full bg-accent" />
              </span>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 px-0.5 text-[11.5px]">
            <span className={clsx('font-mono', i === current ? 'font-semibold text-accent' : 'text-ink-3')}>{i + 1}</span>
            <span className={clsx('truncate', i === current ? 'font-medium text-ink' : 'text-ink-2')}>{slide.title}</span>
          </div>
        </button>
      ))}
    </div>
  )
}

interface ControlBarProps {
  live: boolean
  ready: boolean
  mode: PresentMode | undefined
  slideIndex: number
  slideCount: number
  onPrev: () => void
  onNext: () => void
  onPause: () => void
  onResume: () => void
  onStart: () => void
  startDisabled: boolean
  micBlocked: boolean
  onMicError: () => void
}

/** Floating call-style dock: mic, mode, slide navigation and the main action. */
export function ControlBar(props: ControlBarProps) {
  const { live, ready, mode, slideIndex, slideCount } = props
  return (
    <div className="flex items-center gap-1 rounded-2xl border border-line bg-white p-1.5 shadow-elevated">
      {live && (
        <>
          <MicButton blocked={props.micBlocked} onError={props.onMicError} />
          {ready && <ModeChip mode={mode} />}
          <Divider />
        </>
      )}

      <IconButton aria-label="Previous slide" onClick={props.onPrev} disabled={(live && !ready) || slideIndex === 0}>
        <ChevronLeft className="h-[18px] w-[18px]" />
      </IconButton>
      <span className="w-12 text-center text-[13px] font-medium text-ink-2 tabular-nums">
        {slideIndex + 1} / {slideCount}
      </span>
      <IconButton aria-label="Next slide" onClick={props.onNext} disabled={(live && !ready) || slideIndex === slideCount - 1}>
        <ChevronRight className="h-[18px] w-[18px]" />
      </IconButton>

      <Divider />
      {!live ? (
        <Button variant="primary" onClick={props.onStart} disabled={props.startDisabled}>
          <Mic className="h-4 w-4" /> Start
        </Button>
      ) : mode === 'presenting' ? (
        <Button variant="secondary" onClick={props.onPause} disabled={!ready} title="Pause (Space)">
          <Pause className="h-4 w-4" /> Pause
        </Button>
      ) : (
        <Button variant="primary" onClick={props.onResume} disabled={!ready} title="Continue (Space)">
          {mode === 'finished' ? <RotateCcw className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          {mode === 'finished' ? 'Replay' : 'Continue'}
        </Button>
      )}
    </div>
  )
}

function Divider() {
  return <span className="mx-1 h-6 w-px bg-line" aria-hidden />
}

const MODE_LABELS: Record<PresentMode, string> = {
  idle: 'Starting',
  presenting: 'Presenting',
  paused: 'Paused',
  finished: 'Q&A',
}

function ModeChip({ mode }: { mode: PresentMode | undefined }) {
  if (!mode) return null
  return (
    <span
      className={clsx(
        'ml-1 hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold sm:inline-flex',
        mode === 'presenting' && 'bg-accent-soft text-accent-ink',
        mode === 'paused' && 'bg-warn-soft text-warn',
        (mode === 'finished' || mode === 'idle') && 'bg-hover text-ink-2',
      )}
    >
      <span
        className={clsx(
          'h-1.5 w-1.5 rounded-full',
          mode === 'presenting' && 'animate-blink bg-accent',
          mode === 'paused' && 'bg-warn',
          (mode === 'finished' || mode === 'idle') && 'bg-ink-3',
        )}
      />
      {MODE_LABELS[mode]}
    </span>
  )
}

function MicButton({ blocked, onError }: { blocked: boolean; onError: () => void }) {
  const { localParticipant, isMicrophoneEnabled, microphoneTrack } = useLocalParticipant()
  const trackRef: TrackReference | undefined = microphoneTrack
    ? { participant: localParticipant, publication: microphoneTrack, source: Track.Source.Microphone }
    : undefined
  const level = useTrackVolume(trackRef)
  const on = isMicrophoneEnabled && !blocked

  const toggle = async () => {
    try {
      await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)
    } catch {
      onError()
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={on ? 'Mute microphone (M)' : 'Unmute microphone (M)'}
      aria-label={on ? 'Mute microphone' : 'Unmute microphone'}
      className={clsx(
        'relative flex h-9 w-9 items-center justify-center rounded-xl transition',
        on ? 'text-ink hover:bg-hover' : 'bg-live-soft text-live hover:bg-live-soft/70',
      )}
    >
      {on && (
        <span
          className="absolute inset-1 rounded-lg bg-ok/15 transition-transform duration-75"
          style={{ transform: `scale(${1 + Math.min(level * 2.5, 0.35)})`, opacity: Math.min(level * 6, 1) }}
        />
      )}
      {on ? <Mic className="relative h-[18px] w-[18px]" /> : <MicOff className="relative h-[18px] w-[18px]" />}
    </button>
  )
}
