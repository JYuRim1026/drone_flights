"""
커뮤니티 개인화 영상 추천 엔진
- 기존 프로젝트의 SQLite users(user_id) 테이블 사용
- 설문 선호도 저장
- 영상 조회/좋아요/저장 기록 수집
- 사용자별 선호도 점수 갱신
- 개인화 추천 / 인기순 / 최신순
"""

import sqlite3
import math

from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


CATEGORIES = ("background", "time_slot", "composition")

EVENT_WEIGHTS = {
    "view": 1.0,
    "repeat_view": 2.5,
    "like": 4.0,
    "save": 5.0,
    "select": 6.0,
    "satisfaction": 8.0
}

SORTS = ("recommended", "popular", "latest")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_date(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if date.tzinfo is None:
        return date.replace(tzinfo=timezone.utc)

    return date.astimezone(timezone.utc)


class VideoRecommender:

    def __init__(self, db_path=None):
        if db_path is None:
            # 1. 중앙 설정(settings.DATABASE_URL)과 일원화된 SQLite 경로 연동 (로컬 및 Vercel /tmp 호환)
            try:
                from backend.config import settings
                db_url = settings.DATABASE_URL
                if db_url.startswith("sqlite:///"):
                    self.db_path = db_url.replace("sqlite:///", "")
                else:
                    self.db_path = db_url
            except Exception:
                default_path = Path(__file__).resolve().parent.parent / "sky_command.db"
                self.db_path = str(default_path if default_path.exists() else "sky_command.db")
        else:
            self.db_path = str(db_path)
        self.initialize_db()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---------------------------------
    # 1. DB 테이블 생성 (Self-Healing & Non-blocking)
    # ---------------------------------

    def initialize_db(self):

        with self.connect() as db:

            # 기존 프로젝트 users 테이블 확인 및 미존재 시 자동 복구(Self-Healing)
            tables = db.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name='users'
            """).fetchone()

            if not tables:
                try:
                    from backend.database import Base, engine, SessionLocal
                    from backend.services.auth_service import auth_service
                    Base.metadata.create_all(bind=engine)
                    _sess = SessionLocal()
                    auth_service.init_default_users(_sess)
                    _sess.close()
                    tables = db.execute("""
                        SELECT name
                        FROM sqlite_master
                        WHERE type='table' AND name='users'
                    """).fetchone()
                except Exception as _init_err:
                    print(f"Notice: Community DB self-healing notice: {_init_err}")

            if not tables:
                print("Warning: users table not ready yet; deferring VideoRecommender strict constraint.")
                return

            columns = [
                row["name"]
                for row in db.execute("PRAGMA table_info(users)")
            ]

            if "user_id" not in columns:
                if "id" in columns:
                    try:
                        db.execute("ALTER TABLE users ADD COLUMN user_id INTEGER")
                        db.execute("UPDATE users SET user_id = id WHERE user_id IS NULL")
                    except Exception:
                        pass
                else:
                    print("Warning: users table missing user_id column; continuing in compatibility mode.")

            # 커뮤니티 영상 정보
            db.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    background TEXT NOT NULL,
                    time_slot TEXT NOT NULL,
                    composition TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 최초 설문 선호도
            db.execute("""
                CREATE TABLE IF NOT EXISTS survey_preferences (
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    value TEXT NOT NULL,
                    strength REAL NOT NULL DEFAULT 5,
                    PRIMARY KEY(user_id, category, value),
                    FOREIGN KEY(user_id)
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                )
            """)

            # 사용자 이용 기록
            db.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    video_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    occurred_at TEXT NOT NULL,

                    CHECK(event_type IN ('view', 'like', 'save')),
                    CHECK(active IN (0, 1)),

                    FOREIGN KEY(user_id)
                        REFERENCES users(user_id)
                        ON DELETE CASCADE,

                    FOREIGN KEY(video_id)
                        REFERENCES videos(id)
                        ON DELETE CASCADE
                )
            """)

            # 좋아요와 저장 중복 방지
            db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_unique_active_interaction
                ON interactions(user_id, video_id, event_type)
                WHERE event_type IN ('like', 'save')
                AND active = 1
            """)

            # 사용자별 선호도 점수
            db.execute("""
                CREATE TABLE IF NOT EXISTS user_preference_scores (
                    preference_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    preference_value TEXT NOT NULL,
                    preference_score REAL NOT NULL,
                    updated_at TEXT NOT NULL,

                    UNIQUE(user_id, category, preference_value),

                    FOREIGN KEY(user_id)
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                )
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_interaction_user
                ON interactions(user_id)
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_video_created
                ON videos(created_at)
            """)

    # ---------------------------------
    # 2. 사용자 확인
    # ---------------------------------

    def check_user(self, db, user_id):

        result = db.execute("""
            SELECT user_id
            FROM users
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not result:
            raise ValueError("존재하지 않는 사용자입니다.")

    # ---------------------------------
    # 3. 영상 등록
    # ---------------------------------

    def add_video(
        self,
        title,
        url,
        background,
        time_slot,
        composition
    ):

        values = [
            title, url, background,
            time_slot, composition
        ]

        if not all(
            isinstance(v, str) and v.strip()
            for v in values
        ):
            raise ValueError("영상 정보가 누락되었습니다.")

        with self.connect() as db:

            cursor = db.execute("""
                INSERT INTO videos (
                    title,
                    url,
                    background,
                    time_slot,
                    composition,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                title.strip(),
                url.strip(),
                background.strip(),
                time_slot.strip(),
                composition.strip(),
                utc_now()
            ))

            return cursor.lastrowid

    # ---------------------------------
    # 4. 설문 선호도 저장
    # ---------------------------------

    def set_survey_preference(
        self,
        user_id,
        category,
        value,
        strength=5
    ):

        if category not in CATEGORIES:
            raise ValueError("잘못된 선호도 카테고리입니다.")

        if not value or not 0 <= strength <= 5:
            raise ValueError("선호도 점수는 0~5여야 합니다.")

        with self.connect() as db:

            self.check_user(db, user_id)

            if strength == 0:

                db.execute("""
                    DELETE FROM survey_preferences
                    WHERE user_id = ?
                    AND category = ?
                    AND value = ?
                """, (user_id, category, value))

            else:

                db.execute("""
                    INSERT INTO survey_preferences (
                        user_id,
                        category,
                        value,
                        strength
                    )
                    VALUES (?, ?, ?, ?)

                    ON CONFLICT(user_id, category, value)
                    DO UPDATE SET strength = excluded.strength
                """, (
                    user_id,
                    category,
                    value.strip(),
                    strength
                ))

            self.refresh_preference_scores(db, user_id)

    # ---------------------------------
    # 5. 이용 기록 수집
    # ---------------------------------

    def record_event(
        self,
        user_id,
        video_id,
        event_type,
        active=True
    ):

        if event_type not in EVENT_WEIGHTS:
            raise ValueError(f"지원하지 않는 이벤트입니다: {event_type}. ({', '.join(EVENT_WEIGHTS.keys())} 가능)")

        if event_type in ("view", "repeat_view") and not active:
            raise ValueError("조회 기록은 취소할 수 없습니다.")

        with self.connect() as db:

            self.check_user(db, user_id)

            video = db.execute("""
                SELECT id FROM videos WHERE id = ?
            """, (video_id,)).fetchone()

            if not video:
                raise ValueError("존재하지 않는 영상입니다.")

            if event_type in ("like", "save"):

                existing = db.execute("""
                    SELECT id
                    FROM interactions
                    WHERE user_id = ?
                    AND video_id = ?
                    AND event_type = ?
                    AND active = 1
                """, (
                    user_id,
                    video_id,
                    event_type
                )).fetchone()

                if active and existing:
                    return

                if not active:

                    db.execute("""
                        UPDATE interactions
                        SET active = 0
                        WHERE user_id = ?
                        AND video_id = ?
                        AND event_type = ?
                        AND active = 1
                    """, (
                        user_id,
                        video_id,
                        event_type
                    ))

                else:

                    db.execute("""
                        INSERT INTO interactions (
                            user_id,
                            video_id,
                            event_type,
                            active,
                            occurred_at
                        )
                        VALUES (?, ?, ?, 1, ?)
                    """, (
                        user_id,
                        video_id,
                        event_type,
                        utc_now()
                    ))

            elif event_type in ("view", "repeat_view"):
                # 이전 조회 이력이 있다면 repeat_view로 승격하여 2.5 가중치 부여
                prev_views = db.execute("""
                    SELECT COUNT(*) FROM interactions
                    WHERE user_id = ? AND video_id = ? AND event_type IN ('view', 'repeat_view') AND active = 1
                """, (user_id, video_id)).fetchone()[0]

                actual_etype = "repeat_view" if (prev_views > 0 or event_type == "repeat_view") else "view"
                db.execute("""
                    INSERT INTO interactions (
                        user_id,
                        video_id,
                        event_type,
                        active,
                        occurred_at
                    )
                    VALUES (?, ?, ?, 1, ?)
                """, (user_id, video_id, actual_etype, utc_now()))

            else:
                db.execute("""
                    INSERT INTO interactions (
                        user_id,
                        video_id,
                        event_type,
                        active,
                        occurred_at
                    )
                    VALUES (?, ?, ?, 1, ?)
                """, (user_id, video_id, event_type, utc_now()))

            self.refresh_preference_scores(db, user_id)

    # ---------------------------------
    # 5-1. 직관적인 상호작용 액션 라우팅
    # (조회, 좋아요, 좋아요 취소, 저장, 저장 취소, 선택, 만족도)
    # ---------------------------------

    def record_interaction(self, user_id, video_id, action):
        """
        사용자 행동 액션:
        - 'view': 영상 조회 (단순 조회 1.0점, 반복 시청 2.5점)
        - 'repeat_view': 반복 시청 (2.5점)
        - 'like': 좋아요 반영 (4.0점)
        - 'unlike': 좋아요 취소 반영
        - 'save': 저장(북마크) 반영 (5.0점)
        - 'unsave': 저장 취소 반영
        - 'select': 프로젝트 촬영 기법 선택 (6.0점)
        - 'satisfaction': 촬영 후 만족도 반영 (8.0점)
        """
        action_map = {
            "view": ("view", True),
            "repeat_view": ("repeat_view", True),
            "like": ("like", True),
            "unlike": ("like", False),
            "save": ("save", True),
            "unsave": ("save", False),
            "select": ("select", True),
            "satisfaction": ("satisfaction", True)
        }

        if action not in action_map:
            raise ValueError(f"지원하지 않는 액션입니다: {action}. ({', '.join(action_map.keys())} 가능)")

        event_type, active = action_map[action]
        self.record_event(user_id, video_id, event_type, active)
        return self.get_video_stats(user_id, video_id)

    def get_video_stats(self, user_id, video_id):
        """특정 영상의 최신 통계(조회수, 좋아요수, 저장수 및 현재 사용자 상태) 조회"""
        with self.connect() as db:
            self.check_user(db, user_id)
            v_cnt = db.execute("SELECT COUNT(*) FROM interactions WHERE video_id = ? AND event_type = 'view'", (video_id,)).fetchone()[0]
            l_cnt = db.execute("SELECT COUNT(*) FROM interactions WHERE video_id = ? AND event_type = 'like' AND active = 1", (video_id,)).fetchone()[0]
            s_cnt = db.execute("SELECT COUNT(*) FROM interactions WHERE video_id = ? AND event_type = 'save' AND active = 1", (video_id,)).fetchone()[0]

            is_l = db.execute("SELECT 1 FROM interactions WHERE user_id = ? AND video_id = ? AND event_type = 'like' AND active = 1", (user_id, video_id)).fetchone() is not None
            is_s = db.execute("SELECT 1 FROM interactions WHERE user_id = ? AND video_id = ? AND event_type = 'save' AND active = 1", (user_id, video_id)).fetchone() is not None
            is_v = db.execute("SELECT 1 FROM interactions WHERE user_id = ? AND video_id = ? AND event_type = 'view'", (user_id, video_id)).fetchone() is not None

            return {
                "video_id": video_id,
                "views_count": v_cnt,
                "likes_count": l_cnt,
                "saves_count": s_cnt,
                "is_liked": is_l,
                "is_saved": is_s,
                "is_viewed": is_v
            }

    # ---------------------------------
    # 6. 사용자 선호도 점수 갱신
    # ---------------------------------

    def refresh_preference_scores(self, db, user_id):

        survey = db.execute("""
            SELECT category, value, strength
            FROM survey_preferences
            WHERE user_id = ?
        """, (user_id,)).fetchall()

        events = db.execute("""
            SELECT
                i.event_type,
                i.occurred_at,
                v.background,
                v.time_slot,
                v.composition
            FROM interactions i
            JOIN videos v ON i.video_id = v.id
            WHERE i.user_id = ?
            AND i.active = 1
        """, (user_id,)).fetchall()

        survey_scores = {
            (row["category"], row["value"]): row["strength"]
            for row in survey
        }

        behavior_scores = {}

        now = datetime.now(timezone.utc)

        for event in events:

            days = max(
                0,
                (now - parse_date(event["occurred_at"])).total_seconds()
                / 86400
            )

            weight = EVENT_WEIGHTS.get(event["event_type"], 1.0)

            # 오래된 기록의 영향력 감소
            adjusted_weight = weight * (0.5 ** (days / 90))

            for category in CATEGORIES:

                value = event[category]
                key = (category, value)

                behavior_scores[key] = (
                    behavior_scores.get(key, 0)
                    + adjusted_weight
                )

        all_keys = set(survey_scores) | set(behavior_scores)

        db.execute("""
            DELETE FROM user_preference_scores
            WHERE user_id = ?
        """, (user_id,))

        for category, value in all_keys:

            survey_score = survey_scores.get(
                (category, value), 0
            )

            behavior_score = behavior_scores.get(
                (category, value), 0
            )

            # 설문 70% + 이용 기록 30%
            survey_part = (survey_score / 5) * 70

            behavior_part = (
                min(
                    1,
                    math.log1p(behavior_score) / math.log1p(10)
                ) * 30
            )

            final_score = survey_part + behavior_part

            db.execute("""
                INSERT INTO user_preference_scores (
                    user_id,
                    category,
                    preference_value,
                    preference_score,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                category,
                value,
                round(final_score, 2),
                utc_now()
            ))

    # ---------------------------------
    # 7. 사용자 선호도 조회
    # ---------------------------------

    def get_preference_scores(self, user_id):

        with self.connect() as db:

            self.check_user(db, user_id)

            rows = db.execute("""
                SELECT
                    category,
                    preference_value,
                    preference_score,
                    updated_at
                FROM user_preference_scores
                WHERE user_id = ?
                ORDER BY preference_score DESC
            """, (user_id,)).fetchall()

            return [dict(row) for row in rows]

    # ---------------------------------
    # 8. 영상 추천
    # ---------------------------------

    def recommend(
        self,
        user_id,
        sort="recommended",
        limit=4,
        technique=None
    ):

        if sort not in SORTS:
            raise ValueError("정렬 방식이 올바르지 않습니다.")

        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("추천 개수는 1~100이어야 합니다.")

        with self.connect() as db:

            self.check_user(db, user_id)

            videos = db.execute("""
                SELECT * FROM videos
            """).fetchall()

            if technique:
                import json
                t_str = str(technique).strip().lower()
                filtered = []
                for v in videos:
                    c_techs = []
                    try:
                        v_keys = v.keys() if hasattr(v, "keys") else []
                        if "content_techniques" in v_keys and v["content_techniques"]:
                            raw = v["content_techniques"]
                            c_techs = json.loads(raw) if isinstance(raw, str) else list(raw)
                    except Exception:
                        c_techs = []

                    matched = False
                    if any(t_str == str(ct).strip().lower() for ct in c_techs):
                        matched = True
                    elif t_str in str(v["composition"]).lower() or t_str in str(v["title"]).lower():
                        matched = True

                    if matched:
                        filtered.append(v)
                if filtered:
                    videos = filtered

            preferences = db.execute("""
                SELECT
                    category,
                    preference_value,
                    preference_score
                FROM user_preference_scores
                WHERE user_id = ?
            """, (user_id,)).fetchall()

            events = db.execute("""
                SELECT
                    i.user_id,
                    i.video_id,
                    i.event_type,
                    i.occurred_at,
                    v.background,
                    v.time_slot,
                    v.composition
                FROM interactions i
                JOIN videos v ON i.video_id = v.id
                WHERE i.active = 1
            """).fetchall()

        preference_map = {
            (row["category"], row["preference_value"]):
                row["preference_score"] / 100
            for row in preferences
        }

        popularity = {}
        viewed = set()
        user_likes = set()
        user_saves = set()
        views_count = {}
        likes_count = {}
        saves_count = {}

        now = datetime.now(timezone.utc)

        for event in events:
            vid = event["video_id"]
            etype = event["event_type"]

            days = max(
                0,
                (now - parse_date(event["occurred_at"])).total_seconds()
                / 86400
            )

            weight = EVENT_WEIGHTS[etype]

            popularity[vid] = (
                popularity.get(vid, 0)
                + weight * (0.5 ** (days / 30))
            )

            if etype == "view":
                views_count[vid] = views_count.get(vid, 0) + 1
            elif etype == "like":
                likes_count[vid] = likes_count.get(vid, 0) + 1
                if event["user_id"] == user_id:
                    user_likes.add(vid)
            elif etype == "save":
                saves_count[vid] = saves_count.get(vid, 0) + 1
                if event["user_id"] == user_id:
                    user_saves.add(vid)

            if event["user_id"] == user_id:
                if etype == "view":
                    viewed.add(vid)

        results = []

        for video in videos:

            category_scores = []

            for category in CATEGORIES:

                key = (
                    category,
                    video[category]
                )

                category_scores.append(
                    preference_map.get(key, 0)
                )

            taste_score = (
                sum(category_scores) / len(category_scores)
            )

            pop = math.log1p(
                popularity.get(video["id"], 0)
            )

            age_days = max(
                0,
                (now - parse_date(video["created_at"])).total_seconds()
                / 86400
            )

            freshness = 0.5 ** (age_days / 30)

            # 취향 80% + 인기 12% + 최신성 8%
            final_score = (
                0.8 * taste_score
                + 0.12 * min(1, pop / math.log1p(20))
                + 0.08 * freshness
            )

            results.append({
                **dict(video),
                "score": round(final_score, 4),
                "popularity": round(pop, 4),
                "is_viewed": video["id"] in viewed,
                "is_liked": video["id"] in user_likes,
                "is_saved": video["id"] in user_saves,
                "views_count": views_count.get(video["id"], 0),
                "likes_count": likes_count.get(video["id"], 0),
                "saves_count": saves_count.get(video["id"], 0)
            })

        if sort == "popular":

            results.sort(
                key=lambda v: (
                    v["popularity"],
                    v["created_at"],
                    v["id"]
                ),
                reverse=True
            )

        elif sort == "latest":

            results.sort(
                key=lambda v: (
                    v["created_at"],
                    v["id"]
                ),
                reverse=True
            )

        else:

            results.sort(
                key=lambda v: (
                    v["score"],
                    v["created_at"],
                    v["id"]
                ),
                reverse=True
            )

        return results[:limit]
