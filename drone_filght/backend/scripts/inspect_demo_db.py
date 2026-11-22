import sqlite3

conn = sqlite3.connect('drone_filght/backend/sky_command_demo.db')
cursor = conn.cursor()
tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

for t in ['videos', 'interactions', 'user_preference_scores', 'survey_preferences', 'shooting_projects', 'shooting_analyses']:
    if t in tables:
        count = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n{t} ({count} rows):", cols)
        sample = cursor.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
        print("  sample:", sample)

conn.close()
