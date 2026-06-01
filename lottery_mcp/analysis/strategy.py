"""
比赛特征识别 + 动态策略系统
替代硬编码规则，根据比赛特征动态调整推荐策略
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class LeagueTier(Enum):
    """联赛级别"""
    TOP = "顶级"        # 五大联赛
    SUB = "次级"        # 欧洲二级联赛、日职、美职
    LOW = "低级别"      # 其他联赛


class OddsPattern(Enum):
    """赔率特征"""
    STRONG_HOME = "深盘主让"     # 主让1球以上
    MODERATE_HOME = "中盘主让"   # 主让0.5-1球
    EVEN = "均势"               # 平手盘或接近
    MODERATE_AWAY = "中盘客让"   # 客让0.5-1球
    STRONG_AWAY = "深盘客让"     # 客让1球以上
    ABNORMAL = "异常"           # 赔率结构异常


class DataQuality(Enum):
    """数据完整度"""
    FULL = "完整"       # 有排名+战绩+伤停+欧指亚盘
    PARTIAL = "部分"     # 有排名+战绩+伤停，无欧指亚盘
    MINIMAL = "基础"     # 只有竞彩赔率
    MISSING = "缺失"     # 数据不足


@dataclass
class MatchProfile:
    """比赛特征画像"""
    match_id: str = ""
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    league_tier: LeagueTier = LeagueTier.LOW

    # 赔率特征
    odds_pattern: OddsPattern = OddsPattern.EVEN
    handicap: float = 0.0
    jc_home_win_odds: float = 0.0
    jc_draw_odds: float = 0.0
    jc_away_win_odds: float = 0.0

    # 数据完整度
    data_quality: DataQuality = DataQuality.MINIMAL
    has_rank: bool = False
    has_form: bool = False
    has_injury: bool = False
    has_european_odds: bool = False
    has_asian_handicap: bool = False

    # 基本面摘要
    home_rank: int = 0
    away_rank: int = 0
    home_win_rate: float = 0.0
    away_win_rate: float = 0.0
    home_injury_count: int = 0
    away_injury_count: int = 0

    # 欧指亚盘摘要
    euro_avg_home: float = 0.0
    euro_avg_draw: float = 0.0
    euro_avg_away: float = 0.0
    asian_handicap_line: float = 0.0
    jc_vs_euro_diff: float = 0.0  # 竞彩与欧指差异（正值=竞彩主胜赔率更高）

    # 标签
    tags: List[str] = field(default_factory=list)


@dataclass
class StrategyConfig:
    """策略配置 - 根据比赛特征动态生成"""
    # 价值发现参数
    value_threshold: float = 1.05       # VR阈值，超过此值认为有价值
    min_ev_threshold: float = -0.15     # 最低EV阈值

    # 低赔率处理策略
    low_odds_handling: str = "penalize"  # penalize / avoid / look_for_handicap / accept
    low_odds_threshold: float = 1.5      # 低赔率阈值
    low_odds_penalty: float = 0.7        # 惩罚系数

    # 各数据源权重
    fundamentals_weight: float = 0.2     # 基本面权重
    market_odds_weight: float = 0.2      # 欧指亚盘权重
    model_weight: float = 0.4            # 泊松模型权重
    jc_odds_weight: float = 0.2          # 竞彩赔率权重

    # 推荐限制
    max_selections_per_play: int = 3     # 每种玩法最大推荐选项数
    min_confidence: float = 20.0         # 最低置信度

    # 风险控制
    max_parlay_size: int = 4             # 最大串关场次数
    max_single_stake_ratio: float = 0.15 # 单场最大投注比例

    # 标签
    strategy_name: str = "默认策略"
    reasoning: str = ""


# ============================================================
# 联赛分级
# ============================================================
TOP_LEAGUES = {
    "英超", "意甲", "西甲", "德甲", "法甲", "欧冠", "欧罗巴",
    "英超杯", "足总杯", "意大利杯", "西班牙国王杯", "德国杯", "法国杯",
}

SUB_LEAGUES = {
    "英冠", "英甲", "英乙", "日职", "日职乙", "美职", "美职联",
    "葡超", "荷甲", "苏超", "土超", "比甲", "奥甲",
    "瑞典超", "瑞超", "挪威超", "挪超", "丹麦超", "丹超",
    "巴甲", "阿甲", "墨超",
}


# ============================================================
# 比赛特征识别器
# ============================================================
class MatchProfiler:
    """比赛特征识别器"""

    @staticmethod
    def profile(match: Dict) -> MatchProfile:
        """分析比赛，生成特征画像"""
        p = MatchProfile()
        p.match_id = match.get("match_id", "")
        p.home_team = match.get("home_team", "")
        p.away_team = match.get("away_team", "")
        p.league = match.get("league", "")

        # 1. 联赛级别
        p.league_tier = MatchProfiler._classify_league(p.league)

        # 2. 赔率特征
        # 兼容两种数据格式：
        # 格式A: match['odds']['had']['win'] (data_tools缓存格式)
        # 格式B: match['had']['win'] (竞彩API原始格式)
        odds = match.get("odds", {})
        had = odds.get("had", {}) or match.get("had", {})
        hhad = odds.get("hhad", {}) or match.get("hhad", {})

        p.jc_home_win_odds = float(had.get("win", odds.get("win", odds.get("had_w", 0)) or 0))
        p.jc_draw_odds = float(had.get("draw", odds.get("draw", odds.get("had_d", 0)) or 0))
        p.jc_away_win_odds = float(had.get("lose", odds.get("lose", odds.get("had_l", 0)) or 0))

        handicap_str = hhad.get("handicap", odds.get("handicap", "0"))
        try:
            p.handicap = float(str(handicap_str).replace("+", ""))
        except (ValueError, TypeError):
            p.handicap = 0.0

        p.odds_pattern = MatchProfiler._classify_odds(
            p.handicap, p.jc_home_win_odds, p.jc_away_win_odds
        )

        # 3. 数据完整度
        fundamentals = match.get("fundamentals", {})
        p.has_rank = bool(fundamentals.get("home_rank", 0))
        p.has_form = bool(fundamentals.get("home_win_rate", 0))
        p.has_injury = bool(fundamentals.get("home_injury_count") is not None)
        p.has_european_odds = bool(match.get("european_odds"))
        p.has_asian_handicap = bool(match.get("asian_handicap"))

        quality_score = sum([
            p.has_rank, p.has_form, p.has_injury,
            p.has_european_odds, p.has_asian_handicap
        ])
        if quality_score >= 4:
            p.data_quality = DataQuality.FULL
        elif quality_score >= 2:
            p.data_quality = DataQuality.PARTIAL
        elif quality_score >= 1:
            p.data_quality = DataQuality.MINIMAL
        else:
            p.data_quality = DataQuality.MISSING

        # 4. 基本面摘要
        p.home_rank = fundamentals.get("home_rank", 0) or 0
        p.away_rank = fundamentals.get("away_rank", 0) or 0
        p.home_win_rate = fundamentals.get("home_win_rate", 0) or 0
        p.away_win_rate = fundamentals.get("away_win_rate", 0) or 0
        p.home_injury_count = fundamentals.get("home_injury_count", 0) or 0
        p.away_injury_count = fundamentals.get("away_injury_count", 0) or 0

        # 5. 欧指亚盘摘要
        consensus = match.get("consensus", {})
        p.euro_avg_home = float(consensus.get("avg_home_win", 0) or 0)
        p.euro_avg_draw = float(consensus.get("avg_draw", 0) or 0)
        p.euro_avg_away = float(consensus.get("avg_away_win", 0) or 0)

        asian = match.get("asian_handicap", [])
        if asian:
            p.asian_handicap_line = float(asian[0].get("home_handicap", 0) or 0)

        # 竞彩vs欧指差异
        if p.euro_avg_home > 0 and p.jc_home_win_odds > 0:
            p.jc_vs_euro_diff = p.jc_home_win_odds - p.euro_avg_home

        # 6. 生成标签
        p.tags = MatchProfiler._generate_tags(p)

        return p

    @staticmethod
    def _classify_league(league: str) -> LeagueTier:
        for top in TOP_LEAGUES:
            if top in league:
                return LeagueTier.TOP
        for sub in SUB_LEAGUES:
            if sub in league:
                return LeagueTier.SUB
        return LeagueTier.LOW

    @staticmethod
    def _classify_odds(handicap: float, home_odds: float, away_odds: float) -> OddsPattern:
        # 竞彩API符号约定: -1 = 主队让1球, +1 = 主队受让1球
        # handicap 越小（越负），主队让球越多
        if handicap <= -1.0:
            return OddsPattern.STRONG_HOME      # 深盘主让（主让1球及以上）
        elif handicap <= -0.5:
            return OddsPattern.MODERATE_HOME    # 中盘主让
        elif handicap == 0:
            if home_odds > 0 and away_odds > 0 and abs(home_odds - away_odds) < 0.3:
                return OddsPattern.EVEN
            elif home_odds < away_odds:
                return OddsPattern.MODERATE_HOME
            else:
                return OddsPattern.MODERATE_AWAY
        elif handicap >= 1.0:
            return OddsPattern.STRONG_AWAY      # 深盘客让（主受让1球及以上）
        else:
            return OddsPattern.MODERATE_AWAY    # 中盘客让

    @staticmethod
    def _generate_tags(p: MatchProfile) -> List[str]:
        tags = []
        tags.append(p.league_tier.value)
        tags.append(p.odds_pattern.value)
        tags.append(p.data_quality.value)

        if p.has_rank and p.home_rank > 0 and p.away_rank > 0:
            if abs(p.home_rank - p.away_rank) >= 8:
                tags.append("排名悬殊")
            elif abs(p.home_rank - p.away_rank) <= 3:
                tags.append("排名接近")

        if p.home_win_rate > 0.6:
            tags.append("主队状态好")
        elif p.away_win_rate > 0.6:
            tags.append("客队状态好")

        if p.home_injury_count >= 3:
            tags.append("主队伤停多")
        if p.away_injury_count >= 3:
            tags.append("客队伤停多")

        if p.jc_vs_euro_diff > 0.3:
            tags.append("竞彩主胜偏高")
        elif p.jc_vs_euro_diff < -0.3:
            tags.append("竞彩主胜偏低")

        return tags


# ============================================================
# 动态策略选择器
# ============================================================
class StrategySelector:
    """根据比赛特征动态选择策略"""

    @staticmethod
    def select(profile: MatchProfile) -> StrategyConfig:
        """根据比赛特征选择策略"""
        config = StrategyConfig()

        # 基于联赛级别调整
        if profile.league_tier == LeagueTier.TOP:
            config.fundamentals_weight = 0.25
            config.market_odds_weight = 0.25
            config.model_weight = 0.35
            config.value_threshold = 1.05
            config.max_selections_per_play = 3
            config.strategy_name = "顶级联赛策略"
            config.reasoning = "顶级联赛数据完整，可使用多维度分析"

        elif profile.league_tier == LeagueTier.SUB:
            config.fundamentals_weight = 0.2
            config.market_odds_weight = 0.15
            config.model_weight = 0.4
            config.value_threshold = 1.08
            config.max_selections_per_play = 2
            config.strategy_name = "次级联赛策略"
            config.reasoning = "次级联赛数据可能不完整，更依赖模型"

        else:
            config.fundamentals_weight = 0.1
            config.market_odds_weight = 0.1
            config.model_weight = 0.5
            config.value_threshold = 1.10
            config.max_selections_per_play = 2
            config.strategy_name = "低级别联赛策略"
            config.reasoning = "低级别联赛数据稀缺，主要依赖模型和赔率"

        # 基于数据完整度调整
        if profile.data_quality == DataQuality.FULL:
            config.market_odds_weight += 0.1
            config.fundamentals_weight += 0.05
            config.reasoning += "，数据完整度高"

        elif profile.data_quality == DataQuality.MISSING:
            config.model_weight += 0.1
            config.value_threshold += 0.05
            config.reasoning += "，数据缺失需谨慎"

        # 基于赔率特征调整
        if profile.odds_pattern == OddsPattern.STRONG_HOME:
            config.low_odds_handling = "look_for_handicap"
            config.low_odds_threshold = 1.8
            config.value_threshold += 0.05
            config.reasoning += "，深盘主让建议关注让球价值"

        elif profile.odds_pattern == OddsPattern.EVEN:
            config.low_odds_handling = "accept"
            config.max_selections_per_play = 3
            config.reasoning += "，均势对局可多选项覆盖"

        elif profile.odds_pattern == OddsPattern.STRONG_AWAY:
            config.low_odds_handling = "look_for_handicap"
            config.low_odds_threshold = 1.8
            config.reasoning += "，深盘客让建议关注让球价值"

        # 基于伤停调整
        if profile.home_injury_count >= 3:
            config.fundamentals_weight += 0.05
            config.reasoning += f"，主队伤停{profile.home_injury_count}人需关注"
        if profile.away_injury_count >= 3:
            config.fundamentals_weight += 0.05
            config.reasoning += f"，客队伤停{profile.away_injury_count}人需关注"

        # 基于竞彩vs欧指差异调整
        if profile.jc_vs_euro_diff > 0.3:
            config.market_odds_weight += 0.1
            config.reasoning += "，竞彩主胜赔率偏高可能有价值"
        elif profile.jc_vs_euro_diff < -0.3:
            config.market_odds_weight += 0.1
            config.reasoning += "，竞彩主胜赔率偏低需警惕"

        # 确保权重总和为1.0
        total = (config.fundamentals_weight + config.market_odds_weight +
                 config.model_weight + config.jc_odds_weight)
        if total > 0:
            config.fundamentals_weight /= total
            config.market_odds_weight /= total
            config.model_weight /= total
            config.jc_odds_weight /= total

        return config

    @staticmethod
    def apply_strategy(config: StrategyConfig, score: float, odds: float,
                       ev: float, value_ratio: float) -> float:
        """
        根据策略调整评分（不是硬编码淘汰）

        Args:
            config: 策略配置
            score: 原始评分
            odds: 赔率
            ev: 期望值
            value_ratio: 价值比率

        Returns:
            调整后的评分
        """
        adjusted = score

        # 低赔率处理策略
        if odds > 0 and odds < config.low_odds_threshold:
            if config.low_odds_handling == "penalize":
                # 惩罚但不淘汰
                if odds < 1.3:
                    adjusted *= 0.3
                elif odds < 1.5:
                    adjusted *= 0.5
                elif odds < 1.8:
                    adjusted *= 0.8
            elif config.low_odds_handling == "avoid":
                # 大幅降低但保留（用户可能需要双选）
                adjusted *= 0.2
            elif config.low_odds_handling == "look_for_handicap":
                # 提示用户关注让球玩法，但保留
                adjusted *= 0.6
            elif config.low_odds_handling == "accept":
                pass  # 不做任何调整

        # 价值调整
        if value_ratio > config.value_threshold:
            adjusted *= 1.2  # 有价值，提升
        elif ev < config.min_ev_threshold:
            adjusted *= 0.8  # 负EV，降低

        return adjusted
