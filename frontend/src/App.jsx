import { useState } from 'react'

import './App.css'
import { Composer } from './components/Composer.jsx'
import { Controls } from './components/Controls.jsx'
import { ErrorToast } from './components/ErrorToast.jsx'
import { StatusPill } from './components/StatusPill.jsx'
import { Transcript } from './components/Transcript.jsx'
import { VoiceOrb } from './components/VoiceOrb.jsx'
import { SparkIcon, WaveIcon } from './components/icons.jsx'
import { useVoiceAgent } from './hooks/useVoiceAgent.js'

const CAPTIONS = {
  idle: ['Tap the microphone to start', 'Or type a question below — both hit the same RAG pipeline.'],
  connecting: ['Waking up the assistant', 'Opening the WebSocket and verifying the audio pipeline…'],
  listening: ["I'm listening — go ahead", 'Speak naturally. Transcription streams in live.'],
  thinking: ['Thinking about your question', 'Retrieving the relevant chunks from the knowledge base.'],
  speaking: ['Answering out loud', "I'll be ready for the next question when I finish."],
}

export default function App() {
  const {
    status,
    partial,
    messages,
    error,
    muted,
    connected,
    toggle,
    toggleMute,
    askText,
    clear,
    clearError,
  } = useVoiceAgent()

  const [typed, setTyped] = useState('')

  const active = status !== 'idle'
  const exchanges = messages.filter((message) => message.role === 'agent').length
  const [caption, hint] = CAPTIONS[status] || CAPTIONS.idle

  const send = (text) => {
    const trimmed = text.trim()
    if (!trimmed) return
    void askText(trimmed)
    setTyped('')
  }

  return (
    <div className="app">
      <div className="glow glow--one" aria-hidden="true" />
      <div className="glow glow--two" aria-hidden="true" />
      <div className="glow glow--three" aria-hidden="true" />

      <header className="header">
        <div className="brand">
          <span className="brand__mark">
            <WaveIcon width={22} height={22} />
          </span>

          <div className="brand__text">
            <h1>Apex Global Technologies</h1>
            <p className="subtitle">Enterprise knowledge assistant · voice-first</p>
          </div>
        </div>

        <div className="header__side">
          <span className="chip">
            <SparkIcon width={14} height={14} />
            {exchanges} {exchanges === 1 ? 'answer' : 'answers'}
          </span>

          <StatusPill status={status} />
        </div>
      </header>

      <ErrorToast message={error} onDismiss={clearError} />

      <main className="main">
        <div className="panel">
          <section className="hero">
            <VoiceOrb status={status} muted={muted && connected} />

            <div className="hero__text">
              <p className="hero__caption">{caption}</p>
              <p className="hero__hint">{hint}</p>
            </div>
          </section>

          <Controls
            status={status}
            muted={muted}
            canClear={messages.length > 0}
            onToggle={toggle}
            onMute={toggleMute}
            onClear={clear}
          />

          <Composer value={typed} onChange={setTyped} onSend={send} />
        </div>

        <Transcript messages={messages} partial={partial} status={status} />
      </main>

      <footer className="footer">
        <span>
          RAG over Qdrant · AssemblyAI · Groq · edge-tts
        </span>
        <span className="footer__dot" aria-hidden="true" />
        <span>{connected ? 'Session live' : 'Session idle'}</span>
      </footer>
    </div>
  )
}
