import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import SpeedControl from './SpeedControl';

export default function AudioVisualizer({
  audioUrl,
  color = '#ff4e00',
  showSpeedControl = false,
  onReady = null,
}) {
  const containerRef = useRef(null);
  const wavesurferRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    if (containerRef.current) {
      wavesurferRef.current = WaveSurfer.create({
        container: containerRef.current,
        waveColor: '#DCD3CB',
        progressColor: color,
        cursorColor: color,
        barWidth: 2,
        barRadius: 3,
        cursorWidth: 1,
        height: 80,
        normalize: true,
      });

      wavesurferRef.current.on('play', () => setIsPlaying(true));
      wavesurferRef.current.on('pause', () => setIsPlaying(false));
      wavesurferRef.current.on('finish', () => setIsPlaying(false));

      if (audioUrl) {
        wavesurferRef.current.load(audioUrl);
      }

      if (onReady) {
        wavesurferRef.current.on('ready', () => {
          onReady(wavesurferRef.current);
        });
      }
    }

    return () => {
      if (wavesurferRef.current) {
        wavesurferRef.current.destroy();
      }
    };
  }, [audioUrl, color]);

  const handlePlayPause = () => {
    if (wavesurferRef.current) {
      wavesurferRef.current.playPause();
    }
  };

  const handleSpeedChange = (newSpeed) => {
    setSpeed(newSpeed);
    if (wavesurferRef.current) {
      wavesurferRef.current.setPlaybackRate(newSpeed);
    }
  };

  return (
    <div className="visualizer-container">
      <div ref={containerRef} className="waveform"></div>
      <div className="visualizer-controls">
        <button
          className={`play-pause-btn${isPlaying ? ' playing' : ''}`}
          onClick={handlePlayPause}
        >
          <span className="play-icon">{isPlaying ? '❚❚' : '▶'}</span>
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        {showSpeedControl && (
          <SpeedControl currentSpeed={speed} onSpeedChange={handleSpeedChange} />
        )}
      </div>
    </div>
  );
}
