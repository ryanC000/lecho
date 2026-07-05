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
