"""
Phase 5 Video & Content Techniques Seeder for sky_command_demo.db
Ensures all 10 shooting techniques have linked demonstration videos in the community.
"""

import sqlite3
import json
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Update existing videos with content_techniques
video_updates = {
    1: ["active_track_thirds", "straight_dronie"],
    2: ["orbit_poi", "low_angle_ground"],
    3: ["top_down_overhead", "reveal_obstacle"],
    4: ["reveal_obstacle", "negative_space_landscape"]
}

for vid, techs in video_updates.items():
    c.execute(
        "UPDATE videos SET content_techniques = ? WHERE id = ?",
        (json.dumps(techs, ensure_ascii=False), vid)
    )

# 2. Add sample videos 5 and 6 if they don't exist
existing_ids = [row[0] for row in c.execute("SELECT id FROM videos").fetchall()]

if 5 not in existing_ids:
    c.execute("""
        INSERT INTO videos (id, title, url, background, time_slot, composition, created_at, content_techniques)
        VALUES (5, '호수 일출 반영 시메트리', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
                '수변/도시', '일출/아침', '수면 반영 대칭 (Symmetry)', '2026-11-20T08:00:00', ?)
    """, (json.dumps(["symmetry_reflection", "negative_space_landscape"], ensure_ascii=False),))

if 6 not in existing_ids:
    c.execute("""
        INSERT INTO videos (id, title, url, background, time_slot, composition, created_at, content_techniques)
        VALUES (6, '도심 스카이라인 스파이럴 & 플라이바이', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4',
                '수변/도시', '골든아워', '나선 상승 및 플라이바이', '2026-11-20T17:00:00', ?)
    """, (json.dumps(["high_spiral", "high_speed_flyby"], ensure_ascii=False),))

conn.commit()

# Check results
rows = c.execute("SELECT id, title, composition, content_techniques FROM videos").fetchall()
print(f"Total videos in {os.path.basename(db_path)}: {len(rows)}")
for r in rows:
    print(f"  [{r[0]}] {r[1]} | {r[2]} | techniques: {r[3]}")

conn.close()
