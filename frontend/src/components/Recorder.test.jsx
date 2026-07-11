import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Recorder from './Recorder';
import { blobToWav } from '../utils/audio';

// The recorder's real work happens in browser audio APIs jsdom doesn't have —
// mock the seams (getUserMedia/MediaRecorder/AudioContext/blobToWav) and test
// the component's own behaviour: the ±20% duration gate and upload handoff.
vi.mock('../utils/audio', () => ({ blobToWav: vi.fn() }));
vi.mock('./LiveWaveform', () => ({ default: () => null }));

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
  }
  createAnalyser() {
    return { fftSize: 0, getByteTimeDomainData: vi.fn() };
  }
  createMediaStreamSource() {
    return { connect: vi.fn() };
  }
  close() {
    this.state = 'closed';
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  const stream = { getTracks: () => [{ stop: vi.fn() }] };
  Object.defineProperty(global.navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    configurable: true,
  });
  global.MediaRecorder = FakeMediaRecorder;
  global.AudioContext = FakeAudioContext;
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

  it('hands an in-gate take to onUpload with its duration', async () => {
    blobToWav.mockResolvedValue({ blob: new Blob(), duration: 5.2 });
    const onUpload = vi.fn();
    render(<Recorder nativeDuration={5} onUpload={onUpload} />);

    await recordOnce();

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onUpload).toHaveBeenCalledWith(expect.anything(), 5.2);
    expect(screen.queryByText(/must be within ±20%/)).not.toBeInTheDocument();
  });

  it('surfaces a denied microphone', async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValue(new Error('denied'));
    render(<Recorder nativeDuration={5} onUpload={vi.fn()} />);

    fireEvent.click(screen.getByText('Start Recording'));

    expect(await screen.findByText(/Microphone access denied/)).toBeInTheDocument();
  });
});
