"""
价值发现引擎 - 多维度发现市场低估的投注机会
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import math


class ValueSignalType(Enum):
    """价值信号类型"""
    ODDS_VALUE = "赔率价值"           # 赔率隐含价值
    MARKET_DIFF = "市场差异"          # 不同市场间差异
    FUNDAMENTAL = "基本面价值"         # 基本面被低估
    TREND = "趋势价值"                # 赔率变化趋势
    CONTRARIAN = "逆向价值"           # 与市场反向
    SYNTHESIS = "综合价值"            # 多维度综合


@dataclass
class ValueSignal:
    """单个价值信号"""
    signal_type: ValueSignalType
    strength: float  # 信号强度 0-1
    description: str
    confidence: float = 0.5  # 置信度 0-1
    raw_data: Dict = field(default_factory=dict)


@dataclass
class ValueDiscoveryResult:
    """价值发现结果"""
    match_id: str = ""
    selection: str = ""  # 选项（主胜/平局/客胜等）
    
    # 基础价值指标
    model_probability: float = 0.0  # 模型概率
    implied_probability: float = 0.0  # 赔率隐含概率
    value_ratio: float = 1.0  # 价值比率 VR
    expected_value: float = 0.0  # 期望值 EV
    
    # 多维度价值信号
    signals: List[ValueSignal] = field(default_factory=list)
    
    # 综合评分
    overall_value_score: float = 0.0  # 综合价值评分 0-100
    value_rating: str = "N"  # 价值评级 S/A/B/C/N
    
    # 风险提示
    risk_factors: List[str] = field(default_factory=list)
    confidence_level: str = "中"  # 高/中/低
    
    # 建议
    recommendation: str = ""
    suggested_stake_ratio: float = 0.0  # 建议投注比例


class ValueDiscoveryEngine:
    """价值发现引擎"""
    
    @staticmethod
    def analyze(
        match_id: str,
        selection: str,
        model_prob: float,
        odds: float,
        match_data: Dict,
        profile: Any = None,
        strategy: Any = None
    ) -> ValueDiscoveryResult:
        """
        全面分析一个选项的价值
        
        Args:
            match_id: 比赛ID
            selection: 选项（主胜/平局/客胜等）
            model_prob: 模型概率
            odds: 赔率
            match_data: 完整比赛数据
            profile: 比赛特征画像（可选）
            strategy: 策略配置（可选）
        
        Returns:
            价值发现结果
        """
        result = ValueDiscoveryResult()
        result.match_id = match_id
        result.selection = selection
        result.model_probability = model_prob
        
        if odds <= 0:
            result.value_rating = "N"
            result.recommendation = "无效赔率"
            return result
        
        # 1. 基础赔率价值分析
        result.implied_probability = 1.0 / odds
        result.value_ratio = model_prob / result.implied_probability if result.implied_probability > 0 else 1.0
        result.expected_value = model_prob * odds - 1.0
        
        signals = []
        
        # 2. 赔率价值信号
        odds_signal = ValueDiscoveryEngine._analyze_odds_value(
            model_prob, odds, result.implied_probability, result.value_ratio, result.expected_value
        )
        if odds_signal:
            signals.append(odds_signal)
        
        # 3. 市场差异信号（竞彩 vs 欧指 vs 亚盘）
        market_signal = ValueDiscoveryEngine._analyze_market_differences(
            selection, odds, match_data
        )
        if market_signal:
            signals.append(market_signal)
        
        # 4. 基本面价值信号
        fundamental_signal = ValueDiscoveryEngine._analyze_fundamental_value(
            selection, match_data, profile
        )
        if fundamental_signal:
            signals.append(fundamental_signal)
        
        # 5. 赔率变化趋势信号（如果有历史数据）
        trend_signal = ValueDiscoveryEngine._analyze_odds_trend(
            match_id, selection, match_data
        )
        if trend_signal:
            signals.append(trend_signal)
        
        # 6. 逆向价值信号（与市场反向）
        contrarian_signal = ValueDiscoveryEngine._analyze_contrarian_value(
            selection, match_data, result.implied_probability
        )
        if contrarian_signal:
            signals.append(contrarian_signal)
        
        result.signals = signals
        
        # 7. 综合评分
        result.overall_value_score, result.value_rating = ValueDiscoveryEngine._calculate_overall_score(
            result.expected_value, result.value_ratio, signals, strategy
        )
        
        # 8. 风险评估
        result.risk_factors = ValueDiscoveryEngine._assess_risks(
            selection, match_data, result.value_ratio, signals
        )
        result.confidence_level = ValueDiscoveryEngine._determine_confidence(
            signals, result.risk_factors
        )
        
        # 9. 生成建议
        result.recommendation, result.suggested_stake_ratio = ValueDiscoveryEngine._generate_recommendation(
            result, strategy
        )
        
        return result
    
    @staticmethod
    def _analyze_odds_value(model_prob: float, odds: float, 
                           implied_prob: float, vr: float, ev: float) -> Optional[ValueSignal]:
        """分析赔率价值"""
        if vr <= 0.9:
            return None
        
        if vr >= 1.25:
            strength = min(1.0, (vr - 1.0) / 0.5)
            return ValueSignal(
                signal_type=ValueSignalType.ODDS_VALUE,
                strength=strength,
                description=f"高价值：VR={vr:.2f}，模型概率比隐含概率高{(vr-1)*100:.0f}%",
                confidence=0.8,
                raw_data={"vr": vr, "ev": ev}
            )
        elif vr >= 1.1:
            return ValueSignal(
                signal_type=ValueSignalType.ODDS_VALUE,
                strength=0.5,
                description=f"有价值：VR={vr:.2f}",
                confidence=0.6,
                raw_data={"vr": vr, "ev": ev}
            )
        elif vr >= 0.95:
            return ValueSignal(
                signal_type=ValueSignalType.ODDS_VALUE,
                strength=0.2,
                description=f"接近公平：VR={vr:.2f}",
                confidence=0.4,
                raw_data={"vr": vr, "ev": ev}
            )
        return None
    
    @staticmethod
    def _analyze_market_differences(selection: str, jc_odds: float, 
                                   match_data: Dict) -> Optional[ValueSignal]:
        """分析不同市场间的差异"""
        european = match_data.get("european_odds", [])
        consensus = match_data.get("consensus", {})
        
        if not consensus:
            return None
        
        # 获取欧指平均赔率
        euro_home = consensus.get("avg_home_win", 0)
        euro_draw = consensus.get("avg_draw", 0)
        euro_away = consensus.get("avg_away_win", 0)
        
        # 映射选项到欧指赔率
        euro_odds = 0
        if selection in ["主胜", "让球主胜"]:
            euro_odds = euro_home
        elif selection == "平局":
            euro_odds = euro_draw
        elif selection in ["客胜", "让球客胜"]:
            euro_odds = euro_away
        
        if euro_odds <= 0 or jc_odds <= 0:
            return None
        
        # 竞彩 vs 欧指差异
        diff = jc_odds - euro_odds
        diff_pct = diff / euro_odds if euro_odds > 0 else 0
        
        if abs(diff_pct) < 0.05:
            return None
        
        if diff > 0:
            # 竞彩赔率更高 = 可能有价值
            strength = min(1.0, diff_pct * 5)
            return ValueSignal(
                signal_type=ValueSignalType.MARKET_DIFF,
                strength=strength,
                description=f"竞彩赔率比欧指高{diff_pct*100:.1f}%，可能有价值",
                confidence=0.7,
                raw_data={"jc_odds": jc_odds, "euro_odds": euro_odds, "diff": diff}
            )
        else:
            # 竞彩赔率更低 = 可能定价偏低
            strength = min(1.0, abs(diff_pct) * 3)
            return ValueSignal(
                signal_type=ValueSignalType.MARKET_DIFF,
                strength=strength,
                description=f"竞彩赔率比欧指低{abs(diff_pct)*100:.1f}%，可能定价偏低",
                confidence=0.6,
                raw_data={"jc_odds": jc_odds, "euro_odds": euro_odds, "diff": diff}
            )
    
    @staticmethod
    def _analyze_fundamental_value(selection: str, match_data: Dict,
                                   profile: Any) -> Optional[ValueSignal]:
        """分析基本面价值"""
        if not profile:
            return None
        
        fundamentals = match_data.get("fundamentals", {})
        if not fundamentals:
            return None
        
        # 排名差分析
        home_rank = fundamentals.get("home_rank", 0)
        away_rank = fundamentals.get("away_rank", 0)
        
        if home_rank == 0 or away_rank == 0:
            return None
        
        rank_diff = away_rank - home_rank  # 正值=主队排名更高
        
        # 如果选主胜但客队排名更高 = 可能被低估
        # 如果选客胜但主队排名更高 = 可能被低估
        
        if selection in ["主胜", "让球主胜"] and rank_diff > 5:
            # 主队排名高很多，选主胜合理
            return ValueSignal(
                signal_type=ValueSignalType.FUNDAMENTAL,
                strength=min(0.8, rank_diff / 10),
                description=f"主队排名第{home_rank} vs 客队第{away_rank}，排名优势明显",
                confidence=0.7,
                raw_data={"home_rank": home_rank, "away_rank": away_rank}
            )
        elif selection in ["客胜", "让球客胜"] and rank_diff < -5:
            # 客队排名高很多，选客胜合理
            return ValueSignal(
                signal_type=ValueSignalType.FUNDAMENTAL,
                strength=min(0.8, abs(rank_diff) / 10),
                description=f"客队排名第{away_rank} vs 主队第{home_rank}，排名优势明显",
                confidence=0.7,
                raw_data={"home_rank": home_rank, "away_rank": away_rank}
            )
        elif selection == "平局" and abs(rank_diff) < 3:
            # 排名接近，平局合理
            return ValueSignal(
                signal_type=ValueSignalType.FUNDAMENTAL,
                strength=0.5,
                description=f"排名接近（{home_rank} vs {away_rank}），势均力敌",
                confidence=0.6,
                raw_data={"home_rank": home_rank, "away_rank": away_rank}
            )
        
        return None
    
    @staticmethod
    def _analyze_odds_trend(match_id: str, selection: str, 
                           match_data: Dict) -> Optional[ValueSignal]:
        """分析赔率变化趋势
        
        通过对比不同数据源的赔率差异来推断趋势：
        - 如果竞彩赔率 > 欧指平均赔率，可能竞彩在抬高赔率（不看好）
        - 如果竞彩赔率 < 欧指平均赔率，可能竞彩在降低赔率（看好）
        - 结合亚盘数据判断市场情绪
        """
        odds_data = match_data.get("odds", {})
        consensus = match_data.get("consensus", {})
        asian_handicap = match_data.get("asian_handicap", [])
        
        if not consensus:
            return None
        
        # 获取竞彩赔率
        had = odds_data.get("had", {})
        if not had:
            had = {
                "win": odds_data.get("win") or odds_data.get("had_w"),
                "draw": odds_data.get("draw") or odds_data.get("had_d"),
                "lose": odds_data.get("lose") or odds_data.get("had_l")
            }
        
        # 映射选项到赔率
        jc_odds = 0
        euro_odds = 0
        
        if selection in ["主胜", "让球主胜"]:
            jc_odds = float(had.get("win", 0) or 0)
            euro_odds = consensus.get("avg_home_win", 0)
        elif selection == "平局":
            jc_odds = float(had.get("draw", 0) or 0)
            euro_odds = consensus.get("avg_draw", 0)
        elif selection in ["客胜", "让球客胜"]:
            jc_odds = float(had.get("lose", 0) or 0)
            euro_odds = consensus.get("avg_away_win", 0)
        
        if jc_odds <= 0 or euro_odds <= 0:
            return None
        
        # 计算差异
        diff = jc_odds - euro_odds
        diff_pct = diff / euro_odds if euro_odds > 0 else 0
        
        signals = []
        
        # 趋势信号1: 竞彩vs欧指差异
        if diff > 0.2:
            # 竞彩赔率显著高于欧指，可能竞彩不看好
            signals.append(ValueSignal(
                signal_type=ValueSignalType.TREND,
                strength=min(0.8, diff * 0.4),
                description=f"竞彩赔率({jc_odds:.2f})高于欧指({euro_odds:.2f})，机构态度偏谨慎",
                confidence=0.6,
                raw_data={"jc_odds": jc_odds, "euro_odds": euro_odds, "diff": diff}
            ))
        elif diff < -0.2:
            # 竞彩赔率显著低于欧指，可能竞彩看好
            signals.append(ValueSignal(
                signal_type=ValueSignalType.TREND,
                strength=min(0.8, abs(diff) * 0.4),
                description=f"竞彩赔率({jc_odds:.2f})低于欧指({euro_odds:.2f})，机构态度偏积极",
                confidence=0.6,
                raw_data={"jc_odds": jc_odds, "euro_odds": euro_odds, "diff": diff}
            ))
        
        # 趋势信号2: 亚盘支持度
        if asian_handicap and selection in ["主胜", "让球主胜", "客胜", "让球客胜"]:
            asian = asian_handicap[0]
            line = asian.get("home_handicap", 0)
            
            # 根据盘口判断趋势
            if selection in ["主胜", "让球主胜"]:
                if line <= -0.5:
                    # 亚盘让球，支持主胜
                    signals.append(ValueSignal(
                        signal_type=ValueSignalType.TREND,
                        strength=0.5,
                        description=f"亚盘主让{line}球，市场看好主队",
                        confidence=0.7,
                        raw_data={"asian_line": line}
                    ))
                elif line >= 0.5:
                    # 亚盘受让，不支持主胜
                    signals.append(ValueSignal(
                        signal_type=ValueSignalType.TREND,
                        strength=0.4,
                        description=f"亚盘客让{abs(line)}球，市场对主队谨慎",
                        confidence=0.6,
                        raw_data={"asian_line": line}
                    ))
            elif selection in ["客胜", "让球客胜"]:
                if line >= 0.5:
                    # 亚盘受让，支持客胜
                    signals.append(ValueSignal(
                        signal_type=ValueSignalType.TREND,
                        strength=0.5,
                        description=f"亚盘客让{line}球，市场看好客队",
                        confidence=0.7,
                        raw_data={"asian_line": line}
                    ))
                elif line <= -0.5:
                    # 亚盘让球，不支持客胜
                    signals.append(ValueSignal(
                        signal_type=ValueSignalType.TREND,
                        strength=0.4,
                        description=f"亚盘主让{abs(line)}球，市场对客队谨慎",
                        confidence=0.6,
                        raw_data={"asian_line": line}
                    ))
        
        # 返回最强的信号
        if signals:
            return max(signals, key=lambda x: x.strength)
        return None
    
    @staticmethod
    def _analyze_contrarian_value(selection: str, match_data: Dict,
                                  implied_prob: float) -> Optional[ValueSignal]:
        """分析逆向价值（与市场反向）"""
        # 如果某个选项的隐含概率很高（市场热门），但模型概率一般
        # 可能存在"热门陷阱"
        
        if implied_prob > 0.6:
            # 市场热门
            return ValueSignal(
                signal_type=ValueSignalType.CONTRARIAN,
                strength=0.3,
                description=f"市场热门（隐含概率{implied_prob:.0%}），警惕热门陷阱",
                confidence=0.4,
                raw_data={"implied_prob": implied_prob}
            )
        elif implied_prob < 0.2:
            # 市场冷门
            return ValueSignal(
                signal_type=ValueSignalType.CONTRARIAN,
                strength=0.2,
                description=f"市场冷门（隐含概率{implied_prob:.0%}），可能存在价值",
                confidence=0.3,
                raw_data={"implied_prob": implied_prob}
            )
        
        return None
    
    @staticmethod
    def _calculate_overall_score(ev: float, vr: float, signals: List[ValueSignal],
                                 strategy: Any) -> Tuple[float, str]:
        """计算综合价值评分和评级"""
        # 基础分
        base_score = 50.0
        
        # EV贡献
        if ev > 0.2:
            base_score += 25
        elif ev > 0.1:
            base_score += 15
        elif ev > 0:
            base_score += 5
        elif ev > -0.1:
            base_score -= 5
        else:
            base_score -= 15
        
        # VR贡献
        if vr >= 1.2:
            base_score += 15
        elif vr >= 1.1:
            base_score += 10
        elif vr >= 1.05:
            base_score += 5
        elif vr < 0.9:
            base_score -= 10
        
        # 信号贡献
        for signal in signals:
            if signal.signal_type == ValueSignalType.ODDS_VALUE:
                base_score += signal.strength * 10
            elif signal.signal_type == ValueSignalType.MARKET_DIFF:
                base_score += signal.strength * 8
            elif signal.signal_type == ValueSignalType.FUNDAMENTAL:
                base_score += signal.strength * 6
            elif signal.signal_type == ValueSignalType.CONTRARIAN:
                base_score += signal.strength * 3
        
        # 限制范围
        score = max(0, min(100, base_score))
        
        # 评级
        if score >= 80:
            rating = "S"
        elif score >= 65:
            rating = "A"
        elif score >= 50:
            rating = "B"
        elif score >= 35:
            rating = "C"
        else:
            rating = "N"
        
        return score, rating
    
    @staticmethod
    def _assess_risks(selection: str, match_data: Dict, 
                     vr: float, signals: List[ValueSignal]) -> List[str]:
        """评估风险因素"""
        risks = []
        
        # 价值比率风险
        if vr < 0.9:
            risks.append("价值比率偏低，可能被高估")
        
        # 数据缺失风险
        if not match_data.get("fundamentals"):
            risks.append("基本面数据缺失")
        if not match_data.get("european_odds"):
            risks.append("国际市场赔率数据缺失")
        
        # 信号冲突风险
        strong_signals = [s for s in signals if s.strength > 0.7]
        if len(strong_signals) == 0:
            risks.append("缺乏强价值信号")
        
        # 逆向信号
        contrarian = [s for s in signals if s.signal_type == ValueSignalType.CONTRARIAN]
        if contrarian and contrarian[0].strength > 0.5:
            risks.append("市场热门，存在热门陷阱风险")
        
        return risks
    
    @staticmethod
    def _determine_confidence(signals: List[ValueSignal], 
                             risks: List[str]) -> str:
        """确定置信度等级"""
        if not signals:
            return "低"
        
        # 基于信号强度和数量
        avg_strength = sum(s.strength for s in signals) / len(signals)
        signal_count = len([s for s in signals if s.strength > 0.5])
        
        # 基于风险
        risk_score = len(risks) * 0.2
        
        confidence_score = avg_strength * 0.6 + signal_count * 0.1 - risk_score
        
        if confidence_score >= 0.6:
            return "高"
        elif confidence_score >= 0.4:
            return "中"
        else:
            return "低"
    
    @staticmethod
    def _generate_recommendation(result: ValueDiscoveryResult,
                                 strategy: Any) -> Tuple[str, float]:
        """生成建议"""
        if result.value_rating == "S":
            return "强烈推荐", 0.15
        elif result.value_rating == "A":
            return "推荐", 0.10
        elif result.value_rating == "B":
            return "可考虑", 0.05
        elif result.value_rating == "C":
            return "谨慎", 0.02
        else:
            return "不推荐", 0.0


def batch_analyze(match_data_list: List[Dict], 
                  profile_map: Dict = None,
                  strategy_map: Dict = None) -> List[ValueDiscoveryResult]:
    """
    批量分析多个比赛的价值
    
    Args:
        match_data_list: 比赛数据列表
        profile_map: 比赛特征画像映射 {match_id: profile}
        strategy_map: 策略配置映射 {match_id: strategy}
    
    Returns:
        价值发现结果列表
    """
    results = []
    
    for match_data in match_data_list:
        match_id = match_data.get("match_id", "")
        profile = profile_map.get(match_id) if profile_map else None
        strategy = strategy_map.get(match_id) if strategy_map else None
        
        # 获取比赛分析数据
        analysis = match_data.get("analysis", {})
        recommendation = analysis.get("recommendation", {})
        implied_probs = recommendation.get("implied_probs", {})
        
        # 获取赔率数据
        odds_data = match_data.get("odds", {})
        had = odds_data.get("had", {})
        if not had:
            # 尝试从扁平化键名获取
            had = {
                "win": odds_data.get("win") or odds_data.get("had_w"),
                "draw": odds_data.get("draw") or odds_data.get("had_d"),
                "lose": odds_data.get("lose") or odds_data.get("had_l")
            }
        
        # 获取模型概率（从分析结果或泊松模型）
        model_probs = {}
        poisson = analysis.get("statistical_models", {}).get("poisson", {})
        if poisson:
            # 从泊松模型计算胜平负概率
            home_lambda = poisson.get("home_lambda", 1.5)
            away_lambda = poisson.get("away_lambda", 1.2)
            from math import exp, factorial
            
            # 计算概率分布
            home_win_prob = 0
            draw_prob = 0
            away_win_prob = 0
            
            for h in range(6):
                for a in range(6):
                    p_h = (exp(-home_lambda) * (home_lambda ** h)) / factorial(h)
                    p_a = (exp(-away_lambda) * (away_lambda ** a)) / factorial(a)
                    prob = p_h * p_a
                    
                    if h > a:
                        home_win_prob += prob
                    elif h == a:
                        draw_prob += prob
                    else:
                        away_win_prob += prob
            
            model_probs = {
                "主胜": home_win_prob,
                "平局": draw_prob,
                "客胜": away_win_prob
            }
        else:
            # 使用隐含概率作为回退
            model_probs = {
                "主胜": implied_probs.get("主胜", 0.33),
                "平局": implied_probs.get("平局", 0.33),
                "客胜": implied_probs.get("客胜", 0.33)
            }
        
        # 赔率映射
        odds_map = {
            "主胜": float(had.get("win", 0) or 0),
            "平局": float(had.get("draw", 0) or 0),
            "客胜": float(had.get("lose", 0) or 0)
        }
        
        # 分析胜平负三个选项
        for selection in ["主胜", "平局", "客胜"]:
            model_prob = model_probs.get(selection, 0.33)
            odds = odds_map.get(selection, 2.0)
            
            # 如果赔率无效，跳过
            if odds <= 0:
                continue
            
            result = ValueDiscoveryEngine.analyze(
                match_id=match_id,
                selection=selection,
                model_prob=model_prob,
                odds=odds,
                match_data=match_data,
                profile=profile,
                strategy=strategy
            )
            results.append(result)
    
    return results


# 导出主要组件
__all__ = [
    "ValueDiscoveryEngine",
    "ValueDiscoveryResult",
    "ValueSignal",
    "ValueSignalType",
    "batch_analyze",
]
