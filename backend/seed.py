import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Temporary script that populates the database with some data before the local database is setup

# Ensure we can import from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import Base, SQLALCHEMY_DATABASE_URL
from models import Practice, User

# Delete the old SQLite DB if it exists to ensure a clean slate
if os.path.exists("./lecho.db"):
    os.remove("./lecho.db")

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Recreate all tables
Base.metadata.create_all(bind=engine)

db = SessionLocal()

initial_practices = [
    {
        "title": "Ordering a Coffee",
        "transcript": "Bonjour, je voudrais un café s'il vous plaît.",
        "level": "A1",
        "length": "Short",
        "speed": "Slow",
        "duration": 4.0,
        "notes": "Pay attention to the nasal vowel in 'bonjour' and the liaison in 's'il vous plaît'."
    },
    {
        "title": "Asking for Directions",
        "transcript": "Excusez-moi, où se trouve la gare la plus proche?",
        "level": "A2",
        "length": "Short",
        "speed": "Normal",
        "duration": 5.0,
        "notes": "Watch the rising intonation on the question. The 'r' in 'gare' and 'proche' should be uvular."
    },
    {
        "title": "Weather Small Talk",
        "transcript": "Il fait beau aujourd'hui, mais il va pleuvoir demain matin.",
        "level": "A2",
        "length": "Medium",
        "speed": "Normal",
        "duration": 6.0,
        "notes": "'Il fait beau' is a fixed expression. Note the contraction in 'aujourd'hui'."
    },
    {
        "title": "Weekend Plans",
        "transcript": "Ce week-end, je vais faire la natation et puis retrouver mes amis au restaurant.",
        "level": "B1",
        "length": "Medium",
        "speed": "Normal",
        "duration": 7.0,
        "notes": "'Faire la natation' is a fixed phrase. Listen for the enchaînement in 'mes amis'."
    },
    {
        "title": "Describing a Film",
        "transcript": "C'est un film magnifique qui raconte l'histoire d'une famille pendant la guerre.",
        "level": "B2",
        "length": "Medium",
        "speed": "Normal",
        "duration": 7.5,
        "notes": "Multiple liaisons here. The 'gn' in 'magnifique' is a palatal nasal."
    },
    {
        "title": "Subjunctive Mood",
        "transcript": "Il faut que je m'en aille avant qu'il ne pleuve, bien que le ciel soit encore clair.",
        "level": "C1",
        "length": "Long",
        "speed": "Fast",
        "duration": 8.0,
        "notes": "Three subjunctive triggers: 'il faut que', 'avant que', 'bien que'. This is rapid formal speech."
    }
]

for practice_data in initial_practices:
    practice = Practice(**practice_data)
    db.add(practice)

# Seed a default user for testing auth
user = User(email="test@example.com", password_hash="dummy_hash")
db.add(user)

db.commit()
db.close()
print("Database seeded successfully with new schemas!")
