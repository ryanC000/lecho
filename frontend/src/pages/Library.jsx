import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import practices from '../data/practicesData';

const levels = ['All', 'A1', 'A2', 'B1', 'B2', 'C1'];

const levelColors = {
  A1: 'var(--color-level-a1)',
  A2: 'var(--color-level-a2)',
  B1: 'var(--color-level-b1)',
  B2: 'var(--color-level-b2)',
  C1: 'var(--color-level-c1)',
};

export default function Library() {
  const [activeLevel, setActiveLevel] = useState('All');

  const filtered = activeLevel === 'All'
    ? practices
    : practices.filter(p => p.level === activeLevel);

  return (
    <div className="flat-section page-enter">
      <h2 className="hand-text text-3xl mb-1" style={{ color: 'var(--color-ink)' }}>
        Audio Library
      </h2>
      <p className="library-sub">Browse all available practice sessions ♪</p>

      {/* Filter pills */}
      <div className="filter-bar">
        {levels.map(level => (
          <button
            key={level}
            className={`filter-pill${activeLevel === level ? ' active' : ''}`}
            onClick={() => setActiveLevel(level)}
          >
            {level}
          </button>
        ))}
      </div>

      {/* Library list */}
      <div className="dashboard-list">
        {filtered.map((sample, idx) => (
          <div
            key={sample.id}
            className="dashboard-item fade-in-up"
            style={{ animationDelay: `${idx * 0.06}s` }}
          >
            <div className="dashboard-item-info">
              <span>
                <span
                  className="level-badge-inline"
                  style={{ backgroundColor: levelColors[sample.level] }}
                >
                  {sample.level}
                </span>
                <strong>{sample.title}</strong>
              </span>
              <span className="serif-text">{sample.transcript}</span>
              <span className="library-meta">
                {sample.length} · {sample.speed} speed
              </span>
            </div>
            <Link to={`/practice/${sample.id}`}>
              <button className="btn-primary">Practice</button>
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
