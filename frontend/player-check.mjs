// Throwaway check for Player: run with  node .player-check.mjs
// Stubs the browser APIs (MediaSource / Audio / URL) so the streaming
// state machine can be exercised headlessly.

let objectUrlCount = 0

class FakeEventTarget {
  constructor() {
    this.listeners = {}
  }
  addEventListener(type, fn) {
    ;(this.listeners[type] ||= []).push(fn)
  }
  dispatch(type, event = {}) {
    for (const fn of this.listeners[type] || []) fn(event)
  }
}

class FakeSourceBuffer extends FakeEventTarget {
  constructor() {
    super()
    this.updating = false
    this.mode = 'segments'
    this.appended = []
  }
  appendBuffer(bytes) {
    if (this.updating) throw new Error('InvalidStateError: updating')
    if (this.closed) throw new Error('InvalidStateError: stream ended')
    this.appended.push(bytes)
    this.updating = true
    queueMicrotask(() => {
      this.updating = false
      this.dispatch('updateend')
    })
  }
}

class FakeMediaSource extends FakeEventTarget {
  static supported = true
  static isTypeSupported(mime) {
    return FakeMediaSource.supported && mime === 'audio/mpeg'
  }
  constructor() {
    super()
    this.readyState = 'closed'
    this.ended = false
    this.buffers = []
    this.mediaSource = this
    const url = `blob:fake-${objectUrlCount++}`
    urls.set(url, this)
    queueMicrotask(() => {
      this.readyState = 'open'
      this.dispatch('sourceopen')
    })
  }
  addSourceBuffer(mime) {
    if (this.ended) throw new Error('InvalidStateError: ended')
    const buffer = new FakeSourceBuffer()
    this.buffers.push(buffer)
    this.lastBuffer = buffer
    return buffer
  }
  endOfStream() {
    if (this.ended) throw new Error('InvalidStateError: already ended')
    this.ended = true
  }
}

class FakeAudio extends FakeEventTarget {
  constructor() {
    super()
    this.paused = true
    this.src = ''
    this.playCalls = 0
  }
  play() {
    this.playCalls += 1
    this.paused = false
    return Promise.resolve()
  }
  pause() {
    this.paused = true
  }
  removeAttribute(name) {
    if (name === 'src') this.src = ''
  }
  load() {}
}

const urls = new Map()

globalThis.MediaSource = FakeMediaSource
globalThis.Audio = FakeAudio
globalThis.URL.createObjectURL = (ms) => {
  for (const [url, target] of urls) if (target === ms) return url
  return 'blob:unknown'
}
globalThis.URL.revokeObjectURL = () => {}

const { Player } = await import('./src/audio/player.js')

const b64 = (n) => Buffer.from(Array.from({ length: n }, (_, i) => i)).toString('base64')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const check = (name, cond) => {
  results.push([name, cond])
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`)
}

// ---- reply 1 ----------------------------------------------------------
let drained = false
const player = new Player({ onDrained: () => (drained = true) })
check('chooses streaming mode', player.streaming === true)

player.push(b64(10))
player.push(b64(11))
player.push(b64(12))
await sleep(5)

check('audio element created', player.audio instanceof FakeAudio)
check('play() requested', player.audio.playCalls >= 1)

const source1 = player.mediaSource
const audio1 = player.audio
check('all 3 fragments appended', source1.lastBuffer.appended.length === 3)

player.finish()
await sleep(5)
check('endOfStream called after last append', source1.ended === true)
check('not drained until the element ends', drained === false)

player.audio.dispatch('ended')
check('drained fires on ended', drained === true)

// ---- reply 2 on the same session --------------------------------------
const sourceCountBefore = objectUrlCount
player.push(b64(20))
await sleep(5)

check('new MediaSource for the next reply', objectUrlCount > sourceCountBefore)
check(
  'second reply appended to the NEW stream',
  player.mediaSource !== source1 && player.mediaSource.lastBuffer.appended.length === 1
)
check('old audio element released, not reused', player.audio !== audio1)

player.finish()
await sleep(5)
check('second stream ends too', player.mediaSource.ended === true)

// ---- teardown ---------------------------------------------------------
const audio = player.audio
player.reset()
check('audio paused on reset', audio.paused === true)
check('reset marks drained', player.drained === true)

// ---- fallback mode ----------------------------------------------------
FakeMediaSource.supported = false
let fallbackDrained = false
const ctx = {
  decodeAudioData: async (buf) => ({ duration: 0.1, buf }),
  createBufferSource() {
    return {
      buffer: null,
      connect() {},
      start() {},
      set onended(fn) {
        setTimeout(fn, 1)
      },
    }
  },
  currentTime: 0,
  destination: {},
}
const fallback = new Player({ context: ctx, onDrained: () => (fallbackDrained = true) })
check('falls back when MSE unsupported', fallback.streaming === false)
fallback.push(b64(5))
fallback.push(b64(6))
await sleep(30)
check('fallback drains after playback', fallbackDrained === true)

// ---- summary ----------------------------------------------------------
const failed = results.filter(([, ok]) => !ok)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
