import { useCallback, useEffect, useRef, useState } from 'react'

import { startCapture } from '../audio/capture.js'
import { Player } from '../audio/player.js'

function voiceSocketUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/voice`
}

const IDLE = 'idle'

/**
 * Drives one voice session.
 *
 *   idle -> connecting -> listening <-> thinking -> speaking -> listening
 *
 * `status` reflects the server's idea of the state, except that it stays on
 * "speaking" until the *browser* has finished playing the reply: the server
 * is done the moment the last audio chunk leaves it.
 */
export function useVoiceAgent() {
  const [status, setStatus] = useState(IDLE)
  const [partial, setPartial] = useState('')
  const [messages, setMessages] = useState([])
  const [error, setError] = useState(null)
  const [muted, setMuted] = useState(false)
  const [playing, setPlaying] = useState(false)

  const socketRef = useRef(null)
  const captureRef = useRef(null)
  const playerRef = useRef(null)
  const playbackContextRef = useRef(null)

  const statusRef = useRef(IDLE)
  const mutedRef = useRef(false)
  const startingRef = useRef(false)
  const playingRef = useRef(false)

  // `playing` drives the UI; `playingRef` is the same flag for the capture
  // callback, which runs outside React's render cycle.
  const setPlayingState = useCallback((value) => {
    playingRef.current = value
    setPlaying(value)
  }, [])

  const applyServerState = useCallback((value) => {
    statusRef.current = value
    setStatus(value)
  }, [])

  // ---------------------------------------------------------------
  // Incoming messages
  // ---------------------------------------------------------------

  const handleMessage = useCallback(
    (message) => {
      switch (message.type) {
        case 'state':
          applyServerState(message.value)

          // Older backends announce the end of a reply with "listening"
          // instead of a dedicated audio_end; both are idempotent.
          if (message.value === 'listening') playerRef.current?.finish()
          break

        case 'ready':
          setError(null)
          break

        case 'partial':
          setPartial(message.text)
          break

        case 'final':
          setPartial('')
          setMessages((prev) => [...prev, { role: 'user', text: message.text }])
          break

        case 'answer':
          setMessages((prev) => [
            ...prev,
            { role: 'agent', text: message.text },
          ])
          break

        case 'audio':
          setPlayingState(true)
          playerRef.current?.push(message.data)
          break

        // The server has finished synthesising. Ordering on the socket is
        // guaranteed, so every audio chunk for this reply has arrived.
        case 'audio_end':
          playerRef.current?.finish()
          break

        case 'error':
          setError(message.message)
          break

        default:
          break
      }
    },
    [applyServerState, setPlayingState]
  )

  // ---------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------

  const stop = useCallback(async () => {
    const socket = socketRef.current
    socketRef.current = null

    if (socket) {
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'stop' }))
        }
        socket.close()
      } catch {
        // already gone
      }
    }

    const capture = captureRef.current
    captureRef.current = null
    if (capture) await capture.stop()

    // Stop any reply still playing: MediaSource playback is independent of
    // the AudioContext, so it has to be torn down explicitly.
    const player = playerRef.current
    playerRef.current = null
    if (player) player.reset()

    const playback = playbackContextRef.current
    playbackContextRef.current = null
    if (playback && playback.state !== 'closed') await playback.close()

    setPlayingState(false)
    setPartial('')
    applyServerState(IDLE)
  }, [applyServerState, setPlayingState])

  const start = useCallback(async () => {
    if (startingRef.current || socketRef.current) return
    startingRef.current = true
    setError(null)

    try {
      // Mic permission first: no point opening a session we cannot feed.
      // The capture context doubles as the playback context, so the reply
      // plays out of the same clock and closing the mic also stops it.
      const capture = await startCapture((frame) => {
        const socket = socketRef.current

        // Frames only flow while the agent is actually listening, never
        // while the user has muted, and never while the reply is still
        // playing: with speakers on, the mic would otherwise hear the agent
        // answer itself. The server applies the same rule, so this is the
        // real guard rather than a bandwidth optimisation.
        if (
          !mutedRef.current &&
          !playingRef.current &&
          statusRef.current === 'listening' &&
          socket &&
          socket.readyState === WebSocket.OPEN
        ) {
          socket.send(frame)
        }
      })

      playbackContextRef.current = capture.context
      captureRef.current = capture

      const player = new Player({
        context: capture.context,
        onDrained: () => setPlayingState(false),
      })
      playerRef.current = player

      const socket = new WebSocket(voiceSocketUrl())
      socket.binaryType = 'arraybuffer'
      socketRef.current = socket

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: 'start' }))
      }

      socket.onmessage = (event) => {
        try {
          handleMessage(JSON.parse(event.data))
        } catch (parseError) {
          setError(`Bad message from server: ${parseError.message}`)
        }
      }

      socket.onerror = () => {
        setError('The voice connection failed. Is the backend running on :8000?')
      }

      socket.onclose = () => {
        if (socketRef.current === socket) {
          socketRef.current = null
          applyServerState(IDLE)
        }
      }
    } catch (caught) {
      const denied =
        caught instanceof DOMException &&
        (caught.name === 'NotAllowedError' ||
          caught.name === 'PermissionDeniedError')

      setError(
        denied
          ? 'Microphone permission was denied. Allow the mic and try again.'
          : `Could not start the microphone: ${caught.message}`
      )

      await stop()
    } finally {
      startingRef.current = false
    }
  }, [applyServerState, handleMessage, setPlayingState, stop])

  const toggle = useCallback(() => {
    if (socketRef.current) void stop()
    else void start()
  }, [start, stop])

  const toggleMute = useCallback(() => {
    mutedRef.current = !mutedRef.current
    setMuted(mutedRef.current)
  }, [])

  /** Text fallback: same RAG pipeline, no audio. */
  const askText = useCallback(async (text) => {
    const question = text.trim()
    if (!question) return

    setError(null)

    try {
      const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()

      setMessages((prev) => [
        ...prev,
        { role: 'user', text: question },
        { role: 'agent', text: data.answer },
      ])
    } catch (caught) {
      setError(`Could not reach the assistant: ${caught.message}`)
    }
  }, [])

  useEffect(() => () => void stop(), [stop])

  return {
    status: playing ? 'speaking' : status,
    serverStatus: status,
    partial,
    messages,
    error,
    muted,
    connected: status !== IDLE,
    start,
    stop,
    toggle,
    toggleMute,
    askText,
    clear: () => {
      setMessages([])
      setPartial('')
    },
    clearError: () => setError(null),
  }
}
