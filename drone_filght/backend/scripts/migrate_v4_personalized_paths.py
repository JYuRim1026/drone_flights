"""
Phase 9 DB Migration Script: personalized_shooting_paths table creation
Safety checks:
1. Validates target DB path (default: sky_command_demo.db)
2. Safe IF NOT EXISTS execution
3. Verifies table creation and record counts
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(BASE_DIR, "sky_command_demo.db")


def run_migration_v4(db_path: str = DEFAULT_DB, dry_run: bool = False):
    print("=" * 70)
    print("Phase 9 Migration: Personalized Shooting Paths Table Creation")
    print(f"Target DB: {db_path}")
    print(f"Dry-run: {dry_run}")
    print("=" * 70)

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"대상 데이터베이스 파일을 찾을 수 없습니다: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 기존 테이블 레코드 수 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"1. 기존 테이블 수: {len(tables)}개")

        # DDL 실행
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS personalized_shooting_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES shooting_projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            common_path_id INTEGER REFERENCES project_common_paths(id) ON DELETE SET NULL,
            base_common_version INTEGER NOT NULL DEFAULT 1,
            variation_type VARCHAR(50) NOT NULL DEFAULT 'STRAIGHT',
            personalized_waypoints JSON NOT NULL DEFAULT '[]',
            generation_reason TEXT NOT NULL,
            style_metadata JSON DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        index_sqls = [
            "CREATE INDEX IF NOT EXISTS ix_personalized_paths_project_id ON personalized_shooting_paths (project_id);",
            "CREATE INDEX IF NOT EXISTS ix_personalized_paths_user_id ON personalized_shooting_paths (user_id);",
            "CREATE INDEX IF NOT EXISTS ix_personalized_paths_var_type ON personalized_shooting_paths (variation_type);",
            "CREATE INDEX IF NOT EXISTS ix_personalized_paths_is_active ON personalized_shooting_paths (is_active);"
        ]

        if dry_run:
            print("2. [Dry-Run] 실행 예정 DDL:")
            print(create_table_sql)
            for idx in index_sqls:
                print(f"   {idx}")
        else:
            print("2. DDL 실행 중...")
            cursor.execute(create_table_sql)
            for idx in index_sqls:
                cursor.execute(idx)
            conn.commit()
            print("   -> 테이블 및 인덱스 생성 완료.")

            # 검증
            cursor.execute("PRAGMA table_info(personalized_shooting_paths);")
            columns = cursor.fetchall()
            print(f"3. 생성된 컬럼 수: {len(columns)}개")
            for col in columns:
                print(f"   - {col[1]} ({col[2]})")

            cursor.execute("SELECT count(*) FROM personalized_shooting_paths;")
            count = cursor.fetchone()[0]
            print(f"4. 현재 레코드 수: {count}건")

        print("=" * 70)
        print("🎉 Phase 9 Migration Successfully Completed!")
        print("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    run_migration_v4(dry_run=is_dry)
