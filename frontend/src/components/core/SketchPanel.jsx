// Ink outline traced twice off-register, matching SketchButton's double-trace.
const FILL_PATH = 'M2.6,4.2 C22,2.4 48,3.4 74,2.6 C86,2.2 96.4,3.2 97.4,5.6 C98.4,26 97.2,54 97.8,80 C98,90.4 97,96.2 94.6,97.2 C70,98.6 42,97.4 20,98 C8.6,98.3 2.8,97.2 2.2,94.6 C1.4,72 2.6,44 2.1,18 C1.9,8.6 1.4,4.6 2.6,4.2 Z';
const OUTLINE_PATH = 'M4.4,2.2 C24,4.4 50,1.6 76,3.4 C88,4.2 95.2,2.4 96.2,7.4 C97.6,28 95.8,56 96.4,82 C96.6,92 98.2,95.4 93.2,95.8 C68,94.6 40,96.4 18,95.8 C7,95.5 4.4,97.4 3.8,92.6 C3.2,70 4.4,42 3.9,16 C3.7,7 3.2,2.6 4.4,2.2 Z';
const RULE_PATH = 'M1,4 C22,1.6 44,4.4 66,2.6 C88,1 106,4.2 119,2.4';

/** The reusable hand-drawn panel surface used across the dashboard. */
export function SketchPanel({ label, children }) {
  return (
    <div className="sketch-panel">
      <svg className="sketch-panel-frame" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d={FILL_PATH} fill="var(--color-paper-light)" stroke="var(--color-ink)" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <path d={OUTLINE_PATH} fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" opacity="0.24" />
      </svg>
      <div className="sketch-panel-content">
        {label && (
          <div className="sketch-panel-label">
            <div className="sketch-panel-label-text">{label}</div>
            <svg className="sketch-panel-label-rule" viewBox="0 0 120 6" preserveAspectRatio="none" aria-hidden="true">
              <path d={RULE_PATH} fill="none" stroke="var(--color-accent-warm)" strokeWidth="1.6" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
