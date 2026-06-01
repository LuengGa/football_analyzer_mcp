"""
玩法专属策略系统 - 完全隔离的玩法分析策略
解决不同玩法逻辑差异巨大的问题
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Union
from enum import Enum
import logging

from .play_analysis import PlayProbabilityResult

try:
    from .advanced_enhancements import RiskDiversifier
    _HAS_RISK_DIVERSIFIER = True
except ImportError:
    _HAS_RISK_DIVERSIFIER = False

logger = logging.getLogger("lottery_mcp")


from .models import PlayType, play_type_from_str


class PlayRiskLevel(Enum):
    """玩法风险等级"""
    VERY_LOW = "极低"
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    VERY_HIGH = "极高"


@dataclass
class PlayStrategyConfig:
    """玩法专属配置"""
    play_type: PlayType

    # 评分权重配置
    prob_weight: float = 0.3          # 概率权重
    ev_weight: float = 0.4            # EV权重
    odds_weight: float = 0.2          # 赔率权重
    value_weight: float = 0.1         # 价值权重

    # 风险控制参数
    risk_level: PlayRiskLevel = PlayRiskLevel.MEDIUM
    min_prob_threshold: float = 0.1   # 最低概率阈值
    max_odds_threshold: float = 50.0  # 最高赔率阈值
    min_ev_threshold: float = 0.8     # 最低EV阈值

    # 推荐策略
    max_recommendations: int = 3      # 最大推荐数
    allow_double_chance: bool = False # 是否允许双选
    prefer_high_prob: bool = True     # 是否偏好高概率

    # 混合过关适配参数
    parlay_suitability: float = 0.5   # 适合混合过关的程度（0-1）
    min_parlay_odds: float = 2.0      # 混合过关最低赔率要求

    # 资金管理参数
    max_bankroll_pct: float = 0.05    # 单注最大资金占比（默认5%）
    kelly_fraction: float = 0.25      # Kelly分数（默认四分之一Kelly）

    def __post_init__(self):
        # Validate weights sum to ~1.0
        total = self.prob_weight + self.ev_weight + self.odds_weight
        if hasattr(self, 'value_weight'):
            total += self.value_weight
        if abs(total - 1.0) > 0.05:
            logger.warning(f"策略权重总和={total:.2f}，偏离1.0，已自动归一化")
            scale = 1.0 / total
            self.prob_weight *= scale
            self.ev_weight *= scale
            self.odds_weight *= scale
            if hasattr(self, 'value_weight'):
                self.value_weight *= scale

        # Validate thresholds
        if self.min_prob_threshold < 0 or self.min_prob_threshold > 0.5:
            logger.warning(f"min_prob_threshold={self.min_prob_threshold}超出合理范围[0, 0.5]，已重置为0.05")
            self.min_prob_threshold = 0.05
        if self.max_odds_threshold < 1.5 or self.max_odds_threshold > 1000:
            logger.warning(f"max_odds_threshold={self.max_odds_threshold}超出合理范围[1.5, 1000]，已重置为10.0")
            self.max_odds_threshold = 10.0


@dataclass
class PlayAnalysisResult:
    """单个玩法的分析结果（增强版）"""
    play_type: PlayType
    recommendations: List[Dict[str, Any]]
    probabilities: Dict[str, float]
    expected_values: Dict[str, float]
    confidence: str
    best_selection: Optional[Dict[str, Any]] = None
    strategy_score: float = 0.0
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    analysis_notes: List[str] = field(default_factory=list)


# ============================================================
# 各玩法专属策略类
# ============================================================

class BasePlayStrategy:
    """玩法策略基类"""

    def __init__(self, play_type: PlayType):
        self.play_type = play_type
        self.config = self._get_default_config()

    def _get_default_config(self) -> PlayStrategyConfig:
        """获取默认配置 - 子类覆盖"""
        return PlayStrategyConfig(play_type=self.play_type)

    def _safe_get(self, data: Dict, key: str, default: float, context: str = "") -> float:
        """安全获取值，缺失时记录警告"""
        val = data.get(key)
        if val is None:
            logger.debug(f"数据缺失: {key}（{context}），使用默认值{default}")
            return default
        return val

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        """
        分析玩法（核心方法）

        Args:
            play_data: 玩法原始数据，支持 PlayProbabilityResult（来自PlayAnalyzer）
                       或 Dict 格式（向后兼容）
            match_context: 比赛上下文信息

        Returns:
            PlayAnalysisResult: 玩法专属分析结果
        """
        raise NotImplementedError("子类必须实现analyze方法")

    def _convert_probability_result(self, prob_result: PlayProbabilityResult) -> Dict[str, Any]:
        """将 PlayProbabilityResult 转换为 Dict 格式，供策略方法内部使用。

        Args:
            prob_result: 来自 PlayAnalyzer 的概率分析结果

        Returns:
            包含 recommendations, probabilities, expected_value, confidence, analysis_notes 的字典
        """
        return {
            "recommendations": prob_result.recommendations,
            "probabilities": prob_result.probabilities,
            "expected_value": prob_result.expected_value,
            "confidence": prob_result.confidence,
            "analysis_notes": prob_result.analysis_notes,
        }

    def _normalize_play_data(self, play_data: Union[Dict[str, Any], PlayProbabilityResult]) -> Dict[str, Any]:
        """统一将 play_data 转换为 Dict 格式。

        Args:
            play_data: PlayProbabilityResult 或 Dict

        Returns:
            Dict 格式的玩法数据
        """
        if isinstance(play_data, PlayProbabilityResult):
            data = self._convert_probability_result(play_data)
        else:
            data = play_data

        # Normalize expected_value -> expected_values
        if "expected_value" in data and "expected_values" not in data:
            data["expected_values"] = data["expected_value"]

        return data

    def _compute_dynamic_risk(self, match_context: Dict[str, Any]) -> Dict[str, Any]:
        """根据比赛上下文动态计算风险评估。

        考虑以下因素：
        1. 伤病数据：如果存在伤病信息，增加波动性
        2. 赔率变动：如果赔率有显著变动，增加波动性
        3. 数据质量：如果数据质量低或缺失，增加不可预测性

        Args:
            match_context: 比赛上下文信息

        Returns:
            动态风险评估字典，包含 volatility, predictability, suitable_for_parlay, notes
        """
        # 从配置获取基础风险评估
        base_risk = {
            "volatility": self.config.risk_level.value if hasattr(self.config.risk_level, 'value') else "中",
            "predictability": "中",
            "suitable_for_parlay": self.config.parlay_suitability >= 0.6,
            "notes": [],
        }

        volatility_boost = 0  # 波动性增加计数
        predictability_penalty = 0  # 可预测性惩罚计数

        # 1. 检查伤病数据
        home_injuries = match_context.get("home_injuries")
        away_injuries = match_context.get("away_injuries")
        injury_count = 0
        if home_injuries and isinstance(home_injuries, (list, tuple)):
            injury_count += len(home_injuries)
        if away_injuries and isinstance(away_injuries, (list, tuple)):
            injury_count += len(away_injuries)

        if injury_count > 0:
            volatility_boost += min(injury_count, 5)  # 最多增加5级
            base_risk["notes"].append(f"存在{injury_count}条伤病信息，比赛波动性增加")

        # 2. 检查赔率变动
        odds_movement = match_context.get("odds_movement")
        if odds_movement and isinstance(odds_movement, dict):
            # 检查赔率变动幅度
            movement_amount = odds_movement.get("movement_amount", 0)
            if isinstance(movement_amount, (int, float)) and abs(movement_amount) > 0.1:
                volatility_boost += 2
                base_risk["notes"].append(f"赔率变动显著（幅度{movement_amount:.2f}），波动性增加")
            elif isinstance(movement_amount, str):
                try:
                    if abs(float(movement_amount)) > 0.1:
                        volatility_boost += 2
                        base_risk["notes"].append(f"赔率变动显著（幅度{movement_amount}），波动性增加")
                except ValueError:
                    pass

            # 检查赔率变动方向是否一致（可能暗示内幕信息）
            direction = odds_movement.get("direction", "")
            if direction in ["significant_drift", "sharp_move", "reverse"]:
                volatility_boost += 1
                base_risk["notes"].append(f"赔率变动类型：{direction}，需警惕")

        # 3. 检查数据质量
        data_quality = match_context.get("data_quality", "")
        if isinstance(data_quality, str):
            data_quality = data_quality.upper()
        if data_quality in ["LOW", "低", "MISSING", "缺失", ""]:
            if not data_quality:  # 空字符串表示缺失
                predictability_penalty += 1
                base_risk["notes"].append("数据质量信息缺失，不可预测性增加")
            else:
                predictability_penalty += 2
                base_risk["notes"].append(f"数据质量为{data_quality}，不可预测性显著增加")

        # 根据累计调整更新风险等级
        volatility_levels = ["极低", "低", "中", "高", "极高"]
        current_idx = volatility_levels.index(base_risk["volatility"]) if base_risk["volatility"] in volatility_levels else 2
        new_idx = min(len(volatility_levels) - 1, current_idx + volatility_boost)
        base_risk["volatility"] = volatility_levels[new_idx]

        # 更新可预测性
        predictability_levels = ["极高", "高", "中高", "中", "中低", "低"]
        pred_idx = 2  # 默认"中高"
        if predictability_penalty >= 2:
            pred_idx = 4  # "中低"
        elif predictability_penalty >= 1:
            pred_idx = 3  # "中"
        base_risk["predictability"] = predictability_levels[pred_idx]

        # 更新混合过关适合度
        if volatility_boost >= 3 or predictability_penalty >= 2:
            base_risk["suitable_for_parlay"] = False

        return base_risk

    def calculate_recommended_stake(self, bankroll: float, ev: float, odds: float, risk_level: str) -> Dict[str, Any]:
        """计算推荐投注金额"""
        # Kelly公式
        if odds > 1 and ev > 1.0:
            prob = ev / odds  # 近似真实概率
            kelly = max(0, (prob * odds - 1) / (odds - 1)) * self.config.kelly_fraction
        else:
            kelly = 0

        # 根据风险等级调整
        risk_multipliers = {"低": 1.0, "中": 0.7, "高": 0.4}
        kelly *= risk_multipliers.get(risk_level, 0.7)

        # 不超过最大资金占比
        stake = bankroll * min(kelly, self.config.max_bankroll_pct)

        return {
            "recommended_stake": round(max(2, stake), 2),  # 最低2元
            "kelly_fraction": round(kelly, 4),
            "bankroll_pct": round(stake / bankroll * 100, 2) if bankroll > 0 else 0,
        }

    def score_selection(self, selection: Dict[str, Any]) -> float:
        """为单个选项评分"""
        prob = selection.get("probability", 0)
        ev = selection.get("expected_value", 0)
        odds = selection.get("odds", selection.get("estimated_odds", 0))

        score = (
            prob * self.config.prob_weight +
            max(ev, 0) * self.config.ev_weight +
            min(odds / 5.0, 1.0) * self.config.odds_weight if odds is not None else 0.0
        )
        return score

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        生成中文推理链，解释为何推荐某个选择

        推理链包含五个维度：
        1. 概率依据 - 泊松模型预测概率与市场隐含概率的对比
        2. 价值分析 - 期望值EV评估
        3. 赔率评估 - 赔率合理性判断
        4. 风险提示 - 玩法风险等级提醒
        5. 策略适配 - 混合过关适合度评估

        Args:
            play_data: 玩法原始数据（包含recommendations, probabilities, expected_value等）
            match_context: 比赛上下文信息（包含赔率、预期进球等）
            play_type_name: 玩法中文名称（如"胜平负"、"让球胜平负"等）

        Returns:
            推理链列表，每项为一条中文推理说明
        """
        chain = []
        recs = play_data.get("recommendations", [])
        probs = play_data.get("probabilities", {})
        evs = play_data.get("expected_value", {})

        if not recs:
            chain.append(f"[{play_type_name}] 无有效推荐数据，无法生成推理链")
            return chain

        best_rec = recs[0] if recs else {}
        selection_name = best_rec.get("selection", "未知")
        model_prob = best_rec.get("probability", 0)
        odds_val = best_rec.get("odds", best_rec.get("estimated_odds", 0))
        ev_val = best_rec.get("expected_value", 0)

        # ---- 1. 概率依据 ----
        # 计算市场隐含概率（从赔率反推）
        if odds_val and odds_val > 1.0:
            # 竞彩返还率约70%，真实隐含概率需考虑庄家优势
            market_implied_prob = 1.0 / odds_val * 0.70  # Account for ~70% return rate
            prob_diff = model_prob - market_implied_prob
            if prob_diff > 0:
                chain.append(
                    f"1. 概率依据：泊松模型预测「{selection_name}」概率{model_prob * 100:.1f}%，"
                    f"高于市场隐含概率{market_implied_prob * 100:.1f}%（赔率{odds_val:.2f}），"
                    f"差值+{prob_diff * 100:.1f}%，模型看好该选项"
                )
            elif prob_diff < -0.02:
                chain.append(
                    f"1. 概率依据：泊松模型预测「{selection_name}」概率{model_prob * 100:.1f}%，"
                    f"低于市场隐含概率{market_implied_prob * 100:.1f}%（赔率{odds_val:.2f}），"
                    f"差值{prob_diff * 100:.1f}%，市场可能高估该选项"
                )
            else:
                chain.append(
                    f"1. 概率依据：泊松模型预测「{selection_name}」概率{model_prob * 100:.1f}%，"
                    f"与市场隐含概率{market_implied_prob * 100:.1f}%（赔率{odds_val:.2f}）基本一致"
                )
        else:
            chain.append(
                f"1. 概率依据：泊松模型预测「{selection_name}」概率{model_prob * 100:.1f}%"
            )

        # ---- 2. 价值分析 ----
        if ev_val > 0:
            if ev_val >= 1.0:
                chain.append(
                    f"2. 价值分析：期望值EV={ev_val:.2f}>=1.0，具有正期望值，"
                    f"长期投注该选项具有理论盈利空间"
                )
            elif ev_val >= 0.9:
                chain.append(
                    f"2. 价值分析：期望值EV={ev_val:.2f}，接近盈亏平衡线，"
                    f"需结合其他因素综合判断"
                )
            else:
                chain.append(
                    f"2. 价值分析：期望值EV={ev_val:.2f}<1.0，价值不足，"
                    f"不建议作为重点投注选项"
                )
        else:
            chain.append(
                f"2. 价值分析：无法计算期望值，缺乏足够数据进行价值评估"
            )

        # ---- 3. 赔率评估 ----
        if odds_val and odds_val > 1.0:
            # 根据玩法类型确定合理赔率区间
            if self.play_type == PlayType.SPF:
                odds_range_low, odds_range_high = 1.3, 5.0
                odds_label = "胜平负"
            elif self.play_type == PlayType.RQSPF:
                odds_range_low, odds_range_high = 1.4, 5.5
                odds_label = "让球胜平负"
            elif self.play_type == PlayType.BF:
                odds_range_low, odds_range_high = 4.0, 15.0
                odds_label = "比分"
            elif self.play_type == PlayType.ZJQ:
                odds_range_low, odds_range_high = 1.8, 8.0
                odds_label = "总进球"
            elif self.play_type == PlayType.BQC:
                odds_range_low, odds_range_high = 3.0, 12.0
                odds_label = "半全场"
            else:
                odds_range_low, odds_range_high = 1.5, 10.0
                odds_label = play_type_name

            if odds_val < odds_range_low:
                chain.append(
                    f"3. 赔率评估：赔率{odds_val:.2f}处于{odds_label}玩法的低位区间"
                    f"（合理区间{odds_range_low:.1f}-{odds_range_high:.1f}），"
                    f"投注价值有限，回报率较低"
                )
            elif odds_val > odds_range_high:
                chain.append(
                    f"3. 赔率评估：赔率{odds_val:.2f}处于{odds_label}玩法的高位区间"
                    f"（合理区间{odds_range_low:.1f}-{odds_range_high:.1f}），"
                    f"潜在回报高但命中概率低，属于高赔率博弈"
                )
            else:
                chain.append(
                    f"3. 赔率评估：赔率{odds_val:.2f}处于{odds_label}玩法的合理区间"
                    f"（{odds_range_low:.1f}-{odds_range_high:.1f}），赔率结构合理"
                )
        else:
            chain.append(
                f"3. 赔率评估：赔率数据缺失，无法进行赔率合理性评估"
            )

        # ---- 4. 风险提示 ----
        risk_level = self.config.risk_level
        if risk_level == PlayRiskLevel.VERY_LOW:
            chain.append(
                f"4. 风险提示：{play_type_name}玩法风险极低，适合稳健型投注策略"
            )
        elif risk_level == PlayRiskLevel.LOW:
            chain.append(
                f"4. 风险提示：{play_type_name}玩法风险较低，适合作为混合过关的基础选项"
            )
        elif risk_level == PlayRiskLevel.MEDIUM:
            chain.append(
                f"4. 风险提示：{play_type_name}玩法风险中等，建议控制单注金额"
            )
        elif risk_level == PlayRiskLevel.HIGH:
            chain.append(
                f"4. 风险提示：{play_type_name}玩法风险较高，建议小注或作为混合过关的点缀，不宜重注"
            )
        elif risk_level == PlayRiskLevel.VERY_HIGH:
            chain.append(
                f"4. 风险提示：{play_type_name}玩法风险极高，仅建议以极小注额参与博冷"
            )

        # ---- 5. 策略适配 ----
        parlay_suit = self.config.parlay_suitability
        if parlay_suit >= 0.8:
            chain.append(
                f"5. 策略适配：该选择非常适合混合过关（适合度{parlay_suit:.2f}），"
                f"可作为过关串的基础选项"
            )
        elif parlay_suit >= 0.6:
            chain.append(
                f"5. 策略适配：该选择较适合混合过关（适合度{parlay_suit:.2f}），"
                f"可与低相关性玩法组合使用"
            )
        elif parlay_suit >= 0.4:
            chain.append(
                f"5. 策略适配：该选择不太适合混合过关（适合度{parlay_suit:.2f}），"
                f"建议作为单注或谨慎组合"
            )
        else:
            chain.append(
                f"5. 策略适配：该选择不适合混合过关（适合度{parlay_suit:.2f}），"
                f"建议仅作单注投注"
            )

        # 在推理链末尾添加明确建议
        recommendations = play_data.get("recommendations", [])
        best_rec = recommendations[0] if recommendations else None
        if best_rec:
            ev = best_rec.get("expected_value", 0)
            if ev > 1.10:
                chain.append(f"💡 综合建议：强烈推荐「{best_rec['selection']}」（赔率{best_rec.get('odds', 0):.2f}，EV={ev:.2f}）")
            elif ev > 1.0:
                chain.append(f"💡 综合建议：推荐「{best_rec['selection']}」（赔率{best_rec.get('odds', 0):.2f}，EV={ev:.2f}）")
            elif ev > 0.90:
                chain.append(f"💡 综合建议：可考虑「{best_rec['selection']}」，但EV偏低（{ev:.2f}），需谨慎")
            else:
                chain.append(f"💡 综合建议：不推荐投注「{best_rec['selection']}」，EV不足（{ev:.2f}）")

        # ========== S4-2: 推理链末尾添加校准信息 ==========
        # 添加校准状态说明
        if isinstance(play_data, dict):
            if play_data.get("_calibrated"):
                chain.append("✅ 已应用历史数据贝叶斯校准")
            else:
                chain.append("ℹ️ 基于纯泊松模型（建议补充历史数据）")

            # 添加盘口分析
            handicap_analysis = play_data.get("_handicap_analysis")
            if handicap_analysis:
                interp = handicap_analysis.get("interpretation", "")
                if interp:
                    if handicap_analysis.get("is_reasonable", True):
                        chain.append(f"📊 盘口: {interp}")
                    else:
                        chain.append(f"⚠️ 盘口: {interp}")

            # 添加大小球分析
            ou_analysis = play_data.get("_over_under_analysis")
            if ou_analysis:
                interp = ou_analysis.get("interpretation", "")
                if interp:
                    chain.append(f"📊 大小球: {interp}")

        return chain


class SPFStrategy(BasePlayStrategy):
    """胜平负专属策略"""

    def __init__(self):
        super().__init__(PlayType.SPF)

    def _get_default_config(self) -> PlayStrategyConfig:
        return PlayStrategyConfig(
            play_type=PlayType.SPF,
            prob_weight=0.35,
            ev_weight=0.4,
            odds_weight=0.15,
            value_weight=0.1,
            risk_level=PlayRiskLevel.LOW,
            min_prob_threshold=0.22,
            max_odds_threshold=9.0,
            min_ev_threshold=0.82,
            max_recommendations=3,
            allow_double_chance=True,
            prefer_high_prob=True,
            parlay_suitability=0.9,  # 非常适合混合过关
            min_parlay_odds=1.5,
        )

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        胜平负专属推理链

        在基类推理链基础上增加主客场优势分析
        """
        chain = super().generate_reasoning_chain(play_data, match_context, play_type_name)

        # SPF专属：主客场优势分析
        home_exp = self._safe_get(match_context, "home_expected_goals", 0, "胜平负-主队预期进球")
        away_exp = self._safe_get(match_context, "away_expected_goals", 0, "胜平负-客队预期进球")
        home_team = match_context.get("home_team", "主队")
        away_team = match_context.get("away_team", "客队")

        if home_exp > 0 and away_exp > 0:
            goal_diff = home_exp - away_exp
            if goal_diff > 0.8:
                chain.append(
                    f"6. 主场优势：预期{home_team}（{home_exp:.1f}球）远强于"
                    f"{away_team}（{away_exp:.1f}球），主场优势明显，主胜概率较高"
                )
            elif goal_diff > 0.3:
                chain.append(
                    f"6. 主场优势：预期{home_team}（{home_exp:.1f}球）略强于"
                    f"{away_team}（{away_exp:.1f}球），主场有一定优势"
                )
            elif goal_diff > -0.3:
                chain.append(
                    f"6. 实力对比：预期{home_team}（{home_exp:.1f}球）与"
                    f"{away_team}（{away_exp:.1f}球）实力接近，平局概率值得关注"
                )
            else:
                chain.append(
                    f"6. 客场优势：预期{away_team}（{away_exp:.1f}球）强于"
                    f"{home_team}（{home_exp:.1f}球），客队具备客场取分能力"
                )

        return chain

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        play_data = self._normalize_play_data(play_data)
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        # 为每个推荐评分（基础评分）
        scored_recs = []
        for rec in recs:
            score = self.score_selection(rec)
            rec["strategy_score"] = score
            scored_recs.append(rec)

        scored_recs.sort(key=lambda x: x["strategy_score"], reverse=True)

        # 找出最佳选择
        best_selection = None
        if scored_recs:
            best_rec = scored_recs[0]
            best_selection = {
                "selection": best_rec["selection"],
                "probability": best_rec["probability"],
                "odds": best_rec.get("odds", best_rec.get("estimated_odds", 0)),
                "ev": best_rec["expected_value"],
            }

        # 风险评估（动态计算）
        risk_assessment = self._compute_dynamic_risk(match_context)
        risk_assessment.setdefault("notes", []).insert(0, "胜平负玩法风险低，适合作为混合过关的基础")

        # 生成推理链
        reasoning_chain = self.generate_reasoning_chain(
            play_data, match_context, "胜平负"
        )

        # ========== S4-1: 校准感知逻辑 ==========
        calibration_bonus = 0.0
        calibration_notes = []

        if play_data.get("_calibrated"):
            calibration_bonus = 0.05  # 历史校准可信度+5%
            calibration_notes.append("历史校准增强")
            # 对已评分的推荐应用校准加分
            for rec in scored_recs:
                rec["strategy_score"] = rec.get("strategy_score", 0) * (1 + calibration_bonus)

        # RQSPF盘口合理性（SPF虽无让球，但也检查通用盘口分析）
        handicap_analysis = play_data.get("_handicap_analysis")
        if handicap_analysis:
            if not handicap_analysis.get("is_reasonable", True):
                # 盘口异常，降权
                handicap_penalty = 0.10
                for rec in scored_recs:
                    rec["strategy_score"] = rec.get("strategy_score", 0) * (1 - handicap_penalty)
                calibration_notes.append(f"盘口异常: {handicap_analysis.get('interpretation', '')}")

        # 大小球偏差（ZJQ相关，SPF检查是否有相关分析）
        if "ZJQ" in str(self.play_type) or self.play_type == PlayType.ZJQ:
            ou_analysis = play_data.get("_over_under_analysis")
            if ou_analysis and ou_analysis.get("bias"):
                calibration_notes.append(f"大小球: {ou_analysis.get('interpretation', '')}")

        # 重新排序
        scored_recs.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)

        return PlayAnalysisResult(
            play_type=PlayType.SPF,
            recommendations=scored_recs[:self.config.max_recommendations],
            probabilities=probs,
            expected_values=play_data.get("expected_values", play_data.get("expected_value", {})),
            confidence=conf,
            best_selection=best_selection,
            strategy_score=scored_recs[0].get("strategy_score", 0) if scored_recs else 0,
            risk_assessment=risk_assessment,
            analysis_notes=["胜平负策略：优先考虑高概率+正EV"] + reasoning_chain + calibration_notes,
        )


class RQSPFStrategy(BasePlayStrategy):
    """让球胜平负专属策略"""

    def __init__(self):
        super().__init__(PlayType.RQSPF)

    def _get_default_config(self) -> PlayStrategyConfig:
        return PlayStrategyConfig(
            play_type=PlayType.RQSPF,
            prob_weight=0.32,
            ev_weight=0.42,
            odds_weight=0.16,
            value_weight=0.1,
            risk_level=PlayRiskLevel.MEDIUM,
            min_prob_threshold=0.18,
            max_odds_threshold=11.0,
            min_ev_threshold=0.8,
            max_recommendations=3,
            allow_double_chance=True,
            prefer_high_prob=True,
            parlay_suitability=0.85,
            min_parlay_odds=1.6,
        )

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        让球胜平负专属推理链

        在基类推理链基础上增加让球深度影响分析
        """
        chain = super().generate_reasoning_chain(play_data, match_context, play_type_name)

        # RQSPF专属：让球深度影响分析
        handicap = self._safe_get(match_context, "handicap", 0, "让球胜平负-让球数")
        home_exp = self._safe_get(match_context, "home_expected_goals", 0, "让球胜平负-主队预期进球")
        away_exp = self._safe_get(match_context, "away_expected_goals", 0, "让球胜平负-客队预期进球")

        abs_handicap = abs(handicap)
        if abs_handicap == 0:
            chain.append(
                f"6. 让球分析：本场为平手盘（让球0球），让球胜平负与胜平负完全一致，"
                f"无额外让球调整"
            )
        elif abs_handicap < 0.5:
            chain.append(
                f"6. 让球分析：让球{handicap:+.1f}球属于浅盘，让球幅度较小，"
                f"对胜负判定影响有限，上盘仍需较大比分优势才能赢盘"
            )
        elif abs_handicap < 1.0:
            chain.append(
                f"6. 让球分析：让球{handicap:+.1f}球属于中盘，让球幅度适中，"
                f"胜负判定发生实质性调整，需关注双方实际进攻能力"
            )
        elif abs_handicap < 1.5:
            chain.append(
                f"6. 让球分析：让球{handicap:+.1f}球属于深盘，让球幅度较大，"
                f"上盘需要净胜多球才能赢盘，下盘（让球客胜/平）机会增加"
            )
        else:
            chain.append(
                f"6. 让球分析：让球{handicap:+.1f}球属于极深盘，让球幅度极大，"
                f"上盘赢盘难度很高，冷门概率显著增加，建议关注下盘"
            )

        # 深盘风险提示
        if abs_handicap >= 1.5:
            chain.append(
                f"6.1 深盘风险：让球{handicap:+.1f}球属于深盘区间，"
                f"深盘比赛中上盘需要大比分优势才能赢盘，"
                f"而足球比赛进球数有限，深盘上盘赢盘难度显著增大，"
                f"历史数据显示深盘比赛下盘（让球客胜/平）打出率较高，需谨慎对待"
            )

        # 让球与预期进球差的对比
        if home_exp > 0 and away_exp > 0:
            expected_diff = home_exp - away_exp
            if handicap > 0:
                # 主让客
                effective_diff = expected_diff - handicap
                if effective_diff > 0.3:
                    chain.append(
                        f"7. 盘口匹配：预期净胜球{expected_diff:.1f}球，"
                        f"扣除让球{handicap:+.1f}球后仍为{effective_diff:+.1f}球，"
                        f"上盘（让球主胜）仍有一定优势"
                    )
                elif effective_diff > -0.3:
                    chain.append(
                        f"7. 盘口匹配：预期净胜球{expected_diff:.1f}球，"
                        f"扣除让球{handicap:+.1f}球后为{effective_diff:+.1f}球，"
                        f"盘口与实力基本匹配，让球平局值得关注"
                    )
                else:
                    chain.append(
                        f"7. 盘口匹配：预期净胜球{expected_diff:.1f}球，"
                        f"扣除让球{handicap:+.1f}球后为{effective_diff:+.1f}球，"
                        f"让球偏深，下盘（让球客胜）可能存在价值"
                    )

        return chain

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        play_data = self._normalize_play_data(play_data)
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        handicap = match_context.get("handicap", 0)

        # 为每个推荐评分（基础评分）
        scored_recs = []
        for rec in recs:
            score = self.score_selection(rec)
            # 分级让球深度调整
            abs_handicap = abs(handicap)
            if abs_handicap >= 2.0:
                score *= 0.85  # 深盘(2球+): 15%惩罚
            elif abs_handicap >= 1.5:
                score *= 0.90  # 较深盘(1.5球): 10%惩罚
            elif abs_handicap >= 1.0:
                score *= 0.95  # 中盘(1球): 5%惩罚
            # 0.5球及以下不调整
            rec["strategy_score"] = score
            scored_recs.append(rec)

        scored_recs.sort(key=lambda x: x["strategy_score"], reverse=True)

        # 找出最佳选择
        best_selection = None
        if scored_recs:
            best_rec = scored_recs[0]
            best_selection = {
                "selection": best_rec["selection"],
                "probability": best_rec["probability"],
                "odds": best_rec.get("odds", best_rec.get("estimated_odds", 0)),
                "ev": best_rec["expected_value"],
            }

        risk_assessment = self._compute_dynamic_risk(match_context)
        risk_assessment.setdefault("notes", []).insert(0, f"让球{handicap:+.1f}，需关注让球深度影响")

        # 生成推理链
        reasoning_chain = self.generate_reasoning_chain(
            play_data, match_context, "让球胜平负"
        )

        # ========== S4-1: 校准感知逻辑 ==========
        calibration_bonus = 0.0
        calibration_notes = []

        if play_data.get("_calibrated"):
            calibration_bonus = 0.05  # 历史校准可信度+5%
            calibration_notes.append("历史校准增强")
            # 对已评分的推荐应用校准加分
            for rec in scored_recs:
                rec["strategy_score"] = rec.get("strategy_score", 0) * (1 + calibration_bonus)

        # RQSPF盘口合理性分析
        handicap_analysis = play_data.get("_handicap_analysis")
        if handicap_analysis:
            if not handicap_analysis.get("is_reasonable", True):
                # 盘口异常，降权
                handicap_penalty = 0.10
                for rec in scored_recs:
                    rec["strategy_score"] = rec.get("strategy_score", 0) * (1 - handicap_penalty)
                calibration_notes.append(f"盘口异常: {handicap_analysis.get('interpretation', '')}")

        # 大小球偏差（ZJQ相关检查）
        if "ZJQ" in str(self.play_type) or self.play_type == PlayType.ZJQ:
            ou_analysis = play_data.get("_over_under_analysis")
            if ou_analysis and ou_analysis.get("bias"):
                calibration_notes.append(f"大小球: {ou_analysis.get('interpretation', '')}")

        # 重新排序
        scored_recs.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)

        return PlayAnalysisResult(
            play_type=PlayType.RQSPF,
            recommendations=scored_recs[:self.config.max_recommendations],
            probabilities=probs,
            expected_values=play_data.get("expected_values", play_data.get("expected_value", {})),
            confidence=conf,
            best_selection=best_selection,
            strategy_score=scored_recs[0].get("strategy_score", 0) if scored_recs else 0,
            risk_assessment=risk_assessment,
            analysis_notes=["让球胜平负策略：结合让球深度调整"] + reasoning_chain + calibration_notes,
        )


class BFStrategy(BasePlayStrategy):
    """比分专属策略 - 完全不同的逻辑"""

    def __init__(self):
        super().__init__(PlayType.BF)

    def _get_default_config(self) -> PlayStrategyConfig:
        return PlayStrategyConfig(
            play_type=PlayType.BF,
            prob_weight=0.22,
            ev_weight=0.48,
            odds_weight=0.2,
            value_weight=0.1,
            risk_level=PlayRiskLevel.HIGH,
            min_prob_threshold=0.04,
            max_odds_threshold=85.0,
            min_ev_threshold=0.72,
            max_recommendations=4,
            allow_double_chance=False,
            prefer_high_prob=False,  # 比分不盲目追求高概率
            parlay_suitability=0.45,  # 略提升混合过关适合度
            min_parlay_odds=5.5,
        )

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        比分专属推理链

        在基类推理链基础上增加比分与预期进球的吻合度分析
        """
        chain = super().generate_reasoning_chain(play_data, match_context, play_type_name)

        # BF专属：比分与预期进球吻合度
        recs = play_data.get("recommendations", [])
        if recs:
            best_rec = recs[0]
            selection = best_rec.get("selection", "")
            home_exp = self._safe_get(match_context, "home_expected_goals", 1.4, "比分-主队预期进球")
            away_exp = self._safe_get(match_context, "away_expected_goals", 1.1, "比分-客队预期进球")

            if selection not in ["胜其他", "平其他", "负其他"]:
                try:
                    parts = selection.split(":")
                    h_goals = int(parts[0])
                    a_goals = int(parts[1])
                    goal_diff = abs(h_goals - home_exp) + abs(a_goals - away_exp)

                    if goal_diff <= 1.0:
                        chain.append(
                            f"6. 比分吻合度：推荐比分{selection}与预期进球"
                            f"（{home_exp:.1f}-{away_exp:.1f}）高度吻合"
                            f"（偏差{goal_diff:.1f}球），可信度较高"
                        )
                    elif goal_diff <= 2.0:
                        chain.append(
                            f"6. 比分吻合度：推荐比分{selection}与预期进球"
                            f"（{home_exp:.1f}-{away_exp:.1f}）基本吻合"
                            f"（偏差{goal_diff:.1f}球），属于合理范围"
                        )
                    else:
                        chain.append(
                            f"6. 比分吻合度：推荐比分{selection}与预期进球"
                            f"（{home_exp:.1f}-{away_exp:.1f}）偏差较大"
                            f"（偏差{goal_diff:.1f}球），可能为冷门比分"
                        )

                    # 比分方向分析
                    total_exp = home_exp + away_exp
                    total_actual = h_goals + a_goals
                    if total_actual <= total_exp - 1:
                        chain.append(
                            f"7. 进球趋势：推荐比分总进球{total_actual}球，"
                            f"低于预期总进球{total_exp:.1f}球，偏向小球方向"
                        )
                    elif total_actual >= total_exp + 1:
                        chain.append(
                            f"7. 进球趋势：推荐比分总进球{total_actual}球，"
                            f"高于预期总进球{total_exp:.1f}球，偏向大球方向"
                        )
                    else:
                        chain.append(
                            f"7. 进球趋势：推荐比分总进球{total_actual}球，"
                            f"与预期总进球{total_exp:.1f}球一致"
                        )
                except (ValueError, IndexError):
                    pass
            else:
                chain.append(
                    f"6. 比分分析：推荐「{selection}」，该选项覆盖多个比分结果，"
                    f"命中率较高但赔率相对较低"
                )

        return chain

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        play_data = self._normalize_play_data(play_data)
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        home_exp = match_context.get("home_expected_goals", 1.4)
        away_exp = match_context.get("away_expected_goals", 1.1)

        scored_recs = []
        for rec in recs:
            score = self.score_selection(rec)

            # 比分专属调整：
            # 1. 更倾向于符合预期进球的比分
            selection = rec["selection"]
            if selection not in ["胜其他", "平其他", "负其他"]:
                try:
                    parts = selection.split(":")
                    h_goals = int(parts[0])
                    a_goals = int(parts[1])
                    goal_diff = abs(h_goals - home_exp) + abs(a_goals - away_exp)
                    if goal_diff <= 2.0:
                        score *= 1.2  # 接近预期的比分加分
                except (ValueError, IndexError):
                    pass

            # 2. 避免过于冷门的比分（除非EV特别高）
            prob = rec.get("probability", 0)
            ev = rec.get("expected_value", 0)
            if prob < 0.02 and ev < 1.2:
                score *= 0.6  # 极冷门+低价值: 40%惩罚
            elif prob < 0.03 and ev < 1.5:
                score *= 0.75  # 冷门+低价值: 25%惩罚
            elif prob < 0.04 and ev < 1.8:
                score *= 0.85  # 偏冷+偏低价值: 15%惩罚

            rec["strategy_score"] = score
            scored_recs.append(rec)

        scored_recs.sort(key=lambda x: x["strategy_score"], reverse=True)

        # 找出最佳选择
        best_selection = None
        if scored_recs:
            best_rec = scored_recs[0]
            best_selection = {
                "selection": best_rec["selection"],
                "probability": best_rec["probability"],
                "odds": best_rec.get("odds", best_rec.get("estimated_odds", 0)),
                "ev": best_rec["expected_value"],
            }

        risk_assessment = self._compute_dynamic_risk(match_context)
        risk_assessment.setdefault("notes", []).insert(0, "比分玩法风险高，建议小注或作为混合过关的点缀")

        # 生成推理链
        reasoning_chain = self.generate_reasoning_chain(
            play_data, match_context, "比分"
        )

        # ========== S4-1: 校准感知逻辑 ==========
        calibration_bonus = 0.0
        calibration_notes = []

        if play_data.get("_calibrated"):
            calibration_bonus = 0.05  # 历史校准可信度+5%
            calibration_notes.append("历史校准增强")
            # 对已评分的推荐应用校准加分
            for rec in scored_recs:
                rec["strategy_score"] = rec.get("strategy_score", 0) * (1 + calibration_bonus)

        # RQSPF盘口合理性分析
        handicap_analysis = play_data.get("_handicap_analysis")
        if handicap_analysis:
            if not handicap_analysis.get("is_reasonable", True):
                # 盘口异常，降权
                handicap_penalty = 0.10
                for rec in scored_recs:
                    rec["strategy_score"] = rec.get("strategy_score", 0) * (1 - handicap_penalty)
                calibration_notes.append(f"盘口异常: {handicap_analysis.get('interpretation', '')}")

        # 大小球偏差（ZJQ相关检查）
        if "ZJQ" in str(self.play_type) or self.play_type == PlayType.ZJQ:
            ou_analysis = play_data.get("_over_under_analysis")
            if ou_analysis and ou_analysis.get("bias"):
                calibration_notes.append(f"大小球: {ou_analysis.get('interpretation', '')}")

        # 重新排序
        scored_recs.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)

        return PlayAnalysisResult(
            play_type=PlayType.BF,
            recommendations=scored_recs[:self.config.max_recommendations],
            probabilities=probs,
            expected_values=play_data.get("expected_values", play_data.get("expected_value", {})),
            confidence=conf,
            best_selection=best_selection,
            strategy_score=scored_recs[0].get("strategy_score", 0) if scored_recs else 0,
            risk_assessment=risk_assessment,
            analysis_notes=["比分策略：EV优先，同时考虑预期进球吻合度"] + reasoning_chain + calibration_notes,
        )


class ZJQStrategy(BasePlayStrategy):
    """总进球专属策略"""

    def __init__(self):
        super().__init__(PlayType.ZJQ)

    def _get_default_config(self) -> PlayStrategyConfig:
        return PlayStrategyConfig(
            play_type=PlayType.ZJQ,
            prob_weight=0.28,
            ev_weight=0.43,
            odds_weight=0.19,
            value_weight=0.1,
            risk_level=PlayRiskLevel.MEDIUM,
            min_prob_threshold=0.11,
            max_odds_threshold=32.0,
            min_ev_threshold=0.8,
            max_recommendations=3,
            allow_double_chance=False,
            prefer_high_prob=False,
            parlay_suitability=0.65,  # 略提升适合度
            min_parlay_odds=2.8,
        )

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        总进球专属推理链

        在基类推理链基础上增加预期总进球区间分析
        """
        chain = super().generate_reasoning_chain(play_data, match_context, play_type_name)

        # ZJQ专属：预期总进球区间分析
        total_exp = self._safe_get(match_context, "total_expected_goals", 2.5, "总进球-预期总进球")
        probs = play_data.get("probabilities", {})

        # 计算大小球概率
        small_ball_prob = sum(probs.get(str(i), 0) for i in range(0, 3))
        big_ball_prob = sum(probs.get(str(i), 0) for i in range(3, 8)) + probs.get("7+", 0)

        if total_exp <= 2.0:
            chain.append(
                f"6. 进球预期：预期总进球{total_exp:.1f}球，偏低，"
                f"小球（0-2球）概率{small_ball_prob * 100:.1f}%，"
                f"大球（3+球）概率{big_ball_prob * 100:.1f}%，建议关注小球方向"
            )
        elif total_exp <= 2.5:
            chain.append(
                f"6. 进球预期：预期总进球{total_exp:.1f}球，中等偏低，"
                f"小球（0-2球）概率{small_ball_prob * 100:.1f}%，"
                f"大球（3+球）概率{big_ball_prob * 100:.1f}%，大小球分布较为均衡"
            )
        elif total_exp <= 3.0:
            chain.append(
                f"6. 进球预期：预期总进球{total_exp:.1f}球，中等偏高，"
                f"小球（0-2球）概率{small_ball_prob * 100:.1f}%，"
                f"大球（3+球）概率{big_ball_prob * 100:.1f}%，建议关注大球方向"
            )
        else:
            chain.append(
                f"6. 进球预期：预期总进球{total_exp:.1f}球，偏高，"
                f"小球（0-2球）概率{small_ball_prob * 100:.1f}%，"
                f"大球（3+球）概率{big_ball_prob * 100:.1f}%，大球方向概率明显占优"
            )

        # 找出概率最高的进球数
        if probs:
            sorted_goals = sorted(
                [(k, v) for k, v in probs.items() if k != "7+"],
                key=lambda x: x[1], reverse=True
            )
            if sorted_goals:
                top_goal = sorted_goals[0]
                chain.append(
                    f"7. 最可能进球数：模型预测最可能出现{top_goal[0]}球"
                    f"（概率{top_goal[1] * 100:.1f}%），"
                    f"建议重点关注{top_goal[0]}球及相邻选项"
                )

        return chain

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        play_data = self._normalize_play_data(play_data)
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        total_exp = match_context.get("total_expected_goals", 2.5)

        scored_recs = []
        for rec in recs:
            score = self.score_selection(rec)

            # 总进球专属调整：接近预期的选项加分
            selection = rec["selection"]
            try:
                if selection == "7+":
                    goal_num = 7
                else:
                    goal_num = int(selection)

                distance = abs(goal_num - total_exp)
                if distance <= 1.0:
                    score *= 1.15
                elif distance <= 2.0:
                    score *= 1.05
            except (ValueError, TypeError):
                pass

            rec["strategy_score"] = score
            scored_recs.append(rec)

        scored_recs.sort(key=lambda x: x["strategy_score"], reverse=True)

        best_selection = None
        if scored_recs:
            best_rec = scored_recs[0]
            best_selection = {
                "selection": best_rec["selection"],
                "probability": best_rec["probability"],
                "odds": best_rec.get("odds", best_rec.get("estimated_odds", 0)),
                "ev": best_rec["expected_value"],
            }

        # 计算趋势
        small_ball_prob = sum(probs.get(str(i), 0) for i in range(0, 3))
        big_ball_prob = sum(probs.get(str(i), 0) for i in range(3, 8)) + probs.get("7+", 0)

        risk_assessment = self._compute_dynamic_risk(match_context)
        risk_assessment["small_ball_prob"] = round(small_ball_prob, 3)
        risk_assessment["big_ball_prob"] = round(big_ball_prob, 3)
        risk_assessment.setdefault("notes", []).insert(0, f"预期总进球{total_exp:.1f}")

        # 生成推理链
        reasoning_chain = self.generate_reasoning_chain(
            play_data, match_context, "总进球"
        )

        # ========== S4-1: 校准感知逻辑 ==========
        calibration_bonus = 0.0
        calibration_notes = []

        if play_data.get("_calibrated"):
            calibration_bonus = 0.05  # 历史校准可信度+5%
            calibration_notes.append("历史校准增强")
            # 对已评分的推荐应用校准加分
            for rec in scored_recs:
                rec["strategy_score"] = rec.get("strategy_score", 0) * (1 + calibration_bonus)

        # RQSPF盘口合理性分析
        handicap_analysis = play_data.get("_handicap_analysis")
        if handicap_analysis:
            if not handicap_analysis.get("is_reasonable", True):
                # 盘口异常，降权
                handicap_penalty = 0.10
                for rec in scored_recs:
                    rec["strategy_score"] = rec.get("strategy_score", 0) * (1 - handicap_penalty)
                calibration_notes.append(f"盘口异常: {handicap_analysis.get('interpretation', '')}")

        # 大小球偏差分析（ZJQ核心校准）
        ou_analysis = play_data.get("_over_under_analysis")
        if ou_analysis:
            if ou_analysis.get("bias"):
                calibration_notes.append(f"大小球: {ou_analysis.get('interpretation', '')}")
            # 大小球偏差可能导致大小球概率调整
            bias_direction = ou_analysis.get("bias_direction")
            if bias_direction == "over" or bias_direction == "大":
                # 大球偏多，调整相关推荐
                for rec in scored_recs:
                    goal_num_str = rec.get("selection", "")
                    try:
                        if goal_num_str in ["3", "4", "5", "6", "7+"]:
                            rec["strategy_score"] = rec.get("strategy_score", 0) * 1.05
                    except (ValueError, TypeError):
                        pass
            elif bias_direction == "under" or bias_direction == "小":
                # 小球偏多，调整相关推荐
                for rec in scored_recs:
                    goal_num_str = rec.get("selection", "")
                    try:
                        if goal_num_str in ["0", "1", "2"]:
                            rec["strategy_score"] = rec.get("strategy_score", 0) * 1.05
                    except (ValueError, TypeError):
                        pass

        # 重新排序
        scored_recs.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)

        return PlayAnalysisResult(
            play_type=PlayType.ZJQ,
            recommendations=scored_recs[:self.config.max_recommendations],
            probabilities=probs,
            expected_values=play_data.get("expected_values", play_data.get("expected_value", {})),
            confidence=conf,
            best_selection=best_selection,
            strategy_score=scored_recs[0].get("strategy_score", 0) if scored_recs else 0,
            risk_assessment=risk_assessment,
            analysis_notes=["总进球策略：结合预期进球区间分析"] + reasoning_chain + calibration_notes,
        )


class BQCStrategy(BasePlayStrategy):
    """半全场专属策略"""

    def __init__(self):
        super().__init__(PlayType.BQC)

    def _get_default_config(self) -> PlayStrategyConfig:
        return PlayStrategyConfig(
            play_type=PlayType.BQC,
            prob_weight=0.25,
            ev_weight=0.45,
            odds_weight=0.2,
            value_weight=0.1,
            risk_level=PlayRiskLevel.HIGH,
            min_prob_threshold=0.07,
            max_odds_threshold=42.0,
            min_ev_threshold=0.78,
            max_recommendations=3,
            allow_double_chance=False,
            prefer_high_prob=False,
            parlay_suitability=0.55,  # 略提升适合度
            min_parlay_odds=3.8,
        )

    def generate_reasoning_chain(
        self, play_data: Dict, match_context: Dict, play_type_name: str
    ) -> List[str]:
        """
        半全场专属推理链

        在基类推理链基础上增加一致性vs逆转概率分析
        """
        chain = super().generate_reasoning_chain(play_data, match_context, play_type_name)

        # BQC专属：一致性结果 vs 逆转概率
        probs = play_data.get("probabilities", {})

        # 半场进球比例说明：基于经验数据，约45%的进球发生在上半场（HT_RATIO=0.45），
        # 该比例因联赛而异，例如意甲下半场进球占比通常更高，英超则相对均衡。
        chain.append(
            f"6. 半场模型：半全场计算基于经验数据（约45%进球在上半场），"
            f"该比例因联赛风格而异（如意甲下半场进球占比更高），实际比赛中可能存在偏差"
        )

        consistent_prob = sum(
            probs.get(key, 0) for key in ["胜-胜", "平-平", "负-负"]
        )
        comeback_prob = sum(
            probs.get(key, 0) for key in ["胜-负", "负-胜"]
        )
        half_change_prob = sum(
            probs.get(key, 0) for key in ["胜-平", "平-胜", "负-平", "平-负"]
        )

        total = consistent_prob + comeback_prob + half_change_prob
        if total > 0:
            consistent_pct = consistent_prob / total * 100
            comeback_pct = comeback_prob / total * 100
            half_change_pct = half_change_prob / total * 100

            chain.append(
                f"7. 一致性分析：半全场一致结果（胜-胜/平-平/负-负）概率"
                f"{consistent_pct:.1f}%，半场转折概率{half_change_pct:.1f}%，"
                f"完全逆转概率{comeback_pct:.1f}%"
            )

            if consistent_pct > 55:
                chain.append(
                    f"8. 趋势判断：一致性结果概率较高（{consistent_pct:.1f}%），"
                    f"比赛走势不易发生转折，建议优先选择一致性结果（如胜-胜、平-平）"
                )
            elif consistent_pct > 45:
                chain.append(
                    f"8. 趋势判断：一致性结果与转折结果概率接近"
                    f"（一致{consistent_pct:.1f}% vs 转折{100 - consistent_pct:.1f}%），"
                    f"比赛走势不确定性较大，可适当博取半场转折"
                )
            else:
                chain.append(
                    f"8. 趋势判断：转折概率较高（{100 - consistent_pct:.1f}%），"
                    f"比赛可能出现半场与全场结果不一致的情况，"
                    f"半场转折选项（如胜-平、平-胜）值得关注"
                )

            # 逆转风险提示
            if comeback_pct > 15:
                chain.append(
                    f"9. 逆转风险：完全逆转概率{comeback_pct:.1f}%偏高，"
                    f"需警惕下半场逆转风险，避免过度押注一致性结果"
                )

        return chain

    def analyze(self, play_data: Union[Dict[str, Any], PlayProbabilityResult],
                match_context: Dict[str, Any]) -> PlayAnalysisResult:
        play_data = self._normalize_play_data(play_data)
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        scored_recs = []
        for rec in recs:
            score = self.score_selection(rec)

            # 半全场专属调整：一致性结果加分
            selection = rec["selection"]
            if selection in ["胜-胜", "平-平", "负-负"]:
                score *= 1.1  # 一致结果稍微加分（更可预测）
            elif selection in ["胜-负", "负-胜"]:
                score *= 0.95  # 逆转结果稍微降分

            rec["strategy_score"] = score
            scored_recs.append(rec)

        scored_recs.sort(key=lambda x: x["strategy_score"], reverse=True)

        best_selection = None
        if scored_recs:
            best_rec = scored_recs[0]
            best_selection = {
                "selection": best_rec["selection"],
                "probability": best_rec["probability"],
                "odds": best_rec.get("odds", best_rec.get("estimated_odds", 0)),
                "ev": best_rec["expected_value"],
            }

        # 一致性概率
        consistent_prob = sum(
            probs.get(key, 0) for key in ["胜-胜", "平-平", "负-负"]
        )

        risk_assessment = self._compute_dynamic_risk(match_context)
        risk_assessment["consistent_result_prob"] = round(consistent_prob, 3)
        risk_assessment.setdefault("notes", []).insert(0, "半全场玩法关注半场到全场的趋势")

        # 生成推理链
        reasoning_chain = self.generate_reasoning_chain(
            play_data, match_context, "半全场"
        )

        # ========== S4-1: 校准感知逻辑 ==========
        calibration_bonus = 0.0
        calibration_notes = []

        if play_data.get("_calibrated"):
            calibration_bonus = 0.05  # 历史校准可信度+5%
            calibration_notes.append("历史校准增强")
            # 对已评分的推荐应用校准加分
            for rec in scored_recs:
                rec["strategy_score"] = rec.get("strategy_score", 0) * (1 + calibration_bonus)

        # RQSPF盘口合理性分析
        handicap_analysis = play_data.get("_handicap_analysis")
        if handicap_analysis:
            if not handicap_analysis.get("is_reasonable", True):
                # 盘口异常，降权
                handicap_penalty = 0.10
                for rec in scored_recs:
                    rec["strategy_score"] = rec.get("strategy_score", 0) * (1 - handicap_penalty)
                calibration_notes.append(f"盘口异常: {handicap_analysis.get('interpretation', '')}")

        # 大小球偏差（ZJQ相关检查）
        if "ZJQ" in str(self.play_type) or self.play_type == PlayType.ZJQ:
            ou_analysis = play_data.get("_over_under_analysis")
            if ou_analysis and ou_analysis.get("bias"):
                calibration_notes.append(f"大小球: {ou_analysis.get('interpretation', '')}")

        # 重新排序
        scored_recs.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)

        return PlayAnalysisResult(
            play_type=PlayType.BQC,
            recommendations=scored_recs[:self.config.max_recommendations],
            probabilities=probs,
            expected_values=play_data.get("expected_values", play_data.get("expected_value", {})),
            confidence=conf,
            best_selection=best_selection,
            strategy_score=scored_recs[0].get("strategy_score", 0) if scored_recs else 0,
            risk_assessment=risk_assessment,
            analysis_notes=["半全场策略：趋势一致性优先"] + reasoning_chain + calibration_notes,
        )


# ============================================================
# 策略工厂
# ============================================================

class PlayStrategyFactory:
    """玩法策略工厂"""

    _strategies: Dict[PlayType, BasePlayStrategy] = {}

    @classmethod
    def get_strategy(cls, play_type: PlayType) -> BasePlayStrategy:
        """获取玩法策略"""
        if play_type not in cls._strategies:
            if play_type == PlayType.SPF:
                cls._strategies[play_type] = SPFStrategy()
            elif play_type == PlayType.RQSPF:
                cls._strategies[play_type] = RQSPFStrategy()
            elif play_type == PlayType.BF:
                cls._strategies[play_type] = BFStrategy()
            elif play_type == PlayType.ZJQ:
                cls._strategies[play_type] = ZJQStrategy()
            elif play_type == PlayType.BQC:
                cls._strategies[play_type] = BQCStrategy()
            else:
                raise ValueError(f"未知的玩法类型: {play_type}")

        return cls._strategies[play_type]

    @classmethod
    def assess_diversification(cls, selections: List[Dict]) -> Dict[str, Any]:
        """评估投注组合的多样性"""
        if not _HAS_RISK_DIVERSIFIER:
            return {"diversity_score": 0.5, "note": "风险分散模块未加载"}
        try:
            diversifier = RiskDiversifier()
            return diversifier.calculate_diversification(selections)
        except Exception:
            return {"diversity_score": 0.5, "note": "多样性评估失败"}

    @classmethod
    def analyze_all_plays(cls, plays_data: Dict[str, Union[Dict, PlayProbabilityResult]],
                         match_context: Dict[str, Any]) -> Dict[PlayType, PlayAnalysisResult]:
        """分析所有玩法（兼容多种输入格式）

        Args:
            plays_data: 玩法数据字典，支持两种值类型：
                        - PlayProbabilityResult: 来自 PlayAnalyzer 的概率分析结果
                        - Dict: 向后兼容的字典格式
            match_context: 比赛上下文信息
        """
        results = {}

        # 支持两种格式：key 为 "SPF" 或 "胜平负"
        for play_key, play_data in plays_data.items():
            play_type = play_type_from_str(play_key)
            if play_type:
                strategy = cls.get_strategy(play_type)
                result = strategy.analyze(play_data, match_context)
                results[play_type] = result
            else:
                logger.warning(f"跳过未知玩法类型: {play_key}")

        return results
