"""
混合过关专门优化模块
解决混合过关的系统性策略问题
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging
from itertools import combinations

logger = logging.getLogger("lottery_mcp")

from .models import PlayType, PLAY_MAX_LEGS, play_type_from_str
from .play_strategies import PlayStrategyFactory, PlayAnalysisResult


# 各玩法最大过关场次（从 models 统一导入）
# PLAY_MAX_LEGS 已在 models.py 中定义，此处通过导入使用


class ParlayStrategy(Enum):
    """混合过关策略类型"""
    CONSERVATIVE = "保守型"      # 低风险为主：主要SPF/RQSPF
    BALANCED = "平衡型"         # 均衡组合
    AGGRESSIVE = "激进型"         # 追求高赔率
    VALUE_FOCUSED = "价值型"      # 追求EV
    TREND_FOLLOWING = "趋势型"   # 趋势一致性


@dataclass
class ParlayCandidate:
    """混合过关候选选择"""
    match_id: str
    home_team: str
    away_team: str
    league: str
    play_type: PlayType
    selection: str
    odds: float
    probability: float
    ev: float
    strategy_score: float
    risk_level: str
    parlay_suitability: float
    analysis_notes: List[str] = field(default_factory=list)


@dataclass
class MixedParlayOptimizer:
    """混合过关优化器"""

    def __init__(self):
        self.strategy = ParlayStrategy.BALANCED
        self.max_matches = 8
        self.min_matches = 2
        self.play_diversity = True  # 玩法多样性
        self.league_diversity = True  # 联赛多样性
        self.risk_budget = 0.7  # 风险预算（0-1）

    def select_for_mixed_parlay(self,
                            match_analyses: List[Dict[str, Any]],
                            strategy: ParlayStrategy = ParlayStrategy.BALANCED) -> Dict[str, Any]:
        """
        为混合过关选择最优组合

        Args:
            match_analyses: 比赛分析结果列表
            strategy: 混合过关策略

        Returns:
            混合过关优化结果
        """
        self.strategy = strategy

        # 步骤1：筛选适合混合过关的候选
        candidates = self._filter_candidates(match_analyses)

        if not candidates:
            return {
                "success": False,
                "error": "没有适合混合过关的候选",
                "candidates_count": 0,
            }

        # 步骤2：根据策略选择组合
        parlay_plans = self._generate_parlay_plans(candidates)

        # 步骤3：优化和验证
        optimized_plans = self._optimize_plans(parlay_plans, candidates)

        return {
            "success": True,
            "strategy": strategy.value,
            "total_candidates": len(candidates),
            "parlay_plans": optimized_plans,
            "candidates": candidates[:10],  # 前10个候选
        }

    def _filter_candidates(self, match_analyses: List[Dict[str, Any]]) -> List[ParlayCandidate]:
        """筛选适合混合过关的候选（兼容多种输入格式）"""
        candidates = []

        for match_analysis in match_analyses:
            match_id = match_analysis.get("match_id", "")
            home_team = match_analysis.get("home_team", "")
            away_team = match_analysis.get("away_team", "")
            league = match_analysis.get("league", "")

            # 尝试获取各玩法的策略分析结果
            play_results = match_analysis.get("play_strategy_results", {})

            if play_results:
                # 有策略结果的情况
                for play_type_name, play_result in play_results.items():
                    play_type_enum = play_type_from_str(play_type_name)
                    if not play_type_enum:
                        continue

                    try:
                        # 获取最佳选择
                        best_sel = play_result.get("best_selection")
                        if not best_sel:
                            # 尝试从 recommendations 中获取
                            recs = play_result.get("recommendations", [])
                            if recs:
                                best_sel = recs[0]

                        if not best_sel:
                            continue

                        # 获取策略配置
                        strategy = PlayStrategyFactory.get_strategy(play_type_enum)
                        suitability = strategy.config.parlay_suitability

                        # 提取数值
                        odds = best_sel.get("odds", best_sel.get("estimated_odds", 0))
                        prob = best_sel.get("probability", 0)
                        ev = best_sel.get("expected_value", best_sel.get("ev", 0))
                        strategy_score = play_result.get("strategy_score", 0.5)

                        # 检查最低标准（放宽一些，避免过滤太多）
                        min_odds = strategy.config.min_parlay_odds * 0.8
                        if odds < min_odds:
                            continue

                        candidate = ParlayCandidate(
                            match_id=match_id,
                            home_team=home_team,
                            away_team=away_team,
                            league=league,
                            play_type=play_type_enum,
                            selection=best_sel.get("selection", ""),
                            odds=odds,
                            probability=prob,
                            ev=ev,
                            strategy_score=strategy_score,
                            risk_level=play_result.get("risk_assessment", {}).get("volatility", "中"),
                            parlay_suitability=suitability,
                            analysis_notes=play_result.get("analysis_notes", []),
                        )
                        candidates.append(candidate)
                    except Exception as e:
                        logger.debug(f"处理玩法 {play_type_name} 时出错: {e}")
                        continue
            else:
                # 降级：从 play_ranking 中获取
                play_ranking = match_analysis.get("play_ranking", [])
                if play_ranking:
                    for play_info in play_ranking[:3]:
                        play_type_name = play_info.get("play_type", "")
                        play_type_enum = name_to_type.get(play_type_name)
                        if not play_type_enum:
                            continue

                        try:
                            strategy = PlayStrategyFactory.get_strategy(play_type_enum)

                            odds = play_info.get("best_odds", 0)
                            prob = play_info.get("best_probability", 0)
                            ev = play_info.get("best_ev", 0)

                            # 默认适合度
                            suitability_map = {
                                PlayType.SPF: 0.9,
                                PlayType.RQSPF: 0.85,
                                PlayType.BF: 0.4,
                                PlayType.ZJQ: 0.6,
                                PlayType.BQC: 0.5,
                            }
                            suitability = suitability_map.get(play_type_enum, 0.5)

                            candidate = ParlayCandidate(
                                match_id=match_id,
                                home_team=home_team,
                                away_team=away_team,
                                league=league,
                                play_type=play_type_enum,
                                selection=play_info.get("best_selection", ""),
                                odds=odds,
                                probability=prob,
                                ev=ev,
                                strategy_score=play_info.get("score", play_info.get("strategy_score", 0.5)),
                                risk_level="中",
                                parlay_suitability=suitability,
                                analysis_notes=[],
                            )
                            candidates.append(candidate)
                        except Exception as e:
                            logger.debug(f"处理排名玩法时出错: {e}")
                            continue

        # 去重：每个(match_id, play_type)对只保留EV最高的候选
        # 允许同一比赛的不同玩法类型同时保留
        seen = {}
        for candidate in candidates:
            key = (candidate.match_id, candidate.play_type)
            if key not in seen or candidate.ev > seen[key].ev:
                seen[key] = candidate
        filtered_candidates = list(seen.values())

        # 排序候选
        filtered_candidates.sort(key=lambda x: x.ev * x.parlay_suitability, reverse=True)
        return filtered_candidates

    def _generate_parlay_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """生成混合过关方案"""
        plans = []

        # 根据策略生成不同方案
        if self.strategy == ParlayStrategy.CONSERVATIVE:
            plans.extend(self._generate_conservative_plans(candidates))
        elif self.strategy == ParlayStrategy.BALANCED:
            plans.extend(self._generate_balanced_plans(candidates))
        elif self.strategy == ParlayStrategy.AGGRESSIVE:
            plans.extend(self._generate_aggressive_plans(candidates))
        elif self.strategy == ParlayStrategy.VALUE_FOCUSED:
            plans.extend(self._generate_value_plans(candidates))
        elif self.strategy == ParlayStrategy.TREND_FOLLOWING:
            plans.extend(self._generate_trend_following_plans(candidates))

        return plans

    def _generate_conservative_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """生成保守型方案"""
        plans = []

        # 筛选低风险玩法
        low_risk_candidates = [
            c for c in candidates
            if c.play_type in [PlayType.SPF, PlayType.RQSPF]
        ]

        if not low_risk_candidates:
            return []

        # 生成2-4场组合
        max_n = min(4, len(low_risk_candidates))
        for k in range(2, max_n + 1):
            for combo in combinations(low_risk_candidates, k):
                # 检查联赛和玩法多样性
                diversity_score = self._check_diversity(combo)
                if diversity_score > 0.3:
                    plan = self._build_plan_from_combo(combo, "保守型")
                    plan["diversity_score"] = round(diversity_score, 4)
                    plans.append(plan)

        # 按组合EV和多样性排序，取前5
        plans.sort(key=lambda x: x["combined_ev"] * (0.7 + 0.3 * x.get("diversity_score", 0)), reverse=True)
        return plans[:5]

    def _generate_balanced_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """生成平衡型方案"""
        plans = []

        # 平衡选择：包含不同玩法类型
        play_type_groups = {}
        for c in candidates:
            pt = c.play_type
            if pt not in play_type_groups:
                play_type_groups[pt] = []
            play_type_groups[pt].append(c)

        # 尝试构建均衡组合
        for n in range(3, 5):
            if len(candidates) >= n:
                # 从不同玩法中各选一个
                selected = self._select_balanced_combo(candidates, n)
                if selected:
                    plan = self._build_plan_from_combo(selected, "平衡型")
                    plans.append(plan)

        # 生成一些标准组合
        for k in range(3, min(5, len(candidates) + 1)):
            for combo in combinations(candidates, k):
                diversity_score = self._check_diversity(combo)
                if diversity_score > 0.3:
                    plan = self._build_plan_from_combo(combo, "平衡型")
                    plan["diversity_score"] = round(diversity_score, 4)
                    plans.append(plan)

        plans.sort(key=lambda x: x["combined_ev"] * (1 - x["risk_score"]) * (0.7 + 0.3 * x.get("diversity_score", 0)), reverse=True)
        return plans[:8]

    def _generate_aggressive_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """生成激进型方案"""
        plans = []

        # 高赔率优先
        high_odds_candidates = sorted(candidates, key=lambda x: x.odds, reverse=True)

        for n in range(2, 4):
            for combo in combinations(high_odds_candidates[:10], n):
                plan = self._build_plan_from_combo(combo, "激进型")
                # 检测矛盾组合并添加警告
                contradictions = self._detect_contradictions([
                    {
                        "selection": c.selection,
                        "play_type": str(c.play_type),
                        "match_id": c.match_id,
                    }
                    for c in combo
                ])
                if contradictions:
                    plan["warnings"] = contradictions
                    plan["risk_score"] = min(1.0, plan.get("risk_score", 0.5) + 0.2)
                plans.append(plan)

        plans.sort(key=lambda x: x["combined_odds"], reverse=True)
        return plans[:5]

    def _generate_value_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """生成价值型方案"""
        plans = []

        # EV优先
        ev_sorted = sorted(candidates, key=lambda x: x.ev, reverse=True)

        for n in range(3, 5):
            for combo in combinations(ev_sorted[:12], n):
                plan = self._build_plan_from_combo(combo, "价值型")
                plans.append(plan)

        plans.sort(key=lambda x: x["combined_ev"], reverse=True)
        return plans[:6]

    def _generate_trend_following_plans(self, candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """
        生成趋势型方案
        
        策略逻辑：
        1. 寻找一致趋势：所有主队热门、所有客队热门、所有大球、所有小球等
        2. 优先选择符合主导趋势的选项
        3. 生成3-5场比赛组合
        """
        plans = []
        
        if not candidates:
            return []
        
        # 分析候选中的趋势
        trends = self._analyze_trends(candidates)
        
        # 按趋势强度排序
        sorted_trends = sorted(trends.items(), key=lambda x: len(x[1]), reverse=True)
        
        for trend_name, trend_candidates in sorted_trends:
            if len(trend_candidates) < 3:
                continue
            
            # 为该趋势生成组合方案
            for n in range(3, min(6, len(trend_candidates) + 1)):
                for combo in combinations(trend_candidates[:8], n):
                    # 检查联赛多样性
                    diversity_score = self._check_diversity(combo)
                    if diversity_score > 0.3:
                        plan = self._build_plan_from_combo(combo, f"趋势型-{trend_name}")
                        plan["diversity_score"] = round(diversity_score, 4)
                        plans.append(plan)
        
        # 按组合EV和多样性排序，取前8
        plans.sort(key=lambda x: x["combined_ev"] * (0.7 + 0.3 * x.get("diversity_score", 0)), reverse=True)
        return plans[:8]
    
    def _analyze_trends(self, candidates: List[ParlayCandidate]) -> Dict[str, List[ParlayCandidate]]:
        """
        分析候选中的趋势
        
        Returns:
            Dict[str, List[ParlayCandidate]]: 趋势名称 -> 符合该趋势的候选列表
        """
        trends = {
            "主队热门": [],      # 主胜选项
            "客队热门": [],      # 客胜选项
            "平局趋势": [],      # 平局选项
            "大球趋势": [],      # 总进球>=3
            "小球趋势": [],      # 总进球<3
            "高概率": [],        # 概率>0.4的选项
        }
        
        for candidate in candidates:
            selection = candidate.selection
            play_type = candidate.play_type
            prob = candidate.probability
            
            # SPF/RQSPF 趋势分析
            if play_type in [PlayType.SPF, PlayType.RQSPF]:
                if "主胜" in selection or "胜" == selection:
                    trends["主队热门"].append(candidate)
                elif "客胜" in selection or "负" == selection:
                    trends["客队热门"].append(candidate)
                elif "平" in selection:
                    trends["平局趋势"].append(candidate)
            
            # ZJQ 趋势分析
            elif play_type == PlayType.ZJQ:
                try:
                    if selection == "7+":
                        goals = 7
                    else:
                        goals = int(selection)
                    
                    if goals >= 3:
                        trends["大球趋势"].append(candidate)
                    else:
                        trends["小球趋势"].append(candidate)
                except (ValueError, TypeError):
                    pass
            
            # BF 趋势分析（从比分推断大小球）
            elif play_type == PlayType.BF:
                if selection not in ["胜其他", "平其他", "负其他"]:
                    try:
                        parts = selection.split(":")
                        total_goals = int(parts[0]) + int(parts[1])
                        if total_goals >= 3:
                            trends["大球趋势"].append(candidate)
                        else:
                            trends["小球趋势"].append(candidate)
                    except (ValueError, IndexError):
                        pass
            
            # 高概率趋势（适用于所有玩法）
            if prob > 0.4:
                trends["高概率"].append(candidate)
        
        # 过滤空趋势
        trends = {k: v for k, v in trends.items() if v}
        
        return trends

    def _select_balanced_combo(self, candidates: List[ParlayCandidate], n: int) -> Optional[List[ParlayCandidate]]:
        """选择平衡组合"""
        if len(candidates) < n:
            return None

        # 尝试选n个，包含不同玩法
        selected = []
        used_plays = set()
        used_leagues = set()

        sorted_candidates = sorted(candidates, key=lambda x: x.strategy_score, reverse=True)

        for candidate in sorted_candidates:
            # 玩法多样性
            if self.play_diversity and candidate.play_type in used_plays:
                continue
            # 联赛多样性
            if self.league_diversity and candidate.league in used_leagues:
                continue

            selected.append(candidate)
            used_plays.add(candidate.play_type)
            used_leagues.add(candidate.league)

            if len(selected) >= n:
                break

        # 如果不够，补充
        if len(selected) < n:
            for candidate in sorted_candidates:
                if candidate not in selected:
                    selected.append(candidate)
                    if len(selected) >= n:
                        break

        return selected if len(selected) == n else None

    def _check_diversity(self, combo: Tuple[ParlayCandidate]) -> float:
        """评估组合多样性，返回0-1分数"""
        if not combo:
            return 0.0

        play_types = set(c.play_type for c in combo)
        leagues = set(c.league for c in combo)

        play_diversity = len(play_types) / len(combo)  # 0-1
        league_diversity = len(leagues) / len(combo)  # 0-1

        # 加权平均
        score = play_diversity * 0.6 + league_diversity * 0.4
        return min(1.0, score)

    def _build_plan_from_combo(self, combo: Tuple[ParlayCandidate], plan_type: str) -> Dict[str, Any]:
        """从组合构建方案"""
        total_odds = 1.0
        total_prob = 1.0
        total_ev = 1.0

        for candidate in combo:
            total_odds *= candidate.odds
            total_prob *= candidate.probability
            total_ev *= max(0, candidate.ev)

        # 风险评分
        risk_score = 0.0
        risk_map = {"低": 0.2, "中": 0.5, "高": 0.8, "极高": 1.0}
        for candidate in combo:
            candidate_risk = risk_map.get(candidate.risk_level, 0.5)
            risk_score += candidate_risk

        risk_score /= len(combo)

        return {
            "type": plan_type,
            "selections": [
                {
                    "match_id": c.match_id,
                    "match": f"{c.home_team} vs {c.away_team}",
                    "league": c.league,
                    "play_type": c.play_type.value,
                    "selection": c.selection,
                    "odds": c.odds,
                    "probability": c.probability,
                    "ev": c.ev,
                }
                for c in combo
            ],
            "match_count": len(combo),
            "combined_odds": round(total_odds, 2),
            "combined_probability": round(total_prob, 4),
            "combined_ev": round(total_ev, 3),
            "risk_score": round(risk_score, 2),
            "risk_level": self._get_risk_level(risk_score),
        }

    def _get_risk_level(self, risk_score: float) -> str:
        """获取风险等级"""
        if risk_score < 0.3:
            return "低"
        elif risk_score < 0.6:
            return "中"
        elif risk_score < 0.8:
            return "高"
        else:
            return "极高"

    def _detect_contradictions(self, selections: List[Dict[str, Any]]) -> List[str]:
        """
        检测混合过关选择中的矛盾组合。

        检测以下矛盾情况：
        1. SPF "主胜" + RQSPF "客胜" with handicap=0 (矛盾：主胜vs客胜)
        2. SPF "客胜" + RQSPF "主胜" with handicap=0 (矛盾：客胜vs主胜)
        3. BF "0:0" + ZJQ "7+" (矛盾：0进球vs7+进球)
        4. BF "3:3" + ZJQ "0" (矛盾：6进球vs0进球)
        5. SPF "主胜" + BF "0:2" (矛盾：主胜但客队进球更高)

        Args:
            selections: 选择列表，每个选择包含 match_id, play_type, selection 等字段

        Returns:
            矛盾描述列表，空列表表示无矛盾
        """
        contradictions = []

        # 按比赛ID分组
        by_match: Dict[str, List[Dict[str, Any]]] = {}
        for sel in selections:
            match_id = sel.get("match_id", "")
            if match_id not in by_match:
                by_match[match_id] = []
            by_match[match_id].append(sel)

        # 对每场比赛检查矛盾
        for match_id, match_selections in by_match.items():
            if len(match_selections) < 2:
                continue  # 单场比赛只有一个选择，不可能矛盾

            # 提取各玩法的选择
            spf_sel = None
            rqspf_sel = None
            bf_sel = None
            zjq_sel = None
            bqc_sel = None

            for sel in match_selections:
                play_type = sel.get("play_type", "")
                selection = sel.get("selection", "")

                # 标准化玩法类型
                if play_type in ["SPF", "胜平负"]:
                    spf_sel = selection
                elif play_type in ["RQSPF", "让球胜平负"]:
                    rqspf_sel = selection
                elif play_type in ["BF", "比分"]:
                    bf_sel = selection
                elif play_type in ["ZJQ", "总进球"]:
                    zjq_sel = selection
                elif play_type in ["BQC", "半全场"]:
                    bqc_sel = selection

            # 检测矛盾1和2: SPF与RQSPF（让球数为0时）
            # 注意：需要获取handicap信息，当前选择中可能没有
            # 假设handicap=0的情况（最严格的矛盾检测）
            if spf_sel and rqspf_sel:
                # 获取让球数（默认为0）
                handicap = 0
                for sel in match_selections:
                    if sel.get("play_type") in ["RQSPF", "让球胜平负"]:
                        handicap = sel.get("handicap", 0)
                        break

                if handicap == 0:
                    # SPF主胜 + RQSPF客胜（让球为0时矛盾）
                    if ("主胜" in spf_sel or spf_sel == "胜") and ("客胜" in rqspf_sel or rqspf_sel == "负"):
                        contradictions.append(
                            f"比赛{match_id}: SPF选择'{spf_sel}'与RQSPF选择'{rqspf_sel}'矛盾（让球=0）"
                        )
                    # SPF客胜 + RQSPF主胜（让球为0时矛盾）
                    if ("客胜" in spf_sel or spf_sel == "负") and ("主胜" in rqspf_sel or rqspf_sel == "胜"):
                        contradictions.append(
                            f"比赛{match_id}: SPF选择'{spf_sel}'与RQSPF选择'{rqspf_sel}'矛盾（让球=0）"
                        )

            # 检测矛盾3和4: BF与ZJQ
            if bf_sel and zjq_sel:
                # 解析比分
                if ":" in bf_sel and bf_sel not in ["胜其他", "平其他", "负其他"]:
                    try:
                        parts = bf_sel.split(":")
                        home_goals = int(parts[0])
                        away_goals = int(parts[1])
                        total_goals = home_goals + away_goals

                        # 解析ZJQ选择
                        zjq_goals = None
                        if zjq_sel == "7+":
                            zjq_goals = 7  # 至少7球
                        else:
                            try:
                                zjq_goals = int(zjq_sel)
                            except ValueError:
                                pass

                        if zjq_goals is not None:
                            # 矛盾3: BF "0:0" + ZJQ "7+" (0进球 vs 7+进球)
                            if total_goals == 0 and zjq_sel == "7+":
                                contradictions.append(
                                    f"比赛{match_id}: BF选择'{bf_sel}'(0进球)与ZJQ选择'{zjq_sel}'(7+进球)矛盾"
                                )
                            # 矛盾4: BF "3:3" + ZJQ "0" (6进球 vs 0进球)
                            elif total_goals >= 6 and zjq_goals == 0:
                                contradictions.append(
                                    f"比赛{match_id}: BF选择'{bf_sel}'({total_goals}进球)与ZJQ选择'{zjq_sel}'(0进球)矛盾"
                                )
                            # 通用检测：比分总进球与ZJQ不匹配
                            elif zjq_sel != "7+" and total_goals != zjq_goals:
                                # 这是更强的矛盾检测，但可能过于严格
                                # 仅在明显矛盾时报告
                                if (total_goals < zjq_goals - 2) or (total_goals > zjq_goals + 2):
                                    contradictions.append(
                                        f"比赛{match_id}: BF选择'{bf_sel}'({total_goals}进球)与ZJQ选择'{zjq_sel}'不兼容"
                                    )
                    except (ValueError, IndexError):
                        pass

            # 检测矛盾5: SPF与BF
            if spf_sel and bf_sel:
                if ":" in bf_sel and bf_sel not in ["胜其他", "平其他", "负其他"]:
                    try:
                        parts = bf_sel.split(":")
                        home_goals = int(parts[0])
                        away_goals = int(parts[1])

                        # SPF主胜 + BF显示客队进球更多
                        if ("主胜" in spf_sel or spf_sel == "胜") and away_goals > home_goals:
                            contradictions.append(
                                f"比赛{match_id}: SPF选择'{spf_sel}'与BF选择'{bf_sel}'矛盾（主胜但客队进球更高）"
                            )
                        # SPF客胜 + BF显示主队进球更多
                        if ("客胜" in spf_sel or spf_sel == "负") and home_goals > away_goals:
                            contradictions.append(
                                f"比赛{match_id}: SPF选择'{spf_sel}'与BF选择'{bf_sel}'矛盾（客胜但主队进球更高）"
                            )
                        # SPF平局 + BF显示非平局
                        if ("平" in spf_sel) and home_goals != away_goals:
                            contradictions.append(
                                f"比赛{match_id}: SPF选择'{spf_sel}'与BF选择'{bf_sel}'矛盾（平局但比分非平）"
                            )
                    except (ValueError, IndexError):
                        pass

            # 检测矛盾6: BQC与SPF
            if bqc_sel and spf_sel:
                # BQC格式: "胜胜"/"胜负"/"平胜" 等 (第一个字=半场, 第二个字=全场)
                if len(bqc_sel) >= 2:
                    ht_result = bqc_sel[0]  # 半场结果
                    ft_result = bqc_sel[1]  # 全场结果

                    # BQC"负胜"(半负全胜) vs SPF"主胜" → 矛盾
                    if ft_result == "负" and ("主胜" in spf_sel or spf_sel == "胜"):
                        contradictions.append(
                            f"比赛{match_id}: BQC选择'{bqc_sel}'(全场负)与SPF选择'{spf_sel}'(主胜)矛盾"
                        )
                    # BQC"胜负"(半胜全负) vs SPF"主胜" → 矛盾
                    if ft_result == "负" and ("主胜" in spf_sel or spf_sel == "胜"):
                        contradictions.append(
                            f"比赛{match_id}: BQC选择'{bqc_sel}'(全场负)与SPF选择'{spf_sel}'(主胜)矛盾"
                        )
                    # BQC"胜胜"(全场胜) vs SPF"客胜" → 矛盾
                    if ft_result == "胜" and ("客胜" in spf_sel or spf_sel == "负"):
                        contradictions.append(
                            f"比赛{match_id}: BQC选择'{bqc_sel}'(全场胜)与SPF选择'{spf_sel}'(客胜)矛盾"
                        )

            # 检测矛盾7: BQC与BF
            if bqc_sel and bf_sel:
                if len(bqc_sel) >= 2 and ":" in bf_sel and bf_sel not in ["胜其他", "平其他", "负其他"]:
                    try:
                        parts = bf_sel.split(":")
                        hg, ag = int(parts[0]), int(parts[1])
                        ft_result = bqc_sel[1]  # BQC全场结果

                        # BQC全场胜 但 BF客队进球更多
                        if ft_result == "胜" and ag > hg:
                            contradictions.append(
                                f"比赛{match_id}: BQC选择'{bqc_sel}'(全场胜)与BF选择'{bf_sel}'矛盾"
                            )
                        # BQC全场负 但 BF主队进球更多
                        if ft_result == "负" and hg > ag:
                            contradictions.append(
                                f"比赛{match_id}: BQC选择'{bqc_sel}'(全场负)与BF选择'{bf_sel}'矛盾"
                            )
                    except (ValueError, IndexError):
                        pass

        return contradictions

    def _detect_complementary(self, selections: List[Dict]) -> List[str]:
        """检测互补选择（一致性看好同一方向）"""
        complements = []
        for i, s1 in enumerate(selections):
            for j, s2 in enumerate(selections):
                if i >= j:
                    continue
                # SPF主胜 + BF主胜比分（如2:0, 1:0, 2:1）
                if s1.get("play_type") == "SPF" and "主胜" in s1.get("selection", ""):
                    if s2.get("play_type") == "BF":
                        bf = s2.get("selection", "")
                        parts = bf.split(":")
                        if len(parts) == 2 and int(parts[0]) > int(parts[1]):
                            complements.append(f"SPF主胜 + BF{bf}（一致看好主队）")
                # SPF平局 + BF平局比分（如0:0, 1:1）
                if s1.get("play_type") == "SPF" and "平" in s1.get("selection", ""):
                    if s2.get("play_type") == "BF":
                        bf = s2.get("selection", "")
                        parts = bf.split(":")
                        if len(parts) == 2 and parts[0] == parts[1]:
                            complements.append(f"SPF平局 + BF{bf}（一致看好平局）")
                # ZJQ小球 + BQC平平（一致看好低分）
                if s1.get("play_type") == "ZJQ" and s1.get("selection", "") in ("0", "1"):
                    if s2.get("play_type") == "BQC" and "平-平" in s2.get("selection", ""):
                        complements.append(f"ZJQ{s1['selection']}球 + BQC平平（一致看好低分）")
        return complements

    def _calculate_play_complementarity(self, play_type_1: str, play_type_2: str) -> float:
        """计算两个玩法之间的互补性评分(0-1)。

        互补性高 → 适合混合过关
        互补性低 → 信息冗余，不建议组合

        Args:
            play_type_1: 玩法1名称
            play_type_2: 玩法2名称

        Returns:
            互补性评分 0.0-1.0
        """
        pt1 = play_type_from_str(play_type_1)
        pt2 = play_type_from_str(play_type_2)
        if not pt1 or not pt2:
            return 0.5

        if pt1 == pt2:
            return 0.0  # 同一玩法无互补性

        # 互补性矩阵（基于玩法间的信息重叠度）
        _COMPLEMENTARITY = {
            (PlayType.SPF, PlayType.RQSPF): 0.3,   # 高度重叠
            (PlayType.SPF, PlayType.BF): 0.7,       # SPF提供方向，BF提供精确比分
            (PlayType.SPF, PlayType.ZJQ): 0.6,       # SPF提供方向，ZJQ提供进球数
            (PlayType.SPF, PlayType.BQC): 0.8,       # SPF提供全场方向，BQC提供半场+全场
            (PlayType.RQSPF, PlayType.BF): 0.6,      # 让球+比分
            (PlayType.RQSPF, PlayType.ZJQ): 0.5,     # 让球+进球数
            (PlayType.RQSPF, PlayType.BQC): 0.7,     # 让球+半全场
            (PlayType.BF, PlayType.ZJQ): 0.4,        # 比分和进球数高度重叠
            (PlayType.BF, PlayType.BQC): 0.7,         # 比分和半全场互补
            (PlayType.ZJQ, PlayType.BQC): 0.6,       # 进球数和半全场互补
        }

        key = (min(pt1, pt2), max(pt1, pt2))
        return _COMPLEMENTARITY.get(key, 0.5)

    def _apply_bucket_principle(self, plan: Dict[str, Any], candidates: List[ParlayCandidate]) -> Optional[Dict[str, Any]]:
        """
        应用木桶原则（bucket principle）：
        混合过关的最大场次数由所有选中玩法中最小的最大场次数决定。

        例如：如果方案中包含 BF（最多4场）和 SPF（最多8场），
        则该方案最多只能有 4 场。

        Args:
            plan: 待验证的方案
            candidates: 候选列表（用于查找玩法类型）

        Returns:
            截断后的方案，如果无法截断则返回 None
        """
        selections = plan.get("selections", [])
        if not selections:
            return plan

        # 收集方案中涉及的所有玩法类型
        play_types_in_plan = set()
        for sel in selections:
            play_type_str = sel.get("play_type", "")
            pt = play_type_from_str(play_type_str)
            if pt:
                play_types_in_plan.add(pt)

        if not play_types_in_plan:
            logger.warning("木桶原则验证：方案中未识别到有效玩法类型")
            return plan

        # 找出所有玩法中最小的最大场次数（木桶的最短板）
        max_legs_values = []
        for pt in play_types_in_plan:
            if pt in PLAY_MAX_LEGS:
                max_legs_values.append(PLAY_MAX_LEGS[pt])
            else:
                logger.warning(f"木桶原则验证：未知的玩法类型 {pt}，跳过")
                continue

        if not max_legs_values:
            return plan

        bucket_limit = min(max_legs_values)

        match_count = len(selections)
        if match_count <= bucket_limit:
            # 方案场次数在限制范围内，通过验证
            return plan

        # 超出限制，需要截断：保留 EV 最高的 bucket_limit 场
        logger.info(
            f"木桶原则：方案包含 {match_count} 场，"
            f"涉及玩法 {', '.join(pt.value for pt in play_types_in_plan)}，"
            f"最短限制为 {bucket_limit} 场，需要截断"
        )

        # 按 EV 降序排列，保留前 bucket_limit 场
        sorted_selections = sorted(selections, key=lambda s: s.get("ev", 0), reverse=True)
        truncated_selections = sorted_selections[:bucket_limit]

        # 重新计算组合指标
        total_odds = 1.0
        total_prob = 1.0
        total_ev = 1.0
        risk_score = 0.0
        risk_map = {"低": 0.2, "中": 0.5, "高": 0.8, "极高": 1.0}

        for sel in truncated_selections:
            total_odds *= sel.get("odds", 1.0)
            total_prob *= sel.get("probability", 0.0)
            total_ev *= max(0, sel.get("ev", 0))
            # 风险评分从候选中查找
            risk_level = "中"
            for c in candidates:
                if c.match_id == sel.get("match_id") and c.play_type.value == sel.get("play_type"):
                    risk_level = c.risk_level
                    break
            risk_score += risk_map.get(risk_level, 0.5)

        risk_score /= len(truncated_selections)

        plan["selections"] = truncated_selections
        plan["match_count"] = len(truncated_selections)
        plan["combined_odds"] = round(total_odds, 2)
        plan["combined_probability"] = round(total_prob, 4)
        plan["combined_ev"] = round(total_ev, 3)
        plan["risk_score"] = round(risk_score, 2)
        plan["risk_level"] = self._get_risk_level(risk_score)
        plan["bucket_limit_applied"] = bucket_limit

        logger.info(f"木桶原则：方案已截断为 {bucket_limit} 场")

        return plan

    def _validate_plan_rules(self, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        验证方案的规则合规性：
        1. 同场比赛不可多次选择（同一比赛ID只能出现一次）
        2. 应用木桶原则（最大场次数由最短玩法限制决定）
        3. 检测矛盾选择（同一比赛的多个选择是否矛盾）

        Args:
            plan: 待验证的方案

        Returns:
            验证通过的方案，验证失败返回 None
        """
        selections = plan.get("selections", [])

        # 规则1：同场比赛不可多次选择
        match_ids = [s.get("match_id", "") for s in selections]
        seen_ids = set()
        for mid in match_ids:
            if mid in seen_ids:
                logger.warning(
                    f"方案验证失败：同场比赛 {mid} 出现多次，违反单场限制规则"
                )
                return None
            seen_ids.add(mid)

        # 规则2：应用木桶原则（统一使用 _apply_bucket_principle）
        # _apply_bucket_principle 会在超限时截断方案而非直接作废
        # 此处仅做基本检查：如果超限，记录警告但不作废（由优化器截断）
        play_types_in_plan = set()
        for sel in selections:
            pt = play_type_from_str(sel.get("play_type", ""))
            if pt:
                play_types_in_plan.add(pt)

        if play_types_in_plan:
            max_legs_values = [
                PLAY_MAX_LEGS[pt]
                for pt in play_types_in_plan
                if pt in PLAY_MAX_LEGS
            ]
            if max_legs_values:
                bucket_limit = min(max_legs_values)
                if len(selections) > bucket_limit:
                    logger.info(
                        f"方案包含 {len(selections)} 场，"
                        f"木桶原则限制为 {bucket_limit} 场（将由优化器截断）"
                    )

        # 规则3：检测矛盾选择
        contradictions = self._detect_contradictions(selections)
        plan["contradictions"] = contradictions
        if contradictions:
            logger.warning(
                f"方案存在矛盾选择: {'; '.join(contradictions)}"
            )
            # 矛盾选择不导致方案无效，但会记录在结果中供用户参考

        # 规则4：检测互补选择
        complements = self._detect_complementary(selections)
        plan["complements"] = complements

        return plan

    def _optimize_plans(self, plans: List[Dict[str, Any]], candidates: List[ParlayCandidate]) -> List[Dict[str, Any]]:
        """优化方案"""
        if not plans:
            return []

        # 去重
        unique_plans = []
        seen = set()
        for plan in plans:
            key = tuple(sorted(s["match_id"] for s in plan["selections"]))
            if key not in seen:
                seen.add(key)
                unique_plans.append(plan)

        # 验证每个方案的规则合规性
        validated_plans = []
        for plan in unique_plans:
            # 先做规则验证（同场检查 + 木桶原则基本检查）
            validated = self._validate_plan_rules(plan)
            if validated is None:
                continue

            # 再应用木桶原则（可能截断方案）
            applied = self._apply_bucket_principle(validated, candidates)
            if applied is not None:
                validated_plans.append(applied)

        # 排序
        validated_plans.sort(key=lambda x: x["combined_ev"] * (1 - x["risk_score"] * 0.5), reverse=True)

        # P1-3: 玩法互补性评分应用
        for plan in validated_plans:
            selections = plan.get("selections", [])
            if selections:
                # 计算玩法互补性加成
                complementarity_score = 0.0
                selection_play_types = []
                for sel in selections:
                    pt = sel.get("play_type", "")
                    if pt:
                        selection_play_types.append(pt)

                for i in range(len(selection_play_types)):
                    for j in range(i + 1, len(selection_play_types)):
                        comp = self._calculate_play_complementarity(
                            selection_play_types[i], selection_play_types[j]
                        )
                        complementarity_score += comp

                pair_count = len(selection_play_types) * (len(selection_play_types) - 1) // 2
                avg_complementarity = complementarity_score / max(1, pair_count) if pair_count > 0 else 0.5

                # 互补性好的方案加权提升5%
                original_ev = plan.get("combined_ev", 1.0)
                plan["complementarity_score"] = round(avg_complementarity, 3)
                plan["combined_ev"] = round(original_ev * (1 + avg_complementarity * 0.05), 3)
                plan["complementarity_summary"] = f"互补性={avg_complementarity:.1%}，EV提升{(avg_complementarity * 0.05):.1%}"

        # 重新按调整后的EV排序
        validated_plans.sort(key=lambda x: x.get("combined_ev", 0), reverse=True)

        return validated_plans[:10]
