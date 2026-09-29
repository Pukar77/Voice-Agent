import { MuteIcon, MicIcon, SpeakerIcon } from './icons.jsx'

// Bar heights are the "resting" pose; the animation takes over when the
// agent is listening or speaking.
const BARS = [
  { height: 30, delay: '0ms' },
  { height: 55, delay: '90ms' },
  { height: 85, delay: '180ms' },
  { height: 45, delay: '270ms' },
  { height: 100, delay: '360ms' },
  { height: 60, delay: '450ms' },
  { height: 35, delay: '540ms' },
]

function CoreIcon({ status, muted }) {
  if (muted) return <MuteIcon width={30} height={30} />
  if (status === 'speaking') return <SpeakerIcon width={30} height={30} />
  if (status === 'thinking') {
    return (
      <span className="orb__dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    )
  }
  if (status === 'connecting') return <span className="orb__spinner" aria-hidden="true" />
  return <MicIcon width={30} height={30} />
}

/**
 * The hero element: an orb whose colour and motion encode the session state,
 * with a waveform strip underneath.
 */
export function VoiceOrb({ status, muted = false }) {
  const active = status === 'listening' || status === 'speaking'

  return (
    <div
      className={`orb-wrap orb-wrap--${status}${muted ? ' orb-wrap--muted' : ''}`}
      role="img"
      aria-label={`Assistant status: ${status}`}
    >
      <div className="orb">
        <span className="orb__halo" />
        <span className="orb__ring" />
        <span className="orb__ring orb__ring--second" />
        <span className="orb__core">
          <CoreIcon status={status} muted={muted} />
        </span>
      </div>

      <div className={`wave${active ? ' wave--active' : ''}`} aria-hidden="true">
        {BARS.map((bar, index) => (
          <span
            key={index}
            className="wave__bar"
            style={{ height: `${bar.height}%`, animationDelay: bar.delay }}
          />
        ))}
      </div>
    </div>
  )
}
