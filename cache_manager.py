"""
cache_manager.py
Менеджер кэша для часто используемых данных
"""

import time
from typing import Any, Dict
import threading

class CacheManager:
    """Управление кэшем в памяти"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str, default=None, ttl: int = 60):
        """Получение значения из кэша"""
        with self._lock:
            if key in self._cache:
                cache_time = self._cache_times.get(key, 0)
                if time.time() - cache_time < ttl:
                    return self._cache[key]
        
        return default
    
    def set(self, key: str, value: Any, ttl: int = 60):
        """Установка значения в кэш"""
        with self._lock:
            self._cache[key] = value
            self._cache_times[key] = time.time()
    
    def delete(self, key: str):
        """Удаление значения из кэша"""
        with self._lock:
            self._cache.pop(key, None)
            self._cache_times.pop(key, None)
    
    def clear(self):
        """Очистка всего кэша"""
        with self._lock:
            self._cache.clear()
            self._cache_times.clear()

# Глобальный экземпляр кэш-менеджера
cache = CacheManager()