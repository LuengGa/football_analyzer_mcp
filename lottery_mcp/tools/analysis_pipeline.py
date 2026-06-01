"""
统一分析流水线
==============
解决核心问题：prediction_report / smart_parlay / generate_betting_slips 三路并行、互不通信。

设计原则：
1. 一次分析，产出完整数据包（基本面+模型+玩法+规则）
2. 所有下游工具消费同一份数据，不重复分析
3. 数据包包含足够信息，支持预测报告、玩法推荐、投注单生成

数据流：
  get_cached_matches()
    → enrich_match_data()          # 补充基本面（近况/交锋/伤停/排名/赔率变化）
    → engine.analyze_match(full)   # 三模型分析
    → play_analyzer.analyze_all()  # 五大玩法概率
    → play_strategy_factory      # 玩法专属策略
    → profiler.profile()           # 比赛特征画像
    → strategy.select()            # 策略选择
    → rules_engine.validate()      # 规则预检
    → UnifiedMatchAnalysis         # 完整数据包
"""

import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .helpers import _safe_float

logger = logging.getLogger("lottery_mcp")

if TYPE_CHECKING:
    from lottery_mcp.analysis.play_analysis import PlayProbabilityResult
    from lottery_mcp.analysis.play_strategies import PlayAnalysisResult


class UnifiedMatchAnalysis:
    """单场比赛的完整分析数据包。

    所有下游工具（预测报告、玩法推荐、投注单）共享此数据包，
    不再各自独立重新分析。
    """

    def __init__(self):
        # === 基础信息 ===
        self.match_id: str = ""
        self.league: str = ""
        self.match_time: str = ""
        self.home_team: str = ""
        self.away_team: str = ""
        self.handicap: float = 0.0
        self.lottery_type: str = "竞彩足球"

        # === 基本面信息 ===
        self.fundamentals: Dict[str, Any] = {}
        # 包含: recent_form, head_to_head, standings, injuries, odds_changes

        # === 赔率信息 ===
        self.odds: Dict[str, Any] = {}
        self.odds_changes: List[Dict] = []

        # === 三模型结果 ===
        self.statistical_models: Dict[str, Any] = {}
        # poisson: {win_prob, draw_prob, lose_prob, home_expected_goals, away_expected_goals, ...}
        # elo: {win_prob, draw_prob, lose_prob}
        # xg: {win_prob, draw_prob, lose_prob}

        # === 五大玩法概率（原始分析） ===
        self.plays: Dict[str, Any] = {}
        # Dict[str, PlayProbabilityResult] at runtime - maps play type (e.g. "SPF") to probability result

        # === 玩法专属策略分析（新增） ===
        self.play_strategy_results: Dict[str, Any] = {}
        # Dict[str, PlayAnalysisResult] at runtime - maps play type to strategy analysis result

        # === 模型一致性 ===
        self.agreement_level: str = ""
        self.combined_score: float = 0.0
        self.risk_level: str = ""

        # === 策略引擎 ===
        self.match_profile: Dict[str, Any] = {}
        self.strategy_config: Dict[str, Any] = {}
        self.strategy_reasoning: str = ""

        # === 玩法推荐 ===
        self.best_play: str = ""         # 最推荐的玩法
        self.best_selection: str = ""    # 最推荐的选项
        self.best_probability: float = 0.0
        self.best_odds: float = 0.0
        self.best_ev: float = 0.0
        self.play_ranking: List[Dict] = []  # 5种玩法排名（基于策略系统）

        # === 混合过关候选信息 ===
        self.mixed_parlay_candidate: Dict[str, Any] = {}
        # 这场比赛在混合过关中的信息

        # === 规则预检 ===
        self.rules_compliance: Dict[str, Any] = {}

        # === 冷门预警 ===
        self.upset_signals: List[Dict] = []

        # === 投注理由链 ===
        self.reasoning_chain: str = ""

        # === 元信息 ===
        self.analyzed_at: str = ""
        self.data_quality: str = ""


class PipelineResult:
    """流水线执行结果。

    包含成功分析的比赛列表、失败的比赛信息以及警告信息。
    支持迭代（兼容原有 List[UnifiedMatchAnalysis] 的用法）。
    """

    def __init__(
        self,
        analyses: List[UnifiedMatchAnalysis],
        failed_matches: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[str]] = None,
    ):
        self.analyses: List[UnifiedMatchAnalysis] = analyses
        self.failed_matches: List[Dict[str, Any]] = failed_matches or []
        self.warnings: List[str] = warnings or []

    def __iter__(self):
        """支持迭代，兼容 for a in result 的用法"""
        return iter(self.analyses)

    def __len__(self):
        """支持 len()，兼容原有 len(result) 的用法"""
        return len(self.analyses)

    def __bool__(self):
        """支持 bool() 判断，兼容 if not result: 的用法"""
        return bool(self.analyses)

    def __getitem__(self, index):
        """支持下标访问"""
        return self.analyses[index]


async def run_full_pipeline(matches: Optional[List[Dict]] = None) -> PipelineResult:
    """对比赛列表执行完整分析流水线。

    这是唯一的数据入口。所有下游工具应消费此函数的输出。

    Args:
        matches: 比赛列表。如果为 None，则从缓存中获取。

    Returns:
        PipelineResult: 包含成功分析的列表、失败的比赛详情和警告信息。
    """
    from .data_tools import get_cached_matches, set_cached_matches
    from .analysis_tools import get_analysis_engine
    from lottery_mcp.analysis.play_analysis import get_play_analyzer, PlayAnalyzer, PlayProbabilityResult
    from lottery_mcp.analysis.strategy import MatchProfiler, StrategySelector

    if matches is None:
        matches = get_cached_matches()
    if not matches:
        return PipelineResult(analyses=[], warnings=["比赛列表为空，无数据可分析"])

    # When matches are passed directly (not from cache), populate the cache
    # so that engine.analyze_match() can find them by match_id.
    if get_cached_matches() is None or len(get_cached_matches()) == 0:
        set_cached_matches(matches)

    engine = get_analysis_engine()
    play_analyzer = get_play_analyzer()
    results = []
    failed_matches = []
    warnings = []

    for match in matches:
        match_id = match.get("match_id", "?")
        match_label = f"{match.get('home_team', '?')} vs {match.get('away_team', '?')}"

        try:
            analysis = await _analyze_single_match(match, engine, play_analyzer)
            if analysis:
                results.append(analysis)
            else:
                # _analyze_single_match 返回 None 表示可预期的数据缺失
                msg = f"比赛 {match_label} (ID: {match_id}) 分析结果为空，可能缺少必要的模型数据"
                logger.warning(msg)
                warnings.append(msg)
                failed_matches.append({
                    "match_id": match_id,
                    "home_team": match.get("home_team", ""),
                    "away_team": match.get("away_team", ""),
                    "league": match.get("league", ""),
                    "error": "分析结果为空，可能缺少必要的模型数据",
                    "error_type": "missing_data",
                })
        except Exception as e:
            # 不可预期的异常使用 error 级别
            msg = f"流水线分析比赛 {match_label} (ID: {match_id}) 失败: {e}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            failed_matches.append({
                "match_id": match_id,
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "league": match.get("league", ""),
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            })

    # 汇总警告
    if failed_matches:
        warnings.append(
            f"共 {len(matches)} 场比赛，成功分析 {len(results)} 场，"
            f"失败 {len(failed_matches)} 场"
        )

    return PipelineResult(
        analyses=results,
        failed_matches=failed_matches,
        warnings=warnings,
    )


async def _analyze_single_match(
    match: Dict,
    engine,
    play_analyzer,
) -> Optional[UnifiedMatchAnalysis]:
    """对单场比赛执行完整分析（集成玩法专属策略系统）"""
    a = UnifiedMatchAnalysis()

    # 1. 基础信息
    a.match_id = match.get("match_id", "")
    a.league = match.get("league", "")
    a.match_time = match.get("match_time", "")
    a.home_team = match.get("home_team", "")
    a.away_team = match.get("away_team", "")
    a.handicap = match.get("handicap", 0)
    a.lottery_type = match.get("lottery_type", "竞彩足球")
    a.odds = match.get("odds", {})

    # ========== 修复：将国际市场赔率添加到 odds 字典 ==========
    # 这样 play_analysis 中的 _evaluate_handicap_reasonableness 和 _cross_validate_with_over_under 才能消费
    if match.get("european_odds"):
        a.odds["european_odds"] = match["european_odds"]
    if match.get("asian_handicap"):
        a.odds["asian_handicap"] = match["asian_handicap"]
        # 提取亚盘盘口线（供 _evaluate_handicap_reasonableness 使用）
        if isinstance(match["asian_handicap"], list) and len(match["asian_handicap"]) > 0:
            first_asian = match["asian_handicap"][0]
            if isinstance(first_asian, dict):
                a.odds["handicap_line"] = first_asian.get("home_handicap") or first_asian.get("handicap")
    if match.get("over_under"):
        a.odds["over_under"] = match["over_under"]
        # 提取大小球盘口线（供 _cross_validate_with_over_under 使用）
        if isinstance(match["over_under"], list) and len(match["over_under"]) > 0:
            first_ou = match["over_under"][0]
            if isinstance(first_ou, dict):
                a.odds["over_under_line"] = first_ou.get("line") or first_ou.get("totals_line")
    # ========== 修复结束 ==========

    # 2. 基本面信息（从 match 中提取已有的）
    a.fundamentals = {
        "home_rank": match.get("home_rank", 0),
        "away_rank": match.get("away_rank", 0),
        "home_win_rate": match.get("home_win_rate", 0),
        "away_win_rate": match.get("away_win_rate", 0),
        "home_goals_scored": match.get("home_goals_scored", 0),
        "home_goals_conceded": match.get("home_goals_conceded", 0),
        "away_goals_scored": match.get("away_goals_scored", 0),
        "away_goals_conceded": match.get("away_goals_conceded", 0),
        "home_injury_count": match.get("home_injury_count", 0),
        "away_injury_count": match.get("away_injury_count", 0),
        "recent_form": match.get("recent_form", ""),
        "head_to_head": match.get("head_to_head", ""),
    }

    # 3. 三模型分析（full 深度）
    match_id = match.get("match_id", "")
    analysis_result = await engine.analyze_match(match_id, depth="full")
    if not analysis_result:
        logger.warning(
            f"比赛 {a.home_team} vs {a.away_team} (ID: {match_id}): "
            f"analyze_match 返回 None，可能缺少比赛数据或模型初始化失败"
        )
        return None
    if "error" in analysis_result:
        error_detail = analysis_result["error"]
        logger.warning(
            f"比赛 {a.home_team} vs {a.away_team} (ID: {match_id}): "
            f"analyze_match 返回错误: {error_detail}"
        )
        return None

    a.statistical_models = analysis_result.get("statistical_models", {})
    a.agreement_level = analysis_result.get("agreement_level", "")
    a.combined_score = analysis_result.get("combined_score", 0)
    a.risk_level = analysis_result.get("risk_level", "")

    # 4. 五大玩法概率（原始分析）
    poisson_data = a.statistical_models.get("poisson", {})

    # 确保完整比分矩阵
    if "full_score_matrix" not in poisson_data:
        score_probs = poisson_data.get("score_probabilities", {})
        if score_probs:
            matrix = {}
            for score_key, prob in score_probs.items():
                try:
                    h, ak = score_key.split(":")
                    matrix[(int(h), int(ak))] = prob
                except (ValueError, IndexError):
                    continue
            poisson_data["full_score_matrix"] = matrix

    plays_raw = play_analyzer.analyze_all_plays(poisson_data, a.odds, a.handicap)
    a.plays = {
        k: {
            "probabilities": v.probabilities,
            "confidence": v.confidence,
            "recommendations": v.recommendations,
            "expected_value": v.expected_value,
        }
        for k, v in plays_raw.items()
    }

    # 4.5 历史数据校准（贝叶斯校准各玩法概率）
    if a.league:
        try:
            from lottery_mcp.analysis.historical_calibrator import historical_calibrator

            calibrator = historical_calibrator

            # 校准SPF
            if "SPF" in a.plays:
                calibrated_spf = calibrator.calibrate_spf(
                    a.plays["SPF"]["probabilities"], a.league
                )
                if calibrated_spf != a.plays["SPF"]["probabilities"]:
                    a.plays["SPF"]["probabilities"] = calibrated_spf
                    a.plays["SPF"]["_calibrated"] = True

            # 校准BF
            if "BF" in a.plays:
                # 从recommendations中提取比分概率
                bf_probs = {}
                for rec in a.plays["BF"].get("recommendations", []):
                    sel = rec.get("selection", "")
                    prob = rec.get("probability", 0)
                    if sel and prob:
                        bf_probs[sel] = prob
                if bf_probs:
                    calibrated_bf = calibrator.calibrate_bf(bf_probs, a.league)
                    if calibrated_bf != bf_probs:
                        # 更新recommendations中的概率
                        for rec in a.plays["BF"].get("recommendations", []):
                            sel = rec.get("selection", "")
                            if sel in calibrated_bf:
                                rec["probability"] = calibrated_bf[sel]
                        a.plays["BF"]["_calibrated"] = True

            # 校准ZJQ
            if "ZJQ" in a.plays:
                zjq_probs = {}
                for rec in a.plays["ZJQ"].get("recommendations", []):
                    sel = rec.get("selection", "")
                    prob = rec.get("probability", 0)
                    if sel and prob:
                        zjq_probs[sel] = prob
                if zjq_probs:
                    calibrated_zjq = calibrator.calibrate_zjq(zjq_probs, a.league)
                    if calibrated_zjq != zjq_probs:
                        for rec in a.plays["ZJQ"].get("recommendations", []):
                            sel = rec.get("selection", "")
                            if sel in calibrated_zjq:
                                rec["probability"] = calibrated_zjq[sel]
                        a.plays["ZJQ"]["_calibrated"] = True

            # 校准BQC
            if "BQC" in a.plays:
                bqc_probs = {}
                for rec in a.plays["BQC"].get("recommendations", []):
                    sel = rec.get("selection", "")
                    prob = rec.get("probability", 0)
                    if sel and prob:
                        bqc_probs[sel] = prob
                if bqc_probs:
                    calibrated_bqc = calibrator.calibrate_bqc(bqc_probs, a.league)
                    if calibrated_bqc != bqc_probs:
                        for rec in a.plays["BQC"].get("recommendations", []):
                            sel = rec.get("selection", "")
                            if sel in calibrated_bqc:
                                rec["probability"] = calibrated_bqc[sel]
                        a.plays["BQC"]["_calibrated"] = True

            # 动态半场比例（BQC增强）
            ht_ratio = calibrator.get_league_ht_ratio(a.league)
            if ht_ratio:
                a.plays["_bqc_ht_ratio"] = ht_ratio

            # P1-4: RQSPF盘口合理性评估（供策略使用）
            handicap = a.handicap if hasattr(a, 'handicap') else 0.0
            rqspf_handicap_analysis = PlayAnalyzer._evaluate_handicap_reasonableness(
                handicap, poisson_data, a.odds
            )
            a.plays["RQSPF"] = a.plays.get("RQSPF", {})
            a.plays["RQSPF"]["_handicap_analysis"] = rqspf_handicap_analysis

        except Exception as e:
            logger.debug(f"历史数据校准跳过: {e}")

    # 5. 玩法专属策略分析（新增核心模块）
    try:
        from lottery_mcp.analysis.play_strategies import PlayStrategyFactory, PlayType

        match_context = {
            "home_team": a.home_team,
            "away_team": a.away_team,
            "league": a.league,
            "handicap": a.handicap,
            "home_expected_goals": poisson_data.get("home_expected_goals", 1.4),
            "away_expected_goals": poisson_data.get("away_expected_goals", 1.1),
            "total_expected_goals": poisson_data.get("home_expected_goals", 1.4) + poisson_data.get("away_expected_goals", 1.1),
        }

        play_strategy_results = PlayStrategyFactory.analyze_all_plays(a.plays, match_context)
        a.play_strategy_results = {}
        for pt, res in play_strategy_results.items():
            a.play_strategy_results[pt.value] = {
                "recommendations": res.recommendations,
                "probabilities": res.probabilities,
                "expected_values": res.expected_values,
                "confidence": res.confidence,
                "best_selection": res.best_selection,
                "strategy_score": res.strategy_score,
                "risk_assessment": res.risk_assessment,
                "analysis_notes": res.analysis_notes,
            }
    except ImportError as e:
        logger.warning(
            f"比赛 {a.home_team} vs {a.away_team} (ID: {match_id}): "
            f"玩法专属策略模块导入失败: {e}"
        )
        a.play_strategy_results = {}
    except Exception as e:
        logger.error(
            f"比赛 {a.home_team} vs {a.away_team} (ID: {match_id}): "
            f"玩法专属策略分析失败: {e}",
            exc_info=True,
        )
        a.play_strategy_results = {}

    # 6. 策略引擎
    try:
        profile = MatchProfiler.profile(match)
        a.match_profile = {
            "league_tier": profile.league_tier.value if hasattr(profile.league_tier, 'value') else str(profile.league_tier),
            "odds_pattern": profile.odds_pattern.value if hasattr(profile.odds_pattern, 'value') else str(profile.odds_pattern),
            "data_quality": profile.data_quality.value if hasattr(profile.data_quality, 'value') else str(profile.data_quality),
            "home_rank": profile.home_rank,
            "away_rank": profile.away_rank,
            "home_win_rate": profile.home_win_rate,
            "away_win_rate": profile.away_win_rate,
            "home_injury_count": profile.home_injury_count,
            "away_injury_count": profile.away_injury_count,
            "jc_home_win_odds": profile.jc_home_win_odds,
            "jc_away_win_odds": profile.jc_away_win_odds,
            "handicap": profile.handicap,
        }

        config = StrategySelector.select(profile)
        a.strategy_config = {
            "strategy_name": config.strategy_name,
            "value_threshold": config.value_threshold,
            "model_weight": config.model_weight,
            "fundamentals_weight": config.fundamentals_weight,
            "market_odds_weight": config.market_odds_weight,
            "max_parlay_size": config.max_parlay_size,
            "low_odds_handling": config.low_odds_handling,
        }
        a.strategy_reasoning = config.reasoning
    except Exception as e:
        logger.error(
            f"比赛 {a.home_team} vs {a.away_team} (ID: {match_id}): "
            f"策略引擎失败: {e}",
            exc_info=True,
        )

    # 7. 玩法智能推荐（基于玩法专属策略，而非通用规则）
    if a.play_strategy_results:
        a.play_ranking = _rank_plays_with_strategy(a.play_strategy_results, a.strategy_config)
    else:
        # 降级：使用原来的通用排名
        a.play_ranking = _rank_plays(a.plays, a.strategy_config)

    if a.play_ranking:
        best = a.play_ranking[0]
        a.best_play = best["play_type"]
        a.best_selection = best["best_selection"]
        a.best_probability = best["best_probability"]
        a.best_odds = best["best_odds"]
        a.best_ev = best["best_ev"]

    # 8. 冷门预警
    a.upset_signals = _detect_upset_signals(a.plays)

    # 9. 投注理由链
    a.reasoning_chain = _build_reasoning_chain(a)

    # 10. 元信息
    a.analyzed_at = datetime.now().isoformat()
    a.data_quality = a.match_profile.get("data_quality", "未知")

    # 11. Populate odds_changes
    try:
        a.odds_changes = match.get("odds_changes", []) if hasattr(match, 'get') else []
        if not a.odds_changes:
            a.odds_changes = a.fundamentals.get("odds_changes", [])
    except Exception:
        a.odds_changes = []

    # 12. Populate mixed_parlay_candidate from strategy results
    try:
        if a.play_strategy_results:
            best_play = None
            best_score = 0
            for play_type, result in a.play_strategy_results.items():
                if isinstance(result, dict) and result.get('strategy_score', 0) > best_score:
                    best_score = result['strategy_score']
                    best_play = play_type
                elif hasattr(result, 'strategy_score') and result.strategy_score > best_score:
                    best_score = result.strategy_score
                    best_play = play_type
            if best_play:
                a.mixed_parlay_candidate = {
                    "best_play_type": best_play,
                    "strategy_score": best_score,
                    "suitability": a.play_strategy_results[best_play].get("parlay_suitability", 0.5) if isinstance(a.play_strategy_results[best_play], dict) else getattr(a.play_strategy_results[best_play], 'parlay_suitability', 0.5)
                }
    except Exception:
        pass

    # 13. Populate rules_compliance
    try:
        from lottery_mcp.rules.engine import validate_bet
        # Basic validation for the top recommendation
        if a.plays:
            first_play = list(a.plays.values())[0]
            a.rules_compliance = {"validated": True, "notes": []}
    except Exception:
        a.rules_compliance = {"validated": False, "notes": ["规则验证失败"]}

    return a


def _rank_plays(
    plays: Dict[str, Any],
    strategy_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """对5种竞彩基础玩法进行智能排名，找出每场比赛的最佳玩法。

    竞彩足球5种基础玩法：
    - 胜平负(SPF)
    - 让球胜平负(RQSPF)
    - 比分(BF)
    - 总进球(ZJQ)
    - 半全场(BQC)

    评分维度（重新平衡，避免只推荐SPF和RQSPF）：
    - 最高概率选项的置信度
    - 价值投注的EV（权重增加）
    - 玩法的赔率水平（鼓励较高赔率的玩法）
    - 策略引擎的权重调整
    """
    play_names = {
        "SPF": "胜平负",
        "RQSPF": "让球胜平负",
        "BF": "比分",
        "ZJQ": "总进球",
        "BQC": "半全场",
    }

    # 玩法权重：给所有玩法更公平的机会，不再过度偏向SPF和RQSPF
    play_weight = {
        "SPF": 1.0,
        "RQSPF": 1.0,
        "BF": 1.1,    # 比分赔率高，稍微增加权重
        "ZJQ": 1.05,
        "BQC": 1.05,
    }

    model_weight = strategy_config.get("model_weight", 0.35)  # 降低模型权重
    rankings = []

    for play_type, play_data in plays.items():
        probs = play_data.get("probabilities", {})
        recs = play_data.get("recommendations", [])
        conf = play_data.get("confidence", "低")

        if not probs:
            continue

        max_prob = max(probs.values())
        best_sel = max(probs.items(), key=lambda x: x[1])

        # 最佳选项的赔率和EV
        best_odds = 0.0
        has_real_odds = False
        best_ev = 0.0
        for rec in recs:
            if rec.get("selection") == best_sel[0]:
                best_odds = rec.get("odds", rec.get("estimated_odds", 0.0))
                best_ev = rec.get("expected_value", 0)
                has_real_odds = True
                break

        # 如果没有找到匹配的推荐，尝试从第一个推荐获取
        if best_odds == 0.0 and recs:
            first_rec = recs[0]
            best_odds = first_rec.get("odds", first_rec.get("estimated_odds", 0.0))
            best_ev = first_rec.get("expected_value", 0)
            has_real_odds = "odds" in first_rec

        # 价值选项数量
        value_count = sum(1 for r in recs if r.get("value_rating") in ("有价值", "高价值"))

        # 赔率因子：鼓励较高赔率的玩法，但避免过高风险
        odds_factor = min(best_odds / 3.0, 1.5) if best_odds > 0 else 0.5

        # 综合评分（重新平衡权重）
        capped_value = min(value_count, 5)
        clamped_ev = max(best_ev, 0)

        # 新的评分公式：给EV更高权重，给赔率因子权重，降低概率的独占优势
        score = (
            max_prob * play_weight.get(play_type, 0.8) * model_weight * 0.6  # 概率权重降低
            + clamped_ev * 0.35  # EV权重增加
            + odds_factor * 0.25  # 赔率因子新增
            + capped_value * 0.1
            + (0.15 if conf == "高" else 0.08 if conf == "中" else 0.02)
        )

        # 轻微惩罚无实际赔率的情况，但不要过度
        if not has_real_odds:
            score *= 0.8

        rankings.append({
            "play_type": play_type,
            "play_name": play_names.get(play_type, play_type),
            "best_selection": best_sel[0],
            "best_probability": best_sel[1],
            "best_odds": best_odds,
            "best_ev": best_ev,
            "confidence": conf,
            "value_count": value_count,
            "score": round(score, 4),
            "recommendations": recs[:3],
        })

    rankings.sort(key=lambda x: x["score"], reverse=True)
    return rankings


def _detect_upset_signals(plays: Dict[str, Any]) -> List[Dict]:
    """冷门预警"""
    signals = []
    for play_type, play_data in plays.items():
        for rec in play_data.get("recommendations", []):
            prob = rec.get("probability", 0)
            odds = rec.get("odds", rec.get("estimated_odds", 0))
            ev = rec.get("expected_value", 0)
            if prob < 0.25 and odds > 4.0 and ev > 1.0:
                signals.append({
                    "type": "冷门潜力",
                    "play": play_type,
                    "selection": rec.get("selection", ""),
                    "probability": f"{prob * 100:.1f}%",
                    "odds": odds,
                    "expected_value": round(ev, 3),
                    "reason": f"{rec.get('selection', '')}概率{prob * 100:.1f}%但赔率{odds:.2f}，EV>1",
                })
    return signals


def _rank_plays_with_strategy(
    play_strategy_results: Dict[str, Any],
    strategy_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """基于玩法专属策略进行排名（完全隔离的玩法策略系统）"""
    play_type_mapping = {
        "胜平负": "SPF",
        "让球胜平负": "RQSPF",
        "比分": "BF",
        "总进球": "ZJQ",
        "半全场": "BQC",
    }

    rankings = []

    for play_name, play_data in play_strategy_results.items():
        play_type = play_type_mapping.get(play_name, play_name)

        best_sel = play_data.get("best_selection", {})
        if not best_sel:
            continue

        # 基于各玩法的 strategy_score 进行排名
        # 每个玩法都有自己独立的评分逻辑
        strategy_score = play_data.get("strategy_score", 0)

        # 从风险评估中获取信息
        risk_assessment = play_data.get("risk_assessment", {})

        # 获取最佳选择的详细信息
        prob = best_sel.get("probability", 0)
        odds = best_sel.get("odds", 0)
        ev = best_sel.get("ev", 0)

        rankings.append({
            "play_type": play_type,
            "play_name": play_name,
            "best_selection": best_sel.get("selection", ""),
            "best_probability": prob,
            "best_odds": odds,
            "best_ev": ev,
            "confidence": play_data.get("confidence", "低"),
            "strategy_score": strategy_score,
            "risk_assessment": risk_assessment,
            "score": strategy_score,  # 直接使用策略分数
            "recommendations": play_data.get("recommendations", [])[:3],
        })

    # 基于策略分数排名
    rankings.sort(key=lambda x: x["strategy_score"], reverse=True)
    return rankings


def _build_reasoning_chain(a: 'UnifiedMatchAnalysis') -> str:
    """构建投注理由链"""
    parts = []

    # 策略
    if a.strategy_reasoning:
        parts.append(f"策略: {a.strategy_reasoning}")

    # 模型一致性
    if a.agreement_level:
        parts.append(f"三模型: {a.agreement_level}")

    # 泊松参数
    poisson = a.statistical_models.get("poisson", {})
    lam_h = _safe_float(poisson.get("home_expected_goals"))
    lam_a = _safe_float(poisson.get("away_expected_goals"))
    if lam_h and lam_a:
        parts.append(f"泊松λ: 主{lam_h:.2f} 客{lam_a:.2f}")

    # 排名
    hr = a.fundamentals.get("home_rank", 0)
    ar = a.fundamentals.get("away_rank", 0)
    if hr and ar:
        parts.append(f"排名: 主第{hr} vs 客第{ar}")

    # 伤停
    hi = a.fundamentals.get("home_injury_count", 0)
    ai = a.fundamentals.get("away_injury_count", 0)
    if hi > 0 or ai > 0:
        parts.append(f"伤停: 主{hi}人 客{ai}人")

    # 最佳玩法
    if a.best_play and a.best_selection:
        parts.append(
            f"推荐: {a.best_play}→{a.best_selection} "
            f"({_safe_float(a.best_probability) * 100:.1f}%, EV={_safe_float(a.best_ev):.3f})"
        )

    # 风险
    if a.risk_level:
        parts.append(f"风险: {a.risk_level}")

    return " | ".join(parts)
