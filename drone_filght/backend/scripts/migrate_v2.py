"""
migrate_v2.py — SkyCommand & Nalyeo-Deuryeo Phase 1 Database Migration Script
=============================================================================
목적:
  - 기존 sky_command.db 또는 sky_command_demo.db에 신규 컬럼 및 신규 테이블을 안전하게 추가
  - 기존 데이터(users, shooting_projects, videos 등)를 100% 무손실 보존
  - 타임스탬프 물리 백업 생성 및 백업 무결성(PRAGMA integrity_check) 자동 검증
  - 마이그레이션 전/후 레코드 수 비교 검증 및 실패 시 자동/수동 롤백 가이드 제공

주의 사항:
  - sky_command.db와 sky_command_demo.db를 동시에 자동 수정하지 않으며,
    반드시 --target 인자로 대상 DB를 명시적으로 지정해야 실행됩니다.
  - 본 스크립트는 사용자의 승인 없이 자동 실행되지 않습니다.
"""

import os
import sys
import shutil
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")


def get_available_databases() -> Dict[str, str]:
    """backend 디렉터리 내 사용 가능한 SQLite 데이터베이스 경로 맵 반환"""
    dbs = {}
    for fname in ["sky_command.db", "sky_command_demo.db", "sky_command_backup_original.db"]:
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.exists(fpath):
            dbs[fname] = fpath
    return dbs


def check_integrity(conn: sqlite3.Connection, db_label: str) -> bool:
    """SQLite PRAGMA integrity_check 수행"""
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    result = cursor.fetchone()
    if result and result[0] == "ok":
        print(f"  [무결성 검사] {db_label}: 정상 (ok)")
        return True
    else:
        print(f"  [무결성 오류] {db_label}: {result}")
        return False


def get_table_row_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """데이터베이스 내 모든 일반 테이블의 레코드 수 측정"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
    tables = [row[0] for row in cursor.fetchall()]
    counts = {}
    for tbl in sorted(tables):
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        counts[tbl] = cursor.fetchone()[0]
    return counts


def create_backup(db_path: str) -> str:
    """대상 DB의 타임스탬프 물리 백업 파일 생성 및 무결성 검증"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = os.path.splitext(os.path.basename(db_path))[0]
    backup_path = os.path.join(BACKUP_DIR, f"{db_name}_backup_{timestamp}.db")

    print(f"\n[1단계: 안전 물리 백업 생성]")
    print(f"  원본 DB: {db_path} ({os.path.getsize(db_path):,} bytes)")
    shutil.copy2(db_path, backup_path)
    print(f"  백업 파일 생성 완료: {backup_path} ({os.path.getsize(backup_path):,} bytes)")

    # 백업 무결성 확인
    with sqlite3.connect(backup_path) as bkp_conn:
        if not check_integrity(bkp_conn, f"백업 파일 ({os.path.basename(backup_path)})"):
            raise RuntimeError("백업 파일의 무결성 검증에 실패했습니다. 마이그레이션을 즉시 중단합니다.")
    return backup_path


def get_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """테이블의 현재 컬럼 목록 조회"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    return [row[1] for row in cursor.fetchall()]


def run_migration(db_path: str, dry_run: bool = False) -> bool:
    """
    지정된 단일 DB 파일에 대해 Phase 1 마이그레이션 실행
    1. 원본 무결성 검사
    2. 물리 백업 생성 및 검증
    3. 전/후 레코드 수 측정
    4. DDL(ALTER TABLE, CREATE TABLE, INDEX) 적용
    5. NULL 데이터 초기화 (DEFAULT '[]')
    6. 레코드 보존 여부 대조 검증
    """
    if not os.path.exists(db_path):
        print(f"[오류] 대상 데이터베이스를 찾을 수 없습니다: {db_path}")
        return False

    print("=" * 70)
    print(f"SkyCommand Phase 1 DB 마이그레이션 시작: {os.path.basename(db_path)}")
    print(f"대상 경로: {db_path}")
    print(f"모드: {'DRY RUN (실행 시뮬레이션)' if dry_run else '실제 적용 (APPLY)'}")
    print("=" * 70)

    # 1. 원본 무결성 검사
    with sqlite3.connect(db_path) as conn:
        if not check_integrity(conn, "원본 대상 DB"):
            print("[오류] 원본 DB의 무결성이 훼손되어 있습니다. 마이그레이션을 중단합니다.")
            return False

        # 마이그레이션 전 레코드 수 기록
        before_counts = get_table_row_counts(conn)
        print("\n[마이그레이션 전 테이블 레코드 수]")
        for tbl, cnt in before_counts.items():
            print(f"  - {tbl}: {cnt:,} 행")

    if dry_run:
        print("\n[DRY RUN 완료] 실제 파일 수정 없이 사전 검사 및 상태 점검을 마쳤습니다.")
        return True

    # 2. 물리 백업 생성
    backup_file = create_backup(db_path)

    # 3. DDL 및 DML 적용
    print("\n[2단계: 스키마 확장 및 신규 테이블 생성]")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")  # 스키마 변경 중 외래키 제약 임시 비활성화

        # (1) shooting_projects 테이블 컬럼 확장
        sp_cols = get_columns(conn, "shooting_projects")
        if "desired_techniques" not in sp_cols:
            print("  + shooting_projects.desired_techniques (JSON) 컬럼 추가")
            cursor.execute("ALTER TABLE shooting_projects ADD COLUMN desired_techniques JSON DEFAULT '[]';")
        else:
            print("  = shooting_projects.desired_techniques 이미 존재 (건너뜀)")

        if "recommended_techniques" not in sp_cols:
            print("  + shooting_projects.recommended_techniques (JSON) 컬럼 추가")
            cursor.execute("ALTER TABLE shooting_projects ADD COLUMN recommended_techniques JSON DEFAULT '[]';")
        else:
            print("  = shooting_projects.recommended_techniques 이미 존재 (건너뜀)")

        # 기존 레코드의 NULL 값을 '[]'로 안전 초기화
        cursor.execute("UPDATE shooting_projects SET desired_techniques = '[]' WHERE desired_techniques IS NULL;")
        cursor.execute("UPDATE shooting_projects SET recommended_techniques = '[]' WHERE recommended_techniques IS NULL;")

        # (2) videos 테이블 컬럼 확장
        v_cols = get_columns(conn, "videos")
        if "content_techniques" not in v_cols:
            print("  + videos.content_techniques (JSON) 컬럼 추가")
            cursor.execute("ALTER TABLE videos ADD COLUMN content_techniques JSON DEFAULT '[]';")
        else:
            print("  = videos.content_techniques 이미 존재 (건너뜀)")

        cursor.execute("UPDATE videos SET content_techniques = '[]' WHERE content_techniques IS NULL;")

        # (3) 신규 테이블 1: shooting_paths 생성 (스마트폰 보행 동선 및 센서 방향각 저장)
        print("  + shooting_paths 테이블 생성 (없을 시)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shooting_paths (
                path_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                user_id INTEGER,
                shooting_number INTEGER NOT NULL DEFAULT 1,
                tracking_source VARCHAR(30) NOT NULL DEFAULT 'PHONE_GPS',
                recommended_waypoints JSON DEFAULT '[]',
                actual_waypoints JSON DEFAULT '[]',
                corrected_waypoints JSON DEFAULT '[]',
                alpha_weight FLOAT NOT NULL DEFAULT 0.3,
                deviation_score FLOAT,
                deviation_reason TEXT,
                is_valid BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES shooting_projects(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                CONSTRAINT uq_project_shooting_number UNIQUE (project_id, shooting_number)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_shooting_paths_project_id ON shooting_paths(project_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_shooting_paths_user_id ON shooting_paths(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_shooting_paths_shooting_number ON shooting_paths(shooting_number);")

        # (4) 신규 테이블 2: location_assets 생성 (스마트폰 현장 촬영 자료 및 객체 특징점)
        print("  + location_assets 테이블 생성 (없을 시)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS location_assets (
                asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                user_id INTEGER,
                is_common BOOLEAN NOT NULL DEFAULT 0,
                asset_type VARCHAR(50) NOT NULL,
                file_url VARCHAR(500) NOT NULL,
                thumbnail_url VARCHAR(500),
                detected_features JSON DEFAULT '{}',
                file_size_bytes INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES shooting_projects(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_location_assets_project_id ON location_assets(project_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_location_assets_user_id ON location_assets(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_location_assets_is_common ON location_assets(is_common);")

        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.close()
        print("  -> DDL 및 컬럼 초기화 정상 완료")

    except Exception as e:
        print(f"\n[치명적 오류 발생] 마이그레이션 중 예외가 발생했습니다: {e}")
        print("\n[긴급 복구 가이드]")
        print(f"  백업 파일로부터 원본을 복구하려면 다음 명령을 실행하세요:")
        print(f"  python -c \"import shutil; shutil.copy2('{backup_file}', '{db_path}'); print('복원 완료')\"")
        return False

    # 4. 마이그레이션 후 무결성 및 레코드 보존 대조 검증
    print("\n[3단계: 마이그레이션 후 사후 검증]")
    with sqlite3.connect(db_path) as conn:
        if not check_integrity(conn, "마이그레이션 완료 DB"):
            print("[오류] 마이그레이션 후 무결성 검사에 실패했습니다!")
            return False

        after_counts = get_table_row_counts(conn)
        print("\n[기존 데이터 보존 대조표]")
        has_mismatch = False
        for tbl, b_cnt in before_counts.items():
            a_cnt = after_counts.get(tbl, 0)
            status = "일치 (보존 성공)" if b_cnt == a_cnt else "불일치 (데이터 변경 감지!)"
            if b_cnt != a_cnt:
                has_mismatch = True
            print(f"  - {tbl:<24}: 이전 {b_cnt:>4} 행 -> 이후 {a_cnt:>4} 행 [{status}]")

        if has_mismatch:
            print("\n[경고] 기존 테이블 레코드 수가 일치하지 않습니다. 백업을 확인하세요.")
            return False

        print(f"\n  신규 테이블 shooting_paths: {after_counts.get('shooting_paths', 0)} 행 (정상 생성)")
        print(f"  신규 테이블 location_assets: {after_counts.get('location_assets', 0)} 행 (정상 생성)")

    print("\n" + "=" * 70)
    print(f"SUCCESS: {os.path.basename(db_path)} 마이그레이션이 성공적으로 완료되었습니다!")
    print(f"안전 백업 보관 위치: {backup_file}")
    print("=" * 70)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="SkyCommand & Nalyeo-Deuryeo Phase 1 DB 마이그레이션 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 1. 상태 점검 및 시뮬레이션 (수정 없음)
  python backend/scripts/migrate_v2.py --target sky_command.db --dry-run

  # 2. 로컬 실제 DB에 마이그레이션 적용
  python backend/scripts/migrate_v2.py --target sky_command.db

  # 3. 데모/배포용 DB에 마이그레이션 적용
  python backend/scripts/migrate_v2.py --target sky_command_demo.db
"""
    )
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="마이그레이션 대상 DB 파일명 또는 경로 (예: sky_command.db 또는 sky_command_demo.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 쿼리를 실행하지 않고 무결성 및 레코드 수만 점검합니다."
    )

    args = parser.parse_args()

    # 대상 경로 해결
    target_path = args.target
    if not os.path.isabs(target_path):
        # 1차 시도: backend 디렉터리 기준
        candidate = os.path.join(BASE_DIR, target_path)
        if os.path.exists(candidate):
            target_path = candidate
        elif not os.path.exists(target_path):
            print(f"[오류] 데이터베이스 파일을 찾을 수 없습니다: {args.target}")
            available = get_available_databases()
            print("현재 존재하는 DB 목록:")
            for name, path in available.items():
                print(f"  - {name} ({path})")
            sys.exit(1)

    success = run_migration(target_path, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
