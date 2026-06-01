
"""
杠杆效应分析器
=============
分析 BF 玩法的杠杆效应：某些比分选项的赔率远高于其他选项

指标:
1. 杠杆率: 最高赔率 / 最低赔率
2. 夏普比率: (期望值 - 返还率) / 标准差
3. 风险等级: high/medium/low
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging
import math

logger = logging.getLogger("lottery_mcp")


@dataclass
class LeverageAnalysis:
    """杠杆分析结果"""
    play_type: str
    leverage_ratio: float
    risk_level: str
    expected_return: float
    sharp_ratio: float
    top_leverage_options: List[Tuple[str, float]]
    notes: str


class LeverageAnalyzer:
    """杠杆效应分析器"""
    
    def __init__(self):
        self.high_leverage_threshold = 5.0
        self.medium_leverage_threshold = 2.5
    
    def analyze_bf_leverage(
        self,
        bf_odds: Dict[str, float],
        bf_probs: Dict[str, float]
    ) -&gt; LeverageAnalysis:
        """分析比分玩法的杠杆效应"""
        if not bf_odds:
            return LeverageAnalysis(
                play_type="bf",
                leverage_ratio=0.0,
                risk_level="unknown",
                expected_return=0.0,
                sharp_ratio=0.0,
                top_leverage_options=[],
                notes="无赔率数据"
            )
        
        # 计算杠杆率
        odds_values = list(bf_odds.values())
        if not odds_values:
            odds_values = [1.0]
        
        min_odd = min(odds_values)
        max_odd = max(odds_values)
        leverage_ratio = max_odd / max(min_odd, 0.001)
        
        # 确定风险等级
        if leverage_ratio &gt;= self.high_leverage_threshold:
            risk_level = "high"
        elif leverage_ratio &gt;= self.medium_leverage_threshold:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # 计算期望回报
        expected_return = 0.0
        variance = 0.0
        for score, odd in bf_odds.items():
            prob = bf_probs.get(score, 0)
            er = prob * (odd - 1) - (1 - prob)
            expected_return += er
            variance += prob * (er - expected_return) ** 2
        
        std_dev = math.sqrt(max(variance, 0))
        sharp_ratio = expected_return / max(std_dev, 0.001) if std_dev &gt; 0 else 0
        
        # 找出高杠杆选项
        top_options = sorted(
            [(k, v) for k, v in bf_odds.items()],
            key=lambda x: -x[1]
        )[:5]
        
        return LeverageAnalysis(
            play_type="bf",
            leverage_ratio=leverage_ratio,
            risk_level=risk_level,
            expected_return=expected_return,
            sharp_ratio=sharp_ratio,
            top_leverage_options=top_options,
            notes=f"BF 杠杆分析完成, {len(bf_odds)} 个选项"
        )
    
    def get_risk_summary(self, analysis: LeverageAnalysis) -&gt; Dict[str, str]:
        """获取风险摘要"""
        risk_desc = {
            "high": "高杠杆玩法，存在巨大波动风险，建议谨慎投入",
            "medium": "中等杠杆，波动可控，但仍需注意风险",
            "low": "低杠杆，相对稳定"
        }
        
        return {
            "leverage_level": analysis.risk_level,
            "description": risk_desc.get(analysis.risk_level, "未知风险等级"),
            "recommendation": (
                "建议小注" if analysis.risk_level == "high"
                else "可以适当参与"
            )
        }
