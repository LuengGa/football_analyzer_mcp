# -*- coding: utf-8 -*-
"""
赔率键名标准化模块
================
统一各玩法赔率字典的键名映射，消除分散在各方法中的兼容逻辑。

设计原则：
- 每个玩法有标准键名 (canonical key)
- 支持多种别名自动映射到标准键名
- 提供 get/play_type 级别的便捷方法
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("lottery_mcp")

# ============================================================================
# 各玩法赔率键名映射表
# ============================================================================

# 标准键名 → 别名列表（按优先级排序）
_ODDS_KEY_ALIASES: Dict[str, Dict[str, list]] = {
    # --- SPF 胜平负 ---
    "SPF": {
        "home_win": ["home_win", "win", "spf_home", "w", "主胜", "1"],
        "draw": ["draw", "d", "平", "平局", "X", "x"],
        "away_win": ["away_win", "lose", "spf_away", "l", "客胜", "2"],
    },
    # --- RQSPF 让球胜平负 ---
    "RQSPF": {
        "home_win": ["hhad_w", "rqspf_home", "rq_home_win", "handicap_win",
                      "rqspf_win", "让球主胜", "让球胜", "rq_win"],
        "draw": ["hhad_d", "rqspf_draw", "rq_draw", "handicap_draw",
                 "rqspf_draw", "让球平", "rq_draw"],
        "away_win": ["hhad_l", "rqspf_away", "rq_away_win", "handicap_away",
                     "rqspf_lose", "让球客胜", "让球负", "rq_lose"],
    },
    # --- BF 比分 (crs_X:Y 格式) ---
    "BF": {
        "_prefix": ["crs_"],
    },
    # --- ZJQ 总进球 (ttg_N 格式) ---
    "ZJQ": {
        "_prefix": ["ttg_"],
    },
    # --- BQC 半全场 (hafu_XX 格式) ---
    "BQC": {
        "_prefix": ["hafu_"],
    },
}


class OddsNormalizer:
    """赔率键名标准化器。

    将各种来源的赔率字典统一为标准键名格式，
    消除分散在各玩法方法中的多套兼容逻辑。

    用法::

        normalizer = OddsNormalizer()
        # 获取SPF主胜赔率（自动尝试所有别名）
        home_odds = normalizer.get(odds_dict, "SPF", "home_win")

        # 批量获取某玩法的所有赔率
        spf_odds = normalizer.get_all(odds_dict, "SPF")
        # => {"home_win": 2.10, "draw": 3.20, "away_win": 3.50}
    """

    # 类级别缓存，避免重复实例化
    _instance: Optional["OddsNormalizer"] = None

    def __new__(cls) -> "OddsNormalizer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get(self, odds: Dict[str, Any], play_type: str,
            key: str, default: float = 2.0) -> float:
        """获取标准化后的赔率值。

        Args:
            odds: 原始赔率字典（可能使用各种键名格式）
            play_type: 玩法类型 ("SPF"/"RQSPF"/"BF"/"ZJQ"/"BQC")
            key: 标准键名 ("home_win"/"draw"/"away_win")
            default: 所有别名都未找到时的默认值

        Returns:
            赔率值
        """
        play_aliases = _ODDS_KEY_ALIASES.get(play_type, {})
        if key not in play_aliases:
            logger.debug(f"未知的标准键名 {key} (玩法 {play_type})，直接查找")
            return odds.get(key, default)

        for alias in play_aliases[key]:
            val = odds.get(alias)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return float(val)

        return default

    def get_all(self, odds: Dict[str, Any], play_type: str) -> Dict[str, float]:
        """批量获取某玩法的所有标准化赔率。

        Args:
            odds: 原始赔率字典
            play_type: 玩法类型

        Returns:
            标准键名 → 赔率值 的字典
        """
        result = {}
        play_aliases = _ODDS_KEY_ALIASES.get(play_type, {})

        for canonical_key, aliases in play_aliases.items():
            if canonical_key.startswith("_"):
                continue  # 跳过特殊键（如 _prefix）
            result[canonical_key] = self.get(odds, play_type, canonical_key)

        return result

    def get_score_odds(self, odds: Dict[str, Any], score: str,
                       default: float = 2.0) -> float:
        """获取比分赔率（BF玩法）。

        Args:
            odds: 原始赔率字典
            score: 比分字符串，如 "1:0", "2:1"
            default: 默认值

        Returns:
            赔率值
        """
        # 尝试多种格式: crs_1:0, crs_1-0, "1:0", "1-0"
        candidates = [
            f"crs_{score}",
            f"crs_{score.replace(':', '-')}",
            score,
            score.replace(":", "-"),
        ]
        for c in candidates:
            val = odds.get(c)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return float(val)
        return default

    def get_total_goals_odds(self, odds: Dict[str, Any], goals: int,
                             default: float = 2.0) -> float:
        """获取总进球赔率（ZJQ玩法）。

        Args:
            odds: 原始赔率字典
            goals: 进球数
            default: 默认值

        Returns:
            赔率值
        """
        candidates = [
            f"ttg_{goals}",
            f"ttg_{goals}+",
            f"ttg_7+" if goals >= 7 else None,
            str(goals),
        ]
        for c in candidates:
            if c is None:
                continue
            val = odds.get(c)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return float(val)
        return default

    def get_hafu_odds(self, odds: Dict[str, Any], result: str,
                      default: float = 2.0) -> float:
        """获取半全场赔率（BQC玩法）。

        Args:
            odds: 原始赔率字典
            result: 半全场结果，如 "胜胜", "胜负", "平平"
            default: 默认值

        Returns:
            赔率值
        """
        # 标准化结果名称
        result_map = {
            "胜胜": "33", "胜平": "31", "胜负": "30",
            "平胜": "13", "平平": "11", "平负": "10",
            "负胜": "03", "负平": "01", "负负": "00",
            "HH": "33", "HD": "31", "HA": "30",
            "DH": "13", "DD": "11", "DA": "10",
            "AH": "03", "AD": "01", "AA": "00",
        }
        candidates = [
            f"hafu_{result}",
            f"hafu_{result_map.get(result, result)}",
            result,
        ]
        for c in candidates:
            val = odds.get(c)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return float(val)
        return default

    def get_handicap(self, odds: Dict[str, Any]) -> Optional[float]:
        """获取让球数。

        Args:
            odds: 赔率字典

        Returns:
            让球数，未找到返回 None
        """
        for key in ["handicap", "let_ball", "rqspf_handicap", "hhad_handicap"]:
            val = odds.get(key)
            if val is not None and isinstance(val, (int, float)):
                return float(val)
        return None


# 模块级单例，方便直接导入使用
odds_normalizer = OddsNormalizer()
