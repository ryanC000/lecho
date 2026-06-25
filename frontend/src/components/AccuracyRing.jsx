import React, { useEffect, useState } from 'react';

/**
 * Animated SVG circular progress ring.
 * Colour-coded with generous thresholds:
 *   ≥75% → green   (--green-accent)
 *   50–74% → amber
 *   <50% → warm red
 */
export default function AccuracyRing({ score = 0, size = 180, strokeWidth = 12 }) {
  const [animatedScore, setAnimatedScore] = useState(0);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (animatedScore / 100) * circumference;
  const center = size / 2;

  // Determine colour based on generous thresholds
  let ringColor = 'var(--color-accent-warm)'; // warm red < 50
  let label = 'Keep Practicing!';
  if (score >= 75) {
    ringColor = 'var(--color-accent-sage)';
    label = 'Excellent!';
  } else if (score >= 50) {
    ringColor = 'var(--color-accent-amber)';
    label = 'Great Effort!';
  }

  // Animate from 0 → score
  useEffect(() => {
    let raf;
    const start = performance.now();
    const duration = 1200; // ms

    const animate = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setAnimatedScore(eased * score);
      if (progress < 1) {
        raf = requestAnimationFrame(animate);
      }
    };

    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [score]);

  return (
    <div className="accuracy-ring-container">
      <svg
        className="accuracy-ring-svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--color-cream-border)"
          strokeWidth={strokeWidth}
        />
        {/* Animated progress arc */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={ringColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: 'stroke 0.4s ease' }}
        />
      </svg>
      <div className="accuracy-ring-label">
        <span className="accuracy-ring-percent">{Math.round(animatedScore)}%</span>
        <span className="accuracy-ring-message" style={{ color: ringColor }}>{label}</span>
      </div>
    </div>
  );
}
