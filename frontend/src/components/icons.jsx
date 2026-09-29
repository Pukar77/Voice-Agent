/**
 * Inline SVG icons — one place, all stroke-based so they inherit color.
 */

const STROKE = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

export function MicIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <path d="M12 19v3" />
    </svg>
  )
}

export function StopIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <rect x="6" y="6" width="12" height="12" rx="3" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function SendIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  )
}

export function SpeakerIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M11 5 6 9H3v6h3l5 4z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  )
}

export function MuteIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M11 5 6 9H3v6h3l5 4z" />
      <path d="m16 9 5 6" />
      <path d="m21 9-5 6" />
    </svg>
  )
}

export function CloseIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="m6 6 12 12" />
      <path d="m18 6-12 12" />
    </svg>
  )
}

export function SparkIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M12 2.5 14 9l6.5 2L14 13l-2 6.5L10 13l-6.5-2L10 9z" />
      <path d="M19 17.5v3" />
      <path d="M17.5 19h3" />
    </svg>
  )
}

/** Five-bar waveform used as the app's logo mark. */
export function WaveIcon(props) {
  return (
    <svg {...STROKE} {...props} strokeWidth={2.4}>
      <path d="M4 10v4" />
      <path d="M8 6.5v11" />
      <path d="M12 3.5v17" />
      <path d="M16 6.5v11" />
      <path d="M20 10v4" />
    </svg>
  )
}

export function BotIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <rect x="4" y="8" width="16" height="11" rx="4" />
      <path d="M12 8V4.5" />
      <circle cx="12" cy="3.5" r="1.4" />
      <path d="M9 13.5h.01" />
      <path d="M15 13.5h.01" />
    </svg>
  )
}

export function PersonIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </svg>
  )
}

export function TrashIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M4 7h16" />
      <path d="M9.5 7V5.5a1.5 1.5 0 0 1 1.5-1.5h2a1.5 1.5 0 0 1 1.5 1.5V7" />
      <path d="m6.5 7 .9 12.1a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9L17.5 7" />
      <path d="M10.5 11v5" />
      <path d="M13.5 11v5" />
    </svg>
  )
}

export function AlertIcon(props) {
  return (
    <svg {...STROKE} {...props}>
      <path d="M12 8v5" />
      <path d="M12 16.5h.01" />
      <path d="M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
  )
}
