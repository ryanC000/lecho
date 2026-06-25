/**
 * Practice items — hardcoded for now.
 * Replace audioUrl / videoUrl with real paths when ready.
 *
 * level  : A1 | A2 | B1 | B2 | C1
 * length : Short | Medium | Long
 * speed  : Slow | Normal | Fast
 */

const practices = [
  {
    id: 1,
    title: "Ordering a Coffee",
    transcript: "Bonjour, je voudrais un café s'il vous plaît.",
    level: "A1",
    length: "Short",
    speed: "Slow",
    duration: 4.0,
    audioUrl: null,
    videoUrl: null,
    notes: "Pay attention to the nasal vowel in 'bonjour' and the liaison in 's'il vous plaît'.",
  },
  {
    id: 2,
    title: "Asking for Directions",
    transcript: "Excusez-moi, où se trouve la gare la plus proche?",
    level: "A2",
    length: "Short",
    speed: "Normal",
    duration: 5.0,
    audioUrl: null,
    videoUrl: null,
    notes: "Watch the rising intonation on the question. The 'r' in 'gare' and 'proche' should be uvular.",
  },
  {
    id: 3,
    title: "Weather Small Talk",
    transcript: "Il fait beau aujourd'hui, mais il va pleuvoir demain matin.",
    level: "A2",
    length: "Medium",
    speed: "Normal",
    duration: 6.0,
    audioUrl: null,
    videoUrl: null,
    notes: "'Il fait beau' is a fixed expression. Note the contraction in 'aujourd'hui'.",
  },
  {
    id: 4,
    title: "Weekend Plans",
    transcript: "Ce week-end, je vais faire la natation et puis retrouver mes amis au restaurant.",
    level: "B1",
    length: "Medium",
    speed: "Normal",
    duration: 7.0,
    audioUrl: null,
    videoUrl: null,
    notes: "'Faire la natation' is a fixed phrase. Listen for the enchaînement in 'mes amis'.",
  },
  {
    id: 5,
    title: "Describing a Film",
    transcript: "C'est un film magnifique qui raconte l'histoire d'une famille pendant la guerre.",
    level: "B2",
    length: "Medium",
    speed: "Normal",
    duration: 7.5,
    audioUrl: null,
    videoUrl: null,
    notes: "Multiple liaisons here. The 'gn' in 'magnifique' is a palatal nasal.",
  },
  {
    id: 6,
    title: "Subjunctive Mood",
    transcript: "Il faut que je m'en aille avant qu'il ne pleuve, bien que le ciel soit encore clair.",
    level: "C1",
    length: "Long",
    speed: "Fast",
    duration: 8.0,
    audioUrl: null,
    videoUrl: null,
    notes: "Three subjunctive triggers: 'il faut que', 'avant que', 'bien que'. This is rapid formal speech.",
  },
];

export default practices;
