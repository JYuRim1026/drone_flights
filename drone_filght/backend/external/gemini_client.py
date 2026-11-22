import hashlib
import json
import logging
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
