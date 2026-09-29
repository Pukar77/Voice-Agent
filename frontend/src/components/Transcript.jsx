import { useEffect, useRef } from 'react'

import { BotIcon, PersonIcon, SparkIcon } from './icons.jsx'

function Message({ message }) {
  const isUser = message.role === 'user'

  return (
    <article className={`bubble bubble--${isUser ? 'user' : 'agent'}`}>
      <span className={`avatar avatar--${isUser ? 'user' : 'agent'}`}>
        {isUser ? <PersonIcon width={16} height={16} /> : <BotIcon width={16} height={16} />}
      </span>

      <div className="bubble__body">
        <span className="bubble__who">{isUser ? 'You' : 'Agent'}</span>
        <p>{message.text}</p>
      </div>
    </article>
  )
}

function ThinkingRow() {
  return (
    <article className="bubble bubble--agent bubble--thinking">
      <span className="avatar avatar--agent">
        <BotIcon width={16} height={16} />
      </span>

      <div className="bubble__body">
        <span className="bubble__who">Agent</span>
        <div className="dots" aria-label="Thinking">
          <i />
          <i />
          <i />
        </div>
      </div>
    </article>
  )
}

export function Transcript({ messages, partial, status }) {
  const bodyRef = useRef(null)

  useEffect(() => {
    const body = bodyRef.current
    if (body) body.scrollTop = body.scrollHeight
  }, [messages, partial, status])

  const empty = messages.length === 0 && !partial && status !== 'thinking'

  return (
    <section className="card transcript">
      <header className="card__head">
        <h2>Conversation</h2>
        <span className="card__meta">
          {messages.length} {messages.length === 1 ? 'message' : 'messages'}
        </span>
      </header>

      <div className="transcript__body" ref={bodyRef}>
        {empty && (
          <div className="empty">
            <span className="empty__icon">
              <SparkIcon width={26} height={26} />
            </span>
            <p className="empty__title">Ask me anything about Apex Global</p>
            <p className="empty__sub">
              Press the microphone and ask about Apex Global Technologies — or
              type a question below.
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <Message key={index} message={message} />
        ))}

        {status === 'thinking' && <ThinkingRow />}

        {partial && (
          <article className="bubble bubble--user bubble--partial">
            <span className="avatar avatar--user">
              <PersonIcon width={16} height={16} />
            </span>

            <div className="bubble__body">
              <span className="bubble__who">
                You <em className="bubble__live">live</em>
              </span>
              <p>{partial}…</p>
            </div>
          </article>
        )}
      </div>
    </section>
  )
}
