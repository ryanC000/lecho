import { phraseMap, wordMap } from '../data/frenchPhrases';

/**
 * Translates a French word or short phrase to English
 * using the local placeholder dictionaries.
 *
 * When a real API is connected, swap the fallback
 * to an async fetch instead of the static wordMap lookup.
 */
export function translateWord(word) {
  if (!word) return null;
  const normalised = word.toLowerCase().replace(/[.,!?;:«»""]/g, '').trim();
  if (!normalised) return null;
  return wordMap[normalised] || `[${normalised}]`;
}

/**
 * Attempts to find a multi-word phrase match starting at
 * the given index in the words array.
 * Returns { translation, wordCount } if found, else null.
 */
export function findPhraseMatch(words, startIndex) {
  // Try longest phrases first (up to 6 words)
  for (let len = Math.min(6, words.length - startIndex); len >= 2; len--) {
    const candidate = words
      .slice(startIndex, startIndex + len)
      .join(' ')
      .toLowerCase()
      .replace(/[.,!?;:«»""]/g, '')
      .trim();

    if (phraseMap[candidate]) {
      return { translation: phraseMap[candidate], wordCount: len };
    }
  }
  return null;
}

/**
 * Translates a full French sentence to English.
 * Uses phrase map first, then word-by-word fallback.
 * Returns a placeholder string.
 */
export function translateSentence(sentence) {
  if (!sentence) return '';
  const words = sentence.split(/\s+/);
  const parts = [];
  let i = 0;

  while (i < words.length) {
    const phraseMatch = findPhraseMatch(words, i);
    if (phraseMatch) {
      parts.push(phraseMatch.translation);
      i += phraseMatch.wordCount;
    } else {
      parts.push(translateWord(words[i]));
      i++;
    }
  }

  return parts.join(' ');
}
