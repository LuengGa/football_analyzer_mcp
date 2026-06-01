
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
from enum import Enum


class PlayType(str, Enum):
    SPF = "spf"
    RQSPF = "rqspf"
    BF = "bf"
    ZJQ = "zjq"
    BQC = "bqc"
    MIXED = "mixed"


class PlayData(BaseModel):
    play_type: PlayType
    match_id: str
    home_team: str
    away_team: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    odds: Dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlayRecommendation(BaseModel):
    play_type: PlayType
    recommended_option: str
    confidence: float
    ev: float
    rationale: str
    risk_level: str = "medium"
    alternatives: List[str] = Field(default_factory=list)


class PlayPlugin(ABC):
    """玩法插件基类"""
    
    @property
    @abstractmethod
    def play_type(self) -&gt; PlayType:
        pass
    
    @abstractmethod
    def analyze(self, match_data: Dict[str, Any]) -&gt; PlayData:
        pass
    
    @abstractmethod
    def recommend(self, play_data: PlayData) -&gt; PlayRecommendation:
        pass
    
    @abstractmethod
    def validate_odds(self, odds: Dict[str, float]) -&gt; Tuple[bool, str]:
        pass


class SynergyValidator(ABC):
    """玩法协同验证器"""
    
    @abstractmethod
    def validate_pair(
        self, 
        play1: PlayData, 
        play2: PlayData
    ) -&gt; Tuple[bool, float, str]:
        """
        验证两个玩法的协同性
        返回: (有效, 置信度, 说明)
        """
        pass
    
    @abstractmethod
    def detect_contradictions(
        self,
        plays: List[PlayData]
    ) -&gt; List[Dict[str, Any]]:
        """检测玩法间的矛盾"""
        pass


class CombinationEngine(ABC):
    """组合引擎"""
    
    @abstractmethod
    def generate_combinations(
        self,
        plays: List[PlayData],
        max_combination: int = 4
    ) -&gt; List[Dict[str, Any]]:
        """生成最优组合"""
        pass
    
    @abstractmethod
    def calculate_combined_ev(
        self,
        combination: List[PlayRecommendation]
    ) -&gt; float:
        """计算组合期望"""
        pass
