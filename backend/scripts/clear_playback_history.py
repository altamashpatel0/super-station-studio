from app.database.database import SessionLocal, init_db
from app.services.playback_history import clear_history

if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        deleted = clear_history(db, reset_song_counters=True)
    print(f"Cleared {deleted} playback history rows and reset song counters.")
