import { describe, it, expect } from 'vitest';
import { render, act } from '@testing-library/react';
import WavesurferKaraoke from './WavesurferKaraoke';

// Solo listening drives the karaoke off wavesurfer. These pin that path so the
// decoupled TranscriptKaraoke can't silently regress it.
const TRANSCRIPT = 'Bonjour tout le monde';
const WORDS = [
  { start: 0.0, end: 0.5 },
  { start: 0.6, end: 1.0 },
  { start: 1.0, end: 1.4 },
  { start: 1.4, end: 1.8 },
];

// Minimal stand-in for wavesurfer's emitter: .on() registers and returns its
// own unsubscribe fn, exactly as v7 does.
function fakeWavesurfer() {
  const handlers = {};
  return {
    currentTime: 0,
    getCurrentTime() {
      return this.currentTime;
    },
    on(event, fn) {
      (handlers[event] ??= []).push(fn);
      return () => {
        handlers[event] = handlers[event].filter((h) => h !== fn);
      };
    },
    emit(event) {
      (handlers[event] ?? []).forEach((h) => h());
    },
    handlerCount() {
      return Object.values(handlers).reduce((n, hs) => n + hs.length, 0);
    },
  };
}

const active = (container) => container.querySelector('.karaoke-word.active')?.textContent.trim();

describe('WavesurferKaraoke', () => {
  it('highlights the word the native player has reached', () => {
    const ws = fakeWavesurfer();
    const { container } = render(
      <WavesurferKaraoke transcript={TRANSCRIPT} words={WORDS} wavesurfer={ws} />
    );

    act(() => {
      ws.emit('play');
      ws.currentTime = 0.7;
      ws.emit('audioprocess');
    });
    expect(active(container)).toBe('tout');

    act(() => {
      ws.currentTime = 1.5;
      ws.emit('timeupdate');
    });
    expect(active(container)).toBe('monde');
  });

  it('stops highlighting on pause and on finish', () => {
    const ws = fakeWavesurfer();
    const { container } = render(
      <WavesurferKaraoke transcript={TRANSCRIPT} words={WORDS} wavesurfer={ws} />
    );

    act(() => {
      ws.emit('play');
      ws.currentTime = 0.7;
      ws.emit('audioprocess');
    });
    expect(active(container)).toBe('tout');

    act(() => ws.emit('pause'));
    expect(active(container)).toBeUndefined();

    act(() => {
      ws.emit('play');
      ws.emit('audioprocess');
    });
    expect(active(container)).toBe('tout');

    act(() => ws.emit('finish'));
    expect(active(container)).toBeUndefined();
  });

  it('highlights nothing before playback starts', () => {
    const ws = fakeWavesurfer();
    const { container } = render(
      <WavesurferKaraoke transcript={TRANSCRIPT} words={WORDS} wavesurfer={ws} />
    );

    act(() => {
      ws.currentTime = 0.7;
      ws.emit('audioprocess');
    });
    expect(active(container)).toBeUndefined();
  });

  it('renders nothing when the practice has no alignment', () => {
    const { container } = render(
      <WavesurferKaraoke transcript={TRANSCRIPT} words={undefined} wavesurfer={fakeWavesurfer()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('tolerates the player not being ready yet', () => {
    expect(() =>
      render(<WavesurferKaraoke transcript={TRANSCRIPT} words={WORDS} wavesurfer={null} />)
    ).not.toThrow();
  });

  it('unsubscribes from the player on unmount', () => {
    const ws = fakeWavesurfer();
    const { unmount } = render(
      <WavesurferKaraoke transcript={TRANSCRIPT} words={WORDS} wavesurfer={ws} />
    );
    expect(ws.handlerCount()).toBeGreaterThan(0);

    unmount();

    expect(ws.handlerCount()).toBe(0);
  });
});
