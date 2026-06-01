"""
事件总线 - 实现模块间松耦合通信
==============================

核心功能:
1. 发布-订阅模式
2. 事件优先级
3. 异步事件处理
4. 事件持久化（可选）

设计原则:
- 模块间不直接调用，通过事件通信
- 支持同步和异步事件处理
- 事件可携带上下文信息
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional, Set
from enum import Enum, auto
from datetime import datetime
from collections import defaultdict
import threading

logger = logging.getLogger("lottery_mcp")


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0    # 关键事件，立即处理
    HIGH = 1        # 高优先级
    NORMAL = 2      # 普通优先级
    LOW = 3         # 低优先级
    BACKGROUND = 4  # 后台处理


@dataclass
class Event:
    """事件对象"""
    name: str                           # 事件名称
    data: Any = None                    # 事件数据
    source: str = ""                    # 事件来源
    priority: EventPriority = EventPriority.NORMAL
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}


class EventBus:
    """
    事件总线
    
    实现模块间的松耦合通信。模块可以发布事件，也可以订阅感兴趣的事件。
    
    示例:
        # 订阅事件
        event_bus.subscribe("play.analyzed", on_play_analyzed)
        
        # 发布事件
        event_bus.publish(Event("play.analyzed", data=result))
        
        # 异步发布
        await event_bus.publish_async(Event("play.analyzed", data=result))
    """
    
    def __init__(self):
        # 订阅者字典: event_name -> List[(handler, priority)]
        self._subscribers: Dict[str, List[tuple]] = defaultdict(list)
        
        # 事件历史（用于调试和回放）
        self._event_history: List[Event] = []
        self._max_history = 1000
        
        # 锁（线程安全）
        self._lock = threading.RLock()
        
        # 统计
        self._stats = {
            "published": 0,
            "handled": 0,
            "errors": 0,
        }
    
    def subscribe(
        self,
        event_name: str,
        handler: Callable[[Event], Any],
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """
        订阅事件
        
        Args:
            event_name: 事件名称（支持通配符，如"play.*"）
            handler: 事件处理函数
            priority: 处理优先级
        """
        with self._lock:
            self._subscribers[event_name].append((handler, priority))
            # 按优先级排序
            self._subscribers[event_name].sort(key=lambda x: x[1].value)
        
        logger.debug(f"订阅事件: {event_name}, handler={handler.__name__}")
    
    def unsubscribe(
        self,
        event_name: str,
        handler: Callable[[Event], Any]
    ) -> bool:
        """
        取消订阅
        
        Args:
            event_name: 事件名称
            handler: 事件处理函数
            
        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if event_name in self._subscribers:
                original_len = len(self._subscribers[event_name])
                self._subscribers[event_name] = [
                    (h, p) for h, p in self._subscribers[event_name]
                    if h != handler
                ]
                return len(self._subscribers[event_name]) < original_len
        return False
    
    def publish(self, event: Event) -> None:
        """
        同步发布事件
        
        Args:
            event: 事件对象
        """
        self._record_event(event)
        
        handlers = self._get_handlers(event.name)
        
        for handler, priority in handlers:
            try:
                handler(event)
                self._stats["handled"] += 1
            except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
                # 只捕获预期的业务异常，避免捕获系统级异常
                self._stats["errors"] += 1
                logger.error(f"事件处理失败: {event.name}, handler={handler.__name__}, error={e}")
        
        self._stats["published"] += 1
    
    async def publish_async(self, event: Event) -> None:
        """
        异步发布事件
        
        Args:
            event: 事件对象
        """
        self._record_event(event)
        
        handlers = self._get_handlers(event.name)
        
        # 根据优先级分组处理
        priority_groups: Dict[EventPriority, List[Callable]] = defaultdict(list)
        for handler, priority in handlers:
            priority_groups[priority].append(handler)
        
        # 按优先级顺序处理
        for priority in sorted(priority_groups.keys(), key=lambda p: p.value):
            group_handlers = priority_groups[priority]
            
            if priority == EventPriority.CRITICAL:
                # 关键事件同步处理
                for handler in group_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                        self._stats["handled"] += 1
                    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
                        # 只捕获预期的业务异常
                        self._stats["errors"] += 1
                        logger.error(f"事件处理失败: {event.name}, error={e}")
            else:
                # 其他优先级并发处理
                tasks = []
                for handler in group_handlers:
                    if asyncio.iscoroutinefunction(handler):
                        tasks.append(self._safe_handle(handler, event))
                    else:
                        # 同步处理函数在线程池中运行
                        tasks.append(asyncio.to_thread(self._safe_handle_sync, handler, event))
                
                await asyncio.gather(*tasks, return_exceptions=True)
        
        self._stats["published"] += 1
    
    async def _safe_handle(self, handler: Callable, event: Event) -> None:
        """安全处理异步事件"""
        try:
            await handler(event)
            self._stats["handled"] += 1
        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            # 只捕获预期的业务异常
            self._stats["errors"] += 1
            logger.error(f"异步事件处理失败: {event.name}, error={e}")
    
    def _safe_handle_sync(self, handler: Callable, event: Event) -> None:
        """安全处理同步事件"""
        try:
            handler(event)
            self._stats["handled"] += 1
        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            # 只捕获预期的业务异常
            self._stats["errors"] += 1
            logger.error(f"同步事件处理失败: {event.name}, error={e}")
    
    def _get_handlers(self, event_name: str) -> List[tuple]:
        """获取事件的所有处理函数"""
        handlers = []
        
        with self._lock:
            # 精确匹配
            if event_name in self._subscribers:
                handlers.extend(self._subscribers[event_name])
            
            # 通配符匹配
            for pattern, subs in self._subscribers.items():
                if pattern.endswith(".*") and event_name.startswith(pattern[:-2]):
                    handlers.extend(subs)
                elif pattern.startswith("*.") and event_name.endswith(pattern[2:]):
                    handlers.extend(subs)
        
        # 按优先级排序
        handlers.sort(key=lambda x: x[1].value)
        return handlers
    
    def _record_event(self, event: Event) -> None:
        """记录事件到历史"""
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
    
    def get_event_history(
        self,
        event_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        获取事件历史
        
        Args:
            event_name: 事件名称过滤
            limit: 返回数量限制
            
        Returns:
            List[Event]: 事件列表
        """
        with self._lock:
            events = self._event_history
            if event_name:
                events = [e for e in events if e.name == event_name]
            return events[-limit:]
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return dict(self._stats)
    
    def clear_history(self) -> None:
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()


# 预定义事件名称（用于标准化）
class EventNames:
    """标准事件名称"""
    
    # 玩法分析事件
    PLAY_ANALYSIS_STARTED = "play.analysis.started"
    PLAY_ANALYSIS_COMPLETED = "play.analysis.completed"
    PLAY_ANALYSIS_FAILED = "play.analysis.failed"
    
    # 协同验证事件
    SYNERGY_VALIDATION_STARTED = "synergy.validation.started"
    SYNERGY_VALIDATION_COMPLETED = "synergy.validation.completed"
    SYNERGY_INCONSISTENCY_DETECTED = "synergy.inconsistency.detected"
    SYNERGY_OPPORTUNITY_FOUND = "synergy.opportunity.found"
    
    # 数据获取事件
    DATA_FETCH_STARTED = "data.fetch.started"
    DATA_FETCH_COMPLETED = "data.fetch.completed"
    DATA_FETCH_FAILED = "data.fetch.failed"
    
    # 投注生成事件
    BET_RECOMMENDATION_GENERATED = "bet.recommendation.generated"
    PORTFOLIO_OPTIMIZED = "portfolio.optimized"
    
    # 系统事件
    PLUGIN_REGISTERED = "plugin.registered"
    PLUGIN_UNREGISTERED = "plugin.unregistered"
    CACHE_INVALIDATED = "cache.invalidated"


# 全局事件总线实例
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_event_bus() -> None:
    """重置全局事件总线（主要用于测试）"""
    global _global_event_bus
    _global_event_bus = EventBus()
