import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Recorder from './Recorder';
import { blobToWav } from '../utils/audio';

// The recorder's real work happens in browser audio APIs jsdom doesn't have —
// mock the seams (getUserMedia/MediaRecorder/AudioContext/blobToWav) and test
// the component's own behaviour: the per-mode duration gates, the headphones
// modal, and the upload handoff.
vi.mock('../utils/audio', () => ({ blobToWav: vi.fn() }));
vi.mock('./LiveWaveform', () => ({ default: () => null }));

const NATIVE_DECODED_DURATION = 5;

class FakeMediaRecorder {
  constructor() {
    this.mimeType = 'audio/webm';
  }
  start() {}
  stop() {
    this.onstop?.();
  }
}

class FakeAudioContext {
  constructor() {
    this.state = 'running';
    this.currentTime = 0;
    this.destination = {};
  }
  createAnalyser() {
    return { fftSize: 0, getByteTimeDomainData: vi.fn() };
  }
  createMediaStreamSource() {
    return { connect: vi.fn() };
  }
  createBufferSource() {
    return { buffer: null, connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
  }
  decodeAudioData() {
    return Promise.resolve({ duration: NATIVE_DECODED_DURATION });
  }
  close() {
    this.state = 'closed';
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  const stream = { getTracks: () => [{ stop: vi.fn() }] };
  Object.defineProperty(global.navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    configurable: true,
  });
  global.MediaRecorder = FakeMediaRecorder;
  global.AudioContext = FakeAudioContext;
  global.fetch = vi.fn().mockResolvedValue({ arrayBuffer: async () => new ArrayBuffer(8) });
});

async function recordOnce() {
  fireEvent.click(screen.getByText('Start Recording'));
  const stopButton = await screen.findByText('Stop Recording');
  fireEvent.click(stopButton);
}

describe('Recorder', () => {
  it('renders the start control', () => {
    render(<Recorder nativeDuration={5} onUpload={vi.fn()} />);
    expect(screen.getByText('Start Recording')).toBeInTheDocument();
  });

  it('rejects a take outside ±20% of the native duration and does not upload', async () => {
    blobToWav.mockResolvedValue({ blob: new Blob(), duration: 8.0 });
    const onUpload = vi.fn();
    render(<Recorder nativeDuration={5} onUpload={onUpload} />);

    await recordOnce();

    expect(await screen.findByText(/must be within ±20%/)).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('hands an in-gate take to onUpload with its duration and mode', async () => {
    blobToWav.mockResolvedValue({ blob: new Blob(), duration: 5.2 });
    const onUpload = vi.fn();
    render(<Recorder nativeDuration={5} onUpload={onUpload} />);

    await recordOnce();

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onUpload).toHaveBeenCalledWith(expect.anything(), 5.2, 'solo');
    expect(screen.queryByText(/must be within ±20%/)).not.toBeInTheDocument();
  });

  it('surfaces a denied microphone', async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValue(new Error('denied'));
    render(<Recorder nativeDuration={5} onUpload={vi.fn()} />);

    fireEvent.click(screen.getByText('Start Recording'));

    expect(await screen.findByText(/Microphone access denied/)).toBeInTheDocument();
  });
});

describe('Recorder in shadow mode', () => {
  const renderShadow = (onUpload = vi.fn()) =>
    render(
      <Recorder
        nativeDuration={5}
        nativeAudioUrl="http://localhost:8000/practices/1/audio"
        mode="shadow"
        onUpload={onUpload}
      />
    );

  it('asks for headphones confirmation before the first shadow take, then remembers it', async () => {
    renderShadow();

    fireEvent.click(screen.getByText('Start Recording'));
    expect(await screen.findByText(/use headphones/)).toBeInTheDocument();
    // Nothing records (and nothing plays) until the user confirms.
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText(/wearing headphones/));
    expect(await screen.findByText('Stop Recording')).toBeInTheDocument();
    expect(sessionStorage.getItem('lecho_headphones_ok')).toBeTruthy();
  });

  it('skips the modal once headphones were confirmed this session', async () => {
    sessionStorage.setItem('lecho_headphones_ok', '1');
    renderShadow();

    fireEvent.click(screen.getByText('Start Recording'));

    expect(await screen.findByText('Stop Recording')).toBeInTheDocument();
    expect(screen.queryByText(/use headphones/)).not.toBeInTheDocument();
  });

  it('rejects a shadow take outside native + 1s ± 0.5s and does not upload', async () => {
    sessionStorage.setItem('lecho_headphones_ok', '1');
    blobToWav.mockResolvedValue({ blob: new Blob(), duration: 5.0 }); // expected ~6.0
    const onUpload = vi.fn();
    renderShadow(onUpload);

    await recordOnce();

    expect(await screen.findByText(/Shadow recording/)).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('hands an in-gate shadow take to onUpload tagged with shadow mode', async () => {
    sessionStorage.setItem('lecho_headphones_ok', '1');
    blobToWav.mockResolvedValue({ blob: new Blob(), duration: 6.1 });
    const onUpload = vi.fn();
    renderShadow(onUpload);

    await recordOnce();

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onUpload).toHaveBeenCalledWith(expect.anything(), 6.1, 'shadow');
  });
});
