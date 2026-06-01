# -*- coding: utf-8 -*-
"""
历史数据校准模块
================
利用86,040场历史比赛数据，通过贝叶斯方法校准泊松模型输出的各玩法概率。

核心思想：
    P(结果|联赛) ∝ P_poisson(结果) × P_history(结果|联赛)

校准维度：
    - SPF: 联赛级主胜/平/客胜频率
    - BF: 联赛级比分频率分布
    - ZJQ: 联赛级总进球分布
    - BQC: 联赛级半全场组合频率
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger("lottery_mcp")

# 校准权重：历史先验的权重（0=纯泊松，1=纯历史）
# 使用较保守的权重，避免过度依赖历史数据
_DEFAULT_CALIBRATION_WEIGHT = 0.25


class HistoricalCalibrator:
    """历史数据校准器。

    从 HistoricalDataManager 加载历史比赛数据，
    计算各联赛的统计先验，并用贝叶斯方法校准泊松概率。

    用法::

        calibrator = HistoricalCalibrator()
        calibrator.load_league_data("premier league")

        # 校准SPF概率
        calibrated = calibrator.calibrate_spf(
            poisson_probs={"主胜": 0.45, "平局": 0.28, "客胜": 0.27},
            league="premier league"
        )
    """

    def __init__(self, calibration_weight: float = _DEFAULT_CALIBRATION_WEIGHT):
        self._weight = calibration_weight
        self._league_data: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def load_league_data(self, league: str) -> bool:
        """加载指定联赛的历史统计数据。

        Args:
            league: 联赛名称（支持英文/中文/别名）

        Returns:
            是否成功加载
        """
        try:
            from ..data.historical import HistoricalDataManager
            mgr = HistoricalDataManager()
            if not mgr.load_data():
                logger.warning("历史数据加载失败")
                return False

            # 标准化联赛名称（使用 search_league 方法）
            league_results = mgr.search_league(league)
            if not league_results:
                logger.debug(f"联赛 '{league}' 未在历史数据中找到")
                return False
            actual_league = league_results[0]['name']  # 取第一个匹配结果

            matches = mgr.get_league_matches(actual_league)
            if not matches or isinstance(matches, dict) and "error" in matches:
                return False

            # 计算联赛级统计
            stats = self._compute_league_stats(matches)
            self._league_data[league.lower()] = stats
            self._loaded = True
            logger.info(f"已加载联赛 '{league}' 的历史统计: {len(matches)}场比赛")
            return True

        except Exception as e:
            logger.warning(f"加载历史数据异常: {e}")
            return False

    def _compute_league_stats(self, matches: List[Dict]) -> Dict[str, Any]:
        """从比赛列表计算联赛级统计先验。"""
        spf_counts = Counter()
        score_counts = Counter()
        total_goals_counts = Counter()
        bqc_counts = Counter()
        half_time_goals_home = 0
        half_time_goals_away = 0
        total_matches = len(matches)

        for m in matches:
            # SPF
            ft_result = (m.get("full_time_result") or "").upper()
            if ft_result == "H":
                spf_counts["主胜"] += 1
            elif ft_result == "D":
                spf_counts["平局"] += 1
            elif ft_result == "A":
                spf_counts["客胜"] += 1

            # BF
            hg = m.get("full_time_home_goals", 0) or 0
            ag = m.get("full_time_away_goals", 0) or 0
            score_counts[f"{hg}:{ag}"] += 1

            # ZJQ
            total_goals_counts[hg + ag] += 1

            # BQC
            ht_result = (m.get("half_time_result") or "").upper()
            if ft_result and ht_result:
                ht_cn = {"H": "胜", "D": "平", "A": "负"}.get(ht_result, "")
                ft_cn = {"H": "胜", "D": "平", "A": "负"}.get(ft_result, "")
                if ht_cn and ft_cn:
                    bqc_counts[f"{ht_cn}{ft_cn}"] += 1

            # 半场进球（用于计算半场比例）
            ht_hg = m.get("half_time_home_goals", 0) or 0
            ht_ag = m.get("half_time_away_goals", 0) or 0
            half_time_goals_home += ht_hg
            half_time_goals_away += ht_ag

        # 计算频率（概率）
        def to_freq(counter: Counter, total: int) -> Dict[str, float]:
            if total == 0:
                return {}
            return {k: v / total for k, v in counter.items()}

        # 半场进球比例
        total_full_goals = sum(
            (m.get("full_time_home_goals", 0) or 0) + (m.get("full_time_away_goals", 0) or 0)
            for m in matches
        )
        total_half_goals = half_time_goals_home + half_time_goals_away
        ht_ratio = total_half_goals / total_full_goals if total_full_goals > 0 else 0.45

        return {
            "total_matches": total_matches,
            "spf_freq": to_freq(spf_counts, total_matches),
            "score_freq": to_freq(score_counts, total_matches),
            "total_goals_freq": to_freq(total_goals_counts, total_matches),
            "bqc_freq": to_freq(bqc_counts, total_matches),
            "ht_ratio": round(ht_ratio, 3),
        }

    def calibrate_spf(
        self,
        poisson_probs: Dict[str, float],
        league: str,
    ) -> Dict[str, float]:
        """校准SPF胜平负概率。

        Args:
            poisson_probs: 泊松模型输出的概率 {"主胜": 0.45, "平局": 0.28, "客胜": 0.27}
            league: 联赛名称

        Returns:
            校准后的概率字典
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("spf_freq"):
            return poisson_probs

        hist_freq = hist["spf_freq"]
        return self._bayesian_calibrate(poisson_probs, hist_freq)

    def calibrate_bf(
        self,
        poisson_score_probs: Dict[str, float],
        league: str,
    ) -> Dict[str, float]:
        """校准BF比分概率。

        Args:
            poisson_score_probs: 泊松比分概率 {"1:0": 0.12, "0:0": 0.08, ...}
            league: 联赛名称

        Returns:
            校准后的概率字典
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("score_freq"):
            return poisson_score_probs

        hist_freq = hist["score_freq"]
        return self._bayesian_calibrate(poisson_score_probs, hist_freq)

    def calibrate_zjq(
        self,
        poisson_goal_probs: Dict[str, float],
        league: str,
    ) -> Dict[str, float]:
        """校准ZJQ总进球概率。

        Args:
            poisson_goal_probs: 泊松总进球概率 {"0": 0.05, "1": 0.15, "2": 0.25, ...}
            league: 联赛名称

        Returns:
            校准后的概率字典
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("total_goals_freq"):
            return poisson_goal_probs

        hist_freq = hist["total_goals_freq"]
        # 将历史频率的key转为str
        hist_freq_str = {str(k): v for k, v in hist_freq.items()}
        return self._bayesian_calibrate(poisson_goal_probs, hist_freq_str)

    def calibrate_bqc(
        self,
        poisson_bqc_probs: Dict[str, float],
        league: str,
    ) -> Dict[str, float]:
        """校准BQC半全场概率。

        Args:
            poisson_bqc_probs: 泊松半全场概率 {"胜胜": 0.35, "平平": 0.20, ...}
            league: 联赛名称

        Returns:
            校准后的概率字典
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("bqc_freq"):
            return poisson_bqc_probs

        hist_freq = hist["bqc_freq"]
        return self._bayesian_calibrate(poisson_bqc_probs, hist_freq)

    def get_league_ht_ratio(self, league: str) -> Optional[float]:
        """获取联赛的半场进球比例。

        Args:
            league: 联赛名称

        Returns:
            半场进球比例（如0.43），未找到返回None
        """
        hist = self._get_league_stats(league)
        if not hist:
            return None
        return hist.get("ht_ratio")

    def get_league_characteristic_scores(
        self, league: str, top_n: int = 5
    ) -> List[Tuple[str, float]]:
        """获取联赛特征比分TopN。

        Args:
            league: 联赛名称
            top_n: 返回前N个

        Returns:
            [(比分, 频率), ...] 按频率降序
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("score_freq"):
            return []
        sorted_scores = sorted(
            hist["score_freq"].items(), key=lambda x: x[1], reverse=True
        )
        return sorted_scores[:top_n]

    def get_league_avg_goals(self, league: str) -> Optional[float]:
        """获取联赛场均总进球。

        Args:
            league: 联赛名称

        Returns:
            场均总进球数
        """
        hist = self._get_league_stats(league)
        if not hist or not hist.get("total_goals_freq"):
            return None
        total = 0
        count = 0
        for goals_str, freq in hist["total_goals_freq"].items():
            try:
                goals = int(goals_str)
                total += goals * freq
                count += freq
            except (ValueError, TypeError):
                continue
        return round(total / count, 2) if count > 0 else None

    def _get_league_stats(self, league: str) -> Optional[Dict]:
        """获取联赛统计（带自动加载）"""
        key = league.lower()
        if key not in self._league_data:
            self.load_league_data(league)
        return self._league_data.get(key)

    def _bayesian_calibrate(
        self,
        model_probs: Dict[str, float],
        hist_freq: Dict[str, float],
    ) -> Dict[str, float]:
        """贝叶斯校准：融合模型概率与历史频率。

        公式:
            P_calibrated(i) = P_model(i)^(1-w) × P_hist(i)^w / Z

        其中 w = calibration_weight, Z = 归一化常数

        Args:
            model_probs: 模型概率字典
            hist_freq: 历史频率字典

        Returns:
            校准后的概率字典
        """
        w = self._weight
        calibrated = {}

        all_keys = set(model_probs.keys()) | set(hist_freq.keys())

        for key in all_keys:
            p_model = model_probs.get(key, 1e-6)  # 极小先验避免0
            p_hist = hist_freq.get(key, 1e-6)

            # 加权几何平均
            p_cal = (p_model ** (1 - w)) * (p_hist ** w)
            calibrated[key] = p_cal

        # 归一化
        total = sum(calibrated.values())
        if total > 0:
            calibrated = {k: round(v / total, 4) for k, v in calibrated.items()}

        return calibrated


# 模块级单例
historical_calibrator = HistoricalCalibrator()
