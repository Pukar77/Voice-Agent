const LABELS = {
  idle: 'Ready',
  connecting: 'Connecting…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
}

export function StatusPill({ status }) {
  return (
    <span className={`pill pill--${status}`}>
      <span className="pill__dot" />
      {LABELS[status] || status}
    </span>
  )
}
