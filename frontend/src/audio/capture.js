/**
 * Microphone capture: getUserMedia -> AudioWorklet -> 16 kHz PCM16 frames.
 *
 * The returned `stop()` drains any batched audio, silences the mic and
 * closes the audio context.
 */

const WORKLET_URL = '/worklets/capture.js'

export async function startCapture(onFrame) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  })

  const context = new AudioContext()

  try {
    await context.audioWorklet.addModule(WORKLET_URL)
  } catch (error) {
    stream.getTracks().forEach((track) => track.stop())
    await context.close()
    throw error
  }

  if (context.state === 'suspended') await context.resume()

  const source = context.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(context, 'pcm-capture')

  node.port.onmessage = (event) => onFrame(event.data)

  // Deliberately not connected to the destination: that would play the
  // microphone back through the speakers.
  source.connect(node)

  let stopped = false

  return {
    context,
    stream,
    node,

    async stop() {
      if (stopped) return
      stopped = true

      node.port.postMessage('flush')
      source.disconnect()
      node.disconnect()

      stream.getTracks().forEach((track) => track.stop())
      await context.close()
    },
  }
}
