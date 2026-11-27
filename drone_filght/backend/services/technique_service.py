"""
Shooting Technique Service & Personalized AI Recommendation Engine
스마트폰 촬영 지원 및 드론 시뮬레이션을 위한 맞춤형 AI 촬영 기법 카탈로그 및 추천 서비스

핵심 기능:
1. 확장 가능한 촬영 기법 카탈로그 (스마트폰 지원 vs 실제 드론 전용 구분)
2. 개인화 3요소 추천 알고리즘:
   - (A) 프로젝트 정보 (목적, 장소, 시간대, 피사체, 분위기)
   - (B) 사용자 이전 촬영 기록 (shooting_projects, shooting_analyses, shooting_paths)
   - (C) 커뮤니티 콘텐츠 이용 이력 (interactions: view, like, save, user_preference_scores)
3. 콜드 스타트 (신규 사용자 데이터 부족 시) 기본 추천 Fallback
4. 커뮤니티 콘텐츠 연계 (기법별 데모 영상 조회)
5. 추천 결과, 사용자 선택 및 만족도 피드백 저장 & 선호도 가중치 동적 갱신
"""

import json
import math
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.models.models import (
    User,
    ShootingProject,
    ShootingAnalysis,
    ShootingPath,
    Video,
    Interaction,
    UserPreferenceScore,
    SurveyPreference
)


@dataclass
class TechniqueDefinition:
    technique_id: str
    name: str
    category: str
    description: str
    recommended_scenes: List[str]
    required_environment: Dict[str, Any]
    is_smartphone_supported: bool
    is_drone_only: bool
    related_tags: List[str]
    recommended_composition: str
    precautions: str
    execution_guide: str
    drone_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 기본 내장 촬영 기법 카탈로그 (확장 가능)
# ---------------------------------------------------------------------------
DEFAULT_TECHNIQUES: List[TechniqueDefinition] = [
    TechniqueDefinition(
        technique_id="orbit_poi",
        name="오빗(원형 회전) 촬영",
        category="피사체 중심",
        description="중심 피사체와의 거리를 일정하게 유지한 채 360도 완만하게 원을 그리며 회전 이동하는 대표적인 입체감 연출 기법입니다.",
        recommended_scenes=["단일 조형물/기념비", "중앙 인물", "수변 분수대", "정자/랜드마크"],
        required_environment={"lighting": "주간/골든아워", "space": "반경 4~6m 평탄한 바닥", "obstacles": "보행자 간섭 적음"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["오빗", "회전", "orbit", "피사체강조", "수변/도시", "오빗(원형회전)"],
        recommended_composition="원형 회전 구도 (Orbit POI)",
        precautions="스마트폰을 가슴 높이에 양손으로 밀착하고 발을 11자로 유지하며 천천히 걸으세요.",
        execution_guide="1. 피사체와 4m 거리를 둡니다. 2. 카메라를 피사체에 조준한 채 시계 방향으로 원을 그리며 천천히 보행합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="straight_dronie",
        name="직선 드로니(후방 후진) 촬영",
        category="공간 확장",
        description="피사체 정면에서 시작하여 천천히 뒤로 물러서며 좁은 시야에서 광활한 주변 배경으로 공간감을 드라마틱하게 확장하는 기법입니다.",
        recommended_scenes=["인물 클로즈업 시작", "탁 트인 공원 진입", "자연 숲길", "강변 벤치"],
        required_environment={"lighting": "골든아워/주간 순광", "space": "후방 10~15m 직선 보행로", "obstacles": "후방 장애물 및 턱 없음"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["드로니", "후진", "dronie", "공간확장", "자연/산림", "버드아이 상승"],
        recommended_composition="직선 드로니 구도",
        precautions="뒤로 걸을 때 넘어지지 않도록 사전에 후방 보행 동선을 확인하거나 동행자의 안내를 받으세요.",
        execution_guide="1. 피사체 1m 앞 근접 상태에서 시작. 2. 피사체에 시선을 고정한 채 일정한 보폭으로 뒤로 천천히 후진합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="active_track_thirds",
        name="피사체 삼분할 추적 촬영",
        category="동적 추적",
        description="이동하는 피사체를 화면의 1/3 교차선에 안정적으로 배치한 채 측면 또는 대각선에서 보행 속도를 동기화하여 추적하는 기법입니다.",
        recommended_scenes=["산책하는 인물", "자전거/반려동물 이동", "러닝 트랙", "강변 산책로"],
        required_environment={"lighting": "충분한 자연광", "space": "직선 20m 이상 보행로", "obstacles": "노면 평탄화"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["트래킹", "추적", "tracking", "삼분할", "와이드 트래킹", "액션"],
        recommended_composition="삼분할 추적 구도 (Rule of Thirds)",
        precautions="카메라 앵글의 수평선을 유지하고, 피사체가 프레임 바깥으로 벗어나지 않도록 페이스를 조절하세요.",
        execution_guide="1. 피사체를 우측 1/3 세로선에 위치시킵니다. 2. 피사체의 보행 속도에 맞춰 평행하게 나란히 전진합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="reveal_obstacle",
        name="전경 리빌(장애물 통과 공개) 촬영",
        category="시네마틱 전환",
        description="나무, 기둥, 건축 구조물 등 전경 물체 뒤에서 출발하여 서서히 측면으로 전진하며 숨겨져 있던 웅장한 배경을 극적으로 노출시키는 기법입니다.",
        recommended_scenes=["나무 숲 사이 풍경", "교각 기둥 뒤 도시", "건물 모퉁이 풍경", "조각상 뒤 스카이라인"],
        required_environment={"lighting": "전경-후경 명암 대비 양호", "space": "장애물 우회로 5m", "obstacles": "충돌 위험 없는 고정 구조물"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["리빌", "공개", "reveal", "패럴랙스", "건축/캠퍼스", "패럴랙스 리빌 & 선셋 아크"],
        recommended_composition="전경 리빌 구도 (Foreground Reveal)",
        precautions="구조물과 너무 밀착하지 말고 1~2m 거리를 두고 안전하게 걸어 나가세요.",
        execution_guide="1. 나무나 기둥 뒤에서 카메라를 시작. 2. 우측 또는 좌측 대각선으로 부드럽게 걸어 나오며 후경을 드러냅니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="low_angle_ground",
        name="초저각 로우앵글 지면 촬영",
        category="역동적 시점",
        description="스마트폰 카메라를 지면 10~20cm 높이로 낮추어 지면의 잔디, 흙, 포장 질감을 스치듯 전진하며 피사체와 하늘의 웅장함을 극대화하는 기법입니다.",
        recommended_scenes=["잔디광장 산책", "단풍 낙엽길", "자전거/발걸음 클로즈업", "낮은 화단"],
        required_environment={"lighting": "사광선/역광", "space": "평탄한 노면 10m", "obstacles": "바닥 물웅덩이나 돌부리 주의"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["로우앵글", "지면밀착", "low_angle", "역동적", "자연/산림"],
        recommended_composition="초저각 로우 앵글",
        precautions="카메라 렌즈가 지면에 닿지 않도록 주의하고 스마트폰을 거꾸로 들고 촬영하면 로우앵글 파지가 쉽습니다.",
        execution_guide="1. 스마트폰을 거꾸로 잡고 지면 15cm 높이로 유지. 2. 무릎을 가볍게 굽힌 채 앞으로 낮게 전진합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="negative_space_landscape",
        name="광활한 여백 풍경(네거티브 스페이스) 촬영",
        category="감성 풍경",
        description="화면의 2/3 이상을 탁 트인 하늘이나 수면으로 구성하고 피사체를 한쪽 하단 구석에 작게 배치하여 시원한 개방감과 고요한 서정성을 표현합니다.",
        recommended_scenes=["넓은 바다/호수", "노을 지는 한강 하늘", "끝없는 잔디벌판", "구름 풍경"],
        required_environment={"lighting": "일몰/일출 하늘", "space": "시야 차단 없는 열린 공간", "obstacles": "전방 장애물 전무"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["여백", "풍경", "landscape", "감성", "바다/해안", "하이앵글 팬"],
        recommended_composition="광활한 여백 풍경 (Negative Space)",
        precautions="수평선이 기울어지지 않도록 화면 수평 가이드를 정밀하게 맞추세요.",
        execution_guide="1. 수평선을 화면 하단 1/3선에 맞춥니다. 2. 스마트폰을 안정적으로 고정하고 느린 속도로 패닝하거나 천천히 전진합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="symmetry_reflection",
        name="수면 반영 대칭(시메트리) 촬영",
        category="조형 미학",
        description="호수, 강변 수면 또는 비 온 뒤 바닥의 반영을 화면 정중앙 1:1 대칭 수평선에 배치하여 완벽한 조화와 초현실적 분위기를 연출하는 기법입니다.",
        recommended_scenes=["잔잔한 호수 수면", "강변 반영", "비 온 뒤 포장 광장", "대리석 반사"],
        required_environment={"lighting": "골든아워/역광 순광", "space": "물가 안전 데크", "obstacles": "바람이 적어 수면 잔물결 없음"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["반영", "대칭", "reflection", "symmetry", "수변/도시"],
        recommended_composition="수면 반영 대칭 (Symmetry)",
        precautions="물가에 너무 가까이 접근하지 말고 안전 펜스 안쪽에서 스마트폰을 견고하게 파지하세요.",
        execution_guide="1. 수면 경계선을 정확히 화면 중심 가로선에 배치. 2. 수평 흔들림 없이 카메라를 천천히 좌우로 회전합니다.",
        drone_warning=None
    ),
    TechniqueDefinition(
        technique_id="top_down_overhead",
        name="수직 90도 버드아이 탑다운 촬영",
        category="상공 조감",
        description="상공 50~100m 고도에서 카메라를 90도 직하향으로 내려다보며 지상의 기하학적 도로망, 숲, 파도 패턴을 한눈에 담아내는 기법입니다.",
        recommended_scenes=["교차로 도로 패턴", "해안선 파도 라인", "숲속 미로", "건축물 옥상 조형"],
        required_environment={"lighting": "정오 사광선", "space": "고고도 개활지", "obstacles": "고압선 전무"},
        is_smartphone_supported=False,
        is_drone_only=True,
        related_tags=["버드아이", "탑다운", "top_down", "조감", "수직하강", "탑다운 버티고 & 패닝"],
        recommended_composition="버드아이 구도 (Bird's Eye)",
        precautions="⚠️ 실제 비행 드론 전용: 법정 고도 150m 미만을 준수하고 인구 밀집 지역 상공 비행을 금지합니다.",
        execution_guide="실제 드론 기체 짐벌을 -90도로 틸트 다운한 후 천천히 수직 하강 또는 등속 전진합니다. (스마트폰 환경에서는 지원되지 않습니다)",
        drone_warning="🛸 실제 드론 전용 기법: 상공 50m 이상의 수직 직하강 앵글이 필요하여 현재 스마트폰 환경에서는 안전상 모사할 수 없습니다."
    ),
    TechniqueDefinition(
        technique_id="high_spiral",
        name="고고도 나선 상승(스파이럴) 촬영",
        category="3D 기동",
        description="피사체를 회전 중심으로 삼아 나선형(Spiral) 궤도를 그리며 고도 30m에서 80m까지 급상승하여 3차원 공간을 광대하게 노출하는 고난도 기법입니다.",
        recommended_scenes=["산 정상 전망대", "외딴 등대", "대형 스타디움", "도심 타워"],
        required_environment={"lighting": "골든아워", "space": "반경 50m 상공", "obstacles": "상공 장애물 없음"},
        is_smartphone_supported=False,
        is_drone_only=True,
        related_tags=["스파이럴", "나선상승", "spiral", "고고도", "상승"],
        recommended_composition="나선 상승 구도 (Spiral Climb)",
        precautions="⚠️ 실제 비행 드론 전용: 강력한 상승 모터 출력과 3축 짐벌 오토 트래킹이 필수적입니다.",
        execution_guide="조종기 요(Yaw) 회전과 스로틀(상승)을 대각선으로 동시 입력하며 나선 궤적을 비행합니다.",
        drone_warning="🛸 실제 드론 전용 기법: 80m 이상의 나선형 수직 상승 기동이 필요하여 스마트폰 보행 촬영이 불가합니다."
    ),
    TechniqueDefinition(
        technique_id="high_speed_flyby",
        name="고속 전진 플라이바이 촬영",
        category="다이내믹 액션",
        description="시속 40~60km/h로 피사체 상공이나 측면을 빠르게 스쳐 지나가며 박진감 넘치는 속도감과 배경 압축을 연출하는 시네마틱 기법입니다.",
        recommended_scenes=["달리는 차량", "해안가 모터보트", "익스트림 스포츠", "다리 위 활주"],
        required_environment={"lighting": "쾌청한 자연광", "space": "전방 100m 이상 직선 항로", "obstacles": "시야 차단 장애물 전무"},
        is_smartphone_supported=False,
        is_drone_only=True,
        related_tags=["플라이바이", "고속", "flyby", "액션", "다이내믹"],
        recommended_composition="고속 플라이바이 구도",
        precautions="⚠️ 실제 비행 드론 전용: 전방 센서 장애물 감지 범위 초과 속도이므로 전문 조종사의 목시 비행이 필요합니다.",
        execution_guide="드론의 전진 피치를 70% 이상 가속하여 피사체 측면 10m를 등속 통과합니다.",
        drone_warning="🛸 실제 드론 전용 기법: 시속 40km/h 이상의 고속 비행 기동이 필요하여 스마트폰 보행 촬영이 불가합니다."
    )
]

# ===========================================================================
# 신규 기본 촬영 기법 5종 상수 및 매핑 명세 (Phase 12 핵심 엔진)
# ===========================================================================
BASE_TECH_FORWARD = "FORWARD"
BASE_TECH_LATERAL = "LATERAL"
BASE_TECH_DIAGONAL_REVEAL = "DIAGONAL_REVEAL"
BASE_TECH_ORBIT = "ORBIT"
BASE_TECH_PANORAMA = "PANORAMA"

BASE_TECHNIQUES_5 = [
    BASE_TECH_FORWARD,
    BASE_TECH_LATERAL,
    BASE_TECH_DIAGONAL_REVEAL,
    BASE_TECH_ORBIT,
    BASE_TECH_PANORAMA
]

BASE_TECHNIQUE_METADATA: Dict[str, Dict[str, Any]] = {
    BASE_TECH_FORWARD: {
        "technique_id": BASE_TECH_FORWARD,
        "name": "전진 촬영",
        "category": "직선 접근",
        "description": "피사체 방향으로 시선을 고정하고 천천히 직선으로 접근하여 웅장함과 원근감을 부여하는 기법입니다.",
        "recommended_scenes": ["건축물", "조형물", "단일 피사체", "기념비", "입구", "탑", "조각상"],
        "recommended_composition": "중앙 배치 구도 (Center Framing)",
        "guide_message": "피사체를 바라보며 천천히 앞으로 이동하세요.",
        "requires_walking": True,
        "requires_subject_gps": False
    },
    BASE_TECH_LATERAL: {
        "technique_id": BASE_TECH_LATERAL,
        "name": "측면 이동 촬영",
        "category": "측면 횡이동",
        "description": "피사체를 화면의 특정 분할선에 유지하면서 좌우로 평행 이동하여 입체적인 시선 흐름과 패럴랙스를 연출합니다.",
        "recommended_scenes": ["긴 건축물", "다리", "해안선", "성벽", "가로수길", "수평선", "거리"],
        "recommended_composition": "3x3 삼분할 황금비율 구도 (Rule of Thirds)",
        "guide_message": "피사체를 화면에 유지하면서 오른쪽으로 이동하세요.",
        "requires_walking": True,
        "requires_subject_gps": False
    },
    BASE_TECH_DIAGONAL_REVEAL: {
        "technique_id": BASE_TECH_DIAGONAL_REVEAL,
        "name": "사선 리빌 촬영",
        "category": "사선 전환",
        "description": "전경 요소를 벗어나며 가려져 있던 후경을 드라마틱하게 드러내는 전진과 측면 결합 대각선 이동 기법입니다.",
        "recommended_scenes": ["나무 사이 풍경", "건물 사이 공간", "전망대", "골목 어귀", "전경 모퉁이"],
        "recommended_composition": "전경 리빌 구도 (Foreground Reveal)",
        "guide_message": "전경을 벗어나도록 왼쪽 앞 방향으로 이동하세요.",
        "requires_walking": True,
        "requires_subject_gps": False
    },
    BASE_TECH_ORBIT: {
        "technique_id": BASE_TECH_ORBIT,
        "name": "반원 회전 촬영",
        "category": "반원 선회",
        "description": "피사체의 실측 GPS를 중심으로 일정한 반경의 반원을 그리며 선회 이동하여 3차원 입체감을 극대화합니다.",
        "recommended_scenes": ["독립된 조형물", "건축물", "넓은 광장", "중앙 분수", "단독 기념비"],
        "recommended_composition": "원형 선회 구도 (Orbit Arc)",
        "guide_message": "피사체를 바라보며 반원 방향으로 이동하세요.",
        "requires_walking": True,
        "requires_subject_gps": True
    },
    BASE_TECH_PANORAMA: {
        "technique_id": BASE_TECH_PANORAMA,
        "name": "고정 파노라마 촬영",
        "category": "제자리 회전",
        "description": "보행 이동 없이 현재 위치에 서서 스마트폰 방향 센서의 유도에 따라 수평선을 유지하며 천천히 패닝 회전합니다.",
        "recommended_scenes": ["산", "바다", "도시 전경", "넓은 풍경", "스카이라인", "수평선"],
        "recommended_composition": "수평선 파노라마 구도 (Horizon Panorama)",
        "guide_message": "현재 위치를 유지하고 천천히 오른쪽으로 회전하세요.",
        "requires_walking": False,
        "requires_subject_gps": False
    }
}

LEGACY_TO_BASE_5_MAP: Dict[str, str] = {
    "orbit_poi": BASE_TECH_ORBIT,
    "orbit": BASE_TECH_ORBIT,
    "straight_dronie": BASE_TECH_FORWARD,
    "dronie": BASE_TECH_FORWARD,
    "low_angle_ground": BASE_TECH_FORWARD,
    "low_angle": BASE_TECH_FORWARD,
    "active_track_thirds": BASE_TECH_LATERAL,
    "thirds": BASE_TECH_LATERAL,
    "reveal_obstacle": BASE_TECH_DIAGONAL_REVEAL,
    "reveal": BASE_TECH_DIAGONAL_REVEAL,
    "negative_space_landscape": BASE_TECH_PANORAMA,
    "landscape": BASE_TECH_PANORAMA,
    "symmetry_reflection": BASE_TECH_PANORAMA,
    "symmetry": BASE_TECH_PANORAMA,
    "top_down_overhead": BASE_TECH_FORWARD,
    "high_spiral": BASE_TECH_ORBIT,
    "high_speed_flyby": BASE_TECH_FORWARD
}

BASE_5_TO_LEGACY_MAP: Dict[str, str] = {
    BASE_TECH_FORWARD: "straight_dronie",
    BASE_TECH_LATERAL: "active_track_thirds",
    BASE_TECH_DIAGONAL_REVEAL: "reveal_obstacle",
    BASE_TECH_ORBIT: "orbit_poi",
    BASE_TECH_PANORAMA: "negative_space_landscape"
}


def recommend_technique(
    scene_analysis: Optional[Dict[str, Any]] = None,
    sensor_state: Optional[Dict[str, Any]] = None,
    route_constraints: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    [Phase 12] 5가지 기본 촬영 기법 적합도 점수 산출 및 추천 엔진
    
    입력:
    - scene_analysis: 장면 유형, 피사체, 3단계 공간 레이어, 개활지, 장애물, 가시성 등
    - sensor_state: 스마트폰 센서 (GPS 가용성, 정확도, 방위각, 자이로 등)
    - route_constraints: 보행 경로 제약 (피사체 실측 GPS 여부, 이동 공간 여유 등)

    동작 규칙:
    1. 각 기법별 적합도 점수(0~100) 독립 계산
    2. 실행 불가능한 기법은 추천 점수가 높아도 후보에서 제외 (is_executable=False)
       - ORBIT: 피사체 GPS 실측 좌표가 없으면 반드시 비활성화
       - PANORAMA: 보행 이동 불필요, 방향 센서 기반 회전 유효성 평가
    3. 점수 최상위 기법을 기본 추천하되, 동점/저신뢰도 시 사용자 직접 선택 유도
    """
    sa = scene_analysis or {}
    ss = sensor_state or {}
    rc = route_constraints or {}

    scene_type = str(sa.get("scene_type") or "").lower()
    main_subject = str(sa.get("main_subject") or sa.get("subject") or "").lower()
    foreground = str(sa.get("foreground") or "").lower()
    midground = str(sa.get("midground") or "").lower()
    background = str(sa.get("background") or "").lower()
    open_space = str(sa.get("open_space") or "").lower()
    obstacle_level = str(sa.get("obstacle_level") or "NONE").upper()
    subject_visibility = str(sa.get("subject_visibility") or "CLEAR").upper()

    has_gps = bool(ss.get("has_gps", True))
    gps_accuracy = ss.get("gps_accuracy")
    gps_is_accurate = (gps_accuracy is None or float(gps_accuracy) <= 20.0)

    has_subject_gps = bool(rc.get("has_subject_gps", False))
    subject_lat = rc.get("subject_lat")
    subject_lng = rc.get("subject_lng")
    has_valid_subject_coords = (has_subject_gps and subject_lat is not None and subject_lng is not None)

    scores: Dict[str, float] = {}
    reasons: Dict[str, str] = {}
    feasibility: Dict[str, Dict[str, Any]] = {}

    combined_text = f"{scene_type} {main_subject} {foreground} {midground} {background} {open_space}"

    # -------------------------------------------------------------------------
    # 1. FORWARD (전진 촬영) 스코어링
    # -------------------------------------------------------------------------
    f_score = 50.0
    f_matched = []
    if any(k in combined_text for k in ["건축물", "조형물", "단일 피사체", "기념비", "동상", "입구", "탑", "건물", "문", "성벽"]):
        f_score += 26.0
        f_matched.append("단일 피사체/건축물 정면 구도")
    if obstacle_level in ["NONE", "LOW"] or any(k in open_space for k in ["전방", "직선", "접근", "여유", "보행로"]):
        f_score += 16.0
        f_matched.append("전방 직선 보행 여유 확보")
    if obstacle_level == "HIGH" or "전방 막힘" in open_space:
        f_score -= 22.0
    scores[BASE_TECH_FORWARD] = round(max(10.0, min(98.0, f_score)), 1)
    reasons[BASE_TECH_FORWARD] = " · ".join(f_matched) if f_matched else "피사체 중심 직선 접근 촬영에 적합"
    feasibility[BASE_TECH_FORWARD] = {
        "is_executable": True,
        "reason": "전방 직선 접근 이동 가능"
    }

    # -------------------------------------------------------------------------
    # 2. LATERAL (측면 이동 촬영) 스코어링
    # -------------------------------------------------------------------------
    l_score = 50.0
    l_matched = []
    if any(k in combined_text for k in ["긴 건축물", "다리", "해안선", "성벽", "가로수", "거리", "도로", "선형", "수평"]):
        l_score += 28.0
        l_matched.append("선형 피사체/측면 패럴랙스 효과")
    if any(k in open_space for k in ["측면", "좌우", "평행", "횡", "트랙"]):
        l_score += 14.0
        l_matched.append("좌우 평행 보행 공간 확보")
    scores[BASE_TECH_LATERAL] = round(max(10.0, min(98.0, l_score)), 1)
    reasons[BASE_TECH_LATERAL] = " · ".join(l_matched) if l_matched else "피사체 유지 측면 횡이동에 적합"
    feasibility[BASE_TECH_LATERAL] = {
        "is_executable": True,
        "reason": "측면 평행 이동 가능"
    }

    # -------------------------------------------------------------------------
    # 3. DIAGONAL_REVEAL (사선 리빌 촬영) 스코어링
    # -------------------------------------------------------------------------
    dr_score = 42.0
    dr_matched = []
    has_foreground_element = any(k in foreground for k in ["나무", "기둥", "벽", "장애물", "모퉁이", "전경", "숲"])
    if has_foreground_element:
        dr_score += 32.0
        dr_matched.append("전경 차폐물에서 후경으로의 시각적 전환")
    if obstacle_level in ["MEDIUM", "HIGH"] or subject_visibility == "PARTIALLY_OCCLUDED":
        dr_score += 18.0
        dr_matched.append("전경 장애물 회피 대각선 패턴")
    if not has_foreground_element and obstacle_level == "NONE":
        dr_score -= 25.0
    scores[BASE_TECH_DIAGONAL_REVEAL] = round(max(10.0, min(98.0, dr_score)), 1)
    reasons[BASE_TECH_DIAGONAL_REVEAL] = " · ".join(dr_matched) if dr_matched else "전경 요소를 벗어나며 배경을 드러내는 사선 촬영 패턴"
    feasibility[BASE_TECH_DIAGONAL_REVEAL] = {
        "is_executable": True,
        "reason": "대각선 촬영 패턴 생성 가능 (실제 장애물 회피는 사용자가 육안으로 안전 확인 필요)"
    }

    # -------------------------------------------------------------------------
    # 4. ORBIT (반원 회전 촬영) 스코어링 & 실행 제약 검증
    # -------------------------------------------------------------------------
    o_score = 48.0
    o_matched = []
    if any(k in combined_text for k in ["독립", "조형물", "중앙", "분수", "광장", "기념비", "원형", "동상"]):
        o_score += 26.0
        o_matched.append("중앙 독립 피사체 3차원 입체감 강조")
    if any(k in open_space for k in ["반경", "원형", "광장", "사방", "둘레"]):
        o_score += 15.0
        o_matched.append("피사체 주변 반원 선회 공간 양호")

    # [핵심 제약] 피사체 실측 GPS 및 정확도 미충족 시 실행 불가 처리
    if not has_valid_subject_coords:
        is_orbit_exec = False
        orbit_reason = "피사체의 실제 GPS 좌표가 확보되지 않아 반원 경로 생성이 비활성화되었습니다."
        o_score = max(10.0, o_score - 30.0)
    elif not has_gps or not gps_is_accurate:
        is_orbit_exec = False
        orbit_reason = "GPS 수신 상태 저하(오차 20m 초과 또는 신호 부재)로 인해 반원 궤적 실행이 비활성화되었습니다."
        o_score = max(10.0, o_score - 20.0)
    else:
        is_orbit_exec = True
        orbit_reason = "피사체 실측 GPS 및 이동 반경 공간 확인됨"

    scores[BASE_TECH_ORBIT] = round(max(10.0, min(98.0, o_score)), 1)
    reasons[BASE_TECH_ORBIT] = " · ".join(o_matched) if o_matched else "피사체 중심 반원 선회 연출"
    feasibility[BASE_TECH_ORBIT] = {
        "is_executable": is_orbit_exec,
        "reason": orbit_reason
    }

    # -------------------------------------------------------------------------
    # 5. PANORAMA (고정 파노라마 촬영) 스코어링
    # -------------------------------------------------------------------------
    p_score = 45.0
    p_matched = []
    if any(k in combined_text for k in ["산", "바다", "도시 전경", "넓은 풍경", "스카이라인", "수평선", "호수", "전망", "광활"]):
        p_score += 32.0
        p_matched.append("광활한 풍경 및 스카이라인 조망")
    if foreground in ["없음", "none", ""] or any(k in background for k in ["원경", "하늘", "구름"]):
        p_score += 14.0
        p_matched.append("원경 중심 수평선 구성")
    if any(k in open_space for k in ["개활지", "전망대", "고정", "제자리"]):
        p_score += 10.0
        p_matched.append("제자리 회전 촬영에 최적")
    scores[BASE_TECH_PANORAMA] = round(max(10.0, min(98.0, p_score)), 1)
    reasons[BASE_TECH_PANORAMA] = " · ".join(p_matched) if p_matched else "보행 없는 제자리 패닝 회전 촬영에 적합"
    feasibility[BASE_TECH_PANORAMA] = {
        "is_executable": True,
        "requires_heading_sensor": True,
        "realtime_guidance_capability": "HEADING_SENSOR_REQUIRED (센서 미지원 시 수평선 수동 회전 대체)",
        "reason": "보행 waypoint 없이 제자리 회전 가이드 생성 가능 (실시간 각도 추적은 방향 센서 필요)"
    }

    # -------------------------------------------------------------------------
    # 후보 정렬 및 최적 기법 결정
    # -------------------------------------------------------------------------
    candidates = []
    for tid in BASE_TECHNIQUES_5:
        meta = BASE_TECHNIQUE_METADATA[tid]
        cand = {
            "technique_id": tid,
            "name": meta["name"],
            "category": meta["category"],
            "score": scores[tid],
            "recommendation_reason": reasons[tid],
            "guide_message": meta["guide_message"],
            "recommended_composition": meta["recommended_composition"],
            "requires_walking": meta["requires_walking"],
            "is_executable": feasibility[tid]["is_executable"],
            "feasibility_reason": feasibility[tid]["reason"]
        }
        candidates.append(cand)

    candidates.sort(key=lambda x: (x["is_executable"], x["score"]), reverse=True)

    # 실행 가능한 후보 필터링
    executable_cands = [c for c in candidates if c["is_executable"]]

    if not executable_cands:
        # 모든 보행 기법 불가 시 고정 파노라마로 안전 Fallback
        recommended_tid = BASE_TECH_PANORAMA
        status = "CONFIRMED"
        requires_user_confirmation = False
        prompt_msg = "보행 이동 조건이 제한되어 제자리 [고정 파노라마 촬영]이 추천되었습니다."
    else:
        top_cand = executable_cands[0]
        second_cand = executable_cands[1] if len(executable_cands) > 1 else None

        # 동점(점수 차 5점 미만)이거나 신뢰도 부족(최고점 58점 미만) 시 사용자 확인 요청
        score_diff = (top_cand["score"] - second_cand["score"]) if second_cand else 100.0
        if score_diff < 5.0 or top_cand["score"] < 58.0:
            status = "NEEDS_USER_CHOICE"
            requires_user_confirmation = True
            prompt_msg = f"현장 조건에 부합하는 추천 기법([{top_cand['name']}], [{second_cand['name'] if second_cand else ''}])이 경합 중입니다. 원하시는 기법을 직접 선택해 주세요."
            recommended_tid = top_cand["technique_id"]
        else:
            status = "CONFIRMED"
            requires_user_confirmation = False
            prompt_msg = f"장면 분석 결과 [{top_cand['name']}] 기법이 최적 기법으로 선정되었습니다."
            recommended_tid = top_cand["technique_id"]

    return {
        "status": status,
        "recommended_technique": recommended_tid,
        "requires_user_confirmation": requires_user_confirmation,
        "prompt_message": prompt_msg,
        "scores": scores,
        "candidates": candidates,
        "active_constraints": {
            "has_gps": has_gps,
            "gps_accuracy": gps_accuracy,
            "has_subject_gps": has_subject_gps,
            "subject_coords": {"lat": subject_lat, "lng": subject_lng} if has_valid_subject_coords else None
        }
    }


class ShootingTechniqueService:
    """촬영 기법 카탈로그 및 사용자 맞춤 추천 통합 서비스"""

    def __init__(self):
        self._catalog: Dict[str, TechniqueDefinition] = {}
        for t in DEFAULT_TECHNIQUES:
            self._catalog[t.technique_id] = t
        
        # 신규 5대 기본 기법 카탈로그 등록
        for bid in BASE_TECHNIQUES_5:
            meta = BASE_TECHNIQUE_METADATA[bid]
            self._catalog[bid] = TechniqueDefinition(
                technique_id=bid,
                name=meta["name"],
                category=meta["category"],
                description=meta["description"],
                recommended_scenes=meta["recommended_scenes"],
                required_environment={"space": "지상 보행 또는 고정 회전", "lighting": "자연광"},
                is_smartphone_supported=True,
                is_drone_only=False,
                related_tags=[bid.lower(), meta["name"]],
                recommended_composition=meta["recommended_composition"],
                precautions="보행 시 전방 및 주변 장애물을 육안으로 반드시 확인하세요.",
                execution_guide=meta["guide_message"],
                drone_warning=None
            )

    # -----------------------------------------------------------------------
    # 1. 카탈로그 관리 (동적 등록 및 조회)
    # -----------------------------------------------------------------------
    def register_technique(self, technique: TechniqueDefinition) -> None:
        """신규 촬영 기법 동적 등록 (확장성 확보)"""
        self._catalog[technique.technique_id] = technique

    def get_technique(self, technique_id: str) -> Optional[TechniqueDefinition]:
        return self._catalog.get(technique_id)

    def get_base_5_techniques(self) -> List[Dict[str, Any]]:
        """신규 기본 촬영 기법 5종 메타데이터 목록 반환"""
        return [BASE_TECHNIQUE_METADATA[tid] for tid in BASE_TECHNIQUES_5]

    def map_to_base_5(self, tech_id: str) -> str:
        """기존 10종 기법 ID를 신규 5대 기법 ID로 매핑 (기본값: FORWARD)"""
        if not tech_id:
            return BASE_TECH_FORWARD
        tid = tech_id.strip()
        if tid in BASE_TECHNIQUES_5:
            return tid
        return LEGACY_TO_BASE_5_MAP.get(tid.lower(), BASE_TECH_FORWARD)

    def recommend_technique(
        self,
        scene_analysis: Optional[Dict[str, Any]] = None,
        sensor_state: Optional[Dict[str, Any]] = None,
        route_constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """[Phase 12] 5개 기본 기법 추천 엔진 호출"""
        return recommend_technique(scene_analysis, sensor_state, route_constraints)

    def get_all_techniques(self, filter_supported_only: bool = False) -> List[TechniqueDefinition]:
        techniques = list(self._catalog.values())
        if filter_supported_only:
            techniques = [t for t in techniques if t.is_smartphone_supported]
        return techniques

    # -----------------------------------------------------------------------
    # 2. 개인화 추천 3요소 스코어 계산 엔진
    # -----------------------------------------------------------------------
    def recommend_techniques(
        self,
        db: Session,
        user: Optional[User] = None,
        project: Optional[ShootingProject] = None,
        limit: int = 4,
        smartphone_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        개인화 맞춤 촬영 기법 추천:
        - Factor A (35%): 현재 프로젝트 특성 (장소, 의도, 피사체, 시간대)
        - Factor B (30%): 사용자의 이전 촬영 기록 (shooting_projects, analyses, paths)
        - Factor C (35%): 커뮤니티 콘텐츠 이용 이력 & 선호도 (views, likes, saves, user_preference_scores)
        - 콜드 스타트 Fallback: 신규 사용자 데이터 부족 시 프로젝트 환경 기반 안정적 3~4개 추천
        """
        user_id = user.id if user else (project.user_id if project else None)

        # 1. 프로젝트 컨텍스트 추출
        project_context = self._extract_project_context(project, db)

        # 2. 사용자 이전 촬영 기록 분석 (Factor B)
        history_scores = self._analyze_user_history(db, user_id)

        # 3. 커뮤니티 상호작용 및 선호도 분석 (Factor C)
        pref_scores, interaction_counts = self._analyze_user_preferences(db, user_id)

        # 4. 전체 기법 대상 스코어링
        scored_candidates = []
        is_cold_start = (len(history_scores) == 0 and len(pref_scores) == 0)

        for tid, tech in self._catalog.items():
            if smartphone_only and not tech.is_smartphone_supported:
                continue

            # (A) 프로젝트 적합도 (0~100)
            score_proj, proj_reason = self._compute_project_match(tech, project_context)

            # (B) 사용자 촬영 이력 적합도 (0~100)
            score_hist = history_scores.get(tid, 40.0 if is_cold_start else 20.0)

            # (C) 커뮤니티 선호도 점수 (0~100)
            score_pref = pref_scores.get(tid, 40.0 if is_cold_start else 20.0)

            # 가중치 결합
            # - Cold Start: 프로젝트 적합도 65% + 기본 이력 35%
            # - Warm: 사용자 선호도(취향) 45% + 프로젝트 적합도 30% + 과거 이력 25%
            if is_cold_start:
                total_score = (score_proj * 0.65) + (score_hist * 0.35)
            else:
                total_score = (score_proj * 0.30) + (score_hist * 0.25) + (score_pref * 0.45)

            # 스마트폰 환경 우선권 (스마트폰 지원 기법에 +15점 부여하여 실제 조작 가능한 기법 최우선 노출)
            if tech.is_smartphone_supported:
                total_score += 15.0
            else:
                total_score = max(10.0, total_score - 10.0)

            # 추천 사유 자연어 생성
            reason = self._generate_recommendation_reason(
                tech=tech,
                score_proj=score_proj,
                score_hist=score_hist,
                score_pref=score_pref,
                proj_reason=proj_reason,
                interactions=interaction_counts.get(tid, {}),
                is_cold_start=is_cold_start
            )

            # 관련 커뮤니티 영상 연동 (최대 2건)
            related_vids = self._find_related_videos(db, tech, limit=2)

            scored_candidates.append({
                "technique_id": tech.technique_id,
                "name": tech.name,
                "category": tech.category,
                "description": tech.description,
                "recommendation_score": round(min(99.0, max(25.0, total_score)), 1),
                "recommendation_reason": reason,
                "related_composition": tech.recommended_composition,
                "precautions": tech.precautions,
                "execution_guide": tech.execution_guide,
                "is_smartphone_supported": tech.is_smartphone_supported,
                "is_drone_only": tech.is_drone_only,
                "drone_warning": tech.drone_warning,
                "recommended_scenes": tech.recommended_scenes,
                "required_environment": tech.required_environment,
                "related_tags": tech.related_tags,
                "related_videos": related_vids
            })

        # 내림차순 정렬 및 상위 N개 선택
        scored_candidates.sort(key=lambda x: x["recommendation_score"], reverse=True)
        top_recommendations = scored_candidates[:limit]

        # 프로젝트가 제공된 경우 DB의 recommended_techniques 컬럼 동기화
        if project:
            try:
                rec_ids = [r["technique_id"] for r in top_recommendations]
                project.recommended_techniques = rec_ids
                db.commit()
            except Exception:
                db.rollback()

        return top_recommendations

    # -----------------------------------------------------------------------
    # 3. 내부 분석 및 계산 보조 메서드
    # -----------------------------------------------------------------------
    def _extract_project_context(self, project: Optional[ShootingProject], db: Session) -> Dict[str, Any]:
        """프로젝트의 장소, 시간, 목적, 피사체 특징 추출"""
        if not project:
            return {
                "text": "한강 수변 공원 일몰 풍경 시네마틱 피사체",
                "place": "서울 한강공원",
                "intent": "석양 시네마틱",
                "time_slot": "골든아워"
            }

        text_parts = [
            project.title or "",
            project.place_name or "",
            project.scene_intent or "",
            project.shooting_purpose or "",
            project.recommended_mode or "",
            project.detected_scene or "",
            project.recommended_composition or ""
        ]

        # 최신 AI 분석 결과가 있다면 피사체 및 환경 키워드 보강
        latest_analysis = db.query(ShootingAnalysis).filter(
            ShootingAnalysis.project_id == project.id
        ).order_by(ShootingAnalysis.created_at.desc()).first()

        if latest_analysis:
            if latest_analysis.target_summary:
                text_parts.append(latest_analysis.target_summary)
            if latest_analysis.environment_summary:
                text_parts.append(latest_analysis.environment_summary)

        combined_text = " ".join(text_parts).lower()

        return {
            "text": combined_text,
            "place": project.place_name or "야외",
            "intent": project.scene_intent or project.shooting_purpose or "자유 촬영",
            "time_slot": project.target_time or "주간"
        }

    def _compute_project_match(self, tech: TechniqueDefinition, ctx: Dict[str, Any]) -> Tuple[float, str]:
        """기법과 프로젝트 간의 적합도 점수(0~100) 및 매칭 키워드 분석"""
        text = ctx["text"]
        match_count = 0
        matched_tags = []

        # 1. 태그 매칭
        for tag in tech.related_tags:
            t_low = tag.lower()
            if t_low in text:
                match_count += 2
                matched_tags.append(tag)

        # 2. 추천 씬 매칭
        for scene in tech.recommended_scenes:
            for word in scene.split():
                if len(word) >= 2 and word.lower() in text:
                    match_count += 1
                    if word not in matched_tags:
                        matched_tags.append(word)

        # 3. 환경 키워드 매칭
        env_space = tech.required_environment.get("space", "").lower()
        if any(w in text for w in ["수변", "강변", "공원", "광장", "바다"]) and any(w in env_space for w in ["공간", "평탄", "수변", "데크"]):
            match_count += 1.5

        score = min(95.0, 50.0 + (match_count * 9.0))
        reason = f"[{', '.join(matched_tags[:2])}] 특성과 현재 프로젝트 기획이 부합" if matched_tags else "현장 기본 시네마틱 추천"
        return score, reason

    def _analyze_user_history(self, db: Session, user_id: Optional[int]) -> Dict[str, float]:
        """사용자의 이전 촬영 프로젝트 및 분석 기록 기반 기법 선호도 산출"""
        if not user_id:
            return {}

        history_scores: Dict[str, float] = {}

        # 1. 이전 프로젝트에서 희망/선택했던 기법 집계
        prev_projects = db.query(ShootingProject).filter(ShootingProject.user_id == user_id).all()
        for p in prev_projects:
            desired = p.desired_techniques or []
            if isinstance(desired, str):
                try:
                    desired = json.loads(desired)
                except Exception:
                    desired = [desired]
            for tid in desired:
                history_scores[tid] = history_scores.get(tid, 50.0) + 12.0

        # 2. 이전 AI 분석에서 달성한 구도 점수 가산
        user_analyses = db.query(ShootingAnalysis).join(ShootingProject).filter(
            ShootingProject.user_id == user_id
        ).all()

        for a in user_analyses:
            comp_name = (a.recommended_composition or "").lower()
            for tid, tech in self._catalog.items():
                if tech.recommended_composition.lower() in comp_name or any(t.lower() in comp_name for t in tech.related_tags):
                    bonus = (a.composition_score or 70.0) * 0.15
                    history_scores[tid] = history_scores.get(tid, 50.0) + bonus

        # 0~100 스케일 클램핑
        for k in history_scores:
            history_scores[k] = min(98.0, history_scores[k])

        return history_scores

    def _analyze_user_preferences(
        self,
        db: Session,
        user_id: Optional[int]
    ) -> Tuple[Dict[str, float], Dict[str, Dict[str, int]]]:
        """
        커뮤니티 이용 기록 및 DB user_preference_scores 분석:
        - View: 1.0 (반복 시청: 2.5)
        - Like: 4.0
        - Save: 5.0
        - Project Select: 6.0
        - High Satisfaction (4~5점): 8.0
        """
        if not user_id:
            return {}, {}

        pref_scores: Dict[str, float] = {}
        interaction_counts: Dict[str, Dict[str, int]] = {}

        # 1. DB user_preference_scores 직접 반영 (technique 및 composition 카테고리 중심)
        db_scores = db.query(UserPreferenceScore).filter(UserPreferenceScore.user_id == user_id).all()
        for s in db_scores:
            cat = s.category
            val = s.preference_value
            raw_val = float(s.preference_score or 0.0)

            if cat == "technique":
                if val in self._catalog:
                    pref_scores[val] = max(pref_scores.get(val, 0), raw_val)
            elif cat == "composition":
                norm_val = min(100.0, raw_val * (100.0 / 30.0)) if raw_val <= 30.0 else raw_val
                for tid, tech in self._catalog.items():
                    if val.lower() in tech.recommended_composition.lower() or any(val.lower() == t.lower() for t in tech.related_tags):
                        pref_scores[tid] = max(pref_scores.get(tid, 0), norm_val)

        # 2. interactions 테이블의 활성 이벤트 가중치 집계
        events = db.query(Interaction, Video).join(Video, Interaction.video_id == Video.id).filter(
            Interaction.user_id == user_id,
            Interaction.active == 1
        ).all()

        video_view_counts: Dict[int, int] = {}

        for inter, vid in events:
            etype = inter.event_type.lower()
            vid_techniques = vid.content_techniques or []
            if isinstance(vid_techniques, str):
                try:
                    vid_techniques = json.loads(vid_techniques)
                except Exception:
                    vid_techniques = []

            # 영상의 기법 목록 또는 composition 매칭
            target_tids = list(vid_techniques)
            if not target_tids:
                for tid, tech in self._catalog.items():
                    if tech.recommended_composition.lower() in (vid.composition or "").lower():
                        target_tids.append(tid)

            # 가중치 계산
            if etype == "view":
                video_view_counts[vid.id] = video_view_counts.get(vid.id, 0) + 1
                is_repeat = video_view_counts[vid.id] > 1
                w = 2.5 if is_repeat else 1.0
                e_key = "repeat_view" if is_repeat else "view"
            elif etype == "like":
                w = 4.0
                e_key = "like"
            elif etype == "save":
                w = 5.0
                e_key = "save"
            elif etype == "select":
                w = 6.0
                e_key = "select"
            elif etype in ("satisfaction", "high_rating"):
                w = 8.0
                e_key = "satisfaction"
            else:
                w = 1.0
                e_key = etype

            for tid in target_tids:
                if tid in self._catalog:
                    pref_scores[tid] = pref_scores.get(tid, 35.0) + (w * 4.5)
                    if tid not in interaction_counts:
                        interaction_counts[tid] = {}
                    interaction_counts[tid][e_key] = interaction_counts[tid].get(e_key, 0) + 1

        # 점수 정규화
        for k in pref_scores:
            pref_scores[k] = min(98.0, max(20.0, pref_scores[k]))

        return pref_scores, interaction_counts

    def _generate_recommendation_reason(
        self,
        tech: TechniqueDefinition,
        score_proj: float,
        score_hist: float,
        score_pref: float,
        proj_reason: str,
        interactions: Dict[str, int],
        is_cold_start: bool
    ) -> str:
        """사용자가 직관적으로 납득할 수 있는 개인화 추천 사유 문자열 생성"""
        if is_cold_start:
            if tech.is_smartphone_supported:
                return f"초보자 맞춤 추천: 스마트폰 카메라로 즉시 안정적인 촬영이 가능하며, {proj_reason}입니다."
            else:
                return f"시네마틱 드론 앵글: {proj_reason}이나, 안전을 위해 실제 비행 드론이 권장됩니다."

        reasons = []
        # 상호작용 근거
        if interactions.get("save", 0) > 0:
            reasons.append("회원님이 보관함에 저장하신 영상 기법과 일치")
        elif interactions.get("like", 0) > 0:
            reasons.append("회원님이 좋아요를 누른 영상과 동일한 시네마틱 무빙")
        elif interactions.get("repeat_view", 0) > 0:
            reasons.append("반복 시청하신 커뮤니티 인기 영상 기법")
        elif interactions.get("view", 0) > 0:
            reasons.append("최근 관심 있게 조회하신 촬영 스타일")

        # 과거 촬영 이력 근거
        if score_hist >= 65.0:
            reasons.append("이전 촬영에서 높은 구도 완성도를 달성한 친숙한 기법")

        # 현장 프로젝트 적합성
        if score_proj >= 65.0:
            reasons.append(proj_reason)

        if not reasons:
            reasons.append(proj_reason)

        main_reason = " 및 ".join(reasons[:2])
        if tech.is_smartphone_supported:
            return f"{main_reason}하여 현재 스마트폰 촬영 환경에 가장 이상적입니다."
        else:
            return f"{main_reason}하나, 고고도 비행이 필요한 실제 드론 전용 기법입니다."

    def _find_related_videos(self, db: Session, tech: TechniqueDefinition, limit: int = 2) -> List[Dict[str, Any]]:
        """해당 기법과 연계된 커뮤니티 데모 영상 검색"""
        try:
            videos = db.query(Video).all()
            matched = []

            for v in videos:
                c_techs = v.content_techniques or []
                if isinstance(c_techs, str):
                    try:
                        c_techs = json.loads(c_techs)
                    except Exception:
                        c_techs = []

                is_match = False
                # 1. content_techniques 직접 포함 여부
                if tech.technique_id in c_techs:
                    is_match = True
                # 2. 구도명 매칭
                elif v.composition and any(tag.lower() in v.composition.lower() for tag in tech.related_tags):
                    is_match = True

                if is_match:
                    # 영상 통계 계산
                    v_likes = db.query(Interaction).filter(
                        Interaction.video_id == v.id,
                        Interaction.event_type == "like",
                        Interaction.active == 1
                    ).count()
                    v_views = db.query(Interaction).filter(
                        Interaction.video_id == v.id,
                        Interaction.event_type == "view"
                    ).count()

                    matched.append({
                        "video_id": v.id,
                        "title": v.title,
                        "url": v.url or "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                        "background": v.background,
                        "time_slot": v.time_slot,
                        "composition": v.composition,
                        "likes_count": v_likes,
                        "views_count": v_views
                    })
                    if len(matched) >= limit:
                        break

            return matched
        except Exception:
            return []

    # -----------------------------------------------------------------------
    # 4. 사용자 선택 및 피드백 저장 & 선호도 점수 갱신
    # -----------------------------------------------------------------------
    def record_technique_selection(
        self,
        db: Session,
        user_id: int,
        project_id: int,
        technique_id: str
    ) -> Dict[str, Any]:
        """
        사용자가 추천된 기법 중 실제 촬영할 기법을 최종 선택:
        - ShootingProject.desired_techniques 컬럼에 추가/저장
        - user_preference_scores 에 선택 가중치 6.0점 반영
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise ValueError(f"프로젝트(ID={project_id})를 찾을 수 없습니다.")

        tech = self.get_technique(technique_id)
        if not tech:
            raise ValueError(f"유효하지 않은 기법 ID입니다: {technique_id}")

        # 1. 프로젝트 desired_techniques 갱신
        current_desired = project.desired_techniques or []
        if isinstance(current_desired, str):
            try:
                current_desired = json.loads(current_desired)
            except Exception:
                current_desired = []
        if technique_id not in current_desired:
            current_desired.append(technique_id)
        project.desired_techniques = current_desired

        # 2. 선호도 점수 갱신 (선택 가중치 6.0)
        self._update_preference_score(
            db=db,
            user_id=user_id,
            category="technique",
            preference_value=technique_id,
            weight=6.0
        )

        # 3. 구도 카테고리도 함께 선호도 반영
        self._update_preference_score(
            db=db,
            user_id=user_id,
            category="composition",
            preference_value=tech.recommended_composition,
            weight=6.0
        )

        db.commit()

        return {
            "status": "success",
            "project_id": project_id,
            "selected_technique_id": technique_id,
            "technique_name": tech.name,
            "desired_techniques": project.desired_techniques,
            "message": f"[{tech.name}] 기법이 촬영 목표로 선택되었습니다. 사용자 선호도 점수에 가중치(+6.0)가 반영되었습니다."
        }

    def record_technique_feedback(
        self,
        db: Session,
        user_id: int,
        project_id: int,
        technique_id: str,
        shooting_number: int = 1,
        was_shot: bool = True,
        satisfaction_score: int = 5,
        comment: Optional[str] = None,
        composition_type: Optional[str] = None,
        is_liked: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        촬영 후 사용자 피드백 기록:
        - 실제 촬영 여부 및 만족도(1~5점) 반영
        - 높은 만족도(4~5점)인 경우 선호도 점수 대폭 상향(+8.0점)
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise ValueError(f"프로젝트(ID={project_id})를 찾을 수 없습니다.")

        tech = self.get_technique(technique_id)
        if not tech:
            raise ValueError(f"유효하지 않은 기법 ID입니다: {technique_id}")

        # 1. 기존 동일 피드백 (user_id, project_id, shooting_number, technique_id) 조회 및 중복 검증
        feedback_key = f"{user_id}_{shooting_number}_{technique_id}"

        # 최신 분석 이력 조회
        analysis = db.query(ShootingAnalysis).filter(
            ShootingAnalysis.project_id == project_id
        ).order_by(ShootingAnalysis.created_at.desc()).first()

        prev_feedback = None
        analysis_coords = {}
        if analysis and analysis.target_coordinates and isinstance(analysis.target_coordinates, dict):
            analysis_coords = dict(analysis.target_coordinates)
            # feedbacks_by_key 우선 확인
            by_key = analysis_coords.get("feedbacks_by_key", {})
            if feedback_key in by_key:
                prev_feedback = by_key[feedback_key]
            else:
                # 기존 feedbacks_by_round 호환 확인
                by_round = analysis_coords.get("feedbacks_by_round", {})
                r_item = by_round.get(str(shooting_number))
                if r_item and r_item.get("technique_id") == technique_id and (r_item.get("user_id") is None or r_item.get("user_id") == user_id):
                    prev_feedback = r_item

        # ShootingProject의 analysis_result 백업 확인
        proj_analysis_result = dict(project.analysis_result) if project.analysis_result and isinstance(project.analysis_result, dict) else {}
        if not prev_feedback and proj_analysis_result:
            p_by_key = proj_analysis_result.get("feedbacks_by_key", {})
            if feedback_key in p_by_key:
                prev_feedback = p_by_key[feedback_key]

        # 2. 가중치 계산 함수
        def calc_pref_weight(score: int, shot: bool) -> float:
            if score >= 4:
                w = 8.0
            elif score == 3:
                w = 4.0
            else:
                w = 1.0
            return w if shot else (w * 0.5)

        new_pref_weight = calc_pref_weight(satisfaction_score, was_shot)

        pref_record = db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == user_id,
            UserPreferenceScore.category == "technique",
            UserPreferenceScore.preference_value == technique_id
        ).first()

        # 3. 중복 피드백 검증 및 차분 반영
        if prev_feedback:
            prev_score = prev_feedback.get("satisfaction_score")
            prev_shot = prev_feedback.get("was_shot", True)
            prev_weight = float(prev_feedback.get("applied_weight", calc_pref_weight(prev_score, prev_shot)))

            # 동일 피드백 중복 요청: 점수 추가 가산 방지 (멱등성 보장)
            if prev_score == satisfaction_score and prev_shot == was_shot:
                current_score = float(pref_record.preference_score) if pref_record else 50.0
                return {
                    "status": "already_recorded",
                    "project_id": project_id,
                    "technique_id": technique_id,
                    "satisfaction_score": satisfaction_score,
                    "was_shot": was_shot,
                    "applied_weight": 0.0,
                    "updated_preference_score": current_score,
                    "is_liked": is_liked,
                    "composition_type": composition_type,
                    "message": f"동일 촬영 회차({shooting_number}회차) 피드백이 이미 등록되어 추가 가산되지 않았습니다."
                }

            # 피드백 내용 변경: 이전 가중치와 새 가중치의 차이(delta)만 반영
            delta_weight = new_pref_weight - prev_weight
            updated_score = self._update_preference_score_delta(
                db=db,
                user_id=user_id,
                category="technique",
                preference_value=technique_id,
                delta_weight=delta_weight
            )
            applied_weight = delta_weight
            if composition_type:
                self._update_preference_score_delta(
                    db=db,
                    user_id=user_id,
                    category="composition",
                    preference_value=composition_type,
                    delta_weight=delta_weight
                )
        else:
            # 최초 피드백 반영
            updated_score = self._update_preference_score(
                db=db,
                user_id=user_id,
                category="technique",
                preference_value=technique_id,
                weight=new_pref_weight
            )
            applied_weight = new_pref_weight
            if composition_type:
                self._update_preference_score(
                    db=db,
                    user_id=user_id,
                    category="composition",
                    preference_value=composition_type,
                    weight=new_pref_weight
                )

        # 4. 피드백 메타데이터 저장 (feedbacks_by_key 및 feedbacks_by_round 동시 보존)
        fb_dict = {
            "user_id": user_id,
            "technique_id": technique_id,
            "shooting_number": shooting_number,
            "was_shot": was_shot,
            "satisfaction_score": satisfaction_score,
            "applied_weight": new_pref_weight,
            "comment": comment,
            "composition_type": composition_type,
            "is_liked": is_liked,
            "recorded_at": datetime.utcnow().isoformat()
        }

        if analysis:
            by_key = dict(analysis_coords.get("feedbacks_by_key", {}))
            by_key[feedback_key] = fb_dict
            analysis_coords["feedbacks_by_key"] = by_key

            by_round = dict(analysis_coords.get("feedbacks_by_round", {}))
            by_round[str(shooting_number)] = fb_dict
            analysis_coords["feedbacks_by_round"] = by_round

            analysis_coords["user_feedback"] = fb_dict
            analysis.target_coordinates = analysis_coords

        p_by_key = dict(proj_analysis_result.get("feedbacks_by_key", {}))
        p_by_key[feedback_key] = fb_dict
        proj_analysis_result["feedbacks_by_key"] = p_by_key
        project.analysis_result = proj_analysis_result

        db.commit()

        return {
            "status": "success",
            "project_id": project_id,
            "technique_id": technique_id,
            "satisfaction_score": satisfaction_score,
            "was_shot": was_shot,
            "applied_weight": applied_weight,
            "updated_preference_score": updated_score,
            "is_liked": is_liked,
            "composition_type": composition_type,
            "message": f"[{tech.name}] 만족도 피드백({satisfaction_score}점)이 반영되었습니다. 맞춤 추천 점수가 갱신되었습니다."
        }

    def _update_preference_score_delta(
        self,
        db: Session,
        user_id: int,
        category: str,
        preference_value: str,
        delta_weight: float
    ) -> float:
        """기존 피드백 점수 수정 시 가중치 차분(delta)만 가감 반영"""
        pref = db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == user_id,
            UserPreferenceScore.category == category,
            UserPreferenceScore.preference_value == preference_value
        ).first()

        if pref:
            new_score = min(100.0, max(0.0, float(pref.preference_score or 0.0) + (delta_weight * 3.5)))
            pref.preference_score = round(new_score, 1)
            pref.updated_at = datetime.utcnow()
            return pref.preference_score
        else:
            return self._update_preference_score(db, user_id, category, preference_value, delta_weight)

    def _update_preference_score(
        self,
        db: Session,
        user_id: int,
        category: str,
        preference_value: str,
        weight: float
    ) -> float:
        """user_preference_scores 테이블의 점수를 가중치에 따라 점진적 누적 갱신"""
        pref = db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == user_id,
            UserPreferenceScore.category == category,
            UserPreferenceScore.preference_value == preference_value
        ).first()

        if pref:
            # 점진적 지수 이동 평균 방식 갱신 (최대 100점)
            new_score = min(100.0, float(pref.preference_score or 0.0) + (weight * 3.5))
            pref.preference_score = round(new_score, 1)
            pref.updated_at = datetime.utcnow()
        else:
            new_score = min(100.0, 50.0 + (weight * 4.0))
            pref = UserPreferenceScore(
                user_id=user_id,
                category=category,
                preference_value=preference_value,
                preference_score=round(new_score, 1),
                updated_at=datetime.utcnow()
            )
            db.add(pref)

        return pref.preference_score


# 싱글톤 인스턴스
technique_service = ShootingTechniqueService()
