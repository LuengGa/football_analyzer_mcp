"""
玩法聚类分析模块
==================

第二阶段深化功能：
- 比分聚类分析
- 历史比赛模式识别
- 让球深度评估
- 玩法相关性分析
"""

import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("lottery_mcp")


class ScorePattern(Enum):
    """比分模式类型"""
    LOW_SCORING = "低比分模式"  # 0-1球
    MODERATE_SCORING = "中等比分模式"  # 2-3球
    HIGH_SCORING = "高比分模式"  # 4+球
    TIGHT_MATCH = "胶着模式"  # 差距0-1球
    ONE_SIDED = "一边倒模式"  # 差距2+球
    DRAW_LIKELY = "平局模式"


@dataclass
class ScoreCluster:
    """比分聚类结果"""
    pattern: ScorePattern
    key_scores: List[str]
    probability: float
    avg_odds: float
    description: str


@dataclass
class HandicapDepthAnalysis:
    """让球深度分析结果"""
    handicap: float
    depth_level: str  # "浅盘" "中盘" "深盘" "极深盘"
    home_advantage_prob: float
    draw_prob: float
    away_advantage_prob: float
    recommendation: str
    confidence: str
    key_notes: List[str]


@dataclass
class PlayCorrelation:
    """玩法相关性分析"""
    play_pair: Tuple[str, str]
    correlation_coefficient: float
    risk_reduction: float  # 混合过关选择这两个玩法的风险降低
    recommended: bool
    reason: str


class PlayClusterAnalyzer:
    """玩法聚类分析器"""

    @staticmethod
    def analyze_score_clusters(
        score_probs: Dict[str, float],
        odds: Optional[Dict[str, float]] = None
    ) -> List[ScoreCluster]:
        """
        比分聚类分析

        Args:
            score_probs: 比分概率字典
            odds: 赔率字典

        Returns:
            比分聚类结果列表
        """
        clusters = []

        # 计算各类模式概率
        low_scoring_prob = 0.0
        moderate_scoring_prob = 0.0
        high_scoring_prob = 0.0
        tight_match_prob = 0.0
        one_sided_prob = 0.0
        draw_prob = 0.0

        for score, prob in score_probs.items():
            try:
                parts = score.split(":")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    home = int(parts[0])
                    away = int(parts[1])
                    total = home + away
                    diff = abs(home - away)

                    # 总进球数分类
                    if total <= 1:
                        low_scoring_prob += prob
                    elif total <= 3:
                        moderate_scoring_prob += prob
                    else:
                        high_scoring_prob += prob

                    # 差距分类
                    if diff <= 1:
                        tight_match_prob += prob
                    else:
                        one_sided_prob += prob

                    # 平局
                    if home == away:
                        draw_prob += prob

            except (ValueError, IndexError):
                continue

        # 构造聚类结果
        patterns = [
            {
                "pattern": ScorePattern.LOW_SCORING,
                "key_scores": ["0:0", "1:0", "0:1"],
                "probability": low_scoring_prob,
                "desc": "总进球0-1个，低比分模式"
            },
            {
                "pattern": ScorePattern.MODERATE_SCORING,
                "key_scores": ["1:1", "2:0", "0:2", "2:1", "1:2"],
                "probability": moderate_scoring_prob,
                "desc": "总进球2-3个，中等比分模式"
            },
            {
                "pattern": ScorePattern.HIGH_SCORING,
                "key_scores": ["2:2", "3:1", "1:3", "3:0", "0:3"],
                "probability": high_scoring_prob,
                "desc": "总进球4+个，高比分模式"
            },
            {
                "pattern": ScorePattern.TIGHT_MATCH,
                "key_scores": ["0:0", "1:0", "0:1", "1:1", "2:1", "1:2"],
                "probability": tight_match_prob,
                "desc": "比分差距0-1球，胶着模式"
            },
            {
                "pattern": ScorePattern.ONE_SIDED,
                "key_scores": ["2:0", "0:2", "3:0", "0:3", "3:1", "1:3"],
                "probability": one_sided_prob,
                "desc": "比分差距2+球，一边倒模式"
            },
            {
                "pattern": ScorePattern.DRAW_LIKELY,
                "key_scores": ["0:0", "1:1", "2:2"],
                "probability": draw_prob,
                "desc": "平局模式"
            }
        ]

        for pattern_info in patterns:
            if pattern_info["probability"] > 0.05:  # 至少5%概率
                avg_odds = 0.0
                count = 0
                if odds:
                    for score in pattern_info["key_scores"]:
                        if score in odds:
                            avg_odds += odds[score]
                            count += 1
                    if count > 0:
                        avg_odds /= count

                clusters.append(ScoreCluster(
                    pattern=pattern_info["pattern"],
                    key_scores=pattern_info["key_scores"],
                    probability=pattern_info["probability"],
                    avg_odds=avg_odds,
                    description=pattern_info["desc"]
                ))

        # 按概率排序
        clusters.sort(key=lambda x: x.probability, reverse=True)
        return clusters[:6]  # 前6个聚类

    @staticmethod
    def analyze_handicap_depth(
        handicap: float,
        home_team_strength: float = 0.5,
        away_team_strength: float = 0.5,
        recent_home_performance: Optional[Dict] = None,
        recent_away_performance: Optional[Dict] = None
    ) -> HandicapDepthAnalysis:
        """
        让球深度分析

        Args:
            handicap: 让球数（正数表示主让客，负数表示客让主）
            home_team_strength: 主队实力评分0-1
            away_team_strength: 客队实力评分0-1
            recent_home_performance: 主队近期表现
            recent_away_performance: 客队近期表现

        Returns:
            让球深度分析结果
        """
        # 确定让球深度等级
        abs_handicap = abs(handicap)
        if abs_handicap < 0.5:
            depth_level = "浅盘"
        elif abs_handicap < 1.0:
            depth_level = "中盘"
        elif abs_handicap < 1.5:
            depth_level = "深盘"
        else:
            depth_level = "极深盘"

        # 计算各类结果概率（简化模型）
        home_favor_factor = 1.0 + home_team_strength - away_team_strength

        if handicap > 0:  # 主让客
            home_advantage_prob = 0.5 + (handicap * 0.1)
            home_advantage_prob *= home_favor_factor
            away_advantage_prob = max(0.2, 0.5 - (handicap * 0.15))
            draw_prob = 0.25
        elif handicap < 0:  # 客让主
            away_advantage_prob = 0.5 + (abs_handicap * 0.1)
            away_advantage_prob /= home_favor_factor
            home_advantage_prob = max(0.2, 0.5 - (abs_handicap * 0.15))
            draw_prob = 0.25
        else:  # 平手盘
            home_advantage_prob = 0.38 * home_favor_factor
            draw_prob = 0.28
            away_advantage_prob = max(0.25, 0.34 / home_favor_factor)

        # 归一化概率
        total_prob = home_advantage_prob + draw_prob + away_advantage_prob
        home_advantage_prob /= total_prob
        draw_prob /= total_prob
        away_advantage_prob /= total_prob

        # 生成推荐
        key_notes = []
        if depth_level == "浅盘":
            key_notes.append("让球幅度小，双方实力接近")
            recommendation = "平手/让球平局值得关注"
        elif depth_level == "中盘":
            key_notes.append("中等让球，有一定实力差距")
            if home_advantage_prob > away_advantage_prob:
                recommendation = "让球主胜值得考虑"
            else:
                recommendation = "让球客胜或让球平局可选"
        elif depth_level == "深盘":
            key_notes.append("深盘让球，上盘压力较大")
            recommendation = "考虑让球平局或下盘机会"
        else:  # 极深盘
            key_notes.append("极深盘，冷门概率增加")
            recommendation = "谨慎选择，考虑让球平局或小胜"

        # 置信度
        confidence_calc = max(home_advantage_prob, away_advantage_prob, draw_prob)
        if confidence_calc > 0.55:
            confidence = "高"
        elif confidence_calc > 0.45:
            confidence = "中"
        else:
            confidence = "低"

        key_notes.append(f"让球盘：{handicap:+.1f}球")

        return HandicapDepthAnalysis(
            handicap=handicap,
            depth_level=depth_level,
            home_advantage_prob=home_advantage_prob,
            draw_prob=draw_prob,
            away_advantage_prob=away_advantage_prob,
            recommendation=recommendation,
            confidence=confidence,
            key_notes=key_notes
        )

    @staticmethod
    def analyze_play_correlations() -> List[PlayCorrelation]:
        """
        玩法相关性分析（近似值回退方法）

        注意：此方法返回基于专业经验的近似相关性值。
        当有泊松模型数据时，建议使用 analyze_play_correlations_from_model() 方法
        以获得基于实际概率分布的精确计算结果。

        分析不同玩法之间的相关性，为混合过关提供优化建议

        Returns:
            玩法相关性列表
        """
        correlations = []

        # 预定义的玩法相关性（基于专业知识的近似值）
        play_relations = [
            {
                "pair": ("SPF", "RQSPF"),
                "correlation": 0.85,
                "risk_reduction": 0.1,
                "recommended": False,
                "reason": "胜平负和让球胜平负高度相关，不推荐同时选"
            },
            {
                "pair": ("SPF", "ZJQ"),
                "correlation": 0.45,
                "risk_reduction": 0.25,
                "recommended": True,
                "reason": "胜平负和总进球相关性适中，推荐组合"
            },
            {
                "pair": ("SPF", "BF"),
                "correlation": 0.55,
                "risk_reduction": 0.2,
                "recommended": True,
                "reason": "胜平负和比分中等相关，价值较高但风险也高"
            },
            {
                "pair": ("SPF", "BQC"),
                "correlation": 0.5,
                "risk_reduction": 0.22,
                "recommended": True,
                "reason": "胜平负和半全场相关性适中，可以组合"
            },
            {
                "pair": ("RQSPF", "ZJQ"),
                "correlation": 0.4,
                "risk_reduction": 0.28,
                "recommended": True,
                "reason": "让球胜平负和总进球相关性低，推荐组合"
            },
            {
                "pair": ("RQSPF", "BF"),
                "correlation": 0.5,
                "risk_reduction": 0.23,
                "recommended": True,
                "reason": "让球胜平负和比分中等相关，高赔率高风险"
            },
            {
                "pair": ("ZJQ", "BF"),
                "correlation": 0.7,
                "risk_reduction": 0.15,
                "recommended": False,
                "reason": "总进球和比分高度相关，重复风险"
            },
            {
                "pair": ("ZJQ", "BQC"),
                "correlation": 0.45,
                "risk_reduction": 0.25,
                "recommended": True,
                "reason": "总进球和半全场相关性适中，推荐组合"
            },
            {
                "pair": ("BF", "BQC"),
                "correlation": 0.55,
                "risk_reduction": 0.2,
                "recommended": True,
                "reason": "比分和半全场中等相关，高赔率组合"
            }
        ]

        for relation in play_relations:
            correlations.append(PlayCorrelation(
                play_pair=relation["pair"],
                correlation_coefficient=relation["correlation"],
                risk_reduction=relation["risk_reduction"],
                recommended=relation["recommended"],
                reason=relation["reason"]
            ))

        # 按推荐性和风险降低排序
        correlations.sort(key=lambda x: (x.recommended, x.risk_reduction), reverse=True)
        return correlations

    @staticmethod
    def _parse_score(score_str: str) -> Optional[Tuple[int, int]]:
        """解析比分字符串为(主队进球, 客队进球)元组"""
        try:
            parts = score_str.split(":")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
        return None

    @staticmethod
    def _compute_mutual_information(
        joint_dist: Dict[Tuple[Any, Any], float],
        x_values: List[Any],
        y_values: List[Any]
    ) -> float:
        """
        计算两个离散随机变量之间的互信息

        Args:
            joint_dist: 联合概率分布 P(X, Y)
            x_values: X的所有取值
            y_values: Y的所有取值

        Returns:
            互信息值 I(X; Y)
        """
        # 计算边缘分布
        p_x = {}
        p_y = {}
        for (x, y), p in joint_dist.items():
            p_x[x] = p_x.get(x, 0) + p
            p_y[y] = p_y.get(y, 0) + p

        # 计算互信息
        mi = 0.0
        for x in x_values:
            for y in y_values:
                p_xy = joint_dist.get((x, y), 0)
                p_x_val = p_x.get(x, 0)
                p_y_val = p_y.get(y, 0)
                if p_xy > 1e-10 and p_x_val > 1e-10 and p_y_val > 1e-10:
                    mi += p_xy * math.log2((p_xy + 1e-15) / ((p_x_val + 1e-15) * (p_y_val + 1e-15)))

        return mi

    @staticmethod
    def _compute_entropy(dist: Dict[Any, float]) -> float:
        """计算离散分布的熵（带数值稳定性保护）"""
        h = 0.0
        for p in dist.values():
            if p > 1e-10:  # Epsilon threshold for numerical stability
                h -= p * math.log2(p + 1e-15)  # Small epsilon to prevent log(0)
        return h

    @staticmethod
    def _compute_conditional_entropy(
        joint_dist: Dict[Tuple[Any, Any], float],
        x_values: List[Any],
        y_values: List[Any]
    ) -> float:
        """
        计算条件熵 H(Y|X)

        Args:
            joint_dist: 联合概率分布 P(X, Y)
            x_values: X的所有取值
            y_values: Y的所有取值

        Returns:
            条件熵 H(Y|X)
        """
        # 计算边缘分布 P(X)
        p_x = {}
        for (x, y), p in joint_dist.items():
            p_x[x] = p_x.get(x, 0) + p

        # 计算条件熵 H(Y|X) = sum_x P(x) * H(Y|X=x)
        h_y_given_x = 0.0
        for x in x_values:
            p_x_val = p_x.get(x, 0)
            if p_x_val <= 1e-10:
                continue
            h_y_given_x_val = 0.0
            for y in y_values:
                p_xy = joint_dist.get((x, y), 0)
                if p_xy > 1e-10:
                    p_y_given_x = p_xy / p_x_val
                    h_y_given_x_val -= p_y_given_x * math.log2(p_y_given_x + 1e-15)
            h_y_given_x += p_x_val * h_y_given_x_val

        return h_y_given_x

    @staticmethod
    def _build_distributions_from_scores(
        score_probs: Dict[str, float]
    ) -> Tuple[
        Dict[str, float],           # SPF分布: {W, D, L}
        Dict[str, float],           # ZJQ分布: {0-1, 2-3, 4+}
        Dict[Tuple[str, str], float],  # SPF-ZJQ联合分布
        Dict[Tuple[str, str], float],  # SPF-BF联合分布 (BF按W/D/L分类)
        Dict[Tuple[str, str], float],  # ZJQ-BF联合分布 (BF按进球数分类)
        Dict[str, float],           # BF原始分布
    ]:
        """
        从比分概率矩阵构建各玩法的概率分布

        Args:
            score_probs: 泊松模型输出的比分概率字典，如 {"2:1": 0.12, "1:1": 0.10, ...}

        Returns:
            各玩法的边缘分布和联合分布
        """
        spf_dist = {"W": 0.0, "D": 0.0, "L": 0.0}
        zjq_dist = {"0-1": 0.0, "2-3": 0.0, "4+": 0.0}
        spf_zjq_joint = {}
        spf_bf_joint = {}  # (SPF结果, 比分) -> 概率
        zjq_bf_joint = {}  # (ZJQ类别, 比分) -> 概率
        bf_dist = {}

        for score_str, prob in score_probs.items():
            parsed = PlayClusterAnalyzer._parse_score(score_str)
            if parsed is None:
                continue

            home, away = parsed
            total = home + away

            # SPF分类
            if home > away:
                spf_result = "W"
            elif home == away:
                spf_result = "D"
            else:
                spf_result = "L"

            # ZJQ分类
            if total <= 1:
                zjq_cat = "0-1"
            elif total <= 3:
                zjq_cat = "2-3"
            else:
                zjq_cat = "4+"

            # 累加边缘分布
            spf_dist[spf_result] += prob
            zjq_dist[zjq_cat] += prob
            bf_dist[score_str] = prob

            # 累加联合分布
            key_sz = (spf_result, zjq_cat)
            spf_zjq_joint[key_sz] = spf_zjq_joint.get(key_sz, 0) + prob

            key_sb = (spf_result, score_str)
            spf_bf_joint[key_sb] = spf_bf_joint.get(key_sb, 0) + prob

            key_zb = (zjq_cat, score_str)
            zjq_bf_joint[key_zb] = zjq_bf_joint.get(key_zb, 0) + prob

        return spf_dist, zjq_dist, spf_zjq_joint, spf_bf_joint, zjq_bf_joint, bf_dist

    @staticmethod
    def _build_bqc_distributions_from_model(
        poisson_result: Dict[str, Any],
        score_probs: Dict[str, float]
    ) -> Tuple[
        Dict[str, float],               # BQC边缘分布
        Dict[Tuple[str, str], float],   # SPF-BQC联合分布
        Dict[Tuple[str, str], float],   # ZJQ-BQC联合分布
        Dict[Tuple[str, str], float],   # BF-BQC联合分布
    ]:
        """
        从泊松模型构建BQC（半全场）的概率分布

        BQC有9种结果：(半场结果, 全场结果)，其中每个结果为 H(主胜)/D(平局)/A(客胜)。
        半场进球建模为独立泊松分布，期望值为全场期望值的一半。

        Args:
            poisson_result: 泊松模型结果，包含 home_expected_goals, away_expected_goals
            score_probs: 全场比分概率字典

        Returns:
            BQC边缘分布，以及与SPF、ZJQ、BF的联合分布
        """
        home_exp = poisson_result.get("home_expected_goals", 1.3)
        away_exp = poisson_result.get("away_expected_goals", 1.0)

        # 半场期望值为全场的一半（独立半场模型）
        ht_home_exp = home_exp / 2.0
        ht_away_exp = away_exp / 2.0

        # BQC的9种结果
        bqc_results = ["HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA"]

        # 计算半场比分概率（独立泊松）
        def poisson_pmf(k: int, lam: float) -> float:
            if lam <= 0:
                return 1.0 if k == 0 else 0.0
            return (lam ** k) * math.exp(-lam) / math.factorial(k)

        # 构建半场比分概率矩阵 (ht_home, ht_away) -> prob
        ht_score_probs: Dict[Tuple[int, int], float] = {}
        max_ht_goals = 6
        for hh in range(max_ht_goals + 1):
            for ha in range(max_ht_goals + 1):
                p = poisson_pmf(hh, ht_home_exp) * poisson_pmf(ha, ht_away_exp)
                if p > 1e-15:
                    ht_score_probs[(hh, ha)] = p

        # 确定半场结果
        def ht_result(hh: int, ha: int) -> str:
            if hh > ha:
                return "H"
            elif hh == ha:
                return "D"
            else:
                return "A"

        # 确定全场结果
        def ft_result(h: int, a: int) -> str:
            if h > a:
                return "H"
            elif h == a:
                return "D"
            else:
                return "A"

        # 确定ZJQ类别
        def zjq_category(total: int) -> str:
            if total <= 1:
                return "0-1"
            elif total <= 3:
                return "2-3"
            else:
                return "4+"

        # 构建联合分布: P(ht_score, ft_score) = P(ht_score) * P(ft_score | ft_exp)
        # 由于半场和全场进球独立建模（半场用ht_exp，全场用ft_exp），
        # P(ht_score, ft_score) = P(ht_score) * P(ft_score)
        # 但这忽略了半场进球和全场进球的统计依赖关系。
        # 更好的方法：直接从全场比分概率和半场比分概率构建联合分布。
        # 对于每个全场比分(h,a)，半场比分(hh,ha)满足 hh<=h, ha<=a 的约束。
        # 简化模型：假设半场和全场进球独立（独立半场模型），
        # P(BQC=bqc, FT=(h,a)) = P(HT=(hh,ha)) * P(FT=(h,a))

        bqc_dist: Dict[str, float] = {bqc: 0.0 for bqc in bqc_results}
        spf_bqc_joint: Dict[Tuple[str, str], float] = {}
        zjq_bqc_joint: Dict[Tuple[str, str], float] = {}
        bf_bqc_joint: Dict[Tuple[str, str], float] = {}

        for (hh, ha), ht_prob in ht_score_probs.items():
            ht_res = ht_result(hh, ha)
            for score_str, ft_prob in score_probs.items():
                parsed = PlayClusterAnalyzer._parse_score(score_str)
                if parsed is None:
                    continue
                h, a = parsed
                ft_res = ft_result(h, a)
                total = h + a

                # 联合概率（独立半场模型）
                joint_prob = ht_prob * ft_prob

                bqc_key = ht_res + ft_res
                bqc_dist[bqc_key] = bqc_dist.get(bqc_key, 0) + joint_prob

                # SPF-BQC联合
                spf_key = ft_res  # SPF结果就是全场结果
                key_sb = (spf_key, bqc_key)
                spf_bqc_joint[key_sb] = spf_bqc_joint.get(key_sb, 0) + joint_prob

                # ZJQ-BQC联合
                zjq_key = zjq_category(total)
                key_zb = (zjq_key, bqc_key)
                zjq_bqc_joint[key_zb] = zjq_bqc_joint.get(key_zb, 0) + joint_prob

                # BF-BQC联合
                key_bb = (score_str, bqc_key)
                bf_bqc_joint[key_bb] = bf_bqc_joint.get(key_bb, 0) + joint_prob

        # 过滤掉概率极小的BQC结果
        bqc_dist = {k: v for k, v in bqc_dist.items() if v > 1e-10}
        spf_bqc_joint = {k: v for k, v in spf_bqc_joint.items() if v > 1e-10}
        zjq_bqc_joint = {k: v for k, v in zjq_bqc_joint.items() if v > 1e-10}
        bf_bqc_joint = {k: v for k, v in bf_bqc_joint.items() if v > 1e-10}

        return bqc_dist, spf_bqc_joint, zjq_bqc_joint, bf_bqc_joint

    @staticmethod
    def _normalize_mutual_information(mi: float, h_x: float, h_y: float) -> float:
        """
        将互信息归一化到 [0, 1] 区间

        使用归一化互信息 NMI = 2 * MI / (H(X) + H(Y))

        Args:
            mi: 互信息
            h_x: X的熵
            h_y: Y的熵

        Returns:
            归一化互信息 [0, 1]
        """
        denom = h_x + h_y
        if denom <= 0:
            return 0.0
        nmi = 2.0 * mi / denom
        return min(max(nmi, 0.0), 1.0)

    @staticmethod
    def _compute_correlation_from_entropy(
        h_y: float,
        h_y_given_x: float
    ) -> float:
        """
        从条件熵计算相关性系数

        使用公式: correlation = sqrt(1 - H(Y|X) / H(Y))
        这衡量了X对Y的不确定性减少程度

        Args:
            h_y: Y的熵
            h_y_given_x: 给定X时Y的条件熵

        Returns:
            相关性系数 [0, 1]
        """
        if h_y <= 0:
            return 1.0
        ratio = h_y_given_x / h_y
        if ratio >= 1.0:
            return 0.0
        correlation = math.sqrt(1.0 - ratio)
        return min(max(correlation, 0.0), 1.0)

    @staticmethod
    def analyze_play_correlations_from_model(
        poisson_result: Dict[str, Any],
        odds: Optional[Dict[str, Any]] = None
    ) -> List[PlayCorrelation]:
        """
        基于泊松模型输出的数据驱动玩法相关性分析

        使用信息论方法（互信息、条件熵）从实际概率分布中计算
        不同玩法之间的统计相关性，替代基于经验的近似值。

        Args:
            poisson_result: 泊松模型结果，应包含:
                - score_probabilities: Dict[str, float] - 比分概率矩阵
                  如 {"2:1": 0.12, "1:1": 0.10, "0:0": 0.08, ...}
                - win_prob: float - 主胜概率
                - draw_prob: float - 平局概率
                - lose_prob: float - 客胜概率
                - home_expected_goals: float - 主队预期进球
                - away_expected_goals: float - 客队预期进球
            odds: 赔率数据，可选包含:
                - handicap: float - 让球数
                - spf: Dict - 胜平负赔率
                - rqspf: Dict - 让球胜平负赔率

        Returns:
            玩法相关性列表
        """
        score_probs = poisson_result.get("score_probabilities", {})

        if not score_probs:
            logger.warning("泊松模型结果中缺少比分概率矩阵，回退到近似值方法")
            return PlayClusterAnalyzer.analyze_play_correlations()

        # 构建各玩法的概率分布
        (spf_dist, zjq_dist, spf_zjq_joint,
         spf_bf_joint, zjq_bf_joint, bf_dist) = (
            PlayClusterAnalyzer._build_distributions_from_scores(score_probs)
        )

        # 定义取值空间
        spf_values = ["W", "D", "L"]
        zjq_values = ["0-1", "2-3", "4+"]
        bf_scores = list(bf_dist.keys())

        # 计算各分布的熵
        h_spf = PlayClusterAnalyzer._compute_entropy(spf_dist)
        h_zjq = PlayClusterAnalyzer._compute_entropy(zjq_dist)
        h_bf = PlayClusterAnalyzer._compute_entropy(bf_dist)

        # 计算条件熵
        h_zjq_given_spf = PlayClusterAnalyzer._compute_conditional_entropy(
            spf_zjq_joint, spf_values, zjq_values
        )
        h_bf_given_spf = PlayClusterAnalyzer._compute_conditional_entropy(
            spf_bf_joint, spf_values, bf_scores
        )
        h_bf_given_zjq = PlayClusterAnalyzer._compute_conditional_entropy(
            zjq_bf_joint, zjq_values, bf_scores
        )

        # 计算互信息
        mi_spf_zjq = PlayClusterAnalyzer._compute_mutual_information(
            spf_zjq_joint, spf_values, zjq_values
        )
        mi_spf_bf = PlayClusterAnalyzer._compute_mutual_information(
            spf_bf_joint, spf_values, bf_scores
        )
        mi_zjq_bf = PlayClusterAnalyzer._compute_mutual_information(
            zjq_bf_joint, zjq_values, bf_scores
        )

        # 构建BQC（半全场）分布
        (bqc_dist, spf_bqc_joint, zjq_bqc_joint, bf_bqc_joint) = (
            PlayClusterAnalyzer._build_bqc_distributions_from_model(
                poisson_result, score_probs
            )
        )

        bqc_values = list(bqc_dist.keys())

        # 计算BQC分布的熵
        h_bqc = PlayClusterAnalyzer._compute_entropy(bqc_dist)

        # 计算BQC相关的互信息和条件熵
        mi_spf_bqc = PlayClusterAnalyzer._compute_mutual_information(
            spf_bqc_joint, spf_values, bqc_values
        )
        mi_zjq_bqc = PlayClusterAnalyzer._compute_mutual_information(
            zjq_bqc_joint, zjq_values, bqc_values
        )
        mi_bf_bqc = PlayClusterAnalyzer._compute_mutual_information(
            bf_bqc_joint, bf_scores, bqc_values
        )

        h_bqc_given_spf = PlayClusterAnalyzer._compute_conditional_entropy(
            spf_bqc_joint, spf_values, bqc_values
        )
        h_bqc_given_zjq = PlayClusterAnalyzer._compute_conditional_entropy(
            zjq_bqc_joint, zjq_values, bqc_values
        )
        h_bqc_given_bf = PlayClusterAnalyzer._compute_conditional_entropy(
            bf_bqc_joint, bf_scores, bqc_values
        )

        correlations = []

        # ---- 1. SPF vs RQSPF ----
        # 基于让球深度计算相关性
        handicap = 0.0
        if odds and isinstance(odds, dict):
            handicap = odds.get("handicap", 0.0)
            if handicap is None:
                handicap = 0.0

        abs_handicap = abs(handicap)
        # 让球为0时完全相关(1.0)，让球越大相关性越低
        spf_rqspf_corr = max(0.3, 1.0 - abs_handicap * 0.25)
        spf_rqspf_risk = round(0.05 + abs_handicap * 0.1, 2)
        spf_rqspf_recommended = abs_handicap >= 0.75
        if abs_handicap == 0:
            spf_rqspf_reason = f"让球为0，胜平负与让球胜平负完全相同（相关性{spf_rqspf_corr:.2f}），不推荐同时选择"
        elif abs_handicap < 0.75:
            spf_rqspf_reason = (f"让球{handicap:+.1f}球较浅，两个玩法高度相关"
                                f"（相关性{spf_rqspf_corr:.2f}），混合过关风险降低有限")
        else:
            spf_rqspf_reason = (f"让球{handicap:+.1f}球较深，两个玩法相关性降低"
                                f"（相关性{spf_rqspf_corr:.2f}），可以考虑组合")

        correlations.append(PlayCorrelation(
            play_pair=("SPF", "RQSPF"),
            correlation_coefficient=round(spf_rqspf_corr, 3),
            risk_reduction=spf_rqspf_risk,
            recommended=spf_rqspf_recommended,
            reason=spf_rqspf_reason
        ))

        # ---- 2. SPF vs ZJQ ----
        # 使用归一化互信息
        spf_zjq_corr = PlayClusterAnalyzer._normalize_mutual_information(
            mi_spf_zjq, h_spf, h_zjq
        )
        # 使用条件熵方法交叉验证，取两者的加权平均
        spf_zjq_corr_entropy = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_zjq, h_zjq_given_spf
        )
        spf_zjq_corr_final = round(0.6 * spf_zjq_corr + 0.4 * spf_zjq_corr_entropy, 3)
        spf_zjq_risk = round(0.15 + spf_zjq_corr_final * 0.15, 2)
        spf_zjq_recommended = spf_zjq_corr_final < 0.65
        spf_zjq_reason = (
            f"胜平负与总进球互信息MI={mi_spf_zjq:.4f}，"
            f"归一化相关性={spf_zjq_corr_final:.3f}，"
            f"{'推荐组合，风险分散效果好' if spf_zjq_recommended else '相关性偏高，组合需谨慎'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("SPF", "ZJQ"),
            correlation_coefficient=spf_zjq_corr_final,
            risk_reduction=spf_zjq_risk,
            recommended=spf_zjq_recommended,
            reason=spf_zjq_reason
        ))

        # ---- 3. SPF vs BF ----
        # BF是SPF的细化，使用条件熵方法
        # H(BF|SPF) / H(BF) 衡量了知道SPF后BF的不确定性剩余比例
        spf_bf_corr = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bf, h_bf_given_spf
        )
        # BF是SPF的直接细化，相关性天然较高，设置最低下限
        spf_bf_corr = round(max(0.5, min(spf_bf_corr, 0.95)), 3)
        spf_bf_risk = round(0.1 + (1.0 - spf_bf_corr) * 0.2, 2)
        spf_bf_recommended = spf_bf_corr < 0.75
        spf_bf_reason = (
            f"比分是胜平负的直接细化，条件熵H(BF|SPF)={h_bf_given_spf:.4f}，"
            f"相关性={spf_bf_corr:.3f}，"
            f"{'可以组合但需注意比分不确定性高' if spf_bf_recommended else '相关性过高，不建议同时选择'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("SPF", "BF"),
            correlation_coefficient=spf_bf_corr,
            risk_reduction=spf_bf_risk,
            recommended=spf_bf_recommended,
            reason=spf_bf_reason
        ))

        # ---- 4. SPF vs BQC ----
        # 使用互信息计算SPF与BQC的相关性
        # BQC的第二个字符就是全场结果（即SPF），所以天然有较强关联
        spf_bqc_corr_nmi = PlayClusterAnalyzer._normalize_mutual_information(
            mi_spf_bqc, h_spf, h_bqc
        )
        spf_bqc_corr_entropy = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bqc, h_bqc_given_spf
        )
        spf_bqc_corr = round(0.6 * spf_bqc_corr_nmi + 0.4 * spf_bqc_corr_entropy, 3)
        spf_bqc_risk = round(0.15 + (1.0 - spf_bqc_corr) * 0.15, 2)
        spf_bqc_recommended = spf_bqc_corr < 0.65
        spf_bqc_reason = (
            f"半全场与胜平负互信息MI={mi_spf_bqc:.4f}，"
            f"归一化相关性={spf_bqc_corr:.3f}，"
            f"{'推荐组合，维度互补性好' if spf_bqc_recommended else '相关性偏高，组合需注意'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("SPF", "BQC"),
            correlation_coefficient=spf_bqc_corr,
            risk_reduction=spf_bqc_risk,
            recommended=spf_bqc_recommended,
            reason=spf_bqc_reason
        ))

        # ---- 5. RQSPF vs ZJQ ----
        # 让球胜平负与总进球：让球调整了胜负判定，与总进球的关联不同于SPF
        # 让球越深，RQSPF与ZJQ的相关性越低（因为胜负判定更依赖进球差而非总数）
        rqspf_zjq_base = PlayClusterAnalyzer._normalize_mutual_information(
            mi_spf_zjq, h_spf, h_zjq
        )
        # 让球深度调整：深盘时相关性降低
        rqspf_zjq_corr = round(
            max(0.2, rqspf_zjq_base - abs_handicap * 0.08), 3
        )
        rqspf_zjq_risk = round(0.2 + (1.0 - rqspf_zjq_corr) * 0.12, 2)
        rqspf_zjq_recommended = rqspf_zjq_corr < 0.6
        rqspf_zjq_reason = (
            f"让球{handicap:+.1f}球下，让球胜平负与总进球相关性={rqspf_zjq_corr:.3f}，"
            f"{'推荐组合，风险分散效果较好' if rqspf_zjq_recommended else '有一定相关性，组合需谨慎'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("RQSPF", "ZJQ"),
            correlation_coefficient=rqspf_zjq_corr,
            risk_reduction=rqspf_zjq_risk,
            recommended=rqspf_zjq_recommended,
            reason=rqspf_zjq_reason
        ))

        # ---- 6. RQSPF vs BF ----
        # 让球胜平负与比分：让球调整后与比分的关系
        rqspf_bf_base = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bf, h_bf_given_spf
        )
        # 让球深度调整
        rqspf_bf_corr = round(
            max(0.3, rqspf_bf_base - abs_handicap * 0.06), 3
        )
        rqspf_bf_risk = round(0.15 + (1.0 - rqspf_bf_corr) * 0.15, 2)
        rqspf_bf_recommended = rqspf_bf_corr < 0.7
        rqspf_bf_reason = (
            f"让球{handicap:+.1f}球下，让球胜平负与比分相关性={rqspf_bf_corr:.3f}，"
            f"{'高赔率组合有一定价值' if rqspf_bf_recommended else '相关性偏高，风险较大'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("RQSPF", "BF"),
            correlation_coefficient=rqspf_bf_corr,
            risk_reduction=rqspf_bf_risk,
            recommended=rqspf_bf_recommended,
            reason=rqspf_bf_reason
        ))

        # ---- 7. ZJQ vs BF ----
        # 总进球是比分的直接聚合，相关性天然高
        zjq_bf_corr = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bf, h_bf_given_zjq
        )
        # 总进球是比分的聚合，相关性下限较高
        zjq_bf_corr = round(max(0.6, min(zjq_bf_corr, 0.98)), 3)
        zjq_bf_risk = round(0.05 + (1.0 - zjq_bf_corr) * 0.15, 2)
        zjq_bf_recommended = zjq_bf_corr < 0.75
        zjq_bf_reason = (
            f"总进球是比分的直接聚合，条件熵H(BF|ZJQ)={h_bf_given_zjq:.4f}，"
            f"相关性={zjq_bf_corr:.3f}，"
            f"{'可以组合但需注意重复风险' if zjq_bf_recommended else '高度相关，不推荐同时选择'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("ZJQ", "BF"),
            correlation_coefficient=zjq_bf_corr,
            risk_reduction=zjq_bf_risk,
            recommended=zjq_bf_recommended,
            reason=zjq_bf_reason
        ))

        # ---- 8. ZJQ vs BQC ----
        # 使用互信息计算总进球与半全场的相关性
        zjq_bqc_corr_nmi = PlayClusterAnalyzer._normalize_mutual_information(
            mi_zjq_bqc, h_zjq, h_bqc
        )
        zjq_bqc_corr_entropy = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bqc, h_bqc_given_zjq
        )
        zjq_bqc_corr = round(0.6 * zjq_bqc_corr_nmi + 0.4 * zjq_bqc_corr_entropy, 3)
        zjq_bqc_risk = round(0.2 + (1.0 - zjq_bqc_corr) * 0.12, 2)
        zjq_bqc_recommended = zjq_bqc_corr < 0.6
        zjq_bqc_reason = (
            f"总进球与半全场互信息MI={mi_zjq_bqc:.4f}，"
            f"归一化相关性={zjq_bqc_corr:.3f}，"
            f"{'推荐组合，维度互补' if zjq_bqc_recommended else '有一定相关性，组合需注意'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("ZJQ", "BQC"),
            correlation_coefficient=zjq_bqc_corr,
            risk_reduction=zjq_bqc_risk,
            recommended=zjq_bqc_recommended,
            reason=zjq_bqc_reason
        ))

        # ---- 9. BF vs BQC ----
        # 使用互信息计算比分与半全场的相关性
        bf_bqc_corr_nmi = PlayClusterAnalyzer._normalize_mutual_information(
            mi_bf_bqc, h_bf, h_bqc
        )
        bf_bqc_corr_entropy = PlayClusterAnalyzer._compute_correlation_from_entropy(
            h_bqc, h_bqc_given_bf
        )
        bf_bqc_corr = round(0.6 * bf_bqc_corr_nmi + 0.4 * bf_bqc_corr_entropy, 3)
        bf_bqc_risk = round(0.15 + (1.0 - bf_bqc_corr) * 0.15, 2)
        bf_bqc_recommended = bf_bqc_corr < 0.65
        bf_bqc_reason = (
            f"比分与半全场互信息MI={mi_bf_bqc:.4f}，"
            f"归一化相关性={bf_bqc_corr:.3f}，"
            f"{'高赔率组合有一定价值' if bf_bqc_recommended else '相关性偏高，风险较大'}"
        )

        correlations.append(PlayCorrelation(
            play_pair=("BF", "BQC"),
            correlation_coefficient=bf_bqc_corr,
            risk_reduction=bf_bqc_risk,
            recommended=bf_bqc_recommended,
            reason=bf_bqc_reason
        ))

        # 按推荐性和风险降低排序
        correlations.sort(key=lambda x: (x.recommended, x.risk_reduction), reverse=True)
        return correlations
