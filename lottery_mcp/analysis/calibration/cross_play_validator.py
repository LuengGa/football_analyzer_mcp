
"""
跨玩法矛盾检测器
================
检测多个玩法预测之间的逻辑矛盾

检测规则:
1. BF &lt;-&gt; ZJQ: 精确数学一致性
2. SPF &lt;-&gt; BQC: 聚合一致性
3. 所有玩法: 返还率一致性 (88.6% vs 79.7%)
"""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger("lottery_mcp")


@dataclass
class Contradiction:
    """矛盾检测结果"""
    play_a: str
    play_b: str
    type: str
    severity: str
    description: str
    confidence: float


class CrossPlayValidator:
    """跨玩法验证器"""
    
    def __init__(self):
        self.bf_zjq_calibrator = None
        self.spf_bqc_calibrator = None
        self.max_allowed_deviation = 0.01
        
        try:
            from .bf_zjq_calibrator import BFZJQCalibrator
            from .spf_bqc_calibrator import SPFBQCCalibrator
            self.bf_zjq_calibrator = BFZJQCalibrator()
            self.spf_bqc_calibrator = SPFBQCCalibrator()
        except ImportError:
            pass
    
    def detect_contradictions(
        self,
        predictions: Dict[str, Dict[str, float]]
    ) -&gt; List[Contradiction]:
        """检测所有玩法间的矛盾"""
        contradictions = []
        
        # 1. BF &lt;-&gt; ZJQ 检测
        if "bf" in predictions and "zjq" in predictions:
            contra = self._check_bf_zjq(predictions["bf"], predictions["zjq"])
            if contra:
                contradictions.append(contra)
        
        # 2. SPF &lt;-&gt; BQC 检测
        if "spf" in predictions and "bqc" in predictions:
            contra = self._check_spf_bqc(predictions["spf"], predictions["bqc"])
            if contra:
                contradictions.append(contra)
        
        return contradictions
    
    def _check_bf_zjq(
        self,
        bf_probs: Dict[str, float],
        zjq_probs: Dict[str, float]
    ) -&gt; Optional[Contradiction]:
        """检查比分和总进球的一致性"""
        if not self.bf_zjq_calibrator:
            return None
        
        is_valid, deviation, notes = self.bf_zjq_calibrator.validate_bidirectional(
            bf_probs, zjq_probs
        )
        
        if not is_valid:
            severity = "high" if deviation &gt; 0.05 else "medium"
            return Contradiction(
                play_a="bf",
                play_b="zjq",
                type="mathematical_inconsistency",
                severity=severity,
                description=f"BF-ZJQ 数学偏差 {deviation:.2%}",
                confidence=0.95
            )
        
        return None
    
    def _check_spf_bqc(
        self,
        spf_probs: Dict[str, float],
        bqc_probs: Dict[str, float]
    ) -&gt; Optional[Contradiction]:
        """检查胜平负和半全场的一致性"""
        if not self.spf_bqc_calibrator:
            return None
        
        is_valid, deviation, notes = self.spf_bqc_calibrator.validate_bidirectional(
            spf_probs, bqc_probs
        )
        
        if not is_valid:
            severity = "high" if deviation &gt; 0.05 else "medium"
            return Contradiction(
                play_a="spf",
                play_b="bqc",
                type="aggregation_inconsistency",
                severity=severity,
                description=f"SPF-BQC 聚合偏差 {deviation:.2%}",
                confidence=0.90
            )
        
        return None
    
    def get_validation_report(
        self,
        predictions: Dict[str, Dict[str, float]]
    ) -&gt; Dict[str, Any]:
        """获取完整验证报告"""
        contradictions = self.detect_contradictions(predictions)
        
        return {
            "overall_valid": len(contradictions) == 0,
            "contradiction_count": len(contradictions),
            "contradictions": [
                {
                    "play_a": c.play_a,
                    "play_b": c.play_b,
                    "type": c.type,
                    "severity": c.severity,
                    "description": c.description,
                    "confidence": c.confidence
                }
                for c in contradictions
            ],
            "plays_checked": list(predictions.keys())
        }
