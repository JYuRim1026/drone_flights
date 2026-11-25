import base64
import hashlib
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Tuple

import requests

try:
    from backend.config import settings
    from backend.external.cache import external_cache
except ImportError:
    from config import settings
    from external.cache import external_cache

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-3.1-flash-lite"
_DEFAULT_FALLBACK_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
)


def _load_assistant_fallback():
    """Lazy import to avoid circular dependencies with ai_assistant."""
    try:
        from backend.services.ai_assistant import get_ai_response, SYSTEM_PROMPT
        return get_ai_response, SYSTEM_PROMPT
    except ImportError:
        try:
            from services.ai_assistant import get_ai_response, SYSTEM_PROMPT
            return get_ai_response, SYSTEM_PROMPT
        except ImportError:
            from ai_assistant import get_ai_response, SYSTEM_PROMPT
            return get_ai_response, SYSTEM_PROMPT


class GeminiClient:
    """
    Google Gemini REST API (v1beta generateContent) 클라이언트 및 오프라인 드론 전문가 폴백 엔진.
    연결 풀(requests.Session), 모델 자동 폴백, 타임아웃 격리, 키 마스킹, 응답 캐싱을 제공합니다.
    """

    _session = requests.Session()

    @staticmethod
    def _mask_secret(text: str, secret: str) -> str:
        if not text:
            return ""
        if secret:
            return text.replace(secret, "***")
        return text

    @staticmethod
    def _build_contents(
        user_prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        contents: List[Dict[str, Any]] = []
        if history:
            for msg in history[-10:]:
                if not isinstance(msg, dict):
                    continue
                raw_role = str(msg.get("role", "user")).lower()
                role = "model" if raw_role in ("assistant", "model", "bot") else "user"
                text = msg.get("content")
                if text is None and isinstance(msg.get("parts"), list):
                    text = "".join(
                        p.get("text", "") for p in msg["parts"] if isinstance(p, dict)
                    )
                text_str = str(text or "").strip()
                if text_str:
                    contents.append({"role": role, "parts": [{"text": text_str}]})

        contents.append({"role": "user", "parts": [{"text": user_prompt}]})
        return contents

    @staticmethod
    def _extract_reply_text(payload: Dict[str, Any]) -> Optional[str]:
        candidates = payload.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            return None
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        texts: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("thought"):
                continue
            part_text = part.get("text")
            if isinstance(part_text, str) and part_text:
                texts.append(part_text)
        joined = "".join(texts).strip()
        return joined or None

    @classmethod
    def _candidate_models(cls, primary_model: Optional[str] = None) -> List[str]:
        configured = getattr(settings, "GEMINI_MODEL", None) or _DEFAULT_MODEL
        fallbacks = getattr(settings, "GEMINI_FALLBACK_MODELS", None) or _DEFAULT_FALLBACK_MODELS
        seen = set()
        models: List[str] = []
        for name in (primary_model, configured, *fallbacks):
            cleaned = (name or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                models.append(cleaned)
        return models

    @classmethod
    def generate_text(
        cls,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        v1beta REST generateContent 엔드포인트(X-goog-api-key 헤더)로 텍스트를 생성합니다.
        성공 시 (응답 텍스트, 사용된 모델명), 실패 시 (None, None)을 반환합니다.
        """
        effective_key = (api_key or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        if not effective_key or not (prompt or "").strip():
            return None, None

        endpoint = (getattr(settings, "GEMINI_API_ENDPOINT", None) or _DEFAULT_ENDPOINT).rstrip("/")
        read_timeout = float(timeout or getattr(settings, "GEMINI_API_TIMEOUT", 10.0))

        payload: Dict[str, Any] = {
            "contents": cls._build_contents(prompt.strip(), history=history),
        }
        if system_instruction and system_instruction.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction.strip()}]
            }
        if generation_config:
            payload["generationConfig"] = generation_config

        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": effective_key,
        }

        models_to_try = cls._candidate_models(primary_model=model)[:2]
        for idx, model_name in enumerate(models_to_try):
            url = f"{endpoint}/{model_name}:generateContent"
            try:
                resp = cls._session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(3.0, read_timeout),
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                logger.warning(
                    "Gemini connection failed or timed out (%s): %s",
                    model_name,
                    cls._mask_secret(str(exc), effective_key),
                )
                break
            except requests.RequestException as exc:
                logger.warning(
                    "Gemini request error (%s): %s",
                    model_name,
                    cls._mask_secret(str(exc), effective_key),
                )
                break

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("Gemini returned invalid JSON (%s)", model_name)
                    continue
                reply = cls._extract_reply_text(data)
                if reply:
                    return reply, model_name
                logger.warning("Gemini returned empty candidate parts (%s)", model_name)
                continue

            logger.warning(
                "Gemini HTTP %s on %s: %s",
                resp.status_code,
                model_name,
                cls._mask_secret(resp.text[:200], effective_key),
            )
            if resp.status_code in (400, 401, 403):
                break
            if idx == len(models_to_try) - 1:
                break

        return None, None

    @classmethod
    def generate_vision(
        cls,
        prompt: str,
        image_base64: str,
        mime_type: str = "image/jpeg",
        system_instruction: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Google Gemini REST API (v1beta generateContent) 멀티모달 이미지 분석.
        이미지(base64)와 프롬프트를 함께 전송하여 JSON 형식 등의 분석 결과를 생성합니다.
        """
        effective_key = (api_key or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        if not effective_key or not (image_base64 or "").strip():
            return None, None

        clean_base64 = image_base64
        if "," in clean_base64:
            header, clean_base64 = clean_base64.split(",", 1)
            if "image/png" in header:
                mime_type = "image/png"
            elif "image/webp" in header:
                mime_type = "image/webp"

        endpoint = (getattr(settings, "GEMINI_API_ENDPOINT", None) or _DEFAULT_ENDPOINT).rstrip("/")
        read_timeout = float(timeout or getattr(settings, "GEMINI_API_TIMEOUT", 10.0))

        parts = [
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": clean_base64.strip()
                }
            },
            {"text": prompt.strip()}
        ]

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }
        if system_instruction and system_instruction.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction.strip()}]
            }

        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": effective_key,
        }

        models_to_try = cls._candidate_models(primary_model=model)[:2]
        for idx, model_name in enumerate(models_to_try):
            url = f"{endpoint}/{model_name}:generateContent"
            try:
                resp = cls._session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(3.0, read_timeout),
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                logger.warning(
                    "Gemini vision connection failed or timed out (%s): %s",
                    model_name,
                    cls._mask_secret(str(exc), effective_key),
                )
                break
            except requests.RequestException as exc:
                logger.warning(
                    "Gemini vision request error (%s): %s",
                    model_name,
                    cls._mask_secret(str(exc), effective_key),
                )
                break

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("Gemini vision returned invalid JSON (%s)", model_name)
                    continue
                reply = cls._extract_reply_text(data)
                if reply:
                    return reply, model_name
                logger.warning("Gemini vision returned empty candidate parts (%s)", model_name)
                continue

            logger.warning(
                "Gemini vision HTTP %s on %s: %s",
                resp.status_code,
                model_name,
                cls._mask_secret(resp.text[:200], effective_key),
            )
            if resp.status_code in (400, 401, 403):
                break
            if idx == len(models_to_try) - 1:
                break

        return None, None

    @classmethod
    def generate_multi_vision(
        cls,
        prompt: str,
        images: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        connect_timeout: float = 3.0,
        read_timeout: float = 6.5,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Google Gemini REST API (v1beta generateContent) 멀티모달 다중 이미지 분석.
        3장의 대표 프레임 등 복수의 이미지를 단일 요청(contents.parts 내 복수 inlineData)으로 전송합니다.

        [보안 및 타임아웃 관리]
        - 단일 모델만 호출 (연쇄 폴백으로 인한 Vercel 10초 실행 제한 초과 방지)
        - 연결 타임아웃(connect_timeout: 기본 3.0초)과 응답 타임아웃(read_timeout: 기본 6.5초) 분리
        - ※ 주의: requests의 timeout=(connect, read) 튜플은 각 소켓 작업 간의 타임아웃이며,
          전체 전송/수신 벽시계 시간(wall-clock time)의 절대 상한을 완전 보장하지는 않습니다.

        [반환값 규격]
        - 성공 시: (정제된 JSON 문자열, 사용된 모델명, None)
        - 이미지 검증 실패 시: (None, None, "IMAGE_VALIDATION_ERROR: ...")
        - API 키 누락 시: (None, None, "API_KEY_MISSING: ...")
        - Gemini API 네트워크/타임아웃 오류 시: (None, None, "GEMINI_TIMEOUT_ERROR: ..." 또는 "GEMINI_API_ERROR: ...")
        - JSON 응답 파싱 실패 시: (None, None, "GEMINI_JSON_DECODE_ERROR: ...")
        """
        # 1. API 키 검증
        effective_key = (api_key or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        if not effective_key:
            logger.warning("[Gemini Multi-Vision] GEMINI_API_KEY가 설정되지 않았습니다.")
            return None, None, "API_KEY_MISSING: Gemini API 키가 설정되지 않았습니다."

        # 2. 프롬프트 유효성 검증
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            return None, None, "INVALID_PROMPT: 분석 프롬프트가 비어 있습니다."

        # 3. 이미지 목록 및 데이터 유효성 검증
        if not isinstance(images, list) or len(images) == 0:
            return None, None, "IMAGE_VALIDATION_ERROR: 이미지 목록이 비어 있거나 올바르지 않은 형식입니다."

        if len(images) > 10:
            return None, None, "IMAGE_VALIDATION_ERROR: 전송 가능한 최대 이미지 개수(10장)를 초과했습니다."

        allowed_mimes = {"image/jpeg", "image/png", "image/webp"}
        image_parts: List[Dict[str, Any]] = []

        for idx, img in enumerate(images):
            if not isinstance(img, dict):
                return None, None, f"IMAGE_VALIDATION_ERROR: {idx+1}번째 이미지 항목이 딕셔너리 객체가 아닙니다."

            raw_b64 = img.get("data") or img.get("base64") or img.get("image_base64") or ""
            if not isinstance(raw_b64, str) or not raw_b64.strip():
                return None, None, f"IMAGE_VALIDATION_ERROR: {idx+1}번째 이미지의 Base64 데이터가 비어 있습니다."

            clean_b64 = raw_b64.strip()
            mime_type = img.get("mime_type") or img.get("mimeType") or "image/jpeg"

            # data URI 스킴 헤더 파싱 (예: data:image/png;base64,...)
            if "," in clean_b64:
                header, clean_b64 = clean_b64.split(",", 1)
                clean_b64 = clean_b64.strip()
                if "image/png" in header:
                    mime_type = "image/png"
                elif "image/webp" in header:
                    mime_type = "image/webp"
                elif "image/jpeg" in header or "image/jpg" in header:
                    mime_type = "image/jpeg"

            if mime_type not in allowed_mimes:
                return None, None, f"IMAGE_VALIDATION_ERROR: {idx+1}번째 이미지의 MIME 형식({mime_type})은 지원되지 않습니다. (지원: JPEG, PNG, WebP)"

            # Base64 디코딩 무결성 검증 (손상된 데이터 전송 방지)
            try:
                decoded = base64.b64decode(clean_b64, validate=True)
                if len(decoded) == 0:
                    return None, None, f"IMAGE_VALIDATION_ERROR: {idx+1}번째 이미지의 바이트 크기가 0입니다."
            except Exception as b64_err:
                return None, None, f"IMAGE_VALIDATION_ERROR: {idx+1}번째 이미지의 Base64 인코딩이 유효하지 않습니다: {b64_err}"

            label = img.get("label") or img.get("title")
            if label and str(label).strip():
                image_parts.append({"text": f"[{str(label).strip()}]"})

            image_parts.append({
                "inlineData": {
                    "mimeType": mime_type,
                    "data": clean_b64
                }
            })

        # 4. Gemini REST API 요청 페이로드 구성
        endpoint = (getattr(settings, "GEMINI_API_ENDPOINT", None) or _DEFAULT_ENDPOINT).rstrip("/")
        # 임의 모델 변경 금지: 기존 설정(GEMINI_MODEL) 또는 기본값 사용
        target_model = (model or getattr(settings, "GEMINI_MODEL", None) or _DEFAULT_MODEL).strip()

        # 프롬프트와 이미지 파트 결합
        request_parts = [{"text": clean_prompt}, *image_parts]

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": request_parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }
        if system_instruction and system_instruction.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction.strip()}]
            }

        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": effective_key,
        }

        url = f"{endpoint}/{target_model}:generateContent"
        start_time = time.monotonic()

        # 5. 단일 모델 전송 및 엄격한 타임아웃/예외 처리
        try:
            resp = cls._session.post(
                url,
                headers=headers,
                json=payload,
                timeout=(float(connect_timeout), float(read_timeout)),
            )
        except requests.exceptions.ConnectTimeout as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.warning("[Gemini Multi-Vision] 연결 시간 초과 (%ss, 경과: %ss): %s", connect_timeout, elapsed, cls._mask_secret(str(exc), effective_key))
            return None, None, f"GEMINI_TIMEOUT_ERROR: Gemini API 서버 연결 시간 초과 ({connect_timeout}초, 경과 {elapsed}초)"
        except requests.exceptions.ReadTimeout as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.warning("[Gemini Multi-Vision] 응답 대기 시간 초과 (%ss, 경과: %ss): %s", read_timeout, elapsed, cls._mask_secret(str(exc), effective_key))
            return None, None, f"GEMINI_TIMEOUT_ERROR: Gemini API 서버 응답 대기 시간 초과 ({read_timeout}초, 경과 {elapsed}초)"
        except requests.exceptions.ConnectionError as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.warning("[Gemini Multi-Vision] 네트워크 연결 실패: %s", cls._mask_secret(str(exc), effective_key))
            return None, None, f"GEMINI_CONNECTION_ERROR: Gemini API 네트워크 연결 실패 ({cls._mask_secret(str(exc), effective_key)})"
        except requests.RequestException as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.warning("[Gemini Multi-Vision] HTTP 요청 예외 (%ss): %s", elapsed, cls._mask_secret(str(exc), effective_key))
            return None, None, f"GEMINI_API_ERROR: Gemini API 요청 실패 ({cls._mask_secret(str(exc), effective_key)})"

        # 6. HTTP 응답 상태 및 본문 검증
        if resp.status_code != 200:
            masked_body = cls._mask_secret(resp.text[:300], effective_key)
            logger.warning("[Gemini Multi-Vision] HTTP %s on %s: %s", resp.status_code, target_model, masked_body)
            return None, None, f"GEMINI_HTTP_ERROR_{resp.status_code}: {masked_body}"

        try:
            data = resp.json()
        except ValueError:
            logger.warning("[Gemini Multi-Vision] 유효하지 않은 JSON 응답 본문 수신")
            return None, None, "GEMINI_PARSE_ERROR: Gemini 응답 본문이 JSON 형식이 아닙니다."

        reply = cls._extract_reply_text(data)
        if not reply:
            logger.warning("[Gemini Multi-Vision] 빈 응답 파트 (candidates empty)")
            return None, None, "GEMINI_EMPTY_CANDIDATE: Gemini 모델이 생성한 텍스트 파트가 비어 있습니다."

        # 7. 생성 텍스트의 JSON 구문 무결성 정제 및 검증
        clean_reply = re.sub(r"^```json\s*", "", reply.strip(), flags=re.MULTILINE)
        clean_reply = re.sub(r"\s*```$", "", clean_reply, flags=re.MULTILINE).strip()

        try:
            json.loads(clean_reply)
        except Exception as json_err:
            logger.warning("[Gemini Multi-Vision] 생성된 텍스트 JSON 파싱 실패: %s (원문: %s)", json_err, clean_reply[:150])
            return None, None, f"GEMINI_JSON_DECODE_ERROR: 생성된 결과물이 유효한 JSON 구조가 아닙니다 ({json_err})"

        return clean_reply, target_model, None

    @classmethod
    def ask_ai(
        cls,
        user_prompt: str,
        location_context: str = "서울 여의도 한강공원",
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        드론 비행/촬영 자연어 질의에 대한 실시간 AI 분석 응답 생성.
        """
        clean_prompt = (user_prompt or "").strip()
        history_hash = (
            hashlib.md5(json.dumps(history, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8]
            if history
            else "nohist"
        )
        cache_key = f"gemini:{clean_prompt}:{location_context}:{history_hash}"
        cached = external_cache.get(cache_key)
        if cached:
            return {**cached, "cached": True}

        get_ai_response, system_prompt = _load_assistant_fallback()

        full_prompt = f"[비행 위치: {location_context}]\n사용자 질문: {clean_prompt}"
        reply_text, model_used = cls.generate_text(
            prompt=full_prompt,
            system_instruction=system_prompt,
            history=history,
        )

        if reply_text and model_used:
            source = f"Google Gemini API ({model_used})"
        else:
            reply_text = get_ai_response(
                clean_prompt,
                context_info={"location": location_context},
                conversation_history=history,
                allow_llm=False,
            )
            source = "드론 항공안전법 & 비행촬영 전문 규칙 엔진 (Offline Core)"

        result = {
            "source": source,
            "cached": False,
            "query": clean_prompt,
            "location_context": location_context,
            "reply": reply_text,
            "confidence_score": 0.95 if model_used else 0.90,
            "safety_notice": "실제 비행 시 현장 기상 상태 및 현장 통제관의 안내를 최우선으로 준수하십시오.",
        }

        if model_used:
            external_cache.set(cache_key, result, ttl=3600)
        return result


gemini_client = GeminiClient()
