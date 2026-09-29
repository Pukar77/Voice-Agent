import { SendIcon } from './icons.jsx'

/** Typed fallback — same RAG pipeline, no audio. */
export function Composer({ value, onChange, onSend }) {
  return (
    <form
      className="card composer"
      onSubmit={(event) => {
        event.preventDefault()
        onSend(value)
      }}
    >
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Or type a question…"
        aria-label="Type a question"
      />

      <button type="submit" className="composer__send" disabled={!value.trim()}>
        <SendIcon width={18} height={18} />
        <span>Send</span>
      </button>
    </form>
  )
}
