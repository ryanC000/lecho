import React, { useEffect, useRef } from 'react';

/**
 * LiveWaveform — real-time visual feedback for an active recording.
 *
 * Given a live Web Audio `AnalyserNode`, it draws amplitude bars that react to
 * the microphone signal on every animation frame. Flat/quiet bars mean no
 * sound is reaching the mic; lively bars confirm recording is working.
 */
export default function LiveWaveform({ analyser, active }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    if (!analyser || !active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Time-domain samples give us the raw waveform to measure loudness from.
    const bufferLength = analyser.fftSize;
    const dataArray = new Uint8Array(bufferLength);

    const styles = getComputedStyle(document.documentElement);
    const barColor = styles.getPropertyValue('--color-accent-warm').trim() || '#C75A3A';

    // Keep the canvas crisp on high-DPI screens.
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);

    const BARS = 56;
    const GAP = 3;
    // Smooth each bar toward its target so the waveform glides instead of flickering.
    const levels = new Array(BARS).fill(0);

    const draw = () => {
      rafRef.current = requestAnimationFrame(draw);
      const { width, height } = canvas.getBoundingClientRect();
      analyser.getByteTimeDomainData(dataArray);

      ctx.clearRect(0, 0, width, height);

      const blockSize = Math.floor(bufferLength / BARS);
      const barWidth = (width - GAP * (BARS - 1)) / BARS;
      const mid = height / 2;

      for (let i = 0; i < BARS; i++) {
        // Peak deviation from the 128 midpoint within this block => 0..1 loudness.
        let peak = 0;
        for (let j = 0; j < blockSize; j++) {
          const val = Math.abs(dataArray[i * blockSize + j] - 128) / 128;
          if (val > peak) peak = val;
        }
        // Ease toward the new peak for a fluid motion.
        levels[i] += (peak - levels[i]) * 0.35;

        const barHeight = Math.max(2, levels[i] * height * 0.95);
        const x = i * (barWidth + GAP);
        const y = mid - barHeight / 2;

        ctx.fillStyle = barColor;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
        ctx.fill();
      }
    };
    draw();

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [analyser, active]);

  return (
    <div className="live-waveform-container">
      <canvas ref={canvasRef} className="live-waveform" />
    </div>
  );
}
