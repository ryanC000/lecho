/**
 * Generates a mock audio blob so wavesurfer has something to draw.
 * Creates a real WAV buffer with low-level random noise
 * (the old version tried to fetch from an OfflineAudioContext which broke).
 */
export function generateMockAudioBlob(durationSeconds = 5) {
  const sampleRate = 44100;
  const numChannels = 1;
  const bitsPerSample = 16;
  const numSamples = Math.floor(sampleRate * durationSeconds);
  const dataSize = numSamples * numChannels * (bitsPerSample / 8);

  // Build a proper WAV file in an ArrayBuffer
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  // — RIFF header —
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, 'WAVE');

  // — fmt sub-chunk —
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);               // sub-chunk size
  view.setUint16(20, 1, true);                 // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true);
  view.setUint16(32, numChannels * (bitsPerSample / 8), true);
  view.setUint16(34, bitsPerSample, true);

  // — data sub-chunk —
  writeString(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  // Fill with low-level noise so the waveform isn't a flat line
  for (let i = 0; i < numSamples; i++) {
    // Generate gentle waveform: mix of sine + noise
    const t = i / sampleRate;
    const sine = Math.sin(2 * Math.PI * 220 * t) * 0.15;           // soft tone
    const noise = (Math.random() * 2 - 1) * 0.05;                  // quiet noise
    const envelope = Math.sin(Math.PI * (i / numSamples)) * 0.8;    // fade in/out
    const sample = Math.max(-1, Math.min(1, (sine + noise) * envelope));
    view.setInt16(44 + i * 2, sample * 0x7FFF, true);
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

/**
 * MediaRecorder does NOT produce WAV — Chrome gives WebM/Opus, Firefox Ogg,
 * Safari mp4 — regardless of the Blob's `type` label. Our backend (and the
 * future Parselmouth/Librosa worker) expects real PCM WAV, so we decode the
 * recorded blob and re-encode it to 16-bit mono PCM WAV here, on the client.
 *
 * Returns { blob, duration } where duration is the precise decoded length.
 */
export async function blobToWav(recordedBlob) {
  const arrayBuffer = await recordedBlob.arrayBuffer();
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const audioCtx = new AudioCtx();
  try {
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    const wavBlob = encodeWav(audioBuffer);
    return { blob: wavBlob, duration: audioBuffer.duration };
  } finally {
    audioCtx.close();
  }
}

/** Encode an AudioBuffer to a 16-bit mono PCM WAV Blob (downmixing channels). */
function encodeWav(audioBuffer) {
  const sampleRate = audioBuffer.sampleRate;
  const numChannels = audioBuffer.numberOfChannels;
  const numSamples = audioBuffer.length;

  // Downmix to mono by averaging channels — prosody analysis is single-voice.
  const mono = new Float32Array(numSamples);
  for (let ch = 0; ch < numChannels; ch++) {
    const data = audioBuffer.getChannelData(ch);
    for (let i = 0; i < numSamples; i++) mono[i] += data[i] / numChannels;
  }

  const bitsPerSample = 16;
  const dataSize = numSamples * (bitsPerSample / 8);
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);            // PCM
  view.setUint16(22, 1, true);            // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * (bitsPerSample / 8), true);
  view.setUint16(32, bitsPerSample / 8, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}
