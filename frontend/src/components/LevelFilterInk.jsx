// Hand-drawn loop traced behind the active label, same wobble as SketchPanel/SketchButton.
const LOOP_PATH = 'M13,7 C35,1.6 67,2.2 88,8 C97,12 97,30 86,36 C63,42.4 29,42 12,35.6 C2.6,30.6 3.4,11.6 13,6.6 C19,4.2 27,3 35,2.6';

// Pencil-circled level filter for the dashboard redesign; Library keeps the shipped pill LevelFilter.
export default function LevelFilterInk({ levels, activeLevel, onChange }) {
  return (
    <div className="level-filter-ink">
      {levels.map(level => (
        <button
          key={level}
          type="button"
          className={`level-filter-ink-item${activeLevel === level ? ' active' : ''}`}
          onClick={() => onChange(level)}
        >
          {activeLevel === level && (
            <svg className="level-filter-ink-loop" viewBox="0 0 100 44" preserveAspectRatio="none" aria-hidden="true">
              <path d={LOOP_PATH} fill="none" stroke="var(--color-accent-warm)" strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            </svg>
          )}
          {level}
        </button>
      ))}
    </div>
  );
}
