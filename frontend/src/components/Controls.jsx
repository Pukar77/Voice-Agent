import { MuteIcon, MicIcon, SpeakerIcon, StopIcon, TrashIcon } from './icons.jsx'

/**
 * The talk / mute / clear row.
 *
 * The big button is the only thing that matters, so it gets the gradient and
 * the pulse ring; the rest are quiet ghost buttons.
 */
export function Controls({ status, muted, canClear, onToggle, onMute, onClear }) {
  const active = status !== 'idle'

  return (
    <div className="controls">
      <button
        type="button"
        className={`talk${active ? 'talk--active' : ''}`}
        onClick={onToggle}
        aria-pressed={active}
      >
        {active && <span className="talk__pulse" aria-hidden="true" />}
        <span className="talk__icon">{active ? <StopIcon /> : <MicIcon />}</span>
        <span className="talk__label">{active ? 'Stop' : 'Talk'}</span>
      </button>

      <button
        type="button"
        className={`ghost${muted ? 'ghost--on' : ''}`}
        onClick={onMute}
        aria-pressed={muted}
        aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
      >
        {muted ? <MuteIcon /> : <SpeakerIcon />}
        <span>{muted ? 'Unmute' : 'Mute'}</span>
      </button>

      <button
        type="button"
        className="ghost"
        onClick={onClear}
        disabled={!canClear}
        aria-label="Clear conversation"
      >
        <TrashIcon />
        <span>Clear</span>
      </button>
    </div>
  )
}
