
from typing import Callable, Dict, List, Any
from enum import Enum
import threading


class EventType(str, Enum):
    ANALYSIS_START = "analysis_start"
    ANALYSIS_COMPLETE = "analysis_complete"
    PREDICTION_UPDATE = "prediction_update"
    ODDS_CHANGE = "odds_change"
    VALIDATION_ERROR = "validation_error"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"


class EventBus:
    """发布-订阅事件总线"""
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """订阅事件"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
    
    def publish(self, event_type: EventType, data: Any = None):
        """发布事件"""
        callbacks = []
        with self._lock:
            if event_type in self._subscribers:
                callbacks = list(self._subscribers[event_type])
        
        for callback in callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                pass
