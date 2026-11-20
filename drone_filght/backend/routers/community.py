"""
Community & Video Recommendation Router
커뮤니티 영상 추천 및 사용자 선호도 분석 엔드포인트
- 개인화 추천 영상 조회 (/api/community/videos)
- 영상 상호작용 기록: 조회, 좋아요, 좋아요 취소, 저장, 저장 취소 (/api/community/interactions)
- 사용자 설문 선호도 설정 및 조회 (/api/community/preferences)
- 신규 커뮤니티 영상 등록 (/api/community/videos)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.services.video_recommender import VideoRecommender
from backend.services.auth_service import auth_service
from backend.database import get_db
from sqlalchemy.orm import Session
from backend.models import models

router = APIRouter(prefix="/community", tags=["Community & Video Recommendations"])

# 지연 초기화(Lazy Loading) 프록시: 서버 부팅 시점이 아닌 실제 커뮤니티 API 호출 시점에 안전하게 초기화
_recommender_instance: Optional[VideoRecommender] = None

def get_recommender() -> VideoRecommender:
    global _recommender_instance
    if _recommender_instance is None:
        _recommender_instance = VideoRecommender()
    return _recommender_instance

class _LazyRecommenderProxy:
    def __getattr__(self, name):
        return getattr(get_recommender(), name)

recommender = _LazyRecommenderProxy()


# -------------------------------------------------------------
# Pydantic Schemas
# -------------------------------------------------------------
class InteractionRequest(BaseModel):
    video_id: int = Field(..., description="영상 고유 ID")
    action: str = Field(..., description="행동 구분: 'view', 'like', 'unlike', 'save', 'unsave'")
    user_id: Optional[int] = Field(None, description="조종사 user_id (생략 시 인증 토큰 또는 기본 테스트 계정 사용)")

class SurveyPreferenceItem(BaseModel):
    category: str = Field(..., description="카테고리 ('background', 'time_slot', 'composition')")
    value: str = Field(..., description="선택 값 (예: '수변/도시', '골든아워', '와이드 트래킹')")
    strength: float = Field(5.0, ge=0.0, le=5.0, description="선호 강도 (0~5)")

class SurveyPreferencesRequest(BaseModel):
    preferences: List[SurveyPreferenceItem]
    user_id: Optional[int] = None

class VideoCreateRequest(BaseModel):
    title: str = Field(..., description="영상 제목")
    url: Optional[str] = Field("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4", description="영상 URL")
    background: str = Field(..., description="배경 (예: '수변/도시', '자연/산림', '바다/해안', '건축/캠퍼스')")
    time_slot: str = Field(..., description="촬영 시간대 (예: '주간', '골든아워', '일몰/매직아워', '야간')")
    composition: str = Field(..., description="촬영 구도 (예: '와이드 트래킹', '오빗(원형회전)', '버드아이 상승', '하이앵글 팬')")


def resolve_user_id(explicit_uid: Optional[int], auth_header: Optional[str], db: Session) -> int:
    """토큰 또는 파라미터에서 user_id를 확인, 없으면 기본 테스트 계정(user_id=20 또는 첫 유저) 반환"""
    if explicit_uid:
        return explicit_uid
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        user = auth_service.get_current_user_from_token(db, token)
        if user and user.user_id:
            return user.user_id
    # 기본 계정 확인 (user_id=20 우선, 없으면 첫 번째 유저)
    u = db.query(models.User).filter(models.User.user_id == 20).first()
    if u:
        return u.user_id
    first_u = db.query(models.User).first()
    return first_u.user_id if first_u else 1


# -------------------------------------------------------------
# 1. 커뮤니티 영상 목록 추천 조회 (추천순, 인기순, 최신순)
# -------------------------------------------------------------
@router.get("/videos", summary="커뮤니티 맞춤형 영상 목록 조회")
def get_community_videos(
    sort: str = Query("recommended", description="정렬 방식: 'recommended'(개인화추천), 'popular'(인기순), 'latest'(최신순)"),
    limit: int = Query(20, ge=1, le=100, description="조회 개수"),
    user_id: Optional[int] = Query(None, description="조종사 ID"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        uid = resolve_user_id(user_id, authorization, db)
        videos = recommender.recommend(user_id=uid, sort=sort, limit=limit)
        return {
            "status": "success",
            "user_id": uid,
            "sort": sort,
            "count": len(videos),
            "videos": videos
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------
# 2. 영상 상호작용 기록 (조회, 좋아요, 좋아요 취소, 저장, 저장 취소)
# -------------------------------------------------------------
@router.post("/interactions", summary="영상 이용 기록 저장 (조회/좋아요/저장 및 취소)")
def record_interaction(
    payload: InteractionRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        uid = resolve_user_id(payload.user_id, authorization, db)
        action = payload.action.strip().lower()

        stats = recommender.record_interaction(user_id=uid, video_id=payload.video_id, action=action)

        msg_map = {
            "view": "영상 조회가 기록되었습니다. (조회수 +1)",
            "like": "좋아요를 반영했습니다. 취향 선호도가 갱신됩니다.",
            "unlike": "좋아요를 취소했습니다.",
            "save": "영상을 보관함에 저장했습니다.",
            "unsave": "영상 저장을 취소했습니다."
        }

        return {
            "status": "success",
            "action": action,
            "user_id": uid,
            "video_id": payload.video_id,
            "message": msg_map.get(action, "이용 기록이 반영되었습니다."),
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------
# 3. 사용자 선호도 점수 조회
# -------------------------------------------------------------
@router.get("/preferences", summary="사용자별 선호도 점수 목록 조회")
def get_user_preferences(
    user_id: Optional[int] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        uid = resolve_user_id(user_id, authorization, db)
        scores = recommender.get_preference_scores(user_id=uid)
        return {
            "status": "success",
            "user_id": uid,
            "count": len(scores),
            "preferences": scores
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------
# 4. 사용자 설문 선호도 등록/갱신
# -------------------------------------------------------------
@router.post("/preferences", summary="사용자 초기 설문 선호도 등록/수정")
def save_survey_preferences(
    payload: SurveyPreferencesRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        uid = resolve_user_id(payload.user_id, authorization, db)
        for item in payload.preferences:
            recommender.set_survey_preference(
                user_id=uid,
                category=item.category,
                value=item.value,
                strength=item.strength
            )
        
        updated_scores = recommender.get_preference_scores(user_id=uid)
        return {
            "status": "success",
            "user_id": uid,
            "message": f"{len(payload.preferences)}개 선호도 항목이 반영되었습니다. 맞춤 추천이 갱신됩니다.",
            "updated_preferences": updated_scores
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------
# 5. 신규 커뮤니티 영상 등록
# -------------------------------------------------------------
@router.post("/videos", summary="새 커뮤니티 영상 등록")
def add_new_video(payload: VideoCreateRequest):
    try:
        new_id = recommender.add_video(
            title=payload.title,
            url=payload.url or "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
            background=payload.background,
            time_slot=payload.time_slot,
            composition=payload.composition
        )
        return {
            "status": "success",
            "video_id": new_id,
            "message": "커뮤니티에 영상이 성공적으로 등록되었습니다."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
