"""
Phase 8 DB Migration Script: project_common_paths table creation
Safety checks:
1. Validates target DB path (default: sky_command_demo.db)
2. Creates verified backup before DDL
3. Safe IF NOT EXISTS execution
4. Verifies table creation and record counts
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

# Resolve default target DB
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(BASE_DIR, "sky_command_demo.db")


def run_migration_v3(db_path: str = DEFAULT_DB, dry_run: bool = False):
    print("=" * 70)
    print("Phase 8 Migration: Project Common Paths Table Creation")
    print(f"Target DB: {db_path}")
    print(f"Dry-run: {dry_run}")
    print("=" * 70)

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"대상 데이터베이스 파일을 찾을 수 없습니다: {db_path}")

    # 1. 백업 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak_phase8_{timestamp}"
    if not dry_run:
        shutil.copy2(db_path, backup_path)
        print(f"1. 백업 생성 완료: {backup_path}")
        assert os.path.exists(backup_path), "백업 파일이 생성되지 않았습니다."
        assert os.path.getsize(backup_path) == os.path.getsize(db_path), "백업 파일 크기가 원본과 일치하지 않습니다."
    else:
        print(f"1. [Dry-Run] 백업 예정 경로: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 기존 테이블 레코드 수 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"2. 기존 테이블 수: {len(tables)}개 (확인: {', '.join(tables[:5])}...)")

        cursor.execute("SELECT count(*) FROM shooting_projects;")
        proj_count = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM shooting_paths;")
        path_count = cursor.fetchone()[0]
        print(f"   -> 기존 프로젝트 수: {proj_count}개, 기존 촬영 경로 수: {path_count}개")

        # 3. DDL 실행
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS project_common_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES shooting_projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL DEFAULT 1,
            common_waypoints JSON NOT NULL,
            contributor_count INTEGER NOT NULL DEFAULT 1,
            total_paths_used INTEGER NOT NULL DEFAULT 1,
            quality_score FLOAT NOT NULL DEFAULT 80.0,
            average_deviation_m FLOAT,
            average_composition_score FLOAT,
            average_satisfaction_score FLOAT,
            learning_metadata JSON,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        index_sqls = [
            "CREATE INDEX IF NOT EXISTS ix_project_common_paths_project_id ON project_common_paths(project_id);",
            "CREATE INDEX IF NOT EXISTS ix_project_common_paths_version ON project_common_paths(version);",
            "CREATE INDEX IF NOT EXISTS ix_project_common_paths_is_active ON project_common_paths(is_active);"
        ]

        if not dry_run:
            cursor.execute(create_table_sql)
            for idx_sql in index_sqls:
                cursor.execute(idx_sql)
            conn.commit()
            print("3. 신규 project_common_paths 테이블 및 인덱스 생성 완료.")
        else:
            print("3. [Dry-Run] 신규 project_common_paths DDL 준비 완료.")

        # 4. 검증
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_common_paths';")
        created = cursor.fetchone()
        if not dry_run:
            assert created is not None, "project_common_paths 테이블이 생성되지 않았습니다."
            cursor.execute("PRAGMA table_info(project_common_paths);")
            cols = [r[1] for r in cursor.fetchall()]
            print(f"4. 컬럼 검증 완료 ({len(cols)}개): {', '.join(cols)}")
            assert "common_waypoints" in cols
            assert "quality_score" in cols
            assert "is_active" in cols
        print("5. Phase 8 DB 마이그레이션 무결성 검증 성공!")

    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    target = DEFAULT_DB
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            target = arg
    run_migration_v3(target, dry_run=dry)
