"""
核心接口定义 - 既解耦又耦合的设计契约
======================================

定义所有模块间的标准接口，确保：
1. 解耦: 模块间通过接口交互，不依赖具体实现
2. 耦合: 通过接口契约实现协作
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum, auto
from datetime import datetime


class PlayType(Enum):
    """竞彩足球5大玩法类型"""
    SPF = ("SPF", "胜平负", "Match Result")
    RQSPF = ("RQSPF", "让球胜平负", "Handicap")
    BF = ("BF", "比分", "Correct Score")
    ZJQ = ("ZJQ", "总进球", "Total Goals")
    BQC = ("BQC", "半全场", "Half-time/Full-time")
    
    def __init__(self, code: str, name_cn: str, name_en: str):
        self.code = code
        self.name_cn = name_cn
        self.name_en = name_en
    
    @classmethod
    def from_code(cls, code: str) -> Optional["PlayType"]:
        """从代码获取玩法类型"""
        for pt in cls:
            if pt.code == code:
                return pt
        return None


@dataclass
class PlaySelection:
    """玩法选项"""
    selection: str                    # 选项名称（如"主胜"、"1:0"）
    probability: float               # 概率
    odds: float                      # 赔率
    expected_value: float            # 期望值
    value_rating: str = ""           # 价值评级
    confidence: float = 0.0          # 置信度


@dataclass
class PlayAnalysisResult:
    """
    玩法分析结果标准格式
    
    这是5大玩法间协作的数据契约
    """
    play_type: PlayType
    probabilities: Dict[str, float] = field(default_factory=dict)
    selections: List[PlaySelection] = field(default_factory=list)
    confidence: float = 0.0
    expected_value: float = 0.0
    
    # 用于协同验证（耦合点）
    derived_from: Dict[str, Any] = field(default_factory=dict)  # 从哪些基础概率推导
    validates: Dict[str, Callable] = field(default_factory=dict)  # 可以验证哪些其他玩法
    
    # 元信息
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"
    analysis_notes: List[str] = field(default_factory=list)
    
    def get_best_selection(self) -> Optional[PlaySelection]:
        """获取最佳选项"""
        if not self.selections:
            return None
        return max(self.selections, key=lambda s: s.expected_value)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "play_type": self.play_type.code,
            "play_name": self.play_type.name_cn,
            "probabilities": self.probabilities,
            "selections": [
                {
                    "selection": s.selection,
                    "probability": s.probability,
                    "odds": s.odds,
                    "expected_value": s.expected_value,
                    "value_rating": s.value_rating,
                    "confidence": s.confidence,
                }
                for s in self.selections
            ],
            "confidence": self.confidence,
            "expected_value": self.expected_value,
            "analyzed_at": self.analyzed_at,
        }


@dataclass
class ValidationRule:
    """玩法间验证规则"""
    source_play: PlayType
    target_play: PlayType
    rule_name: str
    validator: Callable[[PlayAnalysisResult, PlayAnalysisResult], bool]
    tolerance: float = 0.05
    description: str = ""


class PlayPlugin(ABC):
    """
    玩法插件基类 - 既解耦又耦合的设计
    
    解耦点:
    - 每个玩法独立实现此接口
    - 不依赖其他玩法的具体实现
    - 可独立开发、测试、部署
    
    耦合点:
    - 通过get_validation_rules声明与其他玩法的关系
    - 通过combine_with支持玩法组合
    - 通过标准数据格式PlayAnalysisResult协作
    """
    
    @property
    @abstractmethod
    def play_type(self) -> PlayType:
        """返回玩法类型"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """返回插件版本"""
        pass
    
    @abstractmethod
    def analyze(
        self,
        match_context: Dict[str, Any],
        base_probabilities: Dict[str, float],
        odds: Dict[str, Any]
    ) -> PlayAnalysisResult:
        """
        独立分析玩法
        
        这是解耦的核心 - 每个玩法完全独立分析，
        不依赖其他玩法的结果。
        
        Args:
            match_context: 比赛上下文（球队、联赛、排名等）
            base_probabilities: 基础概率（来自Poisson/Elo/xG模型）
            odds: 赔率数据
            
        Returns:
            PlayAnalysisResult: 标准格式的分析结果
        """
        pass
    
    @abstractmethod
    def get_validation_rules(self) -> List[ValidationRule]:
        """
        返回与其他玩法的验证规则
        
        这是耦合的核心 - 声明本玩法可以验证哪些其他玩法，
        以及验证规则是什么。
        
        Returns:
            List[ValidationRule]: 验证规则列表
            
        示例:
            [
                ValidationRule(
                    source_play=PlayType.SPF,
                    target_play=PlayType.RQSPF,
                    rule_name="让球一致性",
                    validator=validate_handicap_consistency,
                    tolerance=0.05,
                    description="SPF主胜概率应考虑让球后转换为RQSPF"
                )
            ]
        """
        pass
    
    def combine_with(
        self,
        other_result: PlayAnalysisResult,
        combination_type: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """
        与其他玩法组合分析（可选实现）
        
        这是智能耦合 - 支持玩法间的组合推荐。
        
        Args:
            other_result: 其他玩法的分析结果
            combination_type: 组合类型（如"full_time_consistent"）
            
        Returns:
            Optional[Dict]: 组合分析结果，None表示无法组合
            
        示例:
            SPF主胜 + BQC胜胜 = {
                "type": "全场一致",
                "confidence_boost": 0.15,
                "description": "全场结果双重确认"
            }
        """
        return None
    
    def on_register(self, registry: Any) -> None:
        """
        插件注册时的回调
        
        可以在此进行初始化操作。
        
        Args:
            registry: 插件注册中心
        """
        pass
    
    def on_unregister(self) -> None:
        """插件注销时的回调"""
        pass


class SynergyValidator(ABC):
    """
    协同验证器接口
    
    负责验证多个玩法间的一致性
    """
    
    @abstractmethod
    def add_rule(self, rule: ValidationRule) -> None:
        """添加验证规则"""
        pass
    
    @abstractmethod
    def validate_all(
        self,
        results: Dict[PlayType, PlayAnalysisResult]
    ) -> Dict[str, Any]:
        """
        验证所有玩法的一致性
        
        Args:
            results: 各玩法的分析结果
            
        Returns:
            Dict: 验证结果
            {
                "is_consistent": bool,
                "violations": List[Dict],
                "confidence_adjustments": Dict[PlayType, float],
                "synergy_opportunities": List[Dict]
            }
        """
        pass


class CombinationEngine(ABC):
    """
    组合引擎接口
    
    负责发现玩法间的组合机会
    """
    
    @abstractmethod
    def find_combinations(
        self,
        results: Dict[PlayType, PlayAnalysisResult],
        validation_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        发现玩法组合机会
        
        Args:
            results: 各玩法的分析结果
            validation_results: 验证结果
            
        Returns:
            List[Dict]: 组合机会列表
        """
        pass
