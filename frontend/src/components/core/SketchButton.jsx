import React from 'react';

// Irregular radii that read as a hand-drawn, wobbly ink outline — same device
// as Button's `sketch` shape, kept identical so the two never drift apart.
const SKETCH_RADIUS = '14px 26px 12px 22px / 22px 12px 24px 14px';
const SKETCH_RADIUS_ALT = '22px 12px 24px 14px / 14px 26px 12px 22px';

// Scaled-down version of Card's torn bottom edge. Deterministic, no randomness.
const TORN = 'polygon(0 0, 100% 0, 100% calc(100% - 6px), 88% 100%, 74% calc(100% - 5px), 60% calc(100% - 1px), 46% calc(100% - 7px), 32% calc(100% - 2px), 18% 100%, 6% calc(100% - 4px), 0 calc(100% - 7px))';

const MARKER_CLIP = 'polygon(1% 6%, 99% 0, 100% 88%, 97% 100%, 3% 96%, 0 12%)';

const sizeStyle = {
  sm: { padding: '8px 16px', fontSize: 'var(--text-micro)' },
  md: { padding: '11px 22px', fontSize: 'var(--text-small)' },
  lg: { padding: '15px 30px', fontSize: 'var(--text-body)' },
};

/**
 * Hand-drawn button treatments beyond Button's `sketch` shape.
 *
 * `double`  — a second, fainter outline drawn just off-register.
 * `stamp`   — dashed ink, typewriter caps, set askew; straightens on hover.
 * `marker`  — no border, a rough highlighter block behind the label.
 * `torn`    — the torn-card ripped edge, scaled down to a strip.
 * `pinned`  — the sketch outline plus the sticky-note pushpin, tilted.
 *
 * All five are built only from devices already in the system (irregular radii,
 * 2px ink border, torn clip-path, peel shadow) — no new colours or assets.
 */
export function SketchButton({
  treatment = 'double',
  variant = 'primary',
  size = 'md',
  alt = false,
  disabled = false,
  onClick,
  type = 'button',
  children,
}) {
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const primary = variant === 'primary';
  const fill = primary ? 'var(--accent-primary)' : 'var(--surface-raised)';
  const ink = primary ? 'var(--text-on-accent)' : 'var(--text-primary)';
  const line = primary ? 'var(--accent-primary)' : 'var(--text-primary)';
  const dims = sizeStyle[size] || sizeStyle.md;

  const base = {
    position: 'relative',
    fontFamily: 'var(--font-hand)',
    fontWeight: 700,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    transition: 'transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease',
    ...dims,
  };

  const on = {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => { setHover(false); setActive(false); },
    onMouseDown: () => setActive(true),
    onMouseUp: () => setActive(false),
  };
  const nudge = active ? 'translate(2px,2px)' : hover ? 'translate(-1px,-1px)' : 'translate(0,0)';
  const radius = alt ? SKETCH_RADIUS_ALT : SKETCH_RADIUS;

  if (treatment === 'stamp') {
    const rest = alt ? 'rotate(1deg)' : 'rotate(-1.5deg)';
    return (
      <button type={type} disabled={disabled} onClick={onClick} {...on} style={{
        ...base,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        fontSize: 'var(--text-micro)',
        background: hover ? (primary ? 'rgba(199,90,58,0.07)' : 'rgba(59,49,39,0.04)') : 'transparent',
        color: primary ? 'var(--accent-primary)' : 'var(--text-secondary)',
        border: `2px dashed ${primary ? 'var(--accent-primary)' : 'var(--text-faint)'}`,
        borderRadius: 'var(--radius-sm)',
        transform: active ? 'rotate(0deg) translateY(1px)' : hover ? 'rotate(0deg)' : rest,
      }}>{children}</button>
    );
  }

  if (treatment === 'marker') {
    const wash = primary ? 'rgba(212,152,42,0.72)' : 'rgba(120,108,218,0.42)';
    return (
      <button type={type} disabled={disabled} onClick={onClick} {...on} style={{
        ...base,
        background: 'transparent',
        color: 'var(--text-primary)',
        border: 'none',
        transform: active ? 'translateY(1px)' : hover ? 'translateY(-2px)' : 'none',
      }}>
        <span aria-hidden style={{
          position: 'absolute', left: -4, right: -4, top: 2, bottom: 2,
          background: wash, clipPath: MARKER_CLIP,
          transform: alt ? 'rotate(0.7deg)' : 'rotate(-0.6deg)',
        }} />
        <span style={{ position: 'relative' }}>{children}</span>
      </button>
    );
  }

  if (treatment === 'torn') {
    return (
      <button type={type} disabled={disabled} onClick={onClick} {...on} style={{
        ...base,
        paddingBottom: `calc(${dims.padding.split(' ')[0]} + 5px)`,
        background: primary ? 'var(--accent-primary)' : 'var(--surface-sunken)',
        color: ink,
        border: 'none',
        clipPath: TORN,
        transform: active ? 'translateY(1px)' : hover ? 'translateY(-2px)' : 'none',
      }}>{children}</button>
    );
  }

  if (treatment === 'pinned') {
    const rest = alt ? 'rotate(1.2deg)' : 'rotate(-1deg)';
    return (
      <button type={type} disabled={disabled} onClick={onClick} {...on} style={{
        ...base,
        background: fill,
        color: ink,
        border: `2px solid ${line}`,
        borderRadius: radius,
        boxShadow: active ? 'var(--shadow-sticker-press)' : hover ? 'var(--shadow-sticker-hover)' : 'var(--shadow-sticker)',
        transform: active ? 'rotate(0deg) translate(2px,2px)' : hover ? 'rotate(0deg) translate(-1px,-1px)' : rest,
      }}>
        <span aria-hidden style={{
          position: 'absolute', top: -5, left: 14, width: 10, height: 10, borderRadius: '50%',
          background: primary ? 'var(--text-primary)' : 'var(--accent-secondary)',
          boxShadow: '0 2px 3px rgba(59,49,39,0.35)',
        }} />
        {children}
      </button>
    );
  }

  return (
    <button type={type} disabled={disabled} onClick={onClick} {...on} style={{
      ...base,
      background: primary ? fill : 'transparent',
      color: primary ? ink : 'var(--text-primary)',
      border: `2px solid ${line}`,
      borderRadius: radius,
      transform: nudge,
    }}>
      <span aria-hidden style={{
        position: 'absolute', inset: -5,
        border: `2px solid ${line}`,
        borderRadius: alt ? SKETCH_RADIUS : SKETCH_RADIUS_ALT,
        opacity: primary ? 0.4 : 0.28,
        transform: alt ? 'rotate(0.8deg)' : 'rotate(-0.7deg)',
        pointerEvents: 'none',
      }} />
      {children}
    </button>
  );
}
