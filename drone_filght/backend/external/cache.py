import time
import threading
from typing import Any, Optional, Dict

class TTLCache:
    """
    스레드 안전(Thread-safe) 메모리 내 TTL(Time-To-Live) 캐시 모듈.
    외부 API 호출 제한(Rate Limit)을 방지하고 응답 속도를 극대화합니다.
    """
    def __init__(self, default_ttl: int = 600, max_size: int = 2000):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                self.misses += 1
                return None
            
            # Check expiration
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                self.misses += 1
                return None
            
            self.hits += 1
            return entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            # Simple eviction if size exceeded
            if len(self._cache) >= self.max_size:
                now = time.time()
                # 1. Remove expired keys
                expired = [k for k, v in self._cache.items() if now > v["expires_at"]]
                for k in expired:
                    del self._cache[k]
                
                # 2. If still full, pop oldest 10%
                if len(self._cache) >= self.max_size:
                    keys_to_remove = list(self._cache.keys())[:int(self.max_size * 0.1)]
                    for k in keys_to_remove:
                        del self._cache[k]

            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + effective_ttl,
                "created_at": time.time()
            }

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_ratio = round(self.hits / total * 100, 1) if total > 0 else 0.0
            return {
                "items_count": len(self._cache),
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio_percent": hit_ratio
            }

# 전역 외부 API 캐시 인스턴스
external_cache = TTLCache(default_ttl=600, max_size=3000)
