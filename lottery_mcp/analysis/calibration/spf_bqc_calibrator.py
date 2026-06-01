
"""
SPF (胜平负) &lt;-&gt; BQC (半全场) 聚合校准器
====================================
聚合算法:
1. SPF -&gt; BQC: 根据半场+全场结果组合
2. BQC -&gt; SPF: 聚合全场结果
3. 偏差阈值: &lt; 1.0%
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger("lottery_mcp")


@dataclass
class BQCCalibrationResult:
    """半全场校准结果"""
    source_type: str
    target_type: str
    source_probs: Dict[str, float]
    target_probs: Dict[str, float]
    confidence: float
    deviation: float
    is_valid: bool
    notes: str


class SPFBQCCalibrator:
    """胜平负 &lt;-&gt; 半全场校准器"""
    
    def __init__(self):
        self.max_deviation = 0.01
    
    def spf_to_bqc(self, spf_probs: Dict[str, float]) -&gt; BQCCalibrationResult:
        """从胜平负到半全场 (简化版)"""
        bqc_probs = {}
        
        # 简化模型: 假设半场和全场的过渡
        # 比如, 如果全场胜, 则半场胜/平/胜的分布
        home_win_prob = spf_probs.get("3", 0.33)
        draw_prob = spf_probs.get("1", 0.33)
        away_win_prob = spf_probs.get("0", 0.33)
        
        # 简单的转移概率分布
        bqc_probs["3-3"] = home_win_prob * 0.6
        bqc_probs["1-3"] = home_win_prob * 0.3
        bqc_probs["3-1"] = home_win_prob * 0.1
        
        bqc_probs["1-1"] = draw_prob * 0.6
        bqc_probs["3-1"] = bqc_probs.get("3-1", 0) + draw_prob * 0.2
        bqc_probs["0-1"] = draw_prob * 0.2
        
        bqc_probs["0-0"] = away_win_prob * 0.6
        bqc_probs["0-0"] = bqc_probs.get("0-0", 0) + away_win_prob * 0.3
        bqc_probs["1-0"] = away_win_prob * 0.1
        
        # 归一化
        total = sum(bqc_probs.values())
        if total &gt; 0:
            bqc_probs = {k: v / total for k, v in bqc_probs.items()}
        
        return BQCCalibrationResult(
            source_type="spf",
            target_type="bqc",
            source_probs=spf_probs,
            target_probs=bqc_probs,
            confidence=0.80,
            deviation=0.0,
            is_valid=True,
            notes="简化半场-全场转移模型"
        )
    
    def bqc_to_spf(self, bqc_probs: Dict[str, float]) -&gt; BQCCalibrationResult:
        """从半全场聚合到胜平负"""
        spf_probs = {
            "3": 0.0,
            "1": 0.0,
            "0": 0.0
        }
        
        for bqc_key, prob in bqc_probs.items():
            try:
                _, full_result = bqc_key.split("-")
                if full_result == "3":
                    spf_probs["3"] += prob
                elif full_result == "1":
                    spf_probs["1"] += prob
                elif full_result == "0":
                    spf_probs["0"] += prob
            except ValueError:
                continue
        
        return BQCCalibrationResult(
            source_type="bqc",
            target_type="spf",
            source_probs=bqc_probs,
            target_probs=spf_probs,
            confidence=0.95,
            deviation=0.0,
            is_valid=True,
            notes="全场结果聚合"
        )
    
    def validate_bidirectional(
        self,
        spf_probs: Dict[str, float],
        bqc_probs: Dict[str, float]
    ) -&gt; Tuple[bool, float, str]:
        """验证双向一致性"""
        bqc2spf = self.bqc_to_spf(bqc_probs)
        
        deviation = 0.0
        for key in ["3", "1", "0"]:
            deviation += abs(spf_probs.get(key, 0) - bqc2spf.target_probs.get(key, 0))
        
        deviation = deviation / 3
        
        is_valid = deviation &lt; self.max_deviation
        
        return is_valid, deviation, "半全场验证完成"
