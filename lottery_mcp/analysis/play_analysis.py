"""
五大玩法专业分析模块
覆盖：胜平负(SPF)、让球胜平负(RQSPF)、比分(BF)、总进球(ZJQ)、半全场(BQC)
基于统计模型输出各玩法的概率分布和推荐
"""

import logging
import math
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger("lottery_mcp")

# 统一置信度标准
CONFIDENCE_HIGH_THRESHOLD = 0.45   # 最高概率选项 > 45%
CONFIDENCE_MEDIUM_THRESHOLD = 0.30  # 最高概率选项 > 30%

# 置信度等级（从低到高）
_CONFIDENCE_LEVELS = ["低", "中", "高"]


def _compute_confidence(max_prob: float, has_actual_odds: bool = False,
                        model_favorite: str = None, market_favorite: str = None) -> str:
    """根据统一标准计算置信度等级。

    基础规则：
        - "高": max_prob > CONFIDENCE_HIGH_THRESHOLD (0.45)
        - "中": max_prob > CONFIDENCE_MEDIUM_THRESHOLD (0.30)
        - "低": otherwise

    加成规则：如果实际赔率可用且模型最看好选项与市场最看好选项一致，
    则置信度提升一级（"低" -> "中"，"中" -> "高"，"高" 保持不变）。

    Args:
        max_prob: 最高概率选项的概率值
        has_actual_odds: 是否有实际赔率数据
        model_favorite: 模型最看好的选项名称（用于市场一致性判断）
        market_favorite: 市场最看好的选项名称（赔率最低的选项）

    Returns:
        置信度等级: "高", "中", 或 "低"
    """
    # 基础置信度
    if max_prob > CONFIDENCE_HIGH_THRESHOLD:
        base_level = 2  # "高"
    elif max_prob > CONFIDENCE_MEDIUM_THRESHOLD:
        base_level = 1  # "中"
    else:
        base_level = 0  # "低"

    # 市场一致性加成：实际赔率可用 + 模型与市场一致 -> 提升一级
    if (has_actual_odds and model_favorite and market_favorite
            and model_favorite == market_favorite):
        base_level = min(base_level + 1, 2)

    return _CONFIDENCE_LEVELS[base_level]


def _identify_market_favorite(odds: Dict, outcome_odds_map: Dict[str, str]) -> str:
    """根据赔率识别市场最看好的选项（赔率最低的选项）。

    Args:
        odds: 完整赔率字典
        outcome_odds_map: 选项名称到赔率键名的映射，如 {"主胜": "home_win", "平局": "draw"}

    Returns:
        市场最看好的选项名称，如果无法确定则返回 None
    """
    best_outcome = None
    best_odds = float("inf")
    for outcome, odds_key in outcome_odds_map.items():
        val = odds.get(odds_key)
        if val is not None and isinstance(val, (int, float)) and val > 0 and val < best_odds:
            best_odds = val
            best_outcome = outcome
    return best_outcome


@dataclass
class PlayProbabilityResult:
    """玩法概率分析结果（纯数学模型输出）

    由 PlayAnalyzer 各分析方法产出，包含原始概率分布、期望值和推荐。
    作为 play_strategies 模块的输入数据源。
    """
    play_type: str
    recommendations: List[Dict[str, Any]]
    probabilities: Dict[str, float]
    expected_value: Dict[str, float]
    confidence: str
    analysis_notes: List[str]


class PlayAnalyzer:
    """五大玩法分析器"""

    def __init__(self):
        self.play_names = {
            "SPF": "胜平负",
            "RQSPF": "让球胜平负",
            "BF": "比分",
            "ZJQ": "总进球",
            "BQC": "半全场",
        }

    def analyze_spf(self, poisson_result: Dict, odds: Dict) -> PlayProbabilityResult:
        """
        胜平负(SPF)分析
        基于泊松模型计算主胜/平/客胜概率
        """
        home_win_prob = poisson_result.get("win_prob", 0.33)
        draw_prob = poisson_result.get("draw_prob", 0.33)
        away_win_prob = poisson_result.get("lose_prob", 0.33)

        # 获取赔率，支持多种键名
        home_odds = odds.get("home_win", odds.get("win", odds.get("spf_home", 2.10)))
        draw_odds = odds.get("draw", odds.get("spf_draw", 3.20))
        away_odds = odds.get("away_win", odds.get("lose", odds.get("spf_away", 3.50)))

        # 计算期望值
        home_ev = home_win_prob * home_odds
        draw_ev = draw_prob * draw_odds
        away_ev = away_win_prob * away_odds

        probs = {
            "主胜": home_win_prob,
            "平局": draw_prob,
            "客胜": away_win_prob,
        }

        evs = {
            "主胜": home_ev,
            "平局": draw_ev,
            "客胜": away_ev,
        }

        # 找出价值投注 (EV > 1.0)
        recommendations = []
        for outcome, ev in evs.items():
            odds_key = self._map_to_odds_key(outcome)
            odds_val = odds.get(odds_key, 2.0)
            # 兼容扁平化键名
            if odds_val == 2.0:
                fallback_map = {"home_win": "win", "away_win": "lose", "draw": "draw"}
                odds_val = odds.get(fallback_map.get(odds_key, odds_key), 2.0)

            rec = {
                "selection": outcome,
                "probability": round(probs[outcome], 3),
                "odds": odds_val if odds_val > 0 else None,
                "expected_value": round(ev, 3),
                "value_rating": "高价值" if ev > 1.15 else "有价值" if ev > 1.0 else "普通",
            }
            recommendations.append(rec)

        # 按期望值排序
        recommendations.sort(key=lambda x: x["expected_value"], reverse=True)

        # 确定置信度（统一标准）
        max_prob = max(probs.values())
        model_favorite = max(probs, key=probs.get)
        has_actual_odds = any(
            odds.get(k) is not None and isinstance(odds.get(k), (int, float)) and odds.get(k) > 0
            for k in ["home_win", "win", "spf_home", "draw", "spf_draw", "away_win", "lose", "spf_away"]
        )
        market_favorite = _identify_market_favorite(odds, {
            "主胜": "home_win",
            "平局": "draw",
            "客胜": "away_win",
        })
        confidence = _compute_confidence(
            max_prob, has_actual_odds=has_actual_odds,
            model_favorite=model_favorite, market_favorite=market_favorite,
        )

        notes = [
            f"主胜概率 {home_win_prob:.1%}，期望值 {home_ev:.3f}",
            f"平局概率 {draw_prob:.1%}，期望值 {draw_ev:.3f}",
            f"客胜概率 {away_win_prob:.1%}，期望值 {away_ev:.3f}",
        ]

        # 比分构成分析
        decomp = self._decompose_spf_probability(poisson_result)
        if "error" not in decomp:
            notes.append(f"主胜构成: {decomp['home_win']['summary']}")

        # 欧指对比
        consensus = self._compare_spf_with_consensus(poisson_result, odds)
        if consensus.get("has_anomaly"):
            for sig in consensus["signals"]:
                notes.append(f"欧指分歧: {sig}")

        return PlayProbabilityResult(
            play_type="SPF",
            recommendations=recommendations,
            probabilities=probs,
            expected_value=evs,
            confidence=confidence,
            analysis_notes=notes,
        )

    @staticmethod
    def _decompose_spf_probability(poisson_result: Dict) -> Dict[str, Any]:
        """将SPF胜/平/负概率拆解为具体比分构成。"""
        score_probs = poisson_result.get("score_probabilities", {})
        if not score_probs:
            return {"error": "无比分概率数据"}

        home_wins = {}
        draws = {}
        away_wins = {}

        for score, prob in score_probs.items():
            try:
                parts = score.split(":")
                h, a = int(parts[0]), int(parts[1])
            except (ValueError, IndexError, AttributeError):
                continue
            if h > a:
                home_wins[score] = prob
            elif h == a:
                draws[score] = prob
            else:
                away_wins[score] = prob

        def summarize(name, d):
            total = sum(d.values())
            top3 = sorted(d.items(), key=lambda x: x[1], reverse=True)[:3]
            top_scores = ", ".join(f"{s}({p:.1%})" for s, p in top3)
            return {"total": round(total, 3), "top3": top3, "summary": f"{name}({total:.1%}): {top_scores}"}

        return {
            "home_win": summarize("主胜", home_wins),
            "draw": summarize("平局", draws),
            "away_win": summarize("客胜", away_wins),
        }

    @staticmethod
    def _compare_spf_with_consensus(poisson_result: Dict, market_odds: Dict) -> Dict[str, Any]:
        """将SPF模型概率与市场欧指均值对比，输出分歧信号。"""
        from .odds_normalizer import odds_normalizer

        model_probs = {
            "主胜": poisson_result.get("win_prob", 0.33),
            "平局": poisson_result.get("draw_prob", 0.33),
            "客胜": poisson_result.get("lose_prob", 0.33),
        }

        # 获取市场赔率，计算隐含概率（考虑70%返还率）
        market_implied = {}
        for outcome, key in [("主胜", "home_win"), ("平局", "draw"), ("客胜", "away_win")]:
            odds_val = odds_normalizer.get(market_odds, "SPF", key)
            market_implied[outcome] = round(1.0 / odds_val * 0.70, 4) if odds_val > 0 else 0

        divergences = {}
        signals = []
        for outcome in model_probs:
            diff = abs(model_probs[outcome] - market_implied[outcome])
            divergences[outcome] = round(diff, 4)
            if diff > 0.12:  # 12%以上分歧
                direction = "模型高估" if model_probs[outcome] > market_implied[outcome] else "市场高估"
                signals.append(f"{outcome}: 模型{model_probs[outcome]:.1%} vs 市场{market_implied[outcome]:.1%}，{direction}（分歧{diff:.1%}）")

        return {
            "model": model_probs,
            "market": market_implied,
            "divergences": divergences,
            "signals": signals,
            "has_anomaly": len(signals) > 0,
            "summary": f"发现{len(signals)}个异常信号" if signals else "无明显分歧",
        }

    def decompose_spf_by_scores(self, poisson_result: Dict) -> Dict[str, Any]:
        """SPF比分构成分析：将胜/平/负概率拆解为具体比分构成。

        输出如: "胜(45%) = 1:0(15%) + 2:1(12%) + 2:0(10%) + ..."
        """
        score_probs = poisson_result.get("score_probabilities", {})
        if not score_probs:
            return {"error": "无比分概率数据"}

        home_wins = {}  # 主胜比分
        draws = {}      # 平局比分
        away_wins = {}  # 客胜比分

        for score, prob in score_probs.items():
            try:
                h, a = score.split(":")
                h, a = int(h), int(a)
            except (ValueError, AttributeError):
                continue
            if h > a:
                home_wins[score] = prob
            elif h == a:
                draws[score] = prob
            else:
                away_wins[score] = prob

        def format_group(name, probs_dict):
            total = sum(probs_dict.values())
            sorted_items = sorted(probs_dict.items(), key=lambda x: x[1], reverse=True)[:5]
            details = " + ".join(f"{s}({p:.1%})" for s, p in sorted_items)
            return {"total_prob": round(total, 3), "top_scores": sorted_items, "summary": f"{name}({total:.1%}) = {details}"}

        return {
            "home_win_decomposition": format_group("主胜", home_wins),
            "draw_decomposition": format_group("平局", draws),
            "away_win_decomposition": format_group("客胜", away_wins),
        }

    def compare_with_consensus(self, poisson_result: Dict, market_odds: Dict) -> Dict[str, Any]:
        """SPF欧指对比分析：将模型概率与市场欧指均值对比。

        分歧度 > 15% 时标记为"市场异常信号"
        """
        from .odds_normalizer import odds_normalizer

        model_probs = {
            "主胜": poisson_result.get("win_prob", 0.33),
            "平局": poisson_result.get("draw_prob", 0.33),
            "客胜": poisson_result.get("lose_prob", 0.33),
        }

        # 获取市场赔率并计算隐含概率
        market_implied = {}
        for outcome, key in [("主胜", "home_win"), ("平局", "draw"), ("客胜", "away_win")]:
            odds_val = odds_normalizer.get(market_odds, "SPF", key)
            # 隐含概率 = 1/odds * 返还率(70%)
            market_implied[outcome] = round(1.0 / odds_val * 0.70, 3) if odds_val > 0 else 0

        # 计算分歧度
        divergences = {}
        signals = []
        for outcome in model_probs:
            diff = abs(model_probs[outcome] - market_implied[outcome])
            divergences[outcome] = round(diff, 3)
            if diff > 0.15:
                direction = "模型看好" if model_probs[outcome] > market_implied[outcome] else "市场看好"
                signals.append({
                    "outcome": outcome,
                    "divergence": round(diff, 3),
                    "direction": direction,
                    "model_prob": model_probs[outcome],
                    "market_implied": market_implied[outcome],
                })

        return {
            "model_probs": model_probs,
            "market_implied": market_implied,
            "divergences": divergences,
            "signals": signals,
            "has_anomaly": len(signals) > 0,
        }

    def analyze_rqspf(self, poisson_result: Dict, odds: Dict,
                      handicap: float = 0.0) -> PlayProbabilityResult:
        """
        让球胜平负(RQSPF)分析
        使用 PoissonModel.predict_with_handicap() 官方接口计算让球概率
        """
        from .models import PoissonModel

        home_expected = poisson_result.get("home_expected_goals", 1.2)
        away_expected = poisson_result.get("away_expected_goals", 1.0)

        # 使用 PoissonModel 官方接口计算让球概率
        poisson_model = PoissonModel()
        rq_result = poisson_model.predict_with_handicap(
            home_expected, away_expected, handicap
        )

        home_win_prob = rq_result["home_win_prob"]
        draw_prob = rq_result["draw_prob"]
        away_win_prob = rq_result["away_win_prob"]
        adjusted_home_lambda = rq_result["adjusted_home_lambda"]
        adjusted_away_lambda = rq_result["adjusted_away_lambda"]

        # 获取让球赔率（使用标准化器）
        from .odds_normalizer import odds_normalizer
        rq_home_odds = odds_normalizer.get(odds, "RQSPF", "home_win")
        rq_draw_odds = odds_normalizer.get(odds, "RQSPF", "draw")
        rq_away_odds = odds_normalizer.get(odds, "RQSPF", "away_win")

        probs = {
            "让球主胜": home_win_prob,
            "让球平": draw_prob,
            "让球客胜": away_win_prob,
        }

        evs = {
            "让球主胜": home_win_prob * rq_home_odds,
            "让球平": draw_prob * rq_draw_odds,
            "让球客胜": away_win_prob * rq_away_odds,
        }

        recommendations = []
        for outcome, ev in evs.items():
            if outcome == "让球主胜":
                odds_val = rq_home_odds
            elif outcome == "让球平":
                odds_val = rq_draw_odds
            else:
                odds_val = rq_away_odds

            rec = {
                "selection": outcome,
                "probability": round(probs[outcome], 3),
                "odds": odds_val if odds_val > 0 else None,
                "expected_value": round(ev, 3),
                "value_rating": "高价值" if ev > 1.15 else "有价值" if ev > 1.0 else "普通",
            }
            recommendations.append(rec)

        recommendations.sort(key=lambda x: x["expected_value"], reverse=True)

        # 确定置信度（统一标准）
        max_prob = max(probs.values())
        model_favorite = max(probs, key=probs.get)
        has_actual_odds = any(
            odds_normalizer.get(odds, "RQSPF", k, default=None) is not None
            for k in ["home_win", "draw", "away_win"]
        )
        market_favorite = _identify_market_favorite(odds, {
            "让球主胜": "rq_home_win",
            "让球平": "rq_draw",
            "让球客胜": "rq_away_win",
        })
        confidence = _compute_confidence(
            max_prob, has_actual_odds=has_actual_odds,
            model_favorite=model_favorite, market_favorite=market_favorite,
        )

        notes = [
            f"让球数: {handicap:+.1f}",
            f"调整后主队lambda: {adjusted_home_lambda:.3f} (原始: {home_expected:.3f})",
            f"调整后客队lambda: {adjusted_away_lambda:.3f} (原始: {away_expected:.3f})",
            f"让球主胜概率 {home_win_prob:.1%}",
            f"让球平概率 {draw_prob:.1%}",
            f"让球客胜概率 {away_win_prob:.1%}",
        ]

        # P0-3: RQSPF盘口合理性评估
        handicap_analysis = self._evaluate_handicap_reasonableness(handicap, poisson_result, odds)
        notes.append(f"盘口评估: {handicap_analysis['interpretation']}")

        return PlayProbabilityResult(
            play_type="RQSPF",
            recommendations=recommendations,
            probabilities=probs,
            expected_value=evs,
            confidence=confidence,
            analysis_notes=notes,
        )

    @staticmethod
    def _evaluate_handicap_reasonableness(handicap: float, poisson_result: Dict, market_odds: Dict) -> Dict[str, Any]:
        """评估让球盘口是否合理，对比亚盘数据。

        逻辑：
        1. 从market_odds中提取亚盘盘口（asian_handicap）
        2. 将竞彩让球数与亚盘盘口对比
        3. 偏差 > 0.5球时标记为"异常"
        4. 输出分析报告
        """
        result = {
            "handicap": handicap,
            "asian_comparison": None,
            "deviation": 0.0,
            "is_reasonable": True,
            "signals": [],
            "interpretation": "盘口合理",
        }

        # 尝试从market_odds中获取亚盘盘口
        asian_handicap = None
        if market_odds:
            if isinstance(market_odds, dict):
                asian_handicap = market_odds.get("asian_handicap")
                if asian_handicap is None:
                    asian_handicap = market_odds.get("handicap_line")

        if asian_handicap is not None:
            try:
                asian_val = float(asian_handicap)
                deviation = abs(handicap - asian_val)
                result["asian_comparison"] = asian_val
                result["deviation"] = round(deviation, 2)

                if deviation > 0.5:
                    result["is_reasonable"] = False
                    result["signals"].append(f"竞彩让球{handicap:.1f}与亚盘{asian_val:.1f}偏差{deviation:.1f}球")
                    result["interpretation"] = f"盘口偏深（竞彩让{handicap:.1f} vs 亚盘{asian_val:.1f}）"
                elif deviation > 0.25:
                    result["interpretation"] = f"盘口略有差异（偏差{deviation:.1f}球）"
            except (ValueError, TypeError):
                pass

        # 如果没有亚盘数据，使用Elo差距评估
        if result["asian_comparison"] is None:
            home_elo = poisson_result.get("home_elo_rating", 1500)
            away_elo = poisson_result.get("away_elo_rating", 1500)
            elo_diff = (home_elo - away_elo) / 50.0  # 每50分≈0.1球

            if abs(handicap) > abs(elo_diff) + 1.0:
                result["is_reasonable"] = False
                result["signals"].append(f"让球{handicap:.1f}与Elo差距({elo_diff:.1f})不匹配")
                result["interpretation"] = f"让球数({handicap:.1f})超出Elo预期({elo_diff:.1f})超过1球"

        return result

    def handicap_sensitivity_analysis(self, poisson_result: Dict) -> Dict[str, Any]:
        """让球灵敏度分析：让球数从-3到+3的完整概率变化曲线。

        找出"概率拐点"：让几球时胜平负概率最均衡
        """
        from .models import PoissonModel

        home_expected = poisson_result.get("home_expected_goals", 1.2)
        away_expected = poisson_result.get("away_expected_goals", 1.0)
        model = PoissonModel()

        curve = {}
        for h in range(-3, 4):
            result = model.predict_with_handicap(home_expected, away_expected, float(h))
            curve[str(h)] = {
                "home_win": result["home_win_prob"],
                "draw": result["draw_prob"],
                "away_win": result["away_win_prob"],
            }

        # 找概率最均衡的让球数（三个概率最接近）
        best_balance_handicap = 0
        min_spread = 999
        for h_str, probs in curve.items():
            values = [probs["home_win"], probs["draw"], probs["away_win"]]
            spread = max(values) - min(values)
            if spread < min_spread:
                min_spread = spread
                best_balance_handicap = int(h_str)

        return {
            "sensitivity_curve": curve,
            "balance_point": best_balance_handicap,
            "balance_spread": round(min_spread, 3),
        }

    @staticmethod
    def _poisson_pmf_safe(k: int, lambda_: float) -> float:
        """安全的泊松概率质量函数，使用对数计算防止溢出"""
        if k < 0 or lambda_ <= 0:
            return 0.0
        if k == 0:
            return math.exp(-lambda_)
        try:
            log_pmf = k * math.log(lambda_) - lambda_ - sum(math.log(i) for i in range(1, k + 1))
            return math.exp(log_pmf)
        except (OverflowError, ValueError):
            return 0.0

    @staticmethod
    def _poisson_tail_prob(lambda_: float, max_k: int) -> float:
        """计算泊松分布的尾部概率 P(X > max_k)"""
        try:
            from scipy.stats import poisson as scipy_poisson
            return 1.0 - scipy_poisson.cdf(max_k, lambda_)
        except ImportError:
            # 纯Python回退：1 - sum(PMF(0..max_k))
            total = sum(PlayAnalyzer._poisson_pmf_safe(i, lambda_) for i in range(max_k + 1))
            return max(0.0, 1.0 - total)

    def _build_poisson_matrix(self, home_lambda: float, away_lambda: float,
                              max_goals: int = 8) -> Dict[Tuple[int, int], float]:
        """
        构建泊松比分概率矩阵

        给定主队和客队的预期进球数(lambda)，计算所有比分组合的联合概率。
        返回字典: {(home_goals, away_goals): probability}

        Args:
            home_lambda: 主队预期进球数
            away_lambda: 客队预期进球数
            max_goals: 最大考虑进球数（默认8）

        Returns:
            比分概率矩阵字典
        """
        # 边界保护
        MIN_LAMBDA = 0.05
        home_lambda = max(home_lambda, MIN_LAMBDA)
        away_lambda = max(away_lambda, MIN_LAMBDA)

        # 尝试使用scipy
        try:
            from scipy.stats import poisson as scipy_poisson

            matrix = {}
            for h in range(max_goals + 1):
                p_h = scipy_poisson.pmf(h, home_lambda)
                for a in range(max_goals + 1):
                    p_a = scipy_poisson.pmf(a, away_lambda)
                    matrix[(h, a)] = p_h * p_a

            # 归一化（截断概率补到最后一个"其他"桶中）
            total = sum(matrix.values())
            if total > 0:
                matrix = {k: v / total for k, v in matrix.items()}

            return matrix

        except ImportError:
            pass

        # 纯Python回退实现（使用安全的对数计算）
        matrix = {}
        for h in range(max_goals + 1):
            p_h = self._poisson_pmf_safe(h, home_lambda)
            for a in range(max_goals + 1):
                p_a = self._poisson_pmf_safe(a, away_lambda)
                matrix[(h, a)] = p_h * p_a

        # 归一化
        total = sum(matrix.values())
        if total > 0:
            matrix = {k: v / total for k, v in matrix.items()}

        return matrix

    def analyze_bf(self, poisson_result: Dict, odds: Dict) -> PlayProbabilityResult:
        """
        比分(BF)分析
        基于泊松分布计算各比分概率，包含31个官方选项：
        28个具体比分 + 3个"其他"选项（胜其他/平其他/负其他）
        """
        score_probs = poisson_result.get("score_probabilities", {})

        if not score_probs:
            # 如果没有比分概率，生成默认分布
            score_probs = self._generate_default_score_probs(poisson_result)

        # 官方具体比分范围
        OFFICIAL_HOME_MAX = 7
        OFFICIAL_AWAY_MAX = 5

        # 分类统计
        home_win_probs = {}
        draw_probs = {}
        away_win_probs = {}

        for score, prob in score_probs.items():
            try:
                parts = score.split(":")
                h, a = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue

            if h > a:
                if h <= OFFICIAL_HOME_MAX and a <= OFFICIAL_AWAY_MAX:
                    home_win_probs[score] = prob
            elif h == a:
                if h <= OFFICIAL_HOME_MAX and a <= OFFICIAL_AWAY_MAX:
                    draw_probs[score] = prob
            else:
                if h <= OFFICIAL_HOME_MAX and a <= OFFICIAL_AWAY_MAX:
                    away_win_probs[score] = prob

        # 计算"其他"选项概率
        # 获取预期进球数用于尾部概率补偿
        home_exp = poisson_result.get("home_expected_goals", 1.5)
        away_exp = poisson_result.get("away_expected_goals", 1.0)

        # 确定矩阵中的最大比分
        max_h_in_matrix = 0
        max_a_in_matrix = 0
        for score_key in score_probs:
            try:
                parts = score_key.split(":")
                h, a = int(parts[0]), int(parts[1])
                max_h_in_matrix = max(max_h_in_matrix, h)
                max_a_in_matrix = max(max_a_in_matrix, a)
            except (ValueError, IndexError):
                continue

        # 计算截断尾部概率（矩阵外部分的概率质量）
        home_tail = self._poisson_tail_prob(home_exp, max_h_in_matrix)
        away_tail = self._poisson_tail_prob(away_exp, max_a_in_matrix)
        # 联合尾部概率（近似：P(h>max_h OR a>max_a)）
        truncated_mass = home_tail + away_tail - home_tail * away_tail

        total_home_win = sum(v for k, v in score_probs.items()
                             if ":" in k and int(k.split(":")[0]) > int(k.split(":")[1]))
        total_draw = sum(v for k, v in score_probs.items()
                         if ":" in k and int(k.split(":")[0]) == int(k.split(":")[1]))
        total_away_win = sum(v for k, v in score_probs.items()
                             if ":" in k and int(k.split(":")[0]) < int(k.split(":")[1]))

        # 将截断概率按比例分配到三个结果类别
        total_in_matrix = total_home_win + total_draw + total_away_win
        if total_in_matrix > 0:
            home_share = total_home_win / total_in_matrix
            draw_share = total_draw / total_in_matrix
            away_share = total_away_win / total_in_matrix
        else:
            home_share, draw_share, away_share = 0.45, 0.27, 0.28

        other_home_win = max(0, total_home_win - sum(home_win_probs.values())) + truncated_mass * home_share
        other_draw = max(0, total_draw - sum(draw_probs.values())) + truncated_mass * draw_share
        other_away_win = max(0, total_away_win - sum(away_win_probs.values())) + truncated_mass * away_share

        # 合并所有选项
        all_probs = {}
        all_probs.update(home_win_probs)
        all_probs.update(draw_probs)
        all_probs.update(away_win_probs)

        if other_home_win > 1e-3:
            all_probs["胜其他"] = other_home_win
        if other_draw > 1e-3:
            all_probs["平其他"] = other_draw
        if other_away_win > 1e-3:
            all_probs["负其他"] = other_away_win

        sorted_scores = sorted(all_probs.items(), key=lambda x: x[1], reverse=True)

        other_keys = {"胜其他", "平其他", "负其他"}
        top_specific = [s for s in sorted_scores if s[0] not in other_keys][:8]
        other_options = [s for s in sorted_scores if s[0] in other_keys]
        sorted_scores = top_specific + other_options

        probs = {score: prob for score, prob in sorted_scores}

        # 归一化
        total_prob = sum(probs.values())
        if total_prob > 0 and abs(total_prob - 1.0) > 0.01:
            probs = {score: prob / total_prob for score, prob in probs.items()}

        # 获取实际赔率，支持多种键名格式
        actual_crs_odds = {}
        has_actual_odds = False
        if odds:
            for key, val in odds.items():
                if isinstance(val, (int, float)) and val > 0:
                    score_key = None
                    if key.startswith("crs_"):
                        score_key = key[4:]
                    elif key.startswith("bf_"):
                        score_key = key[3:]
                    elif key.startswith("score_"):
                        score_key = key[6:]
                    elif ":" in key and len(key) <= 5:
                        score_key = key

                    if score_key:
                        actual_crs_odds[score_key] = val
                        has_actual_odds = True

        # 动态计算估算赔率：基于概率反推公平赔率，再扣除市场利润率
        # 0.88 = 近似市场利润率（返还率约88%）
        estimated_odds = {}
        for score, prob in probs.items():
            if prob > 0.001:
                estimated_odds[score] = round(1.0 / prob * 0.88, 2)
            else:
                estimated_odds[score] = 40.0  # 极低概率比分封顶赔率

        recommendations = []
        expected_value_dict = {}
        for score, prob in sorted_scores[:6]:
            odds_val = actual_crs_odds.get(score)
            using_estimated = False
            if odds_val is None or odds_val <= 0:
                odds_val = estimated_odds.get(score, 15.0)
                using_estimated = True
            ev = prob * odds_val

            rec = {
                "selection": score,
                "probability": round(prob, 3),
                "odds": odds_val if not using_estimated else None,
                "estimated_odds": odds_val if using_estimated else None,
                "expected_value": round(ev, 3),
                "value_rating": "高价值" if ev > 1.15 else "有价值" if ev > 1.0 else "高概率" if prob > 0.08 else "可能",
            }
            recommendations.append(rec)
            expected_value_dict[score] = ev

        # 确定置信度（统一标准）
        max_prob = max(probs.values()) if probs else 0.0
        model_favorite = max(probs, key=probs.get) if probs else None
        # 对于BF，市场最看好 = 实际赔率中最低赔率的比分
        market_favorite = None
        if has_actual_odds and actual_crs_odds:
            market_favorite = min(actual_crs_odds, key=actual_crs_odds.get)
        confidence = _compute_confidence(
            max_prob, has_actual_odds=has_actual_odds,
            model_favorite=model_favorite, market_favorite=market_favorite,
        )

        notes = [
            f"最可能比分: {sorted_scores[0][0] if sorted_scores else '1:1'} "
            f"({sorted_scores[0][1]:.1%})" if sorted_scores else "最可能比分: 1:1",
            f"主胜概率合计: {total_home_win:.1%}",
            f"平局概率合计: {total_draw:.1%}",
            f"客胜概率合计: {total_away_win:.1%}",
            f"实际赔率: {'已获取' if has_actual_odds else '使用估算值'}",
        ]

        # P0-1: BF历史数据校准
        league = poisson_result.get("league", "")
        if league:
            try:
                from .historical_calibrator import historical_calibrator
                calibrated_probs = historical_calibrator.calibrate_bf(probs, league)
                if calibrated_probs and calibrated_probs != probs:
                    # 用校准后的概率更新recommendations
                    for rec in recommendations:
                        score = rec["selection"]
                        if score in calibrated_probs:
                            calibrated_prob = calibrated_probs[score]
                            rec["probability"] = round(calibrated_prob, 3)
                            rec["_calibrated"] = True
                            # 重新计算期望值
                            if rec.get("odds"):
                                rec["expected_value"] = round(calibrated_prob * rec["odds"], 3)
                    notes.append(f"历史校准: 已应用联赛 '{league}' 历史数据校准")
            except Exception:
                pass  # 校准失败不影响原有逻辑

        return PlayProbabilityResult(
            play_type="BF",
            recommendations=recommendations,
            probabilities=probs,
            expected_value=expected_value_dict,
            confidence=confidence,
            analysis_notes=notes,
        )

    def cluster_scores_by_probability(self, poisson_result: Dict) -> Dict[str, Any]:
        """BF比分聚类推荐：将比分按概率聚类为3组。

        高概率组(累计~65%)、中概率组(累计~25%)、低概率组(累计~10%)
        """
        score_probs = poisson_result.get("score_probabilities", {})
        if not score_probs:
            return {"error": "无比分概率数据"}

        sorted_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)

        high_group = []   # 累计~65%
        mid_group = []    # 累计~25%
        low_group = []    # 累计~10%

        cumulative = 0
        for score, prob in sorted_scores:
            cumulative += prob
            if cumulative <= 0.65:
                high_group.append((score, prob))
            elif cumulative <= 0.90:
                mid_group.append((score, prob))
            else:
                low_group.append((score, prob))

        def format_group(name, items):
            total = sum(p for _, p in items)
            scores = [s for s, _ in items[:8]]
            return {
                "total_prob": round(total, 3),
                "count": len(items),
                "top_scores": scores,
            }

        return {
            "high_probability": format_group("高概率组", high_group),
            "medium_probability": format_group("中概率组", mid_group),
            "low_probability": format_group("低概率组", low_group),
            "recommendation": f"推荐关注: {', '.join(s for s, _ in high_group[:5])}",
        }

    def analyze_zjq(self, poisson_result: Dict, odds: Dict) -> PlayProbabilityResult:
        """
        总进球(ZJQ)分析
        官方8个固定选项: 0, 1, 2, 3, 4, 5, 6, 7+
        """
        home_expected = poisson_result.get("home_expected_goals", 1.2)
        away_expected = poisson_result.get("away_expected_goals", 1.0)
        total_expected = home_expected + away_expected

        # 使用泊松分布计算各进球数概率
        try:
            from scipy.stats import poisson as scipy_poisson
            has_scipy = True
        except ImportError:
            has_scipy = False

        # 官方8个选项
        official_options = ["0", "1", "2", "3", "4", "5", "6", "7+"]

        probs = {}
        if has_scipy:
            for goals in range(0, 7):
                probs[official_options[goals]] = scipy_poisson.pmf(goals, total_expected)
            probs["7+"] = 1 - sum(scipy_poisson.pmf(g, total_expected) for g in range(0, 7))
        else:
            # 简化计算
            probs = self._approximate_zjq_probs(total_expected)

        # 获取实际赔率，支持多种键名
        actual_zjq_odds = {}
        has_actual_odds = False
        if odds:
            for key, val in odds.items():
                if isinstance(val, (int, float)) and val > 0:
                    goals_key = None
                    if key.startswith("zjq_"):
                        goals_key = key[4:]
                    elif key.startswith("total_"):
                        goals_key = key[6:]
                    elif key.startswith("tg_"):
                        goals_key = key[3:]
                    elif key in official_options:
                        goals_key = key

                    if goals_key:
                        actual_zjq_odds[goals_key] = val
                        has_actual_odds = True

        # 动态计算估算赔率：基于概率反推公平赔率，再扣除市场利润率
        # 0.88 = 近似市场利润率（返还率约88%）
        estimated_odds = {}
        for option, prob in probs.items():
            if prob > 0.001:
                estimated_odds[option] = round(1.0 / prob * 0.88, 2)
            else:
                estimated_odds[option] = 30.0  # 极低概率选项封顶赔率

        recommendations = []
        expected_value_dict = {}
        for option in official_options:
            prob = probs.get(option, 0)
            odds_val = actual_zjq_odds.get(option)
            using_estimated = False
            if odds_val is None or odds_val <= 0:
                odds_val = estimated_odds.get(option, 10.0)
                using_estimated = True
            ev = prob * odds_val

            rec = {
                "selection": option,
                "probability": round(prob, 3),
                "odds": odds_val if not using_estimated else None,
                "estimated_odds": odds_val if using_estimated else None,
                "expected_value": round(ev, 3),
                "value_rating": "高价值" if ev > 1.15 else "有价值" if ev > 1.0 else "高概率" if prob > 0.25 else "可能",
            }
            recommendations.append(rec)
            expected_value_dict[option] = ev

        recommendations.sort(key=lambda x: x["probability"], reverse=True)

        # 确定置信度（统一标准）
        max_prob = max(probs.values()) if probs else 0.0
        model_favorite = max(probs, key=probs.get) if probs else None
        # 对于ZJQ，市场最看好 = 实际赔率中最低赔率的进球数选项
        market_favorite = None
        if has_actual_odds and actual_zjq_odds:
            market_favorite = min(actual_zjq_odds, key=actual_zjq_odds.get)
        confidence = _compute_confidence(
            max_prob, has_actual_odds=has_actual_odds,
            model_favorite=model_favorite, market_favorite=market_favorite,
        )

        notes = [
            f"预期总进球: {total_expected:.2f}",
            f"最可能选项: {max(probs, key=probs.get)} ({max(probs.values()):.1%})",
            f"实际赔率: {'已获取' if has_actual_odds else '使用估算值'}",
        ]

        # P0-4: ZJQ大小球交叉验证
        ou_analysis = self._cross_validate_with_over_under(poisson_result, odds)
        if ou_analysis.get("bias"):
            notes.append(f"大小球验证: {ou_analysis['interpretation']}")

        return PlayProbabilityResult(
            play_type="ZJQ",
            recommendations=recommendations,
            probabilities=probs,
            expected_value=expected_value_dict,
            confidence=confidence,
            analysis_notes=notes,
        )

    @staticmethod
    def _cross_validate_with_over_under(poisson_result: Dict, market_odds: Dict) -> Dict[str, Any]:
        """ZJQ与大小球市场数据交叉验证。"""
        total_exp = poisson_result.get("home_expected_goals", 1.2) + poisson_result.get("away_expected_goals", 1.0)

        result = {
            "model_expected": round(total_exp, 2),
            "market_line": None,
            "market_expected": None,
            "deviation": 0.0,
            "bias": None,  # "大球倾向" / "小球倾向" / None
            "interpretation": "",
        }

        if market_odds and isinstance(market_odds, dict):
            # 尝试获取大小球盘口
            ou_line = market_odds.get("over_under_line") or market_odds.get("totals_line")
            if ou_line is None and "over_under" in market_odds:
                ou_data = market_odds["over_under"]
                if isinstance(ou_data, list) and len(ou_data) > 0:
                    ou_line = ou_data[0].get("line") if isinstance(ou_data[0], dict) else None

            if ou_line is not None:
                try:
                    market_line = float(ou_line)
                    result["market_line"] = market_line
                    result["market_expected"] = market_line  # 市场隐含预期=盘口线
                    result["deviation"] = round(total_exp - market_line, 2)

                    if result["deviation"] > 0.3:
                        result["bias"] = "大球倾向"
                        result["interpretation"] = f"模型预期{total_exp:.1f}球 vs 市场线{market_line:.1f}球，偏差+{result['deviation']:.1f}，倾向大球"
                    elif result["deviation"] < -0.3:
                        result["bias"] = "小球倾向"
                        result["interpretation"] = f"模型预期{total_exp:.1f}球 vs 市场线{market_line:.1f}球，偏差{result['deviation']:.1f}，倾向小球"
                    else:
                        result["interpretation"] = f"模型预期与市场线基本一致（偏差{result['deviation']:.1f}）"
                except (ValueError, TypeError):
                    pass

        return result

    def analyze_goal_expectation_interval(self, poisson_result: Dict) -> Dict[str, Any]:
        """ZJQ进球期望区间分析：输出总进球的置信区间。"""
        home_exp = poisson_result.get("home_expected_goals", 1.2)
        away_exp = poisson_result.get("away_expected_goals", 1.0)
        total_exp = home_exp + away_exp

        # 泊松分布的方差=均值，标准差=sqrt(均值)
        std = math.sqrt(total_exp) if total_exp > 0 else 0

        return {
            "expected_total_goals": round(total_exp, 2),
            "std_dev": round(std, 2),
            "confidence_68": {
                "lower": round(max(0, total_exp - std), 2),
                "upper": round(total_exp + std, 2),
            },
            "confidence_95": {
                "lower": round(max(0, total_exp - 1.96 * std), 2),
                "upper": round(total_exp + 1.96 * std, 2),
            },
            "most_likely_range": f"{int(max(0, total_exp - std))}-{int(total_exp + std)}球",
        }

    def analyze_bqc(self, poisson_result: Dict, odds: Dict) -> PlayProbabilityResult:
        """
        半全场(BQC)分析 - 基于泊松半场/全场独立模型 + 条件概率修正
        """
        home_expected = poisson_result.get("home_expected_goals", 1.2)
        away_expected = poisson_result.get("away_expected_goals", 1.0)

        # 尝试获取完整比分矩阵
        full_matrix = poisson_result.get("full_score_matrix")

        # P0-2: BQC动态HT_RATIO
        # 尝试从pipeline传入的动态半场比例获取（如已有则用之）
        ht_ratio = poisson_result.get("_bqc_ht_ratio")
        if ht_ratio is None:
            # 尝试从历史数据获取联赛级半场比例
            league = poisson_result.get("league", "")
            if league:
                try:
                    from .historical_calibrator import historical_calibrator
                    ht_ratio = historical_calibrator.get_league_ht_ratio(league)
                except Exception:
                    pass
        if ht_ratio is None:
            ht_ratio = 0.45  # 默认值

        # 统一使用新的泊松半全场计算方法（传入动态HT_RATIO）
        probs = self._calculate_bqc_poisson(home_expected, away_expected, full_matrix, ht_ratio)

        # 获取实际赔率，支持多种键名
        actual_bqc_odds = {}
        has_actual_odds = False
        if odds:
            for key, val in odds.items():
                if isinstance(val, (int, float)) and val > 0:
                    bqc_key = None
                    if key.startswith("bqc_"):
                        bqc_key = key[4:]
                    elif key.startswith("hf_"):
                        bqc_key = key[3:]
                    elif "-" in key and len(key) <= 5:
                        bqc_key = key

                    if bqc_key:
                        actual_bqc_odds[bqc_key] = val
                        has_actual_odds = True

        # 动态计算估算赔率：基于概率反推公平赔率，再扣除市场利润率
        # 0.88 = 近似市场利润率（返还率约88%）
        estimated_odds = {}
        for outcome, prob in probs.items():
            if prob > 0.001:
                estimated_odds[outcome] = round(1.0 / prob * 0.88, 2)
            else:
                estimated_odds[outcome] = 30.0  # 极低概率选项封顶赔率

        sorted_outcomes = sorted(probs.items(), key=lambda x: x[1], reverse=True)

        recommendations = []
        expected_value_dict = {}
        for outcome, prob in sorted_outcomes[:6]:
            odds_val = actual_bqc_odds.get(outcome)
            using_estimated = False
            if odds_val is None or odds_val <= 0:
                odds_val = estimated_odds.get(outcome, 10.0)
                using_estimated = True
            ev = prob * odds_val

            rec = {
                "selection": outcome,
                "probability": round(prob, 3),
                "odds": odds_val if not using_estimated else None,
                "estimated_odds": odds_val if using_estimated else None,
                "expected_value": round(ev, 3),
                "value_rating": "高价值" if ev > 1.15 else "有价值" if ev > 1.0 else "高概率" if prob > 0.20 else "可能",
            }
            recommendations.append(rec)
            expected_value_dict[outcome] = ev

        # 确定置信度（统一标准）
        max_prob = max(probs.values()) if probs else 0.0
        model_favorite = max(probs, key=probs.get) if probs else None
        # 对于BQC，市场最看好 = 实际赔率中最低赔率的半全场组合
        market_favorite = None
        if has_actual_odds and actual_bqc_odds:
            market_favorite = min(actual_bqc_odds, key=actual_bqc_odds.get)
        confidence = _compute_confidence(
            max_prob, has_actual_odds=has_actual_odds,
            model_favorite=model_favorite, market_favorite=market_favorite,
        )

        consistent_prob = probs.get("胜-胜", 0) + probs.get("平-平", 0) + probs.get("负-负", 0)
        notes = [
            f"最可能组合: {sorted_outcomes[0][0]} ({sorted_outcomes[0][1]:.1%})",
            f"一致结果(胜胜/平平/负负)总概率: {consistent_prob:.1%}",
            f"实际赔率: {'已获取' if has_actual_odds else '使用估算值'}",
        ]

        return PlayProbabilityResult(
            play_type="BQC",
            recommendations=recommendations,
            probabilities=probs,
            expected_value=expected_value_dict,
            confidence=confidence,
            analysis_notes=notes,
        )

    def analyze_reversal_probability(self, poisson_result: Dict) -> Dict[str, Any]:
        """BQC逆转概率专项分析：分析胜负/负胜的逆转概率。"""
        bqc_probs = poisson_result.get("bqc_probabilities", {})
        if not bqc_probs:
            return {"error": "无半全场概率数据"}

        reversal_prob = bqc_probs.get("胜负", 0) + bqc_probs.get("负胜", 0)
        consistency_prob = bqc_probs.get("胜胜", 0) + bqc_probs.get("平平", 0) + bqc_probs.get("负负", 0)

        return {
            "reversal_prob": round(reversal_prob, 3),
            "consistency_prob": round(consistency_prob, 3),
            "reversal_detail": {
                "胜负(半胜全负)": round(bqc_probs.get("胜负", 0), 3),
                "负胜(半负全胜)": round(bqc_probs.get("负胜", 0), 3),
            },
            "consistency_detail": {
                "胜胜": round(bqc_probs.get("胜胜", 0), 3),
                "平平": round(bqc_probs.get("平平", 0), 3),
                "负负": round(bqc_probs.get("负负", 0), 3),
            },
            "interpretation": (
                f"逆转概率{reversal_prob:.1%}，一致性概率{consistency_prob:.1%}。"
                f"{'逆转概率偏高，注意防冷' if reversal_prob > 0.25 else '逆转概率正常'}"
            ),
        }

    def _calculate_bqc_poisson(
        self, home_expected: float, away_expected: float,
        full_score_matrix: Dict = None, ht_ratio: float = 0.45
    ) -> Dict[str, float]:
        """
        基于独立泊松模型 + 条件概率修正的半全场概率计算。

        原理:
        1. 半场进球服从 Poisson(ht_home_exp) x Poisson(ht_away_exp)，
           其中 ht_*_exp = full_*_exp * HT_RATIO（动态比例，默认约45%进球在半场）。
        2. 全场结果从已有的泊松比分矩阵中聚合。
        3. 半场与全场结果之间引入相关性修正:
           - 一致结果(胜-胜, 平-平, 负-负): 正相关，corr 随主队优势增大
           - 逆转结果(胜-负, 负-胜): 负相关，corr 随平局概率增大
           - 交叉结果(胜-平, 平-胜, 平-负, 负-平): 近独立
        4. 所有9个概率归一化至总和=1。
        """
        # P0-2: 使用动态HT_RATIO，不再使用固定0.45

        # --- 半场比分矩阵 ---
        ht_home_exp = home_expected * ht_ratio
        ht_away_exp = away_expected * ht_ratio
        ht_matrix = self._build_poisson_matrix(ht_home_exp, ht_away_exp, max_goals=8)

        # 聚合半场结果概率
        ht_home_win = 0.0
        ht_draw = 0.0
        ht_away_win = 0.0
        for (h, a), p in ht_matrix.items():
            if h > a:
                ht_home_win += p
            elif h == a:
                ht_draw += p
            else:
                ht_away_win += p

        # --- 全场结果概率 ---
        if full_score_matrix and len(full_score_matrix) > 10:
            # 使用已有的完整比分矩阵
            ft_home_win = 0.0
            ft_draw = 0.0
            ft_away_win = 0.0
            for (h, a), p in full_score_matrix.items():
                if h > a:
                    ft_home_win += p
                elif h == a:
                    ft_draw += p
                else:
                    ft_away_win += p
        else:
            # 回退: 自己构建全场泊松矩阵
            ft_matrix = self._build_poisson_matrix(home_expected, away_expected, max_goals=8)
            ft_home_win = 0.0
            ft_draw = 0.0
            ft_away_win = 0.0
            for (h, a), p in ft_matrix.items():
                if h > a:
                    ft_home_win += p
                elif h == a:
                    ft_draw += p
                else:
                    ft_away_win += p

        # --- 相关性修正 ---
        # draw_prob 用于衡量比赛的不确定性/平衡程度
        draw_prob = ft_draw

        # 一致结果的相关因子: 强队优势越大，一致性越高
        # corr 范围约 [1.0, 1.3]
        consistent_corr = min(1.3, max(1.0, 1.0 + 0.3 * (1.0 - min(draw_prob, 0.35) / 0.35)))

        # 逆转结果(胜-负, 负-胜)的阻尼因子: 平局概率越高，逆转越可能
        # corr 范围约 [0.4, 0.8]
        comeback_corr = min(0.8, max(0.4, 0.6 + 0.2 * draw_prob / 0.35))

        # 交叉结果(胜-平, 平-胜, 平-负, 负-平): 近独立
        cross_corr = 0.85

        # 计算9个组合的概率
        ht_results = {
            "胜": ht_home_win,
            "平": ht_draw,
            "负": ht_away_win,
        }
        ft_results = {
            "胜": ft_home_win,
            "平": ft_draw,
            "负": ft_away_win,
        }

        # 一致结果: 胜-胜, 平-平, 负-负
        consistent = [("胜", "胜"), ("平", "平"), ("负", "负")]
        # 逆转结果: 胜-负, 负-胜
        comeback = [("胜", "负"), ("负", "胜")]
        # 交叉结果: 胜-平, 平-胜, 平-负, 负-平
        cross = [("胜", "平"), ("平", "胜"), ("平", "负"), ("负", "平")]

        bqc_probs = {}
        for ht_r, ft_r in consistent:
            key = f"{ht_r}-{ft_r}"
            bqc_probs[key] = ht_results[ht_r] * ft_results[ft_r] * consistent_corr

        for ht_r, ft_r in comeback:
            key = f"{ht_r}-{ft_r}"
            bqc_probs[key] = ht_results[ht_r] * ft_results[ft_r] * comeback_corr

        for ht_r, ft_r in cross:
            key = f"{ht_r}-{ft_r}"
            bqc_probs[key] = ht_results[ht_r] * ft_results[ft_r] * cross_corr

        # 归一化至总和=1
        total = sum(bqc_probs.values())
        if total > 0:
            bqc_probs = {k: v / total for k, v in bqc_probs.items()}

        return bqc_probs

    def analyze_all_plays(self, poisson_result: Dict, odds: Dict,
                          handicap: float = 0.0) -> Dict[str, PlayProbabilityResult]:
        """分析所有五大玩法"""
        return {
            "SPF": self.analyze_spf(poisson_result, odds),
            "RQSPF": self.analyze_rqspf(poisson_result, odds, handicap),
            "BF": self.analyze_bf(poisson_result, odds),
            "ZJQ": self.analyze_zjq(poisson_result, odds),
            "BQC": self.analyze_bqc(poisson_result, odds),
        }

    def _map_to_odds_key(self, outcome: str) -> str:
        """映射结果到赔率键"""
        mapping = {
            "主胜": "home_win",
            "平局": "draw",
            "客胜": "away_win",
        }
        return mapping.get(outcome, "home_win")

    def _calculate_win_prob(self, team1_expected: float, team2_expected: float) -> float:
        """计算获胜概率（简化模型）"""
        if team1_expected + team2_expected < 0.1:
            return 0.33
        return team1_expected / (team1_expected + team2_expected + 0.5)

    def _generate_default_score_probs(self, poisson_result: Dict) -> Dict[str, float]:
        """生成默认比分概率分布"""
        home_exp = poisson_result.get("home_expected_goals", 1.2)
        away_exp = poisson_result.get("away_expected_goals", 1.0)

        probs = {}
        for h in range(5):
            for a in range(5):
                # 简化泊松计算
                from math import exp, factorial
                p_h = (home_exp ** h / factorial(h)) * exp(-home_exp) if h < 4 else 0.05
                p_a = (away_exp ** a / factorial(a)) * exp(-away_exp) if a < 4 else 0.05
                probs[f"{h}:{a}"] = p_h * p_a
        return probs

    def _approximate_zjq_probs(self, total_expected: float) -> Dict[str, float]:
        """近似计算总进球概率（无scipy时使用）"""
        if total_expected < 1.5:
            return {"0": 0.25, "1": 0.30, "2": 0.25, "3": 0.12, "4": 0.05, "5": 0.02, "6": 0.01, "7+": 0.00}
        elif total_expected < 2.5:
            return {"0": 0.15, "1": 0.25, "2": 0.30, "3": 0.18, "4": 0.08, "5": 0.03, "6": 0.01, "7+": 0.00}
        elif total_expected < 3.5:
            return {"0": 0.08, "1": 0.18, "2": 0.28, "3": 0.25, "4": 0.14, "5": 0.05, "6": 0.02, "7+": 0.00}
        else:
            return {"0": 0.05, "1": 0.12, "2": 0.22, "3": 0.28, "4": 0.20, "5": 0.09, "6": 0.03, "7+": 0.01}


# 全局分析器实例
_play_analyzer: PlayAnalyzer = None


def get_play_analyzer() -> PlayAnalyzer:
    """获取玩法分析器实例（单例模式）"""
    global _play_analyzer
    if _play_analyzer is None:
        _play_analyzer = PlayAnalyzer()
    return _play_analyzer
