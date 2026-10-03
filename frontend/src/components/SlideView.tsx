import clsx from 'clsx'
import type { ReactNode } from 'react'
import type { Slide, SlideItem } from '../lib/types'
import { DeckIcon } from './Icon'

interface SlideViewProps {
  slide: Slide
  theme: string
  index: number
  total: number
  deckTitle: string
  /** Thumbnails drop the footer chrome. */
  thumbnail?: boolean
  className?: string
}

/**
 * Renders a slide at any size. All measurements use container query units (cqw), so the
 * same markup works as a full-screen stage and as a 120px thumbnail.
 */
export function SlideView({ slide, theme, index, total, deckTitle, thumbnail, className }: SlideViewProps) {
  return (
    <div
      className={clsx(
        '@container relative aspect-video w-full overflow-hidden select-none',
        `slide-theme-${theme}`,
        className,
      )}
      style={{ background: 'var(--s-bg)', color: 'var(--s-ink)' }}
    >
      {slide.layout === 'cover' && <CoverArt />}
      <div className="absolute inset-0 flex flex-col p-[5.5cqw]">
        <Body slide={slide} />
      </div>
      {!thumbnail && (
        <div className="s-faint absolute inset-x-[5.5cqw] bottom-[2.1cqw] flex justify-between text-[1.05cqw] tracking-wide">
          <span>{deckTitle}</span>
          <span className="font-mono">
            {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
          </span>
        </div>
      )}
    </div>
  )
}

function Body({ slide }: { slide: Slide }) {
  switch (slide.layout) {
    case 'cover':
      return <Cover slide={slide} />
    case 'steps':
      return <Steps slide={slide} />
    case 'stat':
      return <Stat slide={slide} />
    case 'cards':
      return <Cards slide={slide} />
    case 'bullets':
      return <Bullets slide={slide} />
    case 'closing':
      return <Closing slide={slide} />
  }
}

function Kicker({ children }: { children: ReactNode }) {
  return (
    <div className="s-accent flex items-center gap-[0.9cqw] text-[1.2cqw] font-medium tracking-[0.2em] uppercase">
      <span className="h-[0.15cqw] w-[2.4cqw] rounded-full bg-current" />
      {children}
    </div>
  )
}

function Header({ slide, size = 'md' }: { slide: Slide; size?: 'md' | 'lg' }) {
  return (
    <div>
      {slide.kicker && <Kicker>{slide.kicker}</Kicker>}
      <h2
        className={clsx(
          'mt-[1.5cqw] font-semibold leading-[1.05] tracking-[-0.03em] text-balance',
          size === 'lg' ? 'text-[5cqw]' : 'text-[4.1cqw]',
        )}
      >
        {slide.title}
      </h2>
      {slide.subtitle && slide.layout !== 'closing' && (
        <p className="s-muted mt-[1.3cqw] max-w-[78%] text-[1.75cqw] leading-snug text-pretty">{slide.subtitle}</p>
      )}
    </div>
  )
}

function Footnote({ children }: { children: ReactNode }) {
  return (
    <p className="s-faint mt-[2.2cqw] flex items-center gap-[0.8cqw] text-[1.3cqw]">
      <span className="h-[0.5cqw] w-[0.5cqw] rounded-full" style={{ background: 'var(--s-accent-2)' }} />
      {children}
    </p>
  )
}

function IconBadge({ icon, size = 'md' }: { icon: string | null; size?: 'sm' | 'md' }) {
  return (
    <div
      className={clsx(
        's-icon-badge flex shrink-0 items-center justify-center',
        size === 'md' ? 'h-[4.4cqw] w-[4.4cqw] rounded-[1.2cqw]' : 'h-[3.4cqw] w-[3.4cqw] rounded-[0.9cqw]',
      )}
    >
      <DeckIcon icon={icon} className={size === 'md' ? 'h-[2.2cqw] w-[2.2cqw]' : 'h-[1.7cqw] w-[1.7cqw]'} />
    </div>
  )
}

function Cover({ slide }: { slide: Slide }) {
  return (
    <div className="flex h-full flex-col">
      {slide.kicker && (
        <div className="s-card s-muted self-start rounded-full px-[1.5cqw] py-[0.6cqw] text-[1.2cqw] font-medium">
          {slide.kicker}
        </div>
      )}
      <div className="mt-auto mb-[3cqw]">
        <h1 className="max-w-[72%] text-[6.6cqw] leading-[1.0] font-semibold tracking-[-0.045em] text-balance">
          {slide.title}
        </h1>
        {slide.subtitle && (
          <p className="s-muted mt-[2cqw] max-w-[56%] text-[2.05cqw] leading-snug text-pretty">{slide.subtitle}</p>
        )}
      </div>
      <div className="s-faint flex items-center gap-[1cqw] text-[1.25cqw]">
        <span className="h-[0.55cqw] w-[0.55cqw] rounded-full" style={{ background: 'var(--s-accent)' }} />
        Presented live by Nova on Slidepilot
      </div>
    </div>
  )
}

/** Concentric rings and a soft orb behind the cover title. */
function CoverArt() {
  return (
    <div className="pointer-events-none absolute top-1/2 right-[-12cqw] h-[64cqw] w-[64cqw] -translate-y-1/2">
      {[0, 1, 2, 3].map((ring) => (
        <div
          key={ring}
          className="absolute rounded-full border"
          style={{
            inset: `${ring * 7}cqw`,
            borderColor: `color-mix(in oklab, var(--s-accent) ${18 - ring * 3}%, transparent)`,
          }}
        />
      ))}
      <div
        className="absolute inset-[24cqw] rounded-full opacity-55 blur-[2.2cqw]"
        style={{ background: 'radial-gradient(circle at 35% 35%, var(--s-accent-2), var(--s-accent) 55%, transparent 75%)' }}
      />
    </div>
  )
}

function Steps({ slide }: { slide: Slide }) {
  return (
    <div className="flex h-full flex-col">
      <Header slide={slide} />
      <div className="mt-auto grid grid-cols-3 gap-[2.4cqw]">
        {slide.items.map((item, i) => (
          <div key={item.title} className="s-card relative rounded-[1.5cqw] p-[2.2cqw]">
            <div className="flex items-start justify-between">
              <IconBadge icon={item.icon} />
              <span className="s-faint font-mono text-[1.2cqw]">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <h3 className="mt-[2.4cqw] text-[2cqw] font-semibold tracking-[-0.01em]">{item.title}</h3>
            <p className="s-muted mt-[0.8cqw] text-[1.45cqw] leading-[1.45]">{item.body}</p>
            {i < slide.items.length - 1 && (
              <div
                className="s-accent absolute top-1/2 right-[-1.95cqw] z-10 flex h-[1.5cqw] w-[1.5cqw] -translate-y-1/2 items-center justify-center rounded-full text-[1.1cqw]"
                style={{ background: 'var(--s-card-line)' }}
              >
                ›
              </div>
            )}
          </div>
        ))}
      </div>
      {slide.footnote && <Footnote>{slide.footnote}</Footnote>}
    </div>
  )
}

function Stat({ slide }: { slide: Slide }) {
  return (
    <div className="flex h-full flex-col">
      <div className="grid flex-1 grid-cols-[1.05fr_1fr] gap-[4.5cqw]">
        <div className="flex flex-col">
          <Header slide={slide} />
          {slide.stat && (
            <div className="mt-auto">
              <div className="s-gradient-text text-[9.5cqw] leading-[0.95] font-semibold tracking-[-0.055em]">
                {slide.stat.value}
              </div>
              <p className="s-muted mt-[1.2cqw] max-w-[88%] text-[1.7cqw] leading-snug">{slide.stat.label}</p>
            </div>
          )}
        </div>
        <div className="flex flex-col justify-end gap-[2.1cqw] pb-[0.5cqw]">
          {slide.items.map((item) => (
            <BreakdownRow key={item.title} item={item} />
          ))}
        </div>
      </div>
      {slide.footnote && <Footnote>{slide.footnote}</Footnote>}
    </div>
  )
}

function BreakdownRow({ item }: { item: SlideItem }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-[1cqw] text-[1.5cqw]">
        <span>{item.title}</span>
        <span className="s-accent font-mono text-[1.4cqw]">{item.value}</span>
      </div>
      <div className="mt-[0.8cqw] h-[0.9cqw] overflow-hidden rounded-full" style={{ background: 'var(--s-track)' }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.round((item.share ?? 0.5) * 100)}%`,
            background: 'linear-gradient(90deg, var(--s-accent), var(--s-accent-2))',
          }}
        />
      </div>
    </div>
  )
}

function Cards({ slide }: { slide: Slide }) {
  return (
    <div className="flex h-full flex-col">
      <Header slide={slide} />
      <div className="mt-auto grid grid-cols-3 gap-[2.2cqw]">
        {slide.items.map((item) => (
          <div key={item.title} className="s-card rounded-[1.5cqw] p-[2.3cqw]">
            <IconBadge icon={item.icon} />
            <h3 className="mt-[2.6cqw] text-[2cqw] font-semibold tracking-[-0.01em]">{item.title}</h3>
            <p className="s-muted mt-[0.8cqw] text-[1.45cqw] leading-[1.45]">{item.body}</p>
          </div>
        ))}
      </div>
      {slide.footnote && <Footnote>{slide.footnote}</Footnote>}
    </div>
  )
}

const looksLikeCode = (text: string) => /^[\w.]+\(.*\)$/.test(text)

function Bullets({ slide }: { slide: Slide }) {
  return (
    <div className="flex h-full flex-col">
      <Header slide={slide} />
      <div className={clsx('mt-auto grid items-end gap-[4cqw]', slide.callout ? 'grid-cols-[1.3fr_1fr]' : 'grid-cols-1')}>
        <ol className="space-y-[1.7cqw]">
          {slide.items.map((item, i) => (
            <li key={item.title} className="flex gap-[1.6cqw]">
              <span
                className="s-accent flex h-[3cqw] w-[3cqw] shrink-0 items-center justify-center rounded-full font-mono text-[1.25cqw]"
                style={{ border: '1px solid var(--s-card-line)', background: 'var(--s-card)' }}
              >
                {i + 1}
              </span>
              <div className="pt-[0.2cqw]">
                <div className="text-[1.85cqw] font-semibold">{item.title}</div>
                <div className="s-muted mt-[0.3cqw] text-[1.45cqw] leading-snug">{item.body}</div>
              </div>
            </li>
          ))}
        </ol>
        {slide.callout && (
          <div className="s-card rounded-[1.5cqw] p-[2.4cqw]">
            <div className="s-accent text-[1.15cqw] font-medium tracking-[0.18em] uppercase">{slide.callout.label}</div>
            <div
              className={clsx(
                'mt-[1.4cqw] leading-snug',
                looksLikeCode(slide.callout.text) ? 'font-mono text-[1.8cqw]' : 'text-[1.95cqw] font-medium text-pretty',
              )}
            >
              {slide.callout.text}
            </div>
          </div>
        )}
      </div>
      {slide.footnote && <Footnote>{slide.footnote}</Footnote>}
    </div>
  )
}

function Closing({ slide }: { slide: Slide }) {
  const compact = slide.items.length > 3
  // Compact mode: three across the first row, the rest share the second row evenly.
  const span = (i: number) => (i < 3 ? 'col-span-2' : ['col-span-6', 'col-span-3', 'col-span-2'][slide.items.length - 4])
  return (
    <div className="flex h-full flex-col">
      <Header slide={slide} size="lg" />
      <div className={clsx('mt-auto grid gap-[1.8cqw]', compact ? 'grid-cols-6' : 'grid-cols-3')}>
        {slide.items.map((item, i) =>
          compact ? (
            <div
              key={item.title}
              className={clsx('s-card flex items-center gap-[1.5cqw] rounded-[1.3cqw] p-[1.6cqw]', span(i))}
            >
              <IconBadge icon={item.icon} size="sm" />
              <div>
                <div className="text-[1.6cqw] font-semibold">{item.title}</div>
                <div className="s-muted text-[1.25cqw] leading-snug">{item.body}</div>
              </div>
            </div>
          ) : (
            <div key={item.title} className="s-card rounded-[1.5cqw] p-[2.2cqw]">
              <IconBadge icon={item.icon} />
              <div className="mt-[2cqw] text-[1.9cqw] font-semibold">{item.title}</div>
              <div className="s-muted mt-[0.6cqw] text-[1.4cqw] leading-snug">{item.body}</div>
            </div>
          ),
        )}
      </div>
      {slide.subtitle && (
        <p className="s-gradient-text mt-[2.6cqw] text-[2.3cqw] font-semibold tracking-[-0.01em]">{slide.subtitle}</p>
      )}
    </div>
  )
}
