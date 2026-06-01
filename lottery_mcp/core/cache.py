
"""
持久化缓存模块 - 多级缓存架构
================================
缓存层级:
1. L1: 内存缓存 (最快，进程内)
2. L2: 本地文件缓存 (持久化，跨进程)
3. L3: Redis缓存 (分布式，可选)

数据质量监控:
- 缓存命中率追踪
- 数据新鲜度验证
- 异常数据标记
"""

import json
import hashlib
import logging
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
import threading

logger = logging.getLogger("lottery_mcp")


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    data: Any
    created_at: float
    expires_at: float
    data_source: str = "unknown"
    data_version: str = "1.0"
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self) -&gt; bool:
        return time.time() &gt; self.expires_at
    
    def to_dict(self) -&gt; Dict:
        return {
            "key": self.key,
            "data": self.data,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "data_source": self.data_source,
            "data_version": self.data_version,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -&gt; "CacheEntry":
        return cls(**d)


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0
    
    @property
    def hit_rate(self) -&gt; float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests
    
    def to_dict(self) -&gt; Dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
            "hit_rate": self.hit_rate,
        }


class DataQualityMonitor:
    """数据质量监控器"""
    
    def __init__(self):
        self.quality_scores: Dict[str, float] = {}
        self.anomaly_counts: Dict[str, int] = {}
        self.last_updated: Dict[str, float] = {}
    
    def record_quality_score(self, data_type: str, score: float):
        """记录数据质量分数"""
        self.quality_scores[data_type] = score
        self.last_updated[data_type] = time.time()
    
    def record_anomaly(self, data_type: str):
        """记录异常"""
        self.anomaly_counts[data_type] = self.anomaly_counts.get(data_type, 0) + 1
    
    def get_quality_report(self) -&gt; Dict[str, Any]:
        """获取质量报告"""
        return {
            "quality_scores": self.quality_scores,
            "anomaly_counts": self.anomaly_counts,
            "last_updated": self.last_updated,
            "overall_score": sum(self.quality_scores.values()) / len(self.quality_scores) if self.quality_scores else 0,
        }


class CacheManager:
    """持久化缓存管理器"""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl: int = 3600,
        max_memory_entries: int = 1000,
        enable_file_cache: bool = True,
    ):
        self.default_ttl = default_ttl
        self.max_memory_entries = max_memory_entries
        self.enable_file_cache = enable_file_cache
        
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.cache_dir = project_root / ".cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats = CacheStats()
        self.quality_monitor = DataQualityMonitor()
        self._load_persistent_cache()
    
    def _get_cache_file_path(self, key: str) -&gt; Path:
        key_hash = hashlib.md5(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.json"
    
    def _load_persistent_cache(self):
        if not self.enable_file_cache:
            return
        
        try:
            loaded_count = 0
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        entry_dict = json.load(f)
                        entry = CacheEntry.from_dict(entry_dict)
                        
                        if not entry.is_expired():
                            self._memory_cache[entry.key] = entry
                            loaded_count += 1
                        else:
                            cache_file.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"加载缓存文件失败 {cache_file}: {e}")
            
            if loaded_count &gt; 0:
                logger.info(f"从持久化缓存加载了 {loaded_count} 条记录")
        except Exception as e:
            logger.error(f"加载持久化缓存失败: {e}")
    
    def _save_to_file(self, entry: CacheEntry):
        if not self.enable_file_cache:
            return
        
        try:
            cache_file = self._get_cache_file_path(entry.key)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(entry.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存到文件失败: {e}")
    
    def _evict_if_needed(self):
        if len(self._memory_cache) &lt; self.max_memory_entries:
            return
        
        sorted_entries = sorted(
            self._memory_cache.items(),
            key=lambda x: x[1].last_accessed
        )
        
        to_evict = sorted_entries[:len(sorted_entries) // 10]
        for key, entry in to_evict:
            del self._memory_cache[key]
            self.stats.evictions += 1
            
            if self.enable_file_cache:
                cache_file = self._get_cache_file_path(key)
                cache_file.unlink(missing_ok=True)
    
    def get(self, key: str) -&gt; Optional[Any]:
        with self._lock:
            self.stats.total_requests += 1
            
            entry = self._memory_cache.get(key)
            if entry is None:
                self.stats.misses += 1
                return None
            
            if entry.is_expired():
                del self._memory_cache[key]
                self.stats.misses += 1
                
                if self.enable_file_cache:
                    cache_file = self._get_cache_file_path(key)
                    cache_file.unlink(missing_ok=True)
                return None
            
            entry.access_count += 1
            entry.last_accessed = time.time()
            self.stats.hits += 1
            
            return entry.data
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        data_source: str = "unknown",
        data_version: str = "1.0",
    ):
        ttl = ttl or self.default_ttl
        
        with self._lock:
            self._evict_if_needed()
            
            entry = CacheEntry(
                key=key,
                data=value,
                created_at=time.time(),
                expires_at=time.time() + ttl,
                data_source=data_source,
                data_version=data_version,
            )
            
            self._memory_cache[key] = entry
            self._save_to_file(entry)
    
    def delete(self, key: str):
        with self._lock:
            if key in self._memory_cache:
                del self._memory_cache[key]
            
            if self.enable_file_cache:
                cache_file = self._get_cache_file_path(key)
                cache_file.unlink(missing_ok=True)
    
    def clear(self):
        with self._lock:
            self._memory_cache.clear()
            
            if self.enable_file_cache:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink(missing_ok=True)
        
        logger.info("缓存已清空")
    
    def get_stats(self) -&gt; Dict[str, Any]:
        with self._lock:
            return {
                "memory_entries": len(self._memory_cache),
                "stats": self.stats.to_dict(),
                "cache_dir": str(self.cache_dir),
            }


_global_cache: Optional[CacheManager] = None


def get_cache() -&gt; CacheManager:
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager()
    return _global_cache


def init_cache(**kwargs) -&gt; CacheManager:
    global _global_cache
    _global_cache = CacheManager(**kwargs)
    return _global_cache


TTL_CACHE = {
    "odds": 900,
    "market_odds": 900,
    "live_odds": 300,
    "matches": 3600,
    "match_info": 3600,
    "match_features": 3600,
    "historical": 86400,
    "team_stats": 86400,
    "standings": 86400,
    "h2h": 86400,
    "default": 3600
}
