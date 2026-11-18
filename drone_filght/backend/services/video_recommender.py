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
    "view": 0.5,
    "like": 2.0,
    "save": 3.0
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
            # 기본 경로: backend/sky_command.db
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
    # 1. DB 테이블 생성
    # ---------------------------------

    def initialize_db(self):

        with self.connect() as db:

            # 기존 프로젝트 users 테이블 확인
            tables = db.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name='users'
            """).fetchone()

            if not tables:
                raise RuntimeError(
                    "기존 프로젝트의 users 테이블을 찾을 수 없습니다."
                )

            columns = [
                row["name"]
                for row in db.execute("PRAGMA table_info(users)")
            ]

            if "user_id" not in columns:
                raise RuntimeError(
                    "users 테이블에 user_id 컬럼이 필요합니다."
                )

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
            raise ValueError("view, like, save만 가능합니다.")

        if event_type == "view" and not active:
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

            else:

                db.execute("""
                    INSERT INTO interactions (
                        user_id,
                        video_id,
                        event_type,
                        active,
                        occurred_at
                    )
                    VALUES (?, ?, 'view', 1, ?)
                """, (user_id, video_id, utc_now()))

            self.refresh_preference_scores(db, user_id)

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

            weight = EVENT_WEIGHTS[event["event_type"]]

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
        limit=4
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

        now = datetime.now(timezone.utc)

        for event in events:

            days = max(
                0,
                (now - parse_date(event["occurred_at"])).total_seconds()
                / 86400
            )

            weight = EVENT_WEIGHTS[event["event_type"]]

            popularity[event["video_id"]] = (
                popularity.get(event["video_id"], 0)
                + weight * (0.5 ** (days / 30))
            )

            if event["user_id"] == user_id:
                if event["event_type"] == "view":
                    viewed.add(event["video_id"])

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
                "is_viewed": video["id"] in viewed
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
