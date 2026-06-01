# -*- coding: utf-8 -*-
"""
专业统计模型模块
================
提供精确的泊松分布、Elo评级和xG分析能力。

P0-1: 真正的泊松分布计算（scipy.stats.poisson精确比分概率矩阵）
P0-2: 完整Elo评级系统（动态更新机制）
P0-3: 增强xG分析模型（基于射门数据的xG模型）
"""

import math
import json
import logging
import os
import random
import hashlib
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger("lottery_mcp")

# ============================================================================
# P0-1: 精确泊松分布模型
# ============================================================================

try:
    from scipy.stats import poisson as scipy_poisson
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy不可用，将使用纯Python泊松近似计算")


def poisson_pmf(k: int, lambda_: float) -> float:
    """计算泊松分布概率质量函数 P(X=k)。

    Args:
        k: 进球数
        lambda_: 预期进球数（均值）

    Returns:
        概率值
    """
    if SCIPY_AVAILABLE:
        return float(scipy_poisson.pmf(k, lambda_))
    else:
        # 纯Python实现（精度略低但可用）
        if lambda_ <= 0:
            return 1.0 if k == 0 else 0.0
        return (lambda_ ** k) * math.exp(-lambda_) / math.factorial(k)


# ============================================================================
# 玩法类型枚举（全局统一定义）
# ============================================================================

class PlayType(Enum):
    """竞彩玩法类型（全局唯一枚举，所有模块统一从此导入）"""
    SPF = "胜平负"
    RQSPF = "让球胜平负"
    BF = "比分"
    ZJQ = "总进球"
    BQC = "半全场"


# 各玩法最大过关场次（官方规则）
PLAY_MAX_LEGS: Dict[PlayType, int] = {
    PlayType.SPF: 8,
    PlayType.RQSPF: 8,
    PlayType.ZJQ: 6,
    PlayType.BF: 4,
    PlayType.BQC: 4,
}


def play_type_from_str(name: str) -> Optional[PlayType]:
    """将字符串转换为 PlayType 枚举（支持中英文名称）。

    Args:
        name: 玩法名称，如 "SPF", "胜平负", "比分", "BF" 等

    Returns:
        PlayType 枚举值，未匹配返回 None
    """
    _NAME_MAP = {
        # 英文缩写
        "SPF": PlayType.SPF, "RQSPF": PlayType.RQSPF,
        "BF": PlayType.BF, "ZJQ": PlayType.ZJQ, "BQC": PlayType.BQC,
        # 中文名称
        "胜平负": PlayType.SPF, "让球胜平负": PlayType.RQSPF,
        "比分": PlayType.BF, "总进球": PlayType.ZJQ, "半全场": PlayType.BQC,
        # 小写
        "spf": PlayType.SPF, "rqspf": PlayType.RQSPF,
        "bf": PlayType.BF, "zjq": PlayType.ZJQ, "bqc": PlayType.BQC,
    }
    return _NAME_MAP.get(name)


@dataclass
class PoissonMatchPrediction:
    """泊松分布比赛预测结果"""
    home_expected_goals: float       # 主队预期进球 (λ_home)
    away_expected_goals: float       # 客队预期进球 (λ_away)
    home_win_prob: float             # 主胜概率
    draw_prob: float                 # 平局概率
    away_win_prob: float             # 客胜概率
    home_win_prob_adjusted: float    # 调整后主胜概率（与home_win_prob相同，保留兼容性）
    draw_prob_adjusted: float        # 调整后平局概率（与draw_prob相同，保留兼容性）
    away_win_prob_adjusted: float    # 调整后客胜概率（与away_win_prob相同，保留兼容性）
    score_probabilities: Dict[str, float] = field(default_factory=dict)  # 完整比分概率矩阵
    full_score_matrix: Dict[Tuple[int, int], float] = field(default_factory=dict)  # 原始矩阵（供半全场推导）
    over_under_2_5: float = 0.0     # 大于2.5球概率
    over_under_3_5: float = 0.0     # 大于3.5球概率
    btts_prob: float = 0.0          # 双方进球概率 (BTTS)
    most_likely_score: str = ""     # 最可能比分
    most_likely_score_prob: float = 0.0  # 最可能比分概率
    confidence_interval: Dict[str, float] = field(default_factory=dict)  # 置信区间

    @property
    def win_prob(self) -> float:
        """主胜概率别名（兼容 win_prob 键名）"""
        return self.home_win_prob

    @property
    def lose_prob(self) -> float:
        """客胜概率别名（兼容 lose_prob 键名）"""
        return self.away_win_prob


class PoissonModel:
    """精确泊松分布比赛预测模型

    使用 scipy.stats.poisson 计算精确比分概率矩阵，
    支持联赛均值调整、主场优势调整。

    计算流程：
    1. 计算主/客队预期进球数 λ
    2. 构建比分概率矩阵 P(home_goals, away_goals)
    3. 聚合为胜/平/负概率
    4. 计算衍生市场概率（大小球、BTTS等）

    注意：模型输出的是真实概率，不包含返还率调整。
    返还率仅在 find_value_bets 中用于调整市场赔率的隐含概率。
    """

    # 五大联赛历史平均进球数据（用于基准校准）
    # 扩展覆盖全部27个支持的联赛/杯赛
    LEAGUE_AVG_GOALS = {
        # 五大联赛
        "英超": {"home": 1.55, "away": 1.20, "total": 2.75},
        "西甲": {"home": 1.60, "away": 1.10, "total": 2.70},
        "德甲": {"home": 1.70, "away": 1.25, "total": 2.95},
        "意甲": {"home": 1.50, "away": 1.10, "total": 2.60},
        "法甲": {"home": 1.55, "away": 1.15, "total": 2.70},
        # 欧洲其他联赛
        "荷甲": {"home": 1.80, "away": 1.30, "total": 3.10},
        "葡超": {"home": 1.60, "away": 1.15, "total": 2.75},
        "苏超": {"home": 1.65, "away": 1.10, "total": 2.75},
        "比甲": {"home": 1.65, "away": 1.20, "total": 2.85},
        "土超": {"home": 1.55, "away": 1.15, "total": 2.70},
        "瑞典超": {"home": 1.60, "away": 1.20, "total": 2.80},
        "挪超": {"home": 1.70, "away": 1.25, "total": 2.95},
        "丹超": {"home": 1.65, "away": 1.15, "total": 2.80},
        # 亚洲联赛
        "中超": {"home": 1.50, "away": 1.10, "total": 2.60},
        "日职": {"home": 1.45, "away": 1.15, "total": 2.60},
        "日乙": {"home": 1.40, "away": 1.10, "total": 2.50},
        "韩职": {"home": 1.45, "away": 1.10, "total": 2.55},
        "澳超": {"home": 1.55, "away": 1.20, "total": 2.75},
        # 美洲联赛
        "美职": {"home": 1.60, "away": 1.20, "total": 2.80},
        "巴甲": {"home": 1.55, "away": 1.15, "total": 2.70},
        "阿甲": {"home": 1.40, "away": 1.05, "total": 2.45},
        # 杯赛
        "欧冠": {"home": 1.65, "away": 1.15, "total": 2.80},
        "欧联": {"home": 1.55, "away": 1.15, "total": 2.70},
        "亚冠": {"home": 1.50, "away": 1.10, "total": 2.60},
        # 英格兰低级别
        "英冠": {"home": 1.50, "away": 1.15, "total": 2.65},
        "英甲": {"home": 1.50, "away": 1.10, "total": 2.60},
        "default": {"home": 1.50, "away": 1.15, "total": 2.65},
    }

    # 英文联赛名称别名映射（支持英文输入自动转为中文键名）
    LEAGUE_ALIASES = {
        "English Premier League": "英超", "EPL": "英超", "Premier League": "英超",
        "La Liga": "西甲", "Spanish La Liga": "西甲",
        "Bundesliga": "德甲", "German Bundesliga": "德甲",
        "Serie A": "意甲", "Italian Serie A": "意甲",
        "Ligue 1": "法甲", "French Ligue 1": "法甲",
        "Eredivisie": "荷甲", "Primeira Liga": "葡超", "Scottish Premiership": "苏超",
        "Chinese Super League": "中超", "J1 League": "日职", "J-League": "日职",
        "MLS": "美职", "Major League Soccer": "美职",
        "Champions League": "欧冠", "UEFA Champions League": "欧冠",
        "Europa League": "欧联", "UEFA Europa League": "欧联",
        "A-League": "澳超", "Brasileirão": "巴甲", "Super Lig": "土超",
    }

    # 主场优势因子（主队进球加成）
    HOME_ADVANTAGE_FACTOR = 1.10

    # Dixon-Coles时间衰减参数（xi）
    # 半衰期约3个月（~90天），近期比赛权重更高
    TIME_DECAY_XI = 0.005

    def __init__(self, max_goals: int = 8):
        """
        Args:
            max_goals: 计算的最大进球数（默认8，覆盖99.5%概率）
        """
        self.max_goals = max_goals

    @staticmethod
    def time_decay_weight(days_ago: float, xi: float = 0.005) -> float:
        """计算Dixon-Coles时间衰减权重。

        权重公式: w(t) = exp(-ξ × t)
        其中 t 为距今天数，ξ 为衰减参数。

        默认ξ=0.005时：
        - 7天前: 权重 0.965
        - 30天前: 权重 0.861
        - 90天前: 权重 0.638
        - 180天前: 权重 0.407

        Args:
            days_ago: 距今天数
            xi: 衰减参数（默认0.005）

        Returns:
            时间衰减权重 (0-1)
        """
        return math.exp(-xi * days_ago)

    def calculate_expected_goals_weighted(
        self,
        home_goals_for: int, home_games: int,
        home_goals_against: int,
        away_goals_for: int, away_games: int,
        away_goals_against: int,
        league: str = "default",
        home_match_dates: Optional[List[int]] = None,
        away_match_dates: Optional[List[int]] = None,
        # NEW: home/away split parameters
        away_goals_for_home: Optional[float] = None,
        away_games_home: Optional[int] = None,
        home_goals_against_home: Optional[float] = None,
        home_games_home: Optional[int] = None,
    ) -> Tuple[float, float]:
        """计算带时间衰减的预期进球数。

        如果提供了比赛日期列表，则使用Dixon-Coles时间衰减权重
        对近期比赛赋予更高权重。否则回退到普通计算。

        Args:
            home_goals_for: 主队主场进球总数
            home_games: 主队主场场次
            home_goals_against: 主队主场失球总数
            away_goals_for: 客队客场进球总数
            away_games: 客队客场场次
            away_goals_against: 客队客场失球总数
            league: 联赛名称
            home_match_dates: 主队比赛距今天数列表（可选）
            away_match_dates: 客队比赛距今天数列表（可选）
            away_goals_for_home: 客队在主场时的进球总数（可选）
            away_games_home: 客队主场场次（可选）
            home_goals_against_home: 主队在客场时的失球总数（可选）
            home_games_home: 主队客场场次（可选）

        Returns:
            (home_expected, away_expected) 预期进球数
        """
        # 如果没有提供日期数据，回退到普通计算（传递home/away split参数）
        if not home_match_dates and not away_match_dates:
            return self.calculate_expected_goals(
                home_goals_for, home_games, home_goals_against,
                away_goals_for, away_games, away_goals_against,
                league,
                away_goals_for_home=away_goals_for_home,
                away_games_home=away_games_home,
                home_goals_against_home=home_goals_against_home,
                home_games_home=home_games_home,
            )

        # 通过别名映射解析联赛名称（支持英文联赛名输入）
        resolved_league = self.LEAGUE_ALIASES.get(league, league)
        league_avg = self.LEAGUE_AVG_GOALS.get(resolved_league, self.LEAGUE_AVG_GOALS["default"])

        # 带时间衰减的攻击力/防守力计算
        #
        # Dixon-Coles时间衰减的正确实现：
        # 对于每场比赛i，权重 w_i = exp(-ξ * days_ago_i)
        # 加权攻击力 = sum(w_i * goals_i) / sum(w_i) / league_avg
        #
        # 重要限制说明：
        # 当前接口仅接收聚合数据（总进球、总场次），不包含单场比赛的进球数据。
        # 因此无法对每场比赛的进球进行独立加权。
        # 
        # 近似方案：
        # 使用平均权重因子对整体场均进球进行调整：
        #   avg_weight = sum(w_i) / n
        #   weighted_avg_goals = (total_goals / n) * avg_weight
        # 这相当于假设每场比赛进球相同，仅对时间因素加权。
        # 
        # 未来改进方向：
        # 接口应接收 List[Tuple[goals: int, days_ago: int]] 以支持真正的逐场加权。

        if home_match_dates and len(home_match_dates) > 0:
            weights = [self.time_decay_weight(d) for d in home_match_dates]
            total_w = sum(weights)
            n_matches = len(weights)
            # 平均权重因子：衡量近期比赛的相对重要性
            # 如果所有比赛都是今天，avg_weight = 1.0
            # 如果比赛分散在过去，avg_weight < 1.0（近期权重更高）
            avg_weight = total_w / n_matches
            
            # 基础场均进球
            base_home_goals_for = home_goals_for / home_games if home_games > 0 else league_avg["home"]
            base_home_goals_against = home_goals_against / home_games if home_games > 0 else league_avg["away"]
            
            # 应用时间衰减调整：近期表现权重更高
            # 加权攻击力 = (场均进球 * 平均权重) / 联赛基准
            home_attack = (base_home_goals_for * avg_weight) / league_avg["home"]
            home_defense = (base_home_goals_against * avg_weight) / league_avg["away"]
        else:
            home_attack = (home_goals_for / home_games) / league_avg["home"] if home_games > 0 else 1.0
            home_defense = (home_goals_against / home_games) / league_avg["away"] if home_games > 0 else 1.0

        if away_match_dates and len(away_match_dates) > 0:
            weights = [self.time_decay_weight(d) for d in away_match_dates]
            total_w = sum(weights)
            n_matches = len(weights)
            avg_weight = total_w / n_matches
            
            base_away_goals_for = away_goals_for / away_games if away_games > 0 else league_avg["away"]
            base_away_goals_against = away_goals_against / away_games if away_games > 0 else league_avg["home"]
            
            away_attack = (base_away_goals_for * avg_weight) / league_avg["away"]
            away_defense = (base_away_goals_against * avg_weight) / league_avg["home"]
        else:
            away_attack = (away_goals_for / away_games) / league_avg["away"] if away_games > 0 else 1.0
            away_defense = (away_goals_against / away_games) / league_avg["home"] if away_games > 0 else 1.0

        home_expected = home_attack * away_defense * league_avg["home"] * self.HOME_ADVANTAGE_FACTOR
        away_expected = away_attack * home_defense * league_avg["away"]

        home_expected = max(0.3, min(4.0, home_expected))
        away_expected = max(0.2, min(3.5, away_expected))

        return round(home_expected, 3), round(away_expected, 3)

    def calculate_expected_goals(
        self,
        home_goals_for: int, home_games: int,
        home_goals_against: int,
        away_goals_for: int, away_games: int,
        away_goals_against: int,
        league: str = "default",
        home_advantage: Optional[float] = None,
        # NEW: home/away split parameters for more nuanced prediction
        away_goals_for_home: Optional[float] = None,
        away_games_home: Optional[int] = None,
        home_goals_against_home: Optional[float] = None,
        home_games_home: Optional[int] = None,
    ) -> Tuple[float, float]:
        """计算主客队预期进球数。

        使用Dixon-Coles简化方法：
        λ_home = home_attack × away_defense × league_home_avg
        λ_away = away_attack × home_defense × league_away_avg

        Args:
            home_goals_for: 主队主场进球总数
            home_games: 主队主场场次
            home_goals_against: 主队主场失球总数
            away_goals_for: 客队客场进球总数
            away_games: 客队客场场次
            away_goals_against: 客队客场失球总数
            league: 联赛名称（用于基准校准）
            home_advantage: 动态主场优势因子（None时使用默认固定值）
            away_goals_for_home: 客队在主场时的进球总数（可选，用于估算客队客场攻击力）
            away_games_home: 客队主场场次（可选）
            home_goals_against_home: 主队在客场时的失球总数（可选，用于估算主队主场防守力）
            home_games_home: 主队客场场次（可选）

        Returns:
            (home_expected, away_expected) 预期进球数
        """
        # 通过别名映射解析联赛名称（支持英文联赛名输入）
        resolved_league = self.LEAGUE_ALIASES.get(league, league)
        league_avg = self.LEAGUE_AVG_GOALS.get(resolved_league, self.LEAGUE_AVG_GOALS["default"])

        # 使用传入的动态主场优势或默认值
        advantage = home_advantage if home_advantage is not None else self.HOME_ADVANTAGE_FACTOR

        # 主队攻击力 = 主队主场场均进球 / 联赛主场场均进球
        home_attack = (home_goals_for / home_games) / league_avg["home"] if home_games > 0 else 1.0
        # 客队防守力 = 客队客场场均失球 / 联赛客场场均失球
        away_defense = (away_goals_against / away_games) / league_avg["away"] if away_games > 0 else 1.0
        # 客队攻击力 = 客队客场场均进球 / 联赛客场场均进球
        away_attack = (away_goals_for / away_games) / league_avg["away"] if away_games > 0 else 1.0
        # 主队防守力 = 主队主场场均失球 / 联赛主场场均失球
        home_defense = (home_goals_against / home_games) / league_avg["home"] if home_games > 0 else 1.0

        # 计算基础预期进球
        home_expected = home_attack * away_defense * league_avg["home"] * advantage
        away_expected = away_attack * home_defense * league_avg["away"]

        # NEW: When home/away split parameters are provided, compute more nuanced estimates
        # and blend with the general estimates (50/50 weight)
        has_away_home_split = (
            away_goals_for_home is not None and away_games_home is not None
            and away_games_home > 0
        )
        has_home_away_split = (
            home_goals_against_home is not None and home_games_home is not None
            and home_games_home > 0
        )

        if has_away_home_split or has_home_away_split:
            # Estimate away_attack_strength from away team's home performance
            # (how well they score at home gives insight into their overall attack capability)
            if has_away_home_split:
                away_attack_from_home = (away_goals_for_home / away_games_home) / league_avg["home"]
            else:
                away_attack_from_home = away_attack

            # Estimate home_defense_strength from home team's away performance
            # (how many goals they concede away gives insight into their defensive vulnerability at home)
            if has_home_away_split:
                home_defense_from_away = (home_goals_against_home / home_games_home) / league_avg["away"]
            else:
                home_defense_from_away = home_defense

            # Compute nuanced expected goals using the split estimates
            home_expected_nuanced = home_attack * home_defense_from_away * league_avg["home"] * advantage
            away_expected_nuanced = away_attack_from_home * home_defense * league_avg["away"]

            # Blend: 50/50 weight when both available, otherwise use available split with 50% weight
            if has_away_home_split and has_home_away_split:
                home_expected = 0.5 * home_expected + 0.5 * home_expected_nuanced
                away_expected = 0.5 * away_expected + 0.5 * away_expected_nuanced
            elif has_away_home_split:
                away_expected = 0.5 * away_expected + 0.5 * away_expected_nuanced
            elif has_home_away_split:
                home_expected = 0.5 * home_expected + 0.5 * home_expected_nuanced

        # 合理范围限制
        home_expected = max(0.3, min(4.0, home_expected))
        away_expected = max(0.2, min(3.5, away_expected))

        return round(home_expected, 3), round(away_expected, 3)

    def predict(
        self,
        home_expected: float,
        away_expected: float,
        return_rate: float = 0.70,
        include_score_matrix: bool = True
    ) -> PoissonMatchPrediction:
        """执行泊松分布预测。

        Args:
            home_expected: 主队预期进球数 λ_home
            away_expected: 客队预期进球数 λ_away
            return_rate: 返还率（仅用于价值投注比较，不影响模型概率）
            include_score_matrix: 是否计算比分概率矩阵

        Returns:
            PoissonMatchPrediction 预测结果（包含真实概率，未经返还率调整）
        """
        # 1. 构建比分概率矩阵
        score_matrix = {}
        for h in range(self.max_goals + 1):
            for a in range(self.max_goals + 1):
                prob = poisson_pmf(h, home_expected) * poisson_pmf(a, away_expected)
                score_matrix[(h, a)] = prob

        # 2. 聚合胜/平/负概率
        home_win = sum(p for (h, a), p in score_matrix.items() if h > a)
        draw = sum(p for (h, a), p in score_matrix.items() if h == a)
        away_win = sum(p for (h, a), p in score_matrix.items() if h < a)

        # 归一化（确保总和=1）
        total = home_win + draw + away_win
        if total > 0:
            home_win /= total
            draw /= total
            away_win /= total

        # NOTE: Return rate is NOT applied to model probabilities.
        # The model outputs TRUE probabilities. The return rate should only
        # be used when comparing model probabilities to market odds
        # (i.e., in find_value_bets, adjust implied_prob = 1/odds * return_rate).

        # 3. 构建完整比分概率字典（不再截断为 Top10）
        score_probs = {}
        for (h, a), p in score_matrix.items():
            score_probs[f"{h}:{a}"] = p

        sorted_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)
        most_likely = sorted_scores[0] if sorted_scores else ("1:1", 0.0)

        # 4. 衍生市场概率
        over_2_5 = sum(p for (h, a), p in score_matrix.items() if h + a > 2)
        over_3_5 = sum(p for (h, a), p in score_matrix.items() if h + a > 3)
        btts = sum(p for (h, a), p in score_matrix.items() if h > 0 and a > 0)

        # 5. 置信区间（基于泊松分布的标准差）
        home_std = math.sqrt(home_expected) if home_expected > 0 else 0
        away_std = math.sqrt(away_expected) if away_expected > 0 else 0

        return PoissonMatchPrediction(
            home_expected_goals=home_expected,
            away_expected_goals=away_expected,
            home_win_prob=round(home_win, 4),
            draw_prob=round(draw, 4),
            away_win_prob=round(away_win, 4),
            home_win_prob_adjusted=round(home_win, 4),
            draw_prob_adjusted=round(draw, 4),
            away_win_prob_adjusted=round(away_win, 4),
            score_probabilities={k: round(v, 6) for k, v in score_probs.items()},
            full_score_matrix=score_matrix,
            over_under_2_5=round(over_2_5, 4),
            over_under_3_5=round(over_3_5, 4),
            btts_prob=round(btts, 4),
            most_likely_score=most_likely[0],
            most_likely_score_prob=round(most_likely[1], 4),
            confidence_interval={
                "home_goals_lower": round(max(0, home_expected - 1.96 * home_std), 2),
                "home_goals_upper": round(home_expected + 1.96 * home_std, 2),
                "away_goals_lower": round(max(0, away_expected - 1.96 * away_std), 2),
                "away_goals_upper": round(away_expected + 1.96 * away_std, 2),
            }
        )

    def predict_with_handicap(
        self,
        home_expected: float,
        away_expected: float,
        handicap: float,
        max_goals: int = 8,
    ) -> Dict[str, Any]:
        """让球胜平负专用预测：基于让球数调整λ值，重建泊松矩阵。

        这是 RQSPF 玩法的官方接口，替代 PlayAnalyzer 中重复的矩阵重建逻辑。

        让球规则（竞彩官方）：
            - handicap > 0: 主队让球（如 +1 表示主队让1球）
            - handicap < 0: 客队让球
            - 调整方式: 主队得分 - handicap vs 客队得分
            - 等价于: adjusted_home_lambda = home_expected - handicap

        Args:
            home_expected: 主队预期进球数 λ_home
            away_expected: 客队预期进球数 λ_away
            handicap: 让球数（正=主让，负=客让）
            max_goals: 矩阵最大进球数

        Returns:
            字典包含:
            - "home_win_prob": 让球主胜概率
            - "draw_prob": 让球平概率
            - "away_win_prob": 让球客胜概率
            - "adjusted_home_lambda": 调整后主队λ
            - "adjusted_away_lambda": 调整后客队λ
            - "score_matrix": 调整后的比分概率矩阵
        """
        MIN_LAMBDA = 0.05
        adjusted_home = max(home_expected - handicap, MIN_LAMBDA)
        adjusted_away = max(away_expected + handicap, MIN_LAMBDA)

        # 构建调整后的比分矩阵
        score_matrix = {}
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob = poisson_pmf(h, adjusted_home) * poisson_pmf(a, adjusted_away)
                score_matrix[(h, a)] = prob

        # 聚合为胜/平/负
        home_win = sum(p for (h, a), p in score_matrix.items() if h > a)
        draw = sum(p for (h, a), p in score_matrix.items() if h == a)
        away_win = sum(p for (h, a), p in score_matrix.items() if h < a)

        # 归一化
        total = home_win + draw + away_win
        if total > 0:
            home_win /= total
            draw /= total
            away_win /= total

        return {
            "home_win_prob": round(home_win, 4),
            "draw_prob": round(draw, 4),
            "away_win_prob": round(away_win, 4),
            "adjusted_home_lambda": round(adjusted_home, 4),
            "adjusted_away_lambda": round(adjusted_away, 4),
            "score_matrix": score_matrix,
        }

    def find_value_bets(
        self,
        prediction: PoissonMatchPrediction,
        market_odds: Dict[str, float],
        threshold: float = 0.10,
        return_rate: float = 0.70,
        max_kelly: float = 0.25,
        market_type: str = None
    ) -> List[Dict]:
        """识别价值投注（全玩法覆盖）。

        对比泊松概率与市场赔率隐含概率，找出差异超过阈值的价值投注。
        支持胜平负、让球胜平负、大小球、双方进球(BTTS)等玩法。

        返还率用于调整市场赔率的隐含概率，以正确考虑庄家利润率：
        implied_prob = 1/odds * return_rate

        Args:
            prediction: 泊松预测结果
            market_odds: 市场赔率，支持以下键：
                胜平负: "win", "draw", "lose"
                让球胜平负: "handicap_win", "handicap_draw", "handicap_lose"
                大小球: "over_2.5", "under_2.5", "over_3.5", "under_3.5"
                双方进球: "btts_yes", "btts_no"
            threshold: 价值阈值（默认10%）
            return_rate: 返还率（用于调整隐含概率，默认0.70）
            max_kelly: Kelly分数上限（默认0.25）
            market_type: 市场类型（用于选择对应阈值），支持:
                "spf", "rqspf", "crs", "ttg", "hafu"

        Returns:
            价值投注列表，按edge降序排列
        """
        # 每市场阈值配置
        MARKET_THRESHOLDS = {
            "spf": 0.08,     # 胜平负：低方差，8%即可
            "rqspf": 0.08,   # 让球胜平负
            "crs": 0.15,     # 比分：高方差，需要15%
            "ttg": 0.10,     # 总进球
            "hafu": 0.12,    # 半全场
        }

        effective_threshold = threshold
        if market_type and market_type in MARKET_THRESHOLDS:
            effective_threshold = MARKET_THRESHOLDS[market_type]

        value_bets = []

        # 1. 胜平负市场
        spf_odds_map = {
            "win": (prediction.home_win_prob, "主胜", "SPF"),
            "draw": (prediction.draw_prob, "平局", "SPF"),
            "lose": (prediction.away_win_prob, "客胜", "SPF"),
        }

        # 2. 让球胜平负市场（使用调整后概率）
        # 让球后概率需要根据让球数重新计算，这里使用简化近似
        handicap_odds_map = {
            "handicap_win": (prediction.home_win_prob_adjusted, "让球主胜", "RQSPF"),
            "handicap_draw": (prediction.draw_prob_adjusted, "让球平局", "RQSPF"),
            "handicap_lose": (prediction.away_win_prob_adjusted, "让球客胜", "RQSPF"),
        }

        # 3. 大小球市场
        ou_odds_map = {
            "over_2.5": (prediction.over_under_2_5, "大2.5球", "DXQ"),
            "under_2.5": (1.0 - prediction.over_under_2_5, "小2.5球", "DXQ"),
            "over_3.5": (prediction.over_under_3_5, "大3.5球", "DXQ"),
            "under_3.5": (1.0 - prediction.over_under_3_5, "小3.5球", "DXQ"),
        }

        # 4. 双方进球(BTTS)市场
        btts_odds_map = {
            "btts_yes": (prediction.btts_prob, "双方进球-是", "BTTS"),
            "btts_no": (1.0 - prediction.btts_prob, "双方进球-否", "BTTS"),
        }

        # 合并所有市场
        all_markets = {}
        all_markets.update(spf_odds_map)
        all_markets.update(handicap_odds_map)
        all_markets.update(ou_odds_map)
        all_markets.update(btts_odds_map)

        for key, (true_prob, label, play_type) in all_markets.items():
            if key not in market_odds:
                continue
            odds = market_odds[key]
            # Adjust implied probability by return rate to account for house edge
            implied_prob = (1.0 / odds * return_rate) if odds > 0 else 0
            edge = true_prob - implied_prob

            if edge > effective_threshold:
                kelly_raw = (true_prob * odds - 1) / (odds - 1) if odds > 1 else 0
                value_bets.append({
                    "market": key,
                    "selection": label,
                    "play_type": play_type,
                    "true_probability": round(true_prob, 4),
                    "implied_probability": round(implied_prob, 4),
                    "edge": round(edge, 4),
                    "odds": odds,
                    "expected_value": round(true_prob * odds - 1, 4),
                    "kelly_fraction": round(max(0, min(max_kelly, kelly_raw)), 4),
                    "recommendation": "强价值" if edge > 0.15 else "价值"
                })

        return sorted(value_bets, key=lambda x: x["edge"], reverse=True)


# ============================================================================
# P0-2: Elo评级系统
# ============================================================================

@dataclass
class EloTeamRating:
    """球队Elo评级"""
    team_id: str
    team_name: str
    rating: float = 1500.0          # 当前评级
    peak_rating: float = 1500.0     # 最高评级
    lowest_rating: float = 1500.0   # 最低评级
    matches_played: int = 0         # 已评比赛数
    home_rating: float = 1500.0     # 主场评级
    away_rating: float = 1500.0     # 客场评级
    last_updated: str = ""          # 最后更新时间
    season_ratings: Dict[str, float] = field(default_factory=dict)  # 赛季评级历史
    # 近期比赛结果序列（最多保留20场）
    # 每条记录: {"date": "YYYY-MM-DD", "opponent": "队名", "result": "W/D/L", "elo_change": +15.2, "home_away": "H/A"}
    recent_results: List[Dict[str, Any]] = field(default_factory=list)
    MAX_RECENT_RESULTS = 20


class EloRatingSystem:
    """完整Elo评级系统

    基于国际足联Elo评级方法，适配足球比赛特点：
    - 考虑主客场因素（主场加成）
    - 考虑比赛重要性（友谊赛/联赛/杯赛/国际大赛）
    - 考虑净胜球权重
    - 支持动态K因子（新球队K值更大，快速收敛）
    - 支持联赛均值回归（防止评级漂移）

    与简化版的区别：
    - 简化版：硬编码分段映射 (diff>200 → 90分)
    - 完整版：连续概率函数 + 动态更新 + 持久化
    """

    # K因子配置
    K_FACTORS = {
        "friendly": 20,        # 友谊赛
        "league": 32,          # 联赛
        "cup": 36,             # 国内杯赛
        "continental": 40,     # 洲际比赛
        "world_cup": 48,       # 世界杯
        # 新增
        "champions_league_group": 38,
        "champions_league_knockout": 44,
        "domestic_cup_early": 28,
        "domestic_cup_late": 36,
        "relegation": 38,
        "playoff": 42,
        "international_qualifier": 36,
    }

    # 主场优势Elo加成（约等于100/3 ≈ 33分）
    HOME_ADVANTAGE = 35

    # 联赛基准Elo（用于新球队初始化）
    LEAGUE_BASE_ELO = {
        "英超": 1650,
        "西甲": 1630,
        "德甲": 1600,
        "意甲": 1590,
        "法甲": 1560,
        "欧冠": 1700,
        "欧联": 1550,
        "default": 1500,
    }

    # 默认K因子
    DEFAULT_K = 32

    # 均值回归参数
    MEAN_REVERSION_RATE = 0.02  # 每场比赛向联赛基准回归2%
    MEAN_REVERSION_THRESHOLD = 100  # 偏离基准超过100分时启用均值回归

    def __init__(self, ratings_file: Optional[str] = None, random_seed: Optional[int] = None):
        """
        Args:
            ratings_file: 评级持久化文件路径
            random_seed: 随机种子，用于新球队初始化的可重复性。
                         设为固定值（如42）可获得确定性结果；设为None则使用系统随机。
        """
        self.ratings: Dict[str, EloTeamRating] = {}
        self.ratings_file = ratings_file
        self._rng = random.Random(random_seed)
        self._load_ratings()

    def _get_k_factor(self, match_type: str) -> int:
        """获取K因子，支持模糊匹配"""
        if match_type in self.K_FACTORS:
            return self.K_FACTORS[match_type]
        # 模糊匹配
        match_type_lower = match_type.lower()
        if "champion" in match_type_lower and "knockout" in match_type_lower:
            return self.K_FACTORS["champions_league_knockout"]
        if "champion" in match_type_lower:
            return self.K_FACTORS["champions_league_group"]
        if "relegation" in match_type_lower or "playoff" in match_type_lower:
            return self.K_FACTORS["playoff"]
        # 默认联赛级别
        return self.K_FACTORS["league"]

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """计算A队对B队的预期得分。

        公式: E_A = 1 / (1 + 10^((R_B - R_A) / 400))

        Args:
            rating_a: A队评级
            rating_b: B队评级

        Returns:
            A队预期得分（0-1之间）
        """
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def get_rating(self, team_id: str, team_name: str = "", league: str = "default") -> float:
        """获取球队Elo评级。

        如果球队不存在，根据联赛基准初始化。

        Args:
            team_id: 球队ID
            team_name: 球队名称
            league: 联赛名称

        Returns:
            Elo评级
        """
        if team_id in self.ratings:
            return self.ratings[team_id].rating

        # 新球队：根据联赛基准初始化
        base = self.LEAGUE_BASE_ELO.get(league, self.LEAGUE_BASE_ELO["default"])
        # 使用确定性扰动（基于队名哈希），确保相同队名始终获得相同初始评级
        h = int(hashlib.md5(team_name.encode()).hexdigest()[:8], 16)
        perturbation = (h % 51) - 25  # -25 to +25
        initial_rating = base + perturbation
        self.ratings[team_id] = EloTeamRating(
            team_id=team_id,
            team_name=team_name or team_id,
            rating=initial_rating,
            peak_rating=initial_rating,
            lowest_rating=initial_rating,
            home_rating=initial_rating,
            away_rating=initial_rating,
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return initial_rating

    def update_rating(
        self,
        home_team_id: str,
        away_team_id: str,
        home_goals: int,
        away_goals: int,
        match_type: str = "league",
        home_team_name: str = "",
        away_team_name: str = "",
        league: str = "default"
    ) -> Dict:
        """更新两队Elo评级。

        Args:
            home_team_id: 主队ID
            away_team_id: 客队ID
            home_goals: 主队进球数
            away_goals: 客队进球数
            match_type: 比赛类型
            home_team_name: 主队名称
            away_team_name: 客队名称
            league: 联赛

        Returns:
            更新结果（包含前后评级变化）
        """
        # 获取当前评级
        home_rating = self.get_rating(home_team_id, home_team_name, league)
        away_rating = self.get_rating(away_team_id, away_team_name, league)

        # 计算预期得分（含主场优势）
        home_expected = self.expected_score(
            home_rating + self.HOME_ADVANTAGE, away_rating
        )
        away_expected = 1.0 - home_expected

        # 计算实际得分（考虑净胜球权重）
        home_actual = self._actual_score(home_goals, away_goals)
        away_actual = 1.0 - home_actual

        # 获取K因子
        k = self.K_FACTORS.get(match_type, self.DEFAULT_K)

        # 动态K因子：比赛场次少的球队K值更大
        home_matches = self.ratings[home_team_id].matches_played
        away_matches = self.ratings[away_team_id].matches_played
        home_k = k * max(1.0, 2.0 - home_matches / 30.0) if home_matches < 30 else k
        away_k = k * max(1.0, 2.0 - away_matches / 30.0) if away_matches < 30 else k

        # 更新评级
        home_new = home_rating + home_k * (home_actual - home_expected)
        away_new = away_rating + away_k * (away_actual - away_expected)

        # 联赛均值回归：防止评级过度漂移
        # 当球队评级偏离联赛基准超过阈值时，每场比赛向基准回归一小步
        league_base = self.LEAGUE_BASE_ELO.get(league, self.LEAGUE_BASE_ELO["default"])
        home_deviation = home_new - league_base
        away_deviation = away_new - league_base

        if abs(home_deviation) > self.MEAN_REVERSION_THRESHOLD:
            if home_matches < 5:  # 只在初始化阶段应用
                home_new -= home_deviation * self.MEAN_REVERSION_RATE
        if abs(away_deviation) > self.MEAN_REVERSION_THRESHOLD:
            if away_matches < 5:  # 只在初始化阶段应用
                away_new -= away_deviation * self.MEAN_REVERSION_RATE

        # 更新记录
        home_entry = self.ratings[home_team_id]
        home_entry.rating = round(home_new, 1)
        home_entry.peak_rating = max(home_entry.peak_rating, home_new)
        home_entry.lowest_rating = min(home_entry.lowest_rating, home_new)
        home_entry.matches_played += 1
        home_entry.home_rating = round((home_entry.home_rating * (home_matches) + home_new) / (home_matches + 1), 1)
        home_entry.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 记录近期比赛结果
        home_result = "W" if home_goals > away_goals else ("D" if home_goals == away_goals else "L")
        home_entry.recent_results.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "opponent": away_team_name or away_team_id,
            "result": home_result,
            "elo_change": round(home_new - home_rating, 1),
            "home_away": "H",
            "score": f"{home_goals}:{away_goals}",
        })
        if len(home_entry.recent_results) > home_entry.MAX_RECENT_RESULTS:
            home_entry.recent_results = home_entry.recent_results[-home_entry.MAX_RECENT_RESULTS:]

        away_entry = self.ratings[away_team_id]
        away_entry.rating = round(away_new, 1)
        away_entry.peak_rating = max(away_entry.peak_rating, away_new)
        away_entry.lowest_rating = min(away_entry.lowest_rating, away_new)
        away_entry.matches_played += 1
        away_entry.away_rating = round((away_entry.away_rating * (away_matches) + away_new) / (away_matches + 1), 1)
        away_entry.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 记录客队近期比赛结果
        away_result = "W" if away_goals > home_goals else ("D" if away_goals == home_goals else "L")
        away_entry.recent_results.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "opponent": home_team_name or home_team_id,
            "result": away_result,
            "elo_change": round(away_new - away_rating, 1),
            "home_away": "A",
            "score": f"{away_goals}:{home_goals}",
        })
        if len(away_entry.recent_results) > away_entry.MAX_RECENT_RESULTS:
            away_entry.recent_results = away_entry.recent_results[-away_entry.MAX_RECENT_RESULTS:]

        self._save_ratings()

        return {
            "home_team": home_team_name or home_team_id,
            "home_rating_before": round(home_rating, 1),
            "home_rating_after": round(home_new, 1),
            "home_rating_change": round(home_new - home_rating, 1),
            "away_team": away_team_name or away_team_id,
            "away_rating_before": round(away_rating, 1),
            "away_rating_after": round(away_new, 1),
            "away_rating_change": round(away_new - away_rating, 1),
            "home_expected": round(home_expected, 4),
            "home_actual": round(home_actual, 4),
            "k_factor": k,
            "match_result": f"{home_goals}:{away_goals}",
        }

    def predict_match(
        self,
        home_team_id: str,
        away_team_id: str,
        league: str = "default"
    ) -> Dict:
        """基于Elo评级预测比赛。

        Args:
            home_team_id: 主队ID
            away_team_id: 客队ID
            league: 联赛

        Returns:
            预测结果
        """
        home_rating = self.get_rating(home_team_id, league=league)
        away_rating = self.get_rating(away_team_id, league=league)

        # 含主场优势的预期得分
        home_expected = self.expected_score(
            home_rating + self.HOME_ADVANTAGE, away_rating
        )

        # 转换为胜/平/负概率（基于Elo预期得分的经验公式）
        # 参考: https://en.wikipedia.org/wiki/Elo_rating_system
        home_win_prob = self._elo_to_win_prob(home_expected)
        draw_prob = self._elo_to_draw_prob(home_expected)
        away_win_prob = 1.0 - home_win_prob - draw_prob

        # 评级差距分析
        rating_diff = home_rating - away_rating

        return {
            "home_team_id": home_team_id,
            "home_team_name": self.ratings.get(home_team_id, EloTeamRating(team_id=home_team_id, team_name="")).team_name,
            "home_elo": round(home_rating, 1),
            "home_home_elo": round(self.ratings.get(home_team_id, EloTeamRating(team_id=home_team_id, team_name="")).home_rating, 1),
            "away_team_id": away_team_id,
            "away_team_name": self.ratings.get(away_team_id, EloTeamRating(team_id=away_team_id, team_name="")).team_name,
            "away_elo": round(away_rating, 1),
            "away_away_elo": round(self.ratings.get(away_team_id, EloTeamRating(team_id=away_team_id, team_name="")).away_rating, 1),
            "rating_diff": round(rating_diff, 1),
            "home_advantage": self.HOME_ADVANTAGE,
            "home_win_prob": round(max(0, home_win_prob), 4),
            "draw_prob": round(max(0, draw_prob), 4),
            "away_win_prob": round(max(0, away_win_prob), 4),
            "home_matches_rated": self.ratings.get(home_team_id, EloTeamRating(team_id=home_team_id, team_name="")).matches_played,
            "away_matches_rated": self.ratings.get(away_team_id, EloTeamRating(team_id=away_team_id, team_name="")).matches_played,
            "form_elo": self._get_form_elo(home_team_id, away_team_id),
        }

    def _actual_score(self, goals_for: int, goals_against: int) -> float:
        """将比赛结果转换为实际得分（考虑净胜球权重）。

        胜=1.0, 平=0.5, 负=0.0
        大胜额外加权（最多+0.3）

        Args:
            goals_for: 进球数
            goals_against: 失球数

        Returns:
            实际得分 (0-1.3)
        """
        diff = goals_for - goals_against
        if diff > 0:
            return 1.0 + min(0.3, diff * 0.1)  # 大胜加权
        elif diff == 0:
            return 0.5
        else:
            return max(0.0, 0.0 + diff * 0.1)  # 大负减权

    def _elo_to_win_prob(self, expected: float) -> float:
        """将Elo预期得分转换为主胜概率。

        使用标准Elo预期得分到胜/平/负的映射公式：
        - win_prob = E * (1 - draw_factor)
        - draw_prob = draw_factor * (1 - |E - 0.5| * 2 * dampening)
        - away_win_prob = (1 - E) * (1 - draw_factor)
        
        其中 draw_factor=0.26（足球典型平局率），dampening=0.8（阻尼系数）。
        最后对各项概率进行夹紧和归一化处理。

        Args:
            expected: Elo预期得分 E = 1 / (1 + 10^((Rb-Ra)/400))

        Returns:
            主胜概率
        """
        # 足球典型平局因子和阻尼系数
        draw_factor = 0.26
        dampening = 0.8

        # 基于Elo预期得分的标准映射
        win = expected * (1.0 - draw_factor)
        draw = draw_factor * (1.0 - abs(expected - 0.5) * 2.0 * dampening)
        away_win = (1.0 - expected) * (1.0 - draw_factor)

        # 夹紧到合理范围
        win = max(0.05, min(0.85, win))
        draw = max(0.15, min(0.35, draw))
        away_win = max(0.05, min(0.85, away_win))

        # 归一化确保总和为1
        total = win + draw + away_win
        if total > 0:
            win /= total

        return win

    def _elo_to_draw_prob(self, expected: float) -> float:
        """将Elo预期得分转换为平局概率。

        使用与 _elo_to_win_prob 相同的映射公式，确保胜/平/负概率一致。

        Args:
            expected: Elo预期得分

        Returns:
            平局概率
        """
        # 足球典型平局因子和阻尼系数
        draw_factor = 0.26
        dampening = 0.8

        # 基于Elo预期得分的标准映射
        win = expected * (1.0 - draw_factor)
        draw = draw_factor * (1.0 - abs(expected - 0.5) * 2.0 * dampening)
        away_win = (1.0 - expected) * (1.0 - draw_factor)

        # 夹紧到合理范围
        win = max(0.05, min(0.85, win))
        draw = max(0.15, min(0.35, draw))
        away_win = max(0.05, min(0.85, away_win))

        # 归一化确保总和为1
        total = win + draw + away_win
        if total > 0:
            draw /= total

        return draw

    def _get_form_elo(self, home_team_id: str, away_team_id: str) -> Dict:
        """获取两队近期状态评级（增强版）。

        增强内容：
        - 原有：峰值对比评级（excellent/good/average/poor）
        - 新增：近期N场胜率、趋势方向、动量指标、连续不败/连败

        Args:
            home_team_id: 主队ID
            away_team_id: 客队ID

        Returns:
            状态评级信息
        """
        home = self.ratings.get(home_team_id)
        away = self.ratings.get(away_team_id)

        result = {
            "home_form": "unknown",
            "away_form": "unknown",
            "form_comparison": "even",
            "home_trend": None,
            "away_trend": None,
            "home_momentum": None,
            "away_momentum": None,
            "home_recent": None,
            "away_recent": None,
        }

        # 分析主队状态
        if home and home.matches_played > 0:
            # 原有峰值对比评级
            home_decline = home.peak_rating - home.rating
            if home_decline < 20:
                result["home_form"] = "excellent"
            elif home_decline < 50:
                result["home_form"] = "good"
            elif home_decline < 100:
                result["home_form"] = "average"
            else:
                result["home_form"] = "poor"

            # 新增：趋势分析
            result["home_trend"] = self._analyze_team_trend(home)
            result["home_momentum"] = self._calculate_momentum(home)
            result["home_recent"] = self._summarize_recent(home, n=5)

        # 分析客队状态
        if away and away.matches_played > 0:
            away_decline = away.peak_rating - away.rating
            if away_decline < 20:
                result["away_form"] = "excellent"
            elif away_decline < 50:
                result["away_form"] = "good"
            elif away_decline < 100:
                result["away_form"] = "average"
            else:
                result["away_form"] = "poor"

            result["away_trend"] = self._analyze_team_trend(away)
            result["away_momentum"] = self._calculate_momentum(away)
            result["away_recent"] = self._summarize_recent(away, n=5)

        # 比较两队状态
        form_order = {"excellent": 4, "good": 3, "average": 2, "poor": 1, "unknown": 0}
        h = form_order.get(result["home_form"], 0)
        a = form_order.get(result["away_form"], 0)
        if h > a:
            result["form_comparison"] = "home_better"
        elif a > h:
            result["form_comparison"] = "away_better"

        # 基于动量的补充比较
        hm = result.get("home_momentum")
        am = result.get("away_momentum")
        if hm is not None and am is not None:
            if abs(hm - am) > 15:
                if hm > am and result["form_comparison"] != "home_better":
                    result["form_comparison"] = "home_momentum_better"
                elif am > hm and result["form_comparison"] != "away_better":
                    result["form_comparison"] = "away_momentum_better"

        return result

    def _analyze_team_trend(self, team: 'EloTeamRating') -> Dict[str, Any]:
        """分析球队趋势方向

        Args:
            team: 球队评级数据

        Returns:
            趋势分析结果
        """
        results = team.recent_results
        if len(results) < 3:
            return {
                "direction": "insufficient_data",
                "description": f"仅{len(results)}场比赛数据，趋势不可靠",
                "win_rate": None,
                "elo_trend": None,
            }

        # 近期胜率
        n = min(len(results), 10)
        recent = results[-n:]
        wins = sum(1 for r in recent if r["result"] == "W")
        draws = sum(1 for r in recent if r["result"] == "D")
        win_rate = wins / n

        # Elo变化趋势（线性回归斜率）
        elo_changes = [r["elo_change"] for r in recent]
        avg_change = sum(elo_changes) / len(elo_changes)

        # 前半段 vs 后半段对比
        mid = len(recent) // 2
        first_half_avg = sum(elo_changes[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(elo_changes[mid:]) / (len(recent) - mid) if len(recent) > mid else 0

        # 判断趋势方向
        if second_half_avg > first_half_avg + 2:
            direction = "improving"  # 加速上升
        elif second_half_avg > first_half_avg:
            direction = "stable_improving"  # 稳步上升
        elif second_half_avg < first_half_avg - 2:
            direction = "declining"  # 加速下滑
        elif second_half_avg < first_half_avg:
            direction = "stable_declining"  # 稳步下滑
        else:
            direction = "stable"  # 平稳

        # 连胜/连败检测
        streak_type = None
        streak_count = 0
        for r in reversed(recent):
            if streak_type is None:
                streak_type = r["result"]
                streak_count = 1
            elif r["result"] == streak_type:
                streak_count += 1
            else:
                break

        # 不败序列（W+D）
        unbeaten = 0
        for r in reversed(recent):
            if r["result"] in ("W", "D"):
                unbeaten += 1
            else:
                break

        direction_labels = {
            "improving": "加速上升",
            "stable_improving": "稳步上升",
            "stable": "平稳",
            "stable_declining": "稳步下滑",
            "declining": "加速下滑",
        }

        return {
            "direction": direction,
            "description": direction_labels.get(direction, direction),
            "win_rate": round(win_rate, 3),
            "draw_rate": round(draws / n, 3),
            "loss_rate": round(1 - win_rate - draws / n, 3),
            "avg_elo_change": round(avg_change, 1),
            "recent_n": n,
            "streak": {
                "type": streak_type,
                "count": streak_count,
            },
            "unbeaten_run": unbeaten,
        }

    def _calculate_momentum(self, team: 'EloTeamRating') -> float:
        """计算球队动量指标

        动量 = 近5场Elo变化的加权平均（越近权重越大）
        正值表示上升势头，负值表示下滑趋势

        Args:
            team: 球队评级数据

        Returns:
            动量值（-50 到 +50）
        """
        results = team.recent_results
        if len(results) < 2:
            return 0.0

        n = min(len(results), 5)
        recent = results[-n:]

        # 加权平均：最近的比赛权重更大
        weights = [i + 1 for i in range(n)]  # [1, 2, 3, 4, 5]
        total_weight = sum(weights)

        weighted_change = sum(
            r["elo_change"] * w
            for r, w in zip(recent, weights)
        )

        momentum = weighted_change / total_weight
        return round(max(-50, min(50, momentum)), 1)

    def _summarize_recent(self, team: 'EloTeamRating', n: int = 5) -> Dict[str, Any]:
        """总结球队近期表现

        Args:
            team: 球队评级数据
            n: 近N场

        Returns:
            近期表现摘要
        """
        results = team.recent_results
        if not results:
            return {"available": False}

        recent = results[-n:]
        summary = {
            "available": True,
            "n": len(recent),
            "results": [f"{r['result']}({r['score']})" for r in recent],
            "record": f"{sum(1 for r in recent if r['result']=='W')}W{sum(1 for r in recent if r['result']=='D')}D{sum(1 for r in recent if r['result']=='L')}L",
            "goals_for": 0,
            "goals_against": 0,
        }

        # 计算进失球
        for r in recent:
            if "score" in r:
                parts = r["score"].split(":")
                if len(parts) == 2:
                    summary["goals_for"] += int(parts[0])
                    summary["goals_against"] += int(parts[1])

        return summary

    def get_top_teams(self, n: int = 20, league: Optional[str] = None) -> List[Dict]:
        """获取Elo评级排行榜。

        Args:
            n: 返回前N名
            league: 联赛筛选（可选）

        Returns:
            排行榜列表
        """
        teams = [r for r in self.ratings.values() if r.matches_played > 0]
        teams.sort(key=lambda x: x.rating, reverse=True)

        return [
            {
                "rank": i + 1,
                "team_id": t.team_id,
                "team_name": t.team_name,
                "rating": round(t.rating, 1),
                "matches": t.matches_played,
                "peak": round(t.peak_rating, 1),
                "home_elo": round(t.home_rating, 1),
                "away_elo": round(t.away_rating, 1),
            }
            for i, t in enumerate(teams[:n])
        ]

    def _load_ratings(self):
        """从文件加载评级数据。"""
        if self.ratings_file and os.path.exists(self.ratings_file):
            try:
                with open(self.ratings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for team_id, team_data in data.items():
                    self.ratings[team_id] = EloTeamRating(**team_data)
                logger.info(f"已加载 {len(self.ratings)} 支球队的Elo评级")
            except Exception as e:
                logger.warning(f"加载Elo评级失败: {e}")

    def _save_ratings(self):
        """保存评级数据到文件。"""
        if self.ratings_file:
            try:
                data = {tid: asdict(r) for tid, r in self.ratings.items()}
                os.makedirs(os.path.dirname(self.ratings_file) if os.path.dirname(self.ratings_file) else '.', exist_ok=True)
                with open(self.ratings_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"保存Elo评级失败: {e}")


# ============================================================================
# P0-3: 增强xG分析模型
# ============================================================================

@dataclass
class XGAnalysisResult:
    """xG分析结果"""
    home_xg: float                     # 主队预期进球
    away_xg: float                     # 客队预期进球
    home_xg_per_90: float              # 主队每90分钟xG
    away_xg_per_90: float              # 客队每90分钟xG
    home_xga: float                    # 主队预期失球 (xGA)
    away_xga: float                    # 客队预期失球 (xGA)
    home_xg_difference: float          # 主队xG差值 (xG - xGA)
    away_xg_difference: float          # 客队xG差值
    home_shot_quality: float            # 主队射门质量评分
    away_shot_quality: float            # 客队射门质量评分
    sustainability_score: float         # 表现可持续性评分 (0-100)
    regression_warning: str             # 均值回归预警
    details: Dict[str, Any] = field(default_factory=dict)


class XGModel:
    """增强xG（预期进球）分析模型

    与简化版的区别：
    - 简化版：xG = points_per_game * 0.8 + goal_difference * 0.02
    - 完整版：基于射门数据、进球转化率、联赛均值的多维xG模型

    当详细射门数据不可用时，使用基于联赛统计的估算模型。
    """

    # 联赛平均xG数据（基于历史统计）
    LEAGUE_XG_AVG = {
        "英超": {"xg_for": 1.45, "xga": 1.30, "shots_per_game": 13.5, "shot_on_target_pct": 0.35},
        "西甲": {"xg_for": 1.40, "xga": 1.20, "shots_per_game": 12.8, "shot_on_target_pct": 0.34},
        "德甲": {"xg_for": 1.55, "xga": 1.35, "shots_per_game": 14.2, "shot_on_target_pct": 0.36},
        "意甲": {"xg_for": 1.35, "xga": 1.15, "shots_per_game": 12.5, "shot_on_target_pct": 0.33},
        "法甲": {"xg_for": 1.40, "xga": 1.25, "shots_per_game": 13.0, "shot_on_target_pct": 0.34},
        "default": {"xg_for": 1.40, "xga": 1.25, "shots_per_game": 13.2, "shot_on_target_pct": 0.34},
    }

    def analyze(
        self,
        home_goals_for: int, home_games: int, home_goals_against: int,
        away_goals_for: int, away_games: int, away_goals_against: int,
        home_shots: Optional[int] = None, home_shots_on_target: Optional[int] = None,
        away_shots: Optional[int] = None, away_shots_on_target: Optional[int] = None,
        league: str = "default",
        home_recent_goals: Optional[List[int]] = None,
        away_recent_goals: Optional[List[int]] = None,
    ) -> XGAnalysisResult:
        """执行xG分析。

        支持两种模式：
        1. 完整模式：有射门数据时，使用精确xG计算
        2. 估算模式：无射门数据时，基于进球和联赛均值估算

        Args:
            home_goals_for: 主队主场进球总数
            home_games: 主队主场场次
            home_goals_against: 主队主场失球总数
            away_goals_for: 客队客场进球总数
            away_games: 客队客场场次
            away_goals_against: 客队客场失球总数
            home_shots: 主队射门总数（可选）
            home_shots_on_target: 主队射正总数（可选）
            away_shots: 客队射门总数（可选）
            away_shots_on_target: 客队射正总数（可选）
            league: 联赛名称
            home_recent_goals: 主队近期每场进球数列表（可选）
            away_recent_goals: 客队近期每场进球数列表（可选）

        Returns:
            XGAnalysisResult 分析结果
        """
        league_avg = self.LEAGUE_XG_AVG.get(league, self.LEAGUE_XG_AVG["default"])

        # ---- 主队xG计算 ----
        if home_games > 0:
            home_goals_per_game = home_goals_for / home_games
            home_goals_against_per_game = home_goals_against / home_games
        else:
            home_goals_per_game = league_avg["xg_for"]
            home_goals_against_per_game = league_avg["xga"]

        # 进球转化率调整（实际进球 vs 联赛平均）
        home_attack_strength = home_goals_per_game / league_avg["xg_for"] if league_avg["xg_for"] > 0 else 1.0
        home_defense_strength = home_goals_against_per_game / league_avg["xga"] if league_avg["xga"] > 0 else 1.0

        # 如果有射门数据，使用更精确的模型
        if home_shots and home_shots_on_target and home_games > 0:
            home_shots_per_game = home_shots / home_games
            home_sot_per_game = home_shots_on_target / home_games
            home_sot_rate = home_shots_on_target / home_shots if home_shots > 0 else 0

            # xG = 射正率 × 射正转化率 × 联赛基准
            home_goal_conversion = home_goals_for / home_shots_on_target if home_shots_on_target > 0 else league_avg["shot_on_target_pct"]
            home_xg = home_sot_rate * home_goal_conversion * league_avg["xg_for"] * 1.1  # 1.1为主场加成
            home_shot_quality = min(100, home_sot_rate / league_avg["shot_on_target_pct"] * 50 + home_goal_conversion * 30)
        else:
            # 估算模式：基于进球数据的回归模型
            # xG ≈ 进球率 × 联赛平均转化率倒数 × 进攻强度
            avg_conversion = league_avg["xg_for"] / league_avg["shots_per_game"] * league_avg["shot_on_target_pct"]
            home_xg = home_goals_per_game / avg_conversion * 0.85 if avg_conversion > 0 else home_goals_per_game
            home_shot_quality = 50 + (home_attack_strength - 1.0) * 30

        # ---- 客队xG计算 ----
        if away_games > 0:
            away_goals_per_game = away_goals_for / away_games
            away_goals_against_per_game = away_goals_against / away_games
        else:
            away_goals_per_game = league_avg["xg_for"] * 0.85  # 客场通常低15%
            away_goals_against_per_game = league_avg["xga"] * 0.85

        away_attack_strength = away_goals_per_game / (league_avg["xg_for"] * 0.85) if league_avg["xg_for"] > 0 else 1.0
        away_defense_strength = away_goals_against_per_game / (league_avg["xga"] * 0.85) if league_avg["xga"] > 0 else 1.0

        if away_shots and away_shots_on_target and away_games > 0:
            away_sot_rate = away_shots_on_target / away_shots if away_shots > 0 else 0
            away_goal_conversion = away_goals_for / away_shots_on_target if away_shots_on_target > 0 else league_avg["shot_on_target_pct"]
            away_xg = away_sot_rate * away_goal_conversion * league_avg["xg_for"] * 0.85  # 0.85为客场减成
            away_shot_quality = min(100, away_sot_rate / league_avg["shot_on_target_pct"] * 50 + away_goal_conversion * 30)
        else:
            avg_conversion = league_avg["xg_for"] / league_avg["shots_per_game"] * league_avg["shot_on_target_pct"]
            away_xg = away_goals_per_game / avg_conversion * 0.75 if avg_conversion > 0 else away_goals_per_game
            away_shot_quality = 50 + (away_attack_strength - 1.0) * 30

        # ---- xGA（预期失球）计算 ----
        home_xga = away_xg  # 主队预期失球 = 客队预期进球
        away_xga = home_xg  # 客队预期失球 = 主队预期进球

        # ---- xG差值 ----
        home_xg_diff = home_xg - home_xga
        away_xg_diff = away_xg - away_xga

        # ---- 可持续性评分 ----
        sustainability = self._assess_sustainability(
            home_goals_per_game, home_xg,
            home_recent_goals, league
        )

        # ---- 均值回归预警 ----
        regression_warning = self._check_regression_warning(
            home_goals_per_game, home_xg,
            away_goals_per_game, away_xg
        )

        # 归一化（放宽上限以支持高进攻强度球队）
        home_xg = max(0.2, min(5.0, home_xg))
        away_xg = max(0.2, min(4.5, away_xg))

        return XGAnalysisResult(
            home_xg=round(home_xg, 3),
            away_xg=round(away_xg, 3),
            home_xg_per_90=round(home_xg, 3),
            away_xg_per_90=round(away_xg, 3),
            home_xga=round(home_xga, 3),
            away_xga=round(away_xga, 3),
            home_xg_difference=round(home_xg_diff, 3),
            away_xg_difference=round(away_xg_diff, 3),
            home_shot_quality=round(max(0, min(100, home_shot_quality)), 1),
            away_shot_quality=round(max(0, min(100, away_shot_quality)), 1),
            sustainability_score=round(sustainability, 1),
            regression_warning=regression_warning,
            details={
                "home_attack_strength": round(home_attack_strength, 3),
                "home_defense_strength": round(home_defense_strength, 3),
                "away_attack_strength": round(away_attack_strength, 3),
                "away_defense_strength": round(away_defense_strength, 3),
                "league_avg_xg": league_avg["xg_for"],
                "data_mode": "full" if (home_shots and away_shots) else "estimated",
            }
        )

    def _assess_sustainability(
        self,
        goals_per_game: float,
        xg: float,
        recent_goals: Optional[List[int]],
        league: str
    ) -> float:
        """评估球队表现的可持续性。

        比较实际进球与xG的偏差，偏差越大可持续性越低。

        Args:
            goals_per_game: 实际场均进球
            xg: 预期进球
            recent_goals: 近期每场进球数
            league: 联赛

        Returns:
            可持续性评分 (0-100)
        """
        if xg <= 0:
            return 50.0

        # 实际 vs xG 偏差
        deviation = (goals_per_game - xg) / xg

        # 基础可持续性评分
        base_score = 100 - abs(deviation) * 50

        # 近期趋势调整
        trend_adjustment = 0
        if recent_goals and len(recent_goals) >= 3:
            recent_avg = sum(recent_goals[-3:]) / 3
            overall_avg = sum(recent_goals) / len(recent_goals) if recent_goals else 0
            if overall_avg > 0:
                trend = (recent_avg - overall_avg) / overall_avg
                # 如果近期趋势与xG方向一致，提高可持续性
                if (trend > 0 and deviation > 0) or (trend < 0 and deviation < 0):
                    trend_adjustment = 5
                else:
                    trend_adjustment = -10

        return max(0, min(100, base_score + trend_adjustment))

    def _check_regression_warning(
        self,
        home_goals_per_game: float,
        home_xg: float,
        away_goals_per_game: float,
        away_xg: float
    ) -> str:
        """检查均值回归预警。

        Args:
            home_goals_per_game: 主队实际场均进球
            home_xg: 主队xG
            away_goals_per_game: 客队实际场均进球
            away_xg: 客队xG

        Returns:
            预警信息
        """
        warnings = []

        home_deviation = (home_goals_per_game - home_xg) / home_xg if home_xg > 0 else 0
        away_deviation = (away_goals_per_game - away_xg) / away_xg if away_xg > 0 else 0

        if home_deviation > 0.3:
            warnings.append(f"主队实际进球超出xG {home_deviation:.0%}，存在均值回归风险")
        elif home_deviation < -0.3:
            warnings.append(f"主队实际进球低于xG {abs(home_deviation):.0%}，可能被低估")

        if away_deviation > 0.3:
            warnings.append(f"客队实际进球超出xG {away_deviation:.0%}，存在均值回归风险")
        elif away_deviation < -0.3:
            warnings.append(f"客队实际进球低于xG {abs(away_deviation):.0%}，可能被低估")

        return "; ".join(warnings) if warnings else "无显著均值回归风险"


# ============================================================================
# 统一接口：集成三个模型
# ============================================================================

@dataclass
class StatisticalAnalysisResult:
    """统计模型综合分析结果"""
    poisson: PoissonMatchPrediction
    elo: Dict
    xg: XGAnalysisResult
    combined_score: float              # 综合评分 (0-100)
    combined_reasoning: str            # 综合推理说明
    value_bets: List[Dict]             # 价值投注
    agreement_level: str               # 模型一致性程度


class StatisticalEngine:
    """统计模型引擎 - 统一接口

    集成泊松分布、Elo评级、xG分析三大模型，
    提供统一的比赛预测接口。

    支持动态权重调整：根据历史预测准确率自动调整各模型权重。
    """

    # 默认模型权重
    DEFAULT_WEIGHTS = {"poisson": 0.40, "elo": 0.30, "xg": 0.30}
    # 权重范围限制
    MIN_WEIGHT = 0.10
    MAX_WEIGHT = 0.60

    def __init__(self, elo_ratings_file: Optional[str] = None):
        self.poisson = PoissonModel()
        self.elo = EloRatingSystem(ratings_file=elo_ratings_file)
        self.xg = XGModel()
        # 动态权重（初始为默认值）
        self._weights = dict(self.DEFAULT_WEIGHTS)
        # 预测历史记录（用于校准权重）
        self._prediction_history: List[Dict] = []

    def get_weights(self) -> Dict[str, float]:
        """获取当前模型权重"""
        return dict(self._weights)

    def record_prediction_result(
        self,
        match_id: str,
        predicted_probs: Dict[str, float],
        actual_result: str,
    ) -> Dict:
        """记录预测结果并更新模型权重。

        Args:
            match_id: 比赛ID
            predicted_probs: 各模型预测概率 {"poisson": {"win": 0.5, ...}, "elo": {...}, "xg": {...}}
            actual_result: 实际结果 ("win"/"draw"/"lose")

        Returns:
            各模型的准确率和更新后的权重
        """
        # 计算各模型的对数损失（log loss）
        model_losses = {}
        for model_name, probs in predicted_probs.items():
            actual_prob = probs.get(actual_result, 0.01)
            actual_prob = max(actual_prob, 0.01)  # 避免log(0)
            loss = -math.log(actual_prob)
            model_losses[model_name] = loss

        self._prediction_history.append({
            "match_id": match_id,
            "losses": model_losses,
            "actual_result": actual_result,
        })

        # 基于最近20次预测的滑动窗口更新权重
        self._recalibrate_weights()

        return {
            "match_id": match_id,
            "losses": model_losses,
            "updated_weights": dict(self._weights),
            "history_size": len(self._prediction_history),
        }

    def _recalibrate_weights(self, window: int = 20):
        """基于滑动窗口重新校准模型权重。

        使用softmax反函数：权重与平均损失的倒数成正比。
        限制在MIN_WEIGHT和MAX_WEIGHT之间。
        """
        if len(self._prediction_history) < 5:
            return  # 数据不足，保持默认权重

        # 取最近window次预测
        recent = self._prediction_history[-window:]

        # 计算各模型的平均损失
        avg_losses = {}
        for model_name in self.DEFAULT_WEIGHTS:
            losses = [r["losses"].get(model_name, 1.0) for r in recent if model_name in r["losses"]]
            if losses:
                avg_losses[model_name] = sum(losses) / len(losses)
            else:
                avg_losses[model_name] = 1.0

        # 权重与损失倒数成正比（损失越低，权重越高）
        inv_losses = {k: 1.0 / v for k, v in avg_losses.items()}
        total_inv = sum(inv_losses.values())

        # 归一化并限制范围
        raw_weights = {k: v / total_inv for k, v in inv_losses.items()}
        new_weights = {}
        for k, w in raw_weights.items():
            new_weights[k] = max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, w))

        # 二次归一化（确保总和为1.0）
        total = sum(new_weights.values())
        self._weights = {k: v / total for k, v in new_weights.items()}

    def full_analysis(
        self,
        # 进球数据
        home_goals_for: int, home_games: int, home_goals_against: int,
        away_goals_for: int, away_games: int, away_goals_against: int,
        # 可选数据
        home_shots: Optional[int] = None, home_shots_on_target: Optional[int] = None,
        away_shots: Optional[int] = None, away_shots_on_target: Optional[int] = None,
        # 元数据
        home_team_id: str = "", away_team_id: str = "",
        home_team_name: str = "", away_team_name: str = "",
        league: str = "default",
        match_type: str = "league",
        return_rate: float = 0.70,
        market_odds: Optional[Dict[str, float]] = None,
        # NEW: home/away split parameters for PoissonModel differentiation
        away_goals_for_home: Optional[float] = None,
        away_games_home: Optional[int] = None,
        home_goals_against_home: Optional[float] = None,
        home_games_home: Optional[int] = None,
    ) -> StatisticalAnalysisResult:
        """执行完整的统计模型分析。

        Args:
            home_goals_for: 主队主场进球总数
            home_games: 主队主场场次
            home_goals_against: 主队主场失球总数
            away_goals_for: 客队客场进球总数
            away_games: 客队客场场次
            away_goals_against: 客队客场失球总数
            home_shots: 主队射门总数（可选）
            home_shots_on_target: 主队射正总数（可选）
            away_shots: 客队射门总数（可选）
            away_shots_on_target: 客队射正总数（可选）
            home_team_id: 主队ID
            away_team_id: 客队ID
            home_team_name: 主队名称
            away_team_name: 客队名称
            league: 联赛
            match_type: 比赛类型
            return_rate: 返还率
            market_odds: 市场赔率（可选，用于价值投注分析）
            away_goals_for_home: 客队在主场时的进球总数（可选）
            away_games_home: 客队主场场次（可选）
            home_goals_against_home: 主队在客场时的失球总数（可选）
            home_games_home: 主队客场场次（可选）

        Returns:
            StatisticalAnalysisResult 综合分析结果
        """
        # 0. 从让球胜平负赔率动态计算主场优势
        home_advantage = self._compute_home_advantage(market_odds)

        # 1. 泊松分布预测
        home_expected, away_expected = self.poisson.calculate_expected_goals(
            home_goals_for, home_games, home_goals_against,
            away_goals_for, away_games, away_goals_against,
            league,
            home_advantage=home_advantage,
            away_goals_for_home=away_goals_for_home,
            away_games_home=away_games_home,
            home_goals_against_home=home_goals_against_home,
            home_games_home=home_games_home,
        )
        poisson_result = self.poisson.predict(home_expected, away_expected, return_rate)

        # 2. Elo评级预测
        elo_result = self.elo.predict_match(home_team_id, away_team_id, league)

        # 3. xG分析
        xg_result = self.xg.analyze(
            home_goals_for, home_games, home_goals_against,
            away_goals_for, away_games, away_goals_against,
            home_shots, home_shots_on_target,
            away_shots, away_shots_on_target,
            league
        )

        # 4. 综合评分（使用动态权重）
        w = self._weights
        poisson_score = poisson_result.home_win_prob * 100
        elo_score = elo_result["home_win_prob"] * 100
        xg_score = 50 + (xg_result.home_xg - xg_result.away_xg) * 20

        combined_score = (
            poisson_score * w["poisson"] +
            elo_score * w["elo"] +
            xg_score * w["xg"]
        )
        combined_score = max(0, min(100, combined_score))

        # 5. 模型一致性评估
        probs = [
            poisson_result.home_win_prob,
            elo_result["home_win_prob"],
            max(0, min(1, 0.5 + (xg_result.home_xg - xg_result.away_xg) * 0.3))
        ]
        prob_std = (sum((p - sum(probs)/3)**2 for p in probs) / 3) ** 0.5
        if prob_std < 0.05:
            agreement = "高度一致"
        elif prob_std < 0.10:
            agreement = "基本一致"
        elif prob_std < 0.15:
            agreement = "存在分歧"
        else:
            agreement = "显著分歧"

        # 6. 价值投注
        value_bets = []
        if market_odds:
            value_bets = self.poisson.find_value_bets(poisson_result, market_odds, return_rate=return_rate)

        # 7. 推理说明
        reasoning = (
            f"泊松预测：主胜{poisson_result.home_win_prob:.0%}，"
            f"平{poisson_result.draw_prob:.0%}，"
            f"客胜{poisson_result.away_win_prob:.0%}；"
            f"最可能比分{poisson_result.most_likely_score}"
            f"（{poisson_result.most_likely_score_prob:.0%}）；"
            f"Elo预测：主胜{elo_result['home_win_prob']:.0%}；"
            f"xG分析：主队xG {xg_result.home_xg:.2f}，"
            f"客队xG {xg_result.away_xg:.2f}；"
            f"模型一致性：{agreement}"
        )

        return StatisticalAnalysisResult(
            poisson=poisson_result,
            elo=elo_result,
            xg=xg_result,
            combined_score=round(combined_score, 1),
            combined_reasoning=reasoning,
            value_bets=value_bets,
            agreement_level=agreement,
        )

    @staticmethod
    def _compute_home_advantage(market_odds: Optional[Dict[str, float]]) -> float:
        """从让球胜平负赔率动态计算主场优势因子。

        让球盘口反映了市场对主客队实力差距的判断：
        - handicap < 0（如-1）：主队让球，说明主队更强，主场优势大
        - handicap > 0（如+1）：客队让球，说明客队更强
        - handicap = 0：实力接近

        Args:
            market_odds: 市场赔率字典，支持扁平化键名（如 "handicap"）

        Returns:
            主场优势因子（0.9 ~ 1.2）
        """
        if not market_odds:
            return 1.10  # 默认值

        # 尝试从扁平化字典中获取盘口值
        handicap = None
        for key in ["handicap", "hhad_handicap"]:
            val = market_odds.get(key)
            if val is not None:
                try:
                    handicap = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        if handicap is None:
            return 1.10  # 无盘口数据时使用默认值

        # 盘口每1球对应5%优势调整
        # handicap为负数表示主队让球（主队更强），主场优势更大
        home_advantage = 1.0 + (-handicap * 0.05)

        # 限制在合理范围
        home_advantage = max(0.90, min(1.20, home_advantage))

        return home_advantage

    def update_match_result(
        self,
        home_team_id: str, away_team_id: str,
        home_goals: int, away_goals: int,
        match_type: str = "league",
        home_team_name: str = "", away_team_name: str = "",
        league: str = "default"
    ) -> Dict:
        """更新比赛结果到Elo系统。

        Args:
            home_team_id: 主队ID
            away_team_id: 客队ID
            home_goals: 主队进球
            away_goals: 客队进球
            match_type: 比赛类型
            home_team_name: 主队名称
            away_team_name: 客队名称
            league: 联赛

        Returns:
            Elo更新结果
        """
        return self.elo.update_rating(
            home_team_id, away_team_id,
            home_goals, away_goals,
            match_type, home_team_name, away_team_name, league
        )
