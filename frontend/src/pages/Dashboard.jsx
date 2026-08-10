import React, { useState } from 'react';
import { Link, useLoaderData } from 'react-router-dom';
import { LEVELS, LEVEL_COLORS } from '../constants/levels';
import LevelFilter from '../components/LevelFilter';

export default function Dashboard() {
  const practices = useLoaderData();
  const [activeLevel, setActiveLevel] = useState('All');

  const filtered = activeLevel === 'All'
    ? practices
    : practices.filter(p => p.level === activeLevel);

  return (
    <div className="flat-section">
      {/* Hero welcome */}
      <div className="dashboard-hero">
        <h2 className="dashboard-hero-title">Bienvenue</h2>
        <p className="dashboard-hero-sub">
          {practices.length} practice sessions ready for you, pick one and begin
        </p>
      </div>

      {/* Filter pills */}
      <LevelFilter levels={LEVELS} activeLevel={activeLevel} onChange={setActiveLevel} />

      {/* Practice cards */}
      <div className="practice-grid" key={activeLevel}>
        {filtered.map((practice, idx) => (
          <Link
            to={`/practice/${practice.id}`}
            key={practice.id}
            viewTransition
            className="practice-card"
            style={{ animationDelay: `${idx * 0.06}s` }}
          >
            <div className="practice-card-header">
              <span
                className="level-badge"
                style={{
                  backgroundColor: LEVEL_COLORS[practice.level],
                  viewTransitionName: `level-${practice.id}`
                }}
              >
                {practice.level}
              </span>
              <span className="practice-card-title" style={{ viewTransitionName: `title-${practice.id}` }}>
                {practice.title}
              </span>
            </div>
            <p className="practice-card-transcript">
              {practice.transcript}
            </p>
            <div className="practice-card-meta">
              <span className="meta-tag" style={{ viewTransitionName: `length-${practice.id}` }}>
                {practice.length}
              </span>
              <span className="meta-tag" style={{ viewTransitionName: `speed-${practice.id}` }}>
                {practice.speed}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
