import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import TranscriptKaraoke from './TranscriptKaraoke';

// The component is a pure function of (transcript, words, currentTime, isPlaying) —
// any playback source can drive it, so these tests just feed it a clock.
const TRANSCRIPT = 'Bonjour, tout le monde';
const WORDS = [
  { start: 0.0, end: 0.5 },
  { start: 0.6, end: 1.0 },
  { start: 1.0, end: 1.2 },
  { start: 1.2, end: 1.8 },
];

const active = (container) => container.querySelector('.karaoke-word.active')?.textContent.trim();

describe('TranscriptKaraoke', () => {
  it('highlights the word whose span contains the current time', () => {
    const { container } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={WORDS} currentTime={0.7} isPlaying />
    );
    expect(active(container)).toBe('tout');
  });

  it('follows the clock forward', () => {
    const { container, rerender } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={WORDS} currentTime={0.1} isPlaying />
    );
    expect(active(container)).toBe('Bonjour,');

    rerender(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={WORDS} currentTime={1.5} isPlaying />
    );
    expect(active(container)).toBe('monde');
  });

  it('highlights nothing while paused', () => {
    const { container } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={WORDS} currentTime={0.7} isPlaying={false} />
    );
    expect(active(container)).toBeUndefined();
    expect(container.textContent).toContain('tout');
  });

  it('highlights nothing in the gap between words', () => {
    const { container } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={WORDS} currentTime={0.55} isPlaying />
    );
    expect(active(container)).toBeUndefined();
  });

  it('renders nothing when the practice has no alignment', () => {
    const { container } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={undefined} currentTime={0.7} isPlaying />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for an empty alignment', () => {
    const { container } = render(
      <TranscriptKaraoke transcript={TRANSCRIPT} words={[]} currentTime={0.7} isPlaying />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
