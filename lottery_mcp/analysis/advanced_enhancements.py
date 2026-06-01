"""
高级深化功能模块
===============

第2阶段、第4阶段、第5阶段的深化任务实现：
- 胜平负平局专项优化
- 半全场逆转模式识别
- 混合过关风险分散算法
- 凯利公式优化投注
- 容错方案设计
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("lottery_mcp")


# ============================================================
# 胜平负平局专项优化
# ============================================================
class DrawPattern(Enum):
    """平局模式类型"""
    TIGHT_DEFENSIVE = "胶着防守型"  # 两队防守强，0-0、1-1
    HIGH_SCORING = "高比分平局"  # 2-2、3-3
    COMEBACK_FROM_BEHIND = "追平型"  # 0-1、1-2后追平
    EARLY_GOAL = "早进球平局"  # 早进球后保持平局


@dataclass
class DrawOptimization:
    """平局优化结果"""
    draw_probability: float  # 平局概率
    expected_draw_score: str  # 最可能的平局比分
    draw_confidence: str  # 平局信心
    key_factors: List[str]  # 关键因素
    value_rating: float  # 平局赔率价值（0-1）


class DrawOptimizer:
    """胜平负平局专项优化器"""
    
    @staticmethod
    def analyze_draw_pattern(
        home_team_defense_rating: float,
        away_team_defense_rating: float,
        home_team_offense_rating: float,
        away_team_offense_rating: float,
        recent_draw_rate_home: float = 0.25,
        recent_draw_rate_away: float = 0.25,
        historical_h2h_draw_rate: float = 0.3
    ) -> DrawOptimization:
        """
        分析平局模式并优化
        
        Args:
            home_team_defense_rating: 主队防守评分 0-1
            away_team_defense_rating: 客队防守评分 0-1
            home_team_offense_rating: 主队进攻评分 0-1
            away_team_offense_rating: 客队进攻评分 0-1
            recent_draw_rate_home: 主队近期平局率
            recent_draw_rate_away: 客队近期平局率
            historical_h2h_draw_rate: 历史交锋平局率
            
        Returns:
            平局优化结果
        """
        # 基础平局概率计算
        defense_strength = (home_team_defense_rating + away_team_defense_rating) / 2
        offense_strength = (home_team_offense_rating + away_team_offense_rating) / 2
        
        # 基础概率
        base_prob = 0.28  # 足球比赛平均平局概率
        
        # 防守强，更容易平局
        if defense_strength > 0.7:
            base_prob += 0.08
        
        # 进攻弱，更容易平局
        if offense_strength < 0.4:
            base_prob += 0.06
        
        # 交锋历史平局率调整
        base_prob += (historical_h2h_draw_rate - 0.28) * 0.5
        
        # 近期平局率调整
        base_prob += ((recent_draw_rate_home + recent_draw_rate_away) / 2 - 0.28) * 0.3
        
        # 限制概率范围
        draw_prob = max(0.15, min(0.45, base_prob))
        
        # 判断平局模式
        key_factors = []
        expected_score = "1-1"
        
        if defense_strength > 0.75 and offense_strength < 0.45:
            pattern = DrawPattern.TIGHT_DEFENSIVE
            expected_score = "0-0"
            key_factors.append("双方防守强大，进球困难")
        elif defense_strength < 0.5 and offense_strength > 0.65:
            pattern = DrawPattern.HIGH_SCORING
            expected_score = "2-2"
            key_factors.append("双方进攻强，防守弱，比分可能高")
        else:
            pattern = DrawPattern.TIGHT_DEFENSIVE
            key_factors.append("实力均衡，胶着比赛")
        
        if historical_h2h_draw_rate > 0.4:
            key_factors.append(f"历史交锋平局率高({historical_h2h_draw_rate:.0%})")
        
        if recent_draw_rate_home > 0.35 or recent_draw_rate_away > 0.35:
            key_factors.append("近期平局趋势明显")
        
        # 信心评级
        if draw_prob > 0.35:
            confidence = "高"
        elif draw_prob > 0.25:
            confidence = "中"
        else:
            confidence = "低"
        
        return DrawOptimization(
            draw_probability=draw_prob,
            expected_draw_score=expected_score,
            draw_confidence=confidence,
            key_factors=key_factors,
            value_rating=draw_prob * 1.2  # 简单价值评分
        )


# ============================================================
# 半全场逆转模式识别
# ============================================================
class ComebackPattern(Enum):
    """逆转模式类型"""
    NO_COMEBACK_LIKELY = "无逆转可能"  # 胜胜、平平、负负
    HOME_COMEBACK = "主队逆转"  # 负胜、平胜
    AWAY_COMEBACK = "客队逆转"  # 胜负、平负
    EARLY_LEAD_LOSS = "领先被追平"  # 胜平、负平


@dataclass
class ComebackAnalysis:
    """逆转分析结果"""
    comeback_probability: float  # 总逆转概率
    home_comeback_prob: float  # 主队逆转概率
    away_comeback_prob: float  # 客队逆转概率
    recommended_bqc_options: List[str]  # 推荐的半全场选项
    key_pattern_indicators: List[str]  # 模式指标
    confidence: str


class ComebackPatternRecognizer:
    """半全场逆转模式识别器"""
    
    @staticmethod
    def analyze_comeback_potential(
        home_team_momentum_rating: float,
        away_team_momentum_rating: float,
        home_defense_consistency: float,
        away_defense_consistency: float,
        recent_home_comeback_rate: float = 0.1,
        recent_away_comeback_rate: float = 0.1
    ) -> ComebackAnalysis:
        """
        分析逆转可能性
        
        Args:
            home_team_momentum_rating: 主队势头评分 0-1
            away_team_momentum_rating: 客队势头评分 0-1
            home_defense_consistency: 主队防守稳定性
            away_defense_consistency: 客队防守稳定性
            recent_home_comeback_rate: 主队近期逆转率
            recent_away_comeback_rate: 客队近期逆转率
            
        Returns:
            逆转分析结果
        """
        # 基础逆转概率
        home_comeback = 0.08  # 主队逆转基础概率
        away_comeback = 0.08  # 客队逆转基础概率
        
        indicators = []
        
        # 主队势头强劲，可能逆转
        if home_team_momentum_rating > 0.7:
            home_comeback += 0.05
            indicators.append("主队近期势头强劲")
        
        # 客队势头强劲，可能逆转
        if away_team_momentum_rating > 0.7:
            away_comeback += 0.05
            indicators.append("客队近期势头强劲")
        
        # 防守不稳定，容易被逆转
        if home_defense_consistency < 0.4:
            away_comeback += 0.04
            indicators.append("主队防守不稳定")
        
        if away_defense_consistency < 0.4:
            home_comeback += 0.04
            indicators.append("客队防守不稳定")
        
        # 历史逆转趋势
        home_comeback += recent_home_comeback_rate * 0.3
        away_comeback += recent_away_comeback_rate * 0.3
        
        total_comeback = min(0.3, home_comeback + away_comeback)
        
        # 推荐选项
        recommended = []
        if home_comeback > 0.12:
            recommended.extend(["平胜", "负胜"])
        if away_comeback > 0.12:
            recommended.extend(["平负", "胜负"])
        
        # 一致性选项更安全
        if total_comeback < 0.18:
            recommended.extend(["胜胜", "平平", "负负"])
        
        # 信心评级
        if total_comeback > 0.22:
            confidence = "高"
        elif total_comeback > 0.14:
            confidence = "中"
        else:
            confidence = "低"
        
        return ComebackAnalysis(
            comeback_probability=total_comeback,
            home_comeback_prob=home_comeback,
            away_comeback_prob=away_comeback,
            recommended_bqc_options=recommended,
            key_pattern_indicators=indicators,
            confidence=confidence
        )


# ============================================================
# 混合过关风险分散算法
# ============================================================
@dataclass
class RiskDiversification:
    """风险分散结果"""
    play_diversity_score: float  # 玩法多样性评分
    league_diversity_score: float  # 联赛多样性评分
    time_spread_score: float  # 时间分散评分
    overall_risk_reduction: float  # 总体风险降低
    recommended_play_types: List[str]  # 推荐玩法类型
    key_recommendations: List[str]  # 关键建议


class RiskDiversifier:
    """风险分散优化器"""
    
    @staticmethod
    def calculate_diversification(
        selected_plays: List[str],  # 选择的玩法列表
        leagues: List[str],  # 比赛所属联赛
        match_times: Optional[List[str]] = None  # 比赛时间
    ) -> RiskDiversification:
        """
        计算风险分散情况
        
        Args:
            selected_plays: 选择的玩法列表
            leagues: 比赛所属联赛列表
            match_times: 比赛时间列表（可选）
            
        Returns:
            风险分散结果
        """
        # 玩法多样性评分
        unique_plays = set(selected_plays)
        play_diversity = len(unique_plays) / max(len(selected_plays), 1)
        
        # 联赛多样性评分
        unique_leagues = set(leagues)
        league_diversity = len(unique_leagues) / max(len(leagues), 1)
        
        # 时间分散评分
        time_spread = 0.7  # 默认基础分
        if match_times:
            # 简单时间差计算
            time_spread = 0.5 + (min(len(set(match_times)), 3) / 3) * 0.5
        
        # 总体风险降低
        overall_risk_reduction = (
            play_diversity * 0.4 +
            league_diversity * 0.35 +
            time_spread * 0.25
        )
        
        # 建议
        recommendations = []
        
        if play_diversity < 0.6:
            recommendations.append("建议混合至少2种不同玩法")
        
        if league_diversity < 0.5:
            recommendations.append("建议选择不同联赛的比赛")
        
        if len(selected_plays) > 3 and play_diversity == 1:
            recommendations.append("玩法多样，风险分散良好")
        
        # 推荐玩法类型
        recommended_types = []
        if "SPF" not in unique_plays and len(selected_plays) > 1:
            recommended_types.append("SPF（低风险）")
        if "ZJQ" not in unique_plays and len(selected_plays) > 1:
            recommended_types.append("ZJQ（独立维度）")
        if "BF" not in unique_plays and len(selected_plays) > 2:
            recommended_types.append("BF（高赔率，但风险高）")
        
        return RiskDiversification(
            play_diversity_score=play_diversity,
            league_diversity_score=league_diversity,
            time_spread_score=time_spread,
            overall_risk_reduction=overall_risk_reduction,
            recommended_play_types=recommended_types,
            key_recommendations=recommendations
        )


# ============================================================
# 凯利公式优化投注
# ============================================================
@dataclass
class KellyCriterionResult:
    """凯利公式结果"""
    kelly_fraction: float  # 凯利比例（建议投注比例）
    optimal_bet_units: Dict[str, float]  # 各选项的最优投注单位
    edge_analysis: Dict[str, float]  # 优势分析
    risk_adjustment: str  # 风险调整建议
    confidence: str


class KellyCriterionOptimizer:
    """凯利公式优化器"""
    
    @staticmethod
    def calculate_optimal_bets(
        selections: Dict[str, Tuple[float, float]],  # {选项: (概率, 赔率)}
        bankroll_units: float = 100,
        kelly_multiplier: float = 0.5  # 保守凯利
    ) -> KellyCriterionResult:
        """
        计算最优投注比例
        
        Args:
            selections: 选项字典 {选项: (概率, 赔率)}
            bankroll_units: 资金单位
            kelly_multiplier: 凯利倍数（保守策略）
            
        Returns:
            凯利公式结果
        """
        optimal_bets = {}
        edge_analysis = {}
        total_edge = 0
        
        for selection, (prob, odds) in selections.items():
            if prob <= 0 or odds <= 1:
                continue
            
            # 计算边缘（EV - 1）
            edge = prob * odds - 1
            edge_analysis[selection] = edge
            
            if edge > 0:
                # 凯利公式：f* = (p*(b+1) - 1) / b
                b = odds - 1
                kelly_f = (prob * (b + 1) - 1) / b
                
                # 限制最大比例
                kelly_f = max(0, min(0.25, kelly_f))
                
                optimal_bets[selection] = kelly_f * kelly_multiplier
                total_edge += edge
        
        # 归一化
        total_fraction = sum(optimal_bets.values())
        if total_fraction > 1:
            for s in optimal_bets:
                optimal_bets[s] /= total_fraction
        
        # 计算总凯利比例
        kelly_fraction = sum(optimal_bets.values())
        
        # 风险调整建议
        if kelly_fraction > 0.4:
            risk_adjustment = "建议降低到半凯利或四分之一凯利"
        elif kelly_fraction > 0.2:
            risk_adjustment = "适中风险"
        else:
            risk_adjustment = "风险保守"
        
        # 信心评级
        if total_edge > 0.2:
            confidence = "高"
        elif total_edge > 0.1:
            confidence = "中"
        else:
            confidence = "低"
        
        return KellyCriterionResult(
            kelly_fraction=kelly_fraction,
            optimal_bet_units=optimal_bets,
            edge_analysis=edge_analysis,
            risk_adjustment=risk_adjustment,
            confidence=confidence
        )


# ============================================================
# 容错方案设计
# ============================================================
class ParlayType(Enum):
    """串关类型"""
    STRAIGHT_2 = "2串1"
    STRAIGHT_3 = "3串1"
    STRAIGHT_4 = "4串1"
    DOUBLE_CHANCE = "双选容错"
    TRIPLE_CHANCE = "三选容错"


@dataclass
class ParlayPlan:
    """串关方案"""
    parlay_type: ParlayType
    matches_needed: int  # 需要中几场
    matches_selected: int  # 选择几场
    risk_level: str  # 风险等级
    expected_return_multiplier: float  # 预期回报倍数
    description: str
    example: str


class ParlayPlanGenerator:
    """容错方案生成器"""
    
    @staticmethod
    def generate_plans() -> List[ParlayPlan]:
        """
        生成各种串关方案
        
        Returns:
            串关方案列表
        """
        plans = [
            # 标准串关
            ParlayPlan(
                parlay_type=ParlayType.STRAIGHT_2,
                matches_needed=2,
                matches_selected=2,
                risk_level="高",
                expected_return_multiplier=2.5,
                description="2场全中才算赢，高赔率",
                example="选2场比赛，2场全对中奖"
            ),
            ParlayPlan(
                parlay_type=ParlayType.STRAIGHT_3,
                matches_needed=3,
                matches_selected=3,
                risk_level="很高",
                expected_return_multiplier=4.5,
                description="3场全中才算赢，高赔率",
                example="选3场比赛，3场全对中奖"
            ),
            # 容错方案
            ParlayPlan(
                parlay_type=ParlayType.DOUBLE_CHANCE,
                matches_needed=2,
                matches_selected=3,
                risk_level="中",
                expected_return_multiplier=2.0,
                description="选3场比赛，中2场就算赢",
                example="选3场，允许错1场，中奖注数3注"
            ),
            ParlayPlan(
                parlay_type=ParlayType.TRIPLE_CHANCE,
                matches_needed=3,
                matches_selected=4,
                risk_level="中低",
                expected_return_multiplier=3.0,
                description="选4场比赛，中3场就算赢",
                example="选4场，允许错1场，中奖注数4注"
            ),
        ]
        return plans


# ============================================================
# 剩余高优先级功能（精确进球、赔率偏差、受让方韧性）
# ============================================================
class PreciseExpectedGoals:
    """精确进球预期模型 - 比分玩法专用"""
    
    @staticmethod
    def calculate_precise_distribution(
        home_exp_goals: float,
        away_exp_goals: float
    ) -> Dict[str, float]:
        """
        计算精确的比分概率分布（泊松分布+双变量）
        """
        from math import exp, factorial
        
        def poisson_prob(k: int, lam: float) -> float:
            return (lam ** k * exp(-lam)) / factorial(k) if k >= 0 else 0.0
        
        distribution = {}
        
        for home_goals in range(0, 7):
            for away_goals in range(0, 6):
                prob = poisson_prob(home_goals, home_exp_goals) * poisson_prob(away_goals, away_exp_goals)
                score_str = f"{home_goals}:{away_goals}"
                distribution[score_str] = prob
        
        # 处理胜其他、负其他
        total_prob = sum(distribution.values())
        home_other_prob = sum(
            poisson_prob(h, home_exp_goals) * poisson_prob(a, away_exp_goals)
            for h in range(7, 12) for a in range(0, 6)
        )
        away_other_prob = sum(
            poisson_prob(h, home_exp_goals) * poisson_prob(a, away_exp_goals)
            for h in range(0, 7) for a in range(6, 12)
        )
        
        distribution["胜其他"] = home_other_prob
        distribution["负其他"] = away_other_prob
        
        return distribution
    
    @staticmethod
    def get_value_odds(
        distribution: Dict[str, float],
        market_odds: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """
        找出赔率偏离模型预期的比分（价值发现）
        """
        value_bets = []
        
        for score, prob in distribution.items():
            if prob <= 0:
                continue
            
            fair_odds = 1.0 / prob if prob > 0 else float('inf')
            
            if score in market_odds:
                market_odd = market_odds[score]
                edge = (prob * market_odd) - 1
                
                if edge > 0.1:
                    value_bets.append({
                        "score": score,
                        "model_probability": round(prob * 100, 2),
                        "fair_odds": round(fair_odds, 2),
                        "market_odds": market_odd,
                        "edge": round(edge * 100, 2),
                        "rating": "高价值" if edge > 0.2 else "价值"
                    })
        
        value_bets.sort(key=lambda x: x["edge"], reverse=True)
        return value_bets


class OddsDeviationAnalyzer:
    """赔率偏差分析器 - 系统对比模型与市场"""
    
    @staticmethod
    def analyze_deviation(
        model_probabilities: Dict[str, float],
        market_odds: Dict[str, float],
        play_type: str = "SPF"
    ) -> Dict[str, Any]:
        """
        分析赔率偏差
        """
        result = {
            "play_type": play_type,
            "deviation_scores": {},
            "recommended_options": [],
            "undervalued": [],
            "overvalued": []
        }
        
        for option, market_odd in market_odds.items():
            if option not in model_probabilities:
                continue
            
            model_prob = model_probabilities[option]
            fair_odds = 1.0 / model_prob if model_prob > 0 else float('inf')
            
            deviation = (market_odd - fair_odds) / max(fair_odds, 0.01)
            
            result["deviation_scores"][option] = {
                "model_probability": round(model_prob * 100, 2),
                "fair_odds": round(fair_odds, 2),
                "market_odds": market_odd,
                "deviation_pct": round(deviation * 100, 1)
            }
            
            if deviation > 0.15:
                result["undervalued"].append(option)
            elif deviation < -0.15:
                result["overvalued"].append(option)
        
        # 生成推荐
        result["recommended_options"] = result["undervalued"][:3]
        
        return result


class UnderdogResilienceAnalyzer:
    """受让方韧性分析器 - 让球胜平负专用"""
    
    @staticmethod
    def analyze_resilience(
        handicap: float,
        underdog_defense_strength: float,
        underdog_possession: float = 0.45,
        recent_underdog_performance: List[str] = None
    ) -> Dict[str, Any]:
        """
        分析受让方在让球下的韧性
        """
        if recent_underdog_performance is None:
            recent_underdog_performance = ["W", "D", "L", "D", "W"]
        
        result = {
            "handicap": handicap,
            "is_home_underdog": handicap < 0,
            "resilience_score": 0.0,
            "handicap_draw_recommendation": False,
            "underdog_advantage_recommendation": False,
            "key_factors": []
        }
        
        # 防守强度权重最大
        resilience = 0.4 * underdog_defense_strength
        
        # 控球率权重
        resilience += 0.25 * underdog_possession
        
        # 近期表现
        win_count = recent_underdog_performance.count("W")
        draw_count = recent_underdog_performance.count("D")
        recent_form = (win_count * 0.3 + draw_count * 0.15) / 5
        resilience += 0.35 * recent_form
        
        result["resilience_score"] = round(resilience, 2)
        
        # 深度让球情况下，韧性更重要
        if abs(handicap) >= 1.0:
            if resilience > 0.6:
                result["handicap_draw_recommendation"] = True
                result["key_factors"].append("深度让球+高韧性=平局概率上升")
            elif resilience > 0.5:
                result["underdog_advantage_recommendation"] = True
                result["key_factors"].append("受让方韧性不错，考虑下盘")
        else:
            if resilience > 0.7:
                result["underdog_advantage_recommendation"] = True
                result["key_factors"].append("浅盘+高韧性，受让方有机会")
        
        result["key_factors"].append(f"防守强度评分: {round(underdog_defense_strength, 2)}")
        result["key_factors"].append(f"近期表现: W{win_count}-D{draw_count}-L{5-win_count-draw_count}")
        
        return result
