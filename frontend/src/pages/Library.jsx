import React, { useState } from 'react';
import { Link, useLoaderData } from 'react-router-dom';
import { LEVELS, LEVEL_COLORS } from '../constants/levels';
import LevelFilter from '../components/LevelFilter';

export default function Library() {
  const practices = useLoaderData();
  const [activeLevel, setActiveLevel] = useState('All');

  const filtered = activeLevel === 'All'
    ? practices
    : practices.filter(p => p.level === activeLevel);

  return (
    <div className="flat-section">
      <h2 className="hand-text text-3xl mb-1" style={{ color: 'var(--color-ink)' }}>
        Audio Library
      </h2>
      <p className="library-sub">Browse all available practice sessions ♪</p>

      {/* Filter pills */}
      <LevelFilter levels={LEVELS} activeLevel={activeLevel} onChange={setActiveLevel} />

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
                  style={{ backgroundColor: LEVEL_COLORS[sample.level] }}
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
