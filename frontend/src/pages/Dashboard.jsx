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

export default function Dashboard() {
  const [activeLevel, setActiveLevel] = useState('All');

  const filtered = activeLevel === 'All'
    ? practices
    : practices.filter(p => p.level === activeLevel);

  return (
    <div className="flat-section page-enter">
      {/* Hero welcome */}
      <div className="dashboard-hero">
        <h2 className="dashboard-hero-title">Bienvenue</h2>
        <p className="dashboard-hero-sub">
          {practices.length} practice sessions ready for you — pick one and begin ✎
        </p>
      </div>

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

      {/* Practice cards */}
      <div className="practice-grid">
        {filtered.map((practice, idx) => (
          <Link
            to={`/practice/${practice.id}`}
            key={practice.id}
            className="practice-card"
            style={{ animationDelay: `${idx * 0.06}s` }}
          >
            <div className="practice-card-header">
              <span
                className="level-badge"
                style={{ backgroundColor: levelColors[practice.level] }}
              >
                {practice.level}
              </span>
              <span className="practice-card-title">{practice.title}</span>
            </div>
            <p className="practice-card-transcript">
              {practice.transcript}
            </p>
            <div className="practice-card-meta">
              <span className="meta-tag">{practice.length}</span>
              <span className="meta-tag">{practice.speed}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
