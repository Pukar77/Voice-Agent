/**
 * AudioWorklet: microphone -> mono Float32 -> 16 kHz Int16 frames.
 *
 * Runs on the audio thread, so the UI never stutters. Everything AssemblyAI
 * needs (a fixed 16 kHz mono PCM16 stream) is produced here:
 *
 *   - channels are mixed down to mono
 *   - sample-rate conversion by linear interpolation (48 kHz -> 16 kHz is an
 *     exact 1/3 decimation; 44.1 kHz is not, so it interpolates)
 *   - Float32 [-1, 1] -> Int16 little-endian
 *   - frames are batched to ~64 ms before posting, to keep message traffic
 *     sane (one `process()` call is only 128 samples ≈ 2.7 ms)
 */

const TARGET_RATE = 16000
const FLUSH_SAMPLES = 1024 // post once we hold ~64 ms of 16 kHz audio

class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()

    this.step = sampleRate / TARGET_RATE // input samples per output sample
    this.pos = 0 // fractional read position inside this.buf
    this.buf = new Float32Array(0)

    this.out = [] // Int16Array chunks waiting to be posted
    this.outCount = 0

    this.port.onmessage = (event) => {
      if (event.data === 'flush') this.flush()
    }
  }

  append(chunk) {
    const merged = new Float32Array(this.buf.length + chunk.length)
    merged.set(this.buf, 0)
    merged.set(chunk, this.buf.length)
    this.buf = merged
  }

  toMono(input) {
    const channels = input.filter(Boolean)

    if (channels.length === 0) return null
    if (channels.length === 1) return channels[0]

    const mono = new Float32Array(channels[0].length)

    for (const channel of channels) {
      for (let i = 0; i < mono.length; i += 1) mono[i] += channel[i]
    }

    for (let i = 0; i < mono.length; i += 1) mono[i] /= channels.length

    return mono
  }

  process(inputs) {
    const mono = this.toMono(inputs[0] || [])
    if (!mono) return true

    this.append(mono)
    this.resample()

    return true
  }

  resample() {
    const { buf, step } = this
    const produced = []

    while (this.pos + 1 < buf.length) {
      const index = Math.floor(this.pos)
      const frac = this.pos - index
      const sample = buf[index] * (1 - frac) + buf[index + 1] * frac
      const clipped = Math.max(-1, Math.min(1, sample))

      produced.push(
        clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff
      )

      this.pos += step
    }

    if (produced.length === 0) return

    const chunk = Int16Array.from(produced)
    this.out.push(chunk)
    this.outCount += chunk.length

    // Drop the input we have already consumed; one sample must stay as the
    // interpolation partner for the next fractional position.
    const drop = Math.floor(this.pos)
    if (drop > 0) {
      this.buf = this.buf.subarray(drop)
      this.pos -= drop
    }

    if (this.outCount >= FLUSH_SAMPLES) this.flush()
  }

  flush() {
    if (this.outCount === 0) return

    const merged = new Int16Array(this.outCount)
    let offset = 0

    for (const chunk of this.out) {
      merged.set(chunk, offset)
      offset += chunk.length
    }

    this.out = []
    this.outCount = 0

    this.port.postMessage(merged.buffer, [merged.buffer])
  }
}

registerProcessor('pcm-capture', PCMCaptureProcessor)
