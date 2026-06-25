import React from 'react';

const speeds = [
  { label: '0.5×', value: 0.5 },
  { label: '0.75×', value: 0.75 },
  { label: '1×', value: 1 },
];

export default function SpeedControl({ currentSpeed = 1, onSpeedChange }) {
  return (
    <div className="speed-control">
      <span className="speed-label">Speed</span>
      {speeds.map(({ label, value }) => (
        <button
          key={value}
          className={`speed-btn${currentSpeed === value ? ' active' : ''}`}
          onClick={() => onSpeedChange(value)}
          aria-label={`Set playback speed to ${label}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
