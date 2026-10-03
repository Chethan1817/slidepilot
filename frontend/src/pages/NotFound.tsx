import { Link } from 'react-router-dom'
import { buttonClass } from '../components/button-class'

export function NotFoundPage() {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 text-center">
      <p className="text-sm text-ink-2">That page doesn't exist.</p>
      <Link to="/" className={buttonClass('secondary')}>
        Back to library
      </Link>
    </div>
  )
}
