/**
 * Plays the agent's reply.
 *
 * edge-tts hands the answer over as a stream of small mp3 fragments. Playing
 * each fragment as its own AudioBuffer loses audio at every join: the
 * fragments are not frame-aligned, so a per-fragment decode drops the
 * partial frame at the cut — which is exactly what makes the reply sound
 * chopped up. (The CLI does not have this problem because ffplay reads the
 * whole answer from one continuous pipe.)
 *
 * So when the browser supports it, every fragment is appended to a single
 * MediaSource, which demuxes them as one uninterrupted mp3 stream — the
 * browser equivalent of that pipe. Browsers without MSE fall back to
 * per-fragment AudioBuffers.
 */

const MP3_MIME = 'audio/mpeg'

// How long after the buffered audio should have run out the reply is declared
// finished anyway. `ended` normally arrives first; this only covers the cases
// where it does not (see #armDrainGuard).
const DRAIN_GRACE = 1.0

// How much `currentTime` has to move between two guard checks to count as
// "still playing", in seconds.
const CLOCK_EPSILON = 0.05

function base64ToArrayBuffer(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)

  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)

  return bytes.buffer
}

function supportsStreaming() {
  return (
    typeof MediaSource !== 'undefined' &&
    MediaSource.isTypeSupported(MP3_MIME)
  )
}

export class Player {
  /**
   * @param {object} options
   * @param {AudioContext} [options.context] only used by the fallback path
   * @param {() => void} [options.onDrained] fired once the reply has finished
   */
  constructor({ context = null, onDrained = null } = {}) {
    this.onDrained = onDrained
    this.streaming = supportsStreaming()

    // Streaming mode
    this.audio = null
    this.mediaSource = null
    this.sourceBuffer = null
    this.mediaUrl = null
    this.pending = []
    this.noMoreComing = false
    this.streamFinished = false
    this.playRequested = false

    // Fallback mode
    this.context = context
    this.tail = 0
    this.inFlight = 0
    this.chain = Promise.resolve()

    this.started = false
    this.drained = true

    // Drain guard (see #armDrainGuard)
    this.drainTimer = null
    this.guardTime = 0
  }

  get playing() {
    return !this.drained
  }

  /** Queue one base64 mp3 fragment. Fragments play in arrival order. */
  push(base64) {
    const bytes = base64ToArrayBuffer(base64)

    this.started = true
    this.drained = false

    // This is a new reply: a guard armed for the previous one no longer
    // describes what is playing.
    this.#clearDrainGuard()

    if (this.streaming) this.#pushFragment(bytes)
    else this.#pushBuffer(bytes)
  }

  /** The server said no more audio is coming: let the tail play out. */
  finish() {
    if (!this.started) return

    if (this.streaming) {
      this.noMoreComing = true
      this.#pump()
    }
    // Fallback mode drains itself when the last scheduled buffer ends.

    // Neither mode may wait forever for a signal the browser might never
    // send: arm the guard instead.
    this.#armDrainGuard()
  }

  /** Stop immediately and release everything, e.g. when the session ends. */
  reset() {
    this.started = false
    this.drained = true
    this.inFlight = 0
    this.tail = 0
    this.chain = Promise.resolve()

    this.#clearDrainGuard()
    this.#teardownStream()
  }

  #teardownStream() {
    this.pending.length = 0
    this.#clearDrainGuard()
    this.noMoreComing = false
    this.streamFinished = false
    this.playRequested = false

    if (this.audio) {
      try {
        this.audio.pause()
        this.audio.removeAttribute('src')
        this.audio.load()
      } catch {
        // teardown, nothing useful to do
      }
      this.audio = null
    }

    if (this.mediaSource && this.mediaSource.readyState === 'open') {
      try {
        this.mediaSource.endOfStream()
      } catch {
        // already ended
      }
    }

    if (this.mediaUrl) {
      URL.revokeObjectURL(this.mediaUrl)
      this.mediaUrl = null
    }

    this.mediaSource = null
    this.sourceBuffer = null
  }

  #drain() {
    if (this.drained) return
    this.drained = true
    this.onDrained?.()
  }

  // ---------------------------------------------------------------
  // Drain guard
  // ---------------------------------------------------------------

  /**
   * Make sure "the reply has finished" is announced even when the browser
   * never fires `ended`.
   *
   * `ended` is the normal signal, but it is not guaranteed: a media element
   * whose play() is still waiting on a gesture, or a SourceBuffer that stops
   * firing `updateend`, leaves the element looking like it is playing
   * forever. The session would then stay in "speaking" and never unmute the
   * microphone again, so the guard waits out the audio that is *still
   * buffered* and then declares the reply over by itself.
   */
  #armDrainGuard() {
    this.#clearDrainGuard()

    const { audio } = this
    // An element that has not started yet may not report a clock at all; treat
    // that as "the guard cannot tell" and let it declare the reply over.
    this.guardTime = audio ? Number(audio.currentTime) || 0 : 0

    const seconds = this.#remainingSeconds() + DRAIN_GRACE

    this.drainTimer = setTimeout(() => this.#checkDrained(), seconds * 1000)
  }

  #clearDrainGuard() {
    if (this.drainTimer !== null) {
      clearTimeout(this.drainTimer)
      this.drainTimer = null
    }
  }

  #checkDrained() {
    this.drainTimer = null

    if (this.drained) return

    const { audio } = this
    const playing = Boolean(audio) && !audio.paused && !audio.ended
    const advanced = Boolean(audio) && Number(audio.currentTime) > this.guardTime + CLOCK_EPSILON

    // Genuinely still playing - it may simply have started late - so give it
    // the time this round of audio still needs.
    if (this.streaming ? playing && advanced : this.inFlight > 0) {
      this.#armDrainGuard()
      return
    }

    // Nothing is coming out of the speakers any more.
    this.#teardownStream()
    this.#drain()
  }

  /** Seconds of audio that have been buffered but not played yet. */
  #remainingSeconds() {
    if (!this.streaming) {
      // Fallback mode schedules decoded buffers on the audio clock.
      if (!this.context) return 0
      return Math.max(0, this.tail - this.context.currentTime)
    }

    const { audio } = this
    if (!audio || !audio.buffered) return 0

    const { currentTime, buffered } = audio

    for (let i = 0; i < buffered.length; i += 1) {
      if (currentTime >= buffered.start(i) && currentTime <= buffered.end(i)) {
        return Math.max(0, buffered.end(i) - currentTime)
      }
    }

    return 0
  }

  // ---------------------------------------------------------------
  // Streaming mode (MediaSource)
  // ---------------------------------------------------------------

  #pushFragment(bytes) {
    // A previous reply may already have closed this stream; the next reply
    // needs a fresh one rather than an append that throws InvalidStateError.
    if (this.streamFinished) this.#teardownStream()

    if (!this.audio) this.#createStream()

    this.pending.push(bytes)
    this.#pump()
  }

  #createStream() {
    const mediaSource = new MediaSource()
    const mediaUrl = URL.createObjectURL(mediaSource)
    const audio = new Audio()

    audio.preload = 'auto'
    audio.src = mediaUrl

    mediaSource.addEventListener('sourceopen', () => {
      let buffer

      try {
        buffer = mediaSource.addSourceBuffer(MP3_MIME)
      } catch (error) {
        console.error('MediaSource rejected mp3:', error)
        return
      }

      // Append order is playback order: mp3 fragments carry no timestamps.
      buffer.mode = 'sequence'
      buffer.addEventListener('updateend', () => this.#pump())

      this.sourceBuffer = buffer
      this.#requestPlay()
      this.#pump()
    })

    audio.addEventListener('ended', () => this.#drain())
    audio.addEventListener('error', () => {
      console.error('Audio playback failed:', audio.error)
      this.#drain()
    })

    this.mediaSource = mediaSource
    this.mediaUrl = mediaUrl
    this.audio = audio
  }

  #requestPlay() {
    if (this.playRequested || !this.audio) return
    this.playRequested = true

    this.audio.play().catch(() => {
      // Autoplay blocked. The session started with a click, so this is
      // usually a browser that insists on a gesture for the element itself:
      // retry on the next one.
      this.playRequested = false

      const retry = () => {
        document.removeEventListener('pointerdown', retry)
        this.audio?.play().catch(() => {})
      }

      document.addEventListener('pointerdown', retry)
    })
  }

  #pump() {
    const { sourceBuffer, mediaSource } = this

    if (!sourceBuffer || sourceBuffer.updating) return
    if (!mediaSource || mediaSource.readyState !== 'open') return

    if (this.pending.length > 0) {
      try {
        sourceBuffer.appendBuffer(this.pending.shift())
      } catch (error) {
        console.error('appendBuffer failed:', error)
        this.#drain()
      }
      return
    }

    if (this.noMoreComing && !this.streamFinished) {
      this.streamFinished = true

      try {
        mediaSource.endOfStream()
      } catch (error) {
        console.warn('endOfStream failed:', error)
      }
    }
  }

  // ---------------------------------------------------------------
  // Fallback mode (per-fragment AudioBuffer)
  // ---------------------------------------------------------------

  #pushBuffer(bytes) {
    if (!this.context) {
      console.error('No AudioContext for fallback playback')
      return
    }

    this.inFlight += 1

    this.chain = this.chain
      .then(() => this.context.decodeAudioData(bytes))
      .then((buffer) => this.#schedule(buffer))
      .catch((error) => {
        this.inFlight -= 1
        console.error('Audio playback failed:', error)

        if (this.inFlight <= 0) this.#drain()
      })
  }

  #schedule(buffer) {
    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.connect(this.context.destination)

    const start = Math.max(this.context.currentTime, this.tail)
    source.start(start)
    this.tail = start + buffer.duration

    source.onended = () => {
      this.inFlight -= 1
      this.tail = 0

      if (this.inFlight <= 0) this.#drain()
    }
  }
}
