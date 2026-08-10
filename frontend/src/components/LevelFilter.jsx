import React from 'react';

// Filter-pill row, shared by Dashboard and Library.
export default function LevelFilter({ levels, activeLevel, onChange }) {
  return (
    <div className="filter-bar">
      {levels.map(level => (
        <button
          key={level}
          className={`filter-pill${activeLevel === level ? ' active' : ''}`}
          onClick={() => onChange(level)}
        >
          {level}
        </button>
      ))}
    </div>
  );
}
