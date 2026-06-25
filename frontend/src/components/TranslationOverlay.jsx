import React, { useState, useCallback } from 'react';
import { translateWord, findPhraseMatch, translateSentence } from '../utils/translate';

/**
 * Renders French text as clickable tokens.
 * Tap a word to see its English translation in a tooltip.
 * "Translate All" shows the full-sentence translation.
 */
export default function TranslationOverlay({ text }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [showFullTranslation, setShowFullTranslation] = useState(false);

  const words = text ? text.split(/\s+/) : [];

  const handleWordClick = useCallback((index) => {
    if (activeIndex === index) {
      // Toggle off
      setActiveIndex(null);
      setTooltip(null);
      return;
    }

    // Try phrase match first
    const phraseMatch = findPhraseMatch(words, index);
    if (phraseMatch) {
      setActiveIndex(index);
      setTooltip({
        startIndex: index,
        endIndex: index + phraseMatch.wordCount - 1,
        text: phraseMatch.translation,
      });
    } else {
      // Single word
      const translation = translateWord(words[index]);
      setActiveIndex(index);
      setTooltip({
        startIndex: index,
        endIndex: index,
        text: translation,
      });
    }
  }, [activeIndex, words]);

  const isHighlighted = (index) => {
    if (!tooltip) return false;
    return index >= tooltip.startIndex && index <= tooltip.endIndex;
  };

  return (
    <div className="translation-overlay">
      <div className="translation-text">
        {words.map((word, idx) => (
          <span key={idx} className="translation-word-wrapper">
            <span
              className={`translation-word${isHighlighted(idx) ? ' highlighted' : ''}`}
              onClick={() => handleWordClick(idx)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleWordClick(idx)}
            >
              {word}
            </span>
            {tooltip && tooltip.startIndex === idx && (
              <span className="translation-tooltip" key={`tip-${idx}`}>
                {tooltip.text}
              </span>
            )}
          </span>
        ))}
      </div>

      <div className="translation-actions">
        <button
          className={`translate-all-btn${showFullTranslation ? ' active' : ''}`}
          onClick={() => setShowFullTranslation(!showFullTranslation)}
        >
          {showFullTranslation ? 'Hide Translation' : 'Translate All'}
        </button>
      </div>

      {showFullTranslation && (
        <div className="full-translation">
          <p>{translateSentence(text)}</p>
        </div>
      )}
    </div>
  );
}
