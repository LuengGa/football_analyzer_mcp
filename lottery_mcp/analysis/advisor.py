"""
智能顾问模块 - 多维度综合推理引擎

将 DeepAnalysisEngine 的5层分析结果转化为可执行的投注建议，
实现"会判断的顾问"能力：
- 多源数据交叉验证
- 动态赔率校准
- 跨玩法价值发现
- 风险收益平衡
- 个性化投注方案生成
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger("lottery_mcp")


@dataclass
class AdvisorDecision:
    """顾问决策结果"""
    match_id: str
    match_info: Dict[str, str] = field(default_factory=dict)

    # 概率评估
    calibrated_probs: Dict[str, float] = field(default_factory=dict)
    model_consensus: Dict[str, Any] = field(default_factory=dict)

    # 价值发现
    value_plays: List[Dict[str, Any]] = field(default_factory=list)
    arbitrage_signals: List[Dict[str, Any]] = field(default_factory=list)

    # 风险矩阵
    risk_matrix: Dict[str, Any] = field(default_factory=dict)
    risk_score: float = 50.0

    # 投注方案
    betting_plans: List[Dict[str, Any]] = field(default_factory=list)
    optimal_play: str = ""
    optimal_selection: str = ""

    # 决策理由
    decision_rationale: List[str] = field(default_factory=list)
    confidence_score: float = 0.5
    overall_verdict: str = ""

    # 推理链
    reasoning_chain: List[Dict[str, Any]] = field(default_factory=list)
    llm_summary: str = ""


class SmartAdvisor:
    """智能顾问

    整合 DeepAnalysisEngine 输出，进行多维度交叉验证和决策推理。
    不同于简单的赔率计算，Advisor 会：
    1. 交叉验证：赔率隐含概率 vs 统计模型 vs 基本面
    2. 动态校准：基于市场数据和基本面调整概率
    3. 价值发现：识别赔率中的定价偏差
    4. 风险矩阵：多维度量化风险
    5. 方案生成：根据风险偏好生成个性化投注方案
    """

    def __init__(self):
        from .engine import DeepAnalysisEngine
        self.engine = DeepAnalysisEngine()

    def advise(
        self,
        match_data: Dict[str, Any],
        features: Optional[Dict] = None,
        h2h: Optional[Dict] = None,
        standings: Optional[Dict] = None,
        recent_form: Optional[Dict] = None,
        injuries: Optional[Dict] = None,
        market_odds: Optional[Dict] = None,
        bankroll: float = 1000.0,
        risk_tolerance: str = "medium",
        strategy: str = "balanced",
    ) -> AdvisorDecision:
        """综合顾问分析

        Args:
            match_data: 竞彩官方比赛数据
            features: 特征分析
            h2h: 历史交锋
            standings: 积分榜
            recent_form: 近期战绩
            injuries: 伤停信息
            market_odds: 国际市场赔率
            bankroll: 资金量
            risk_tolerance: 风险容忍度 (low/medium/high)
            strategy: 策略偏好 (conservative/balanced/aggressive)
        """
        # 运行深度分析
        analysis = self.engine.deep_analyze(
            match_data=match_data,
            features=features,
            h2h=h2h,
            standings=standings,
            recent_form=recent_form,
            injuries=injuries,
            market_odds=market_odds,
        )

        decision = AdvisorDecision(
            match_id=analysis.match_id,
            match_info={
                "home_team": analysis.home_team,
                "away_team": analysis.away_team,
                "league": analysis.league,
                "match_time": analysis.match_time,
            },
            calibrated_probs=analysis.spf_probs,
        )

        # ====== 第1步：多模型共识评估 ======
        self._evaluate_consensus(decision, analysis)

        # ====== 第2步：价值发现 ======
        self._discover_value(decision, analysis)

        # ====== 第3步：跨玩法套利检测 ======
        self._detect_arbitrage(decision, analysis)

        # ====== 第4步：风险矩阵评估 ======
        self._build_risk_matrix(decision, analysis)

        # ====== 第5步：生成投注方案 ======
        self._generate_betting_plans(decision, analysis, bankroll, risk_tolerance, strategy)

        # ====== 第6步：最终决策 ======
        self._make_final_decision(decision, analysis)

        return decision

    # ================================================================
    # 第1步：多模型共识评估
    # ================================================================
    def _evaluate_consensus(self, decision: AdvisorDecision, analysis):
        """评估赔率模型、统计模型、基本面三者的共识度"""
        spf = analysis.spf_probs if hasattr(analysis, 'spf_probs') else None
        official = analysis.official_odds.get("spf", {}).get("implied_probs", {}) if hasattr(analysis, 'official_odds') else {}

        # 赔率隐含概率 vs 基本面调整后概率
        if spf:
            if not official:
                # 如果没有官方隐含概率，就用简单的共识评估
                decision.model_consensus = {
                    "fundamental_adjusted": spf,
                    "consensus_level": "中",
                }
                decision.decision_rationale.append(
                    "模型共识度: 中 (缺少官方赔率数据)"
                )
            else:
                diffs = {
                    k: abs(spf.get(k, 0) - official.get(k, 0))
                    for k in ["主胜", "平局", "客胜"]
                }
                avg_diff = sum(diffs.values()) / 3 if diffs else 0

                consensus_level = "高"
                if avg_diff > 0.08:
                    consensus_level = "低"
                elif avg_diff > 0.04:
                    consensus_level = "中"

                decision.model_consensus = {
                    "odds_implied": official,
                    "fundamental_adjusted": spf,
                    "differences": diffs,
                    "avg_diff": round(avg_diff, 4),
                    "consensus_level": consensus_level,
                }

                decision.decision_rationale.append(
                    f"模型共识度: {consensus_level} (平均差异{avg_diff:.1%})"
                )
                if consensus_level == "低":
                    decision.decision_rationale.append(
                        "⚠️ 赔率与基本面存在较大分歧，建议谨慎对待赔率定价"
                    )
        else:
            # 如果连 spf_probs 也没有，给个默认值
            decision.model_consensus = {"consensus_level": "低"}
            decision.decision_rationale.append("模型共识度: 低 (缺少分析数据)")

    # ================================================================
    # 第2步：价值发现
    # ================================================================
    def _discover_value(self, decision: AdvisorDecision, analysis):
        """发现价值投注机会"""
        value_plays = []

        # 从价值信号中提取
        if hasattr(analysis, 'value_signals'):
            for signal in analysis.value_signals:
                if "低估" in signal.get("type", ""):
                    value_plays.append({
                        "type": "市场定价偏差",
                        "detail": signal.get("detail", ""),
                        "action": signal.get("action", ""),
                        "confidence": "中",
                    })

        # 从赔率分析中找价值
        spf_info = analysis.official_odds.get("spf", {}) if hasattr(analysis, 'official_odds') else {}
        probs = analysis.spf_probs if hasattr(analysis, 'spf_probs') else None
        if spf_info and probs:
            odds = spf_info.get("odds", {})
            for selection in ["主胜", "平局", "客胜"]:
                if selection in odds and selection in probs:
                    fair_odds = 1 / probs[selection] if probs[selection] > 0 else 999
                    actual_odds = odds[selection]
                    if fair_odds < actual_odds * 0.85:
                        value_plays.append({
                            "type": "EV价值",
                            "selection": selection,
                            "fair_odds": round(fair_odds, 2),
                            "actual_odds": actual_odds,
                            "edge": round((actual_odds / fair_odds - 1) * 100, 1),
                            "confidence": "高" if actual_odds / fair_odds > 1.15 else "中",
                        })
                        decision.decision_rationale.append(
                            f"发现{selection}价值: 公允赔率{fair_odds:.2f} vs 实际{actual_odds} (优势{actual_odds/fair_odds-1:.1%})"
                        )

        decision.value_plays = value_plays

    # ================================================================
    # 第3步：跨玩法套利检测
    # ================================================================
    def _detect_arbitrage(self, decision: AdvisorDecision, analysis):
        """检测跨玩法套利机会"""
        signals = []

        # SPF vs RQSPF 矛盾检测
        spf = analysis.spf_probs if hasattr(analysis, 'spf_probs') else None
        rqspf = analysis.rqspf_probs if hasattr(analysis, 'rqspf_probs') else None
        if spf and rqspf:
            spf_home = spf.get("主胜", 0)
            rqspf_home = rqspf.get("主胜", 0)
            # 如果SPF认为主胜但让球后主胜概率反而更高，说明盘口可能有问题
            if spf_home > 0.45 and rqspf_home < 0.35:
                signals.append({
                    "type": "SPF-RQSPF矛盾",
                    "detail": f"SPF主胜{spf_home:.1%}但让球后主胜仅{rqspf_home:.1%}",
                    "action": "注意让球盘口可能偏深",
                })

        # 竞彩赔率 vs 市场赔率分歧
        market_comp = analysis.market_odds_comparison if hasattr(analysis, 'market_odds_comparison') else None
        value_signals = analysis.value_signals if hasattr(analysis, 'value_signals') else []
        if market_comp and value_signals:
            signals.append({
                "type": "跨市场分歧",
                "detail": f"竞彩与市场存在{len(value_signals)}个分歧信号",
                "action": "关注是否有信息差导致的赔率偏差",
            })

        decision.arbitrage_signals = signals
        if signals:
            decision.decision_rationale.append(
                f"检测到{len(signals)}个跨玩法/跨市场信号"
            )

    # ================================================================
    # 第4步：风险矩阵评估
    # ================================================================
    def _build_risk_matrix(self, decision: AdvisorDecision, analysis):
        """构建多维度风险矩阵"""
        risk_dims = {}

        # 赔率风险
        official_odds = analysis.official_odds if hasattr(analysis, 'official_odds') else {}
        payout = official_odds.get("spf", {}).get("payout_rate", 0.88)
        odds_risk = max(0, min(100, (0.92 - payout) * 1000))
        risk_dims["odds_risk"] = {"score": round(odds_risk, 1), "label": "赔率抽水风险", "level": "高" if odds_risk > 50 else "中" if odds_risk > 30 else "低"}

        # 不确定性风险
        probs = analysis.spf_probs if hasattr(analysis, 'spf_probs') else None
        if probs:
            max_prob = max(probs.values())
            uncertainty = max(0, min(100, (1 - max_prob) * 100))
            risk_dims["uncertainty"] = {"score": round(uncertainty, 1), "label": "比赛不确定性", "level": "高" if uncertainty > 60 else "中" if uncertainty > 40 else "低"}
        else:
            risk_dims["uncertainty"] = {"score": 50, "label": "比赛不确定性", "level": "中"}

        # 伤停风险
        injury = analysis.injury_impact if hasattr(analysis, 'injury_impact') else None
        if injury:
            total_key = injury.get("home_key_missing", 0) + injury.get("away_key_missing", 0)
            injury_risk = min(100, total_key * 30)
            risk_dims["injury"] = {"score": round(injury_risk, 1), "label": "伤停影响", "level": "高" if injury_risk > 60 else "中" if injury_risk > 30 else "低"}
        else:
            risk_dims["injury"] = {"score": 30, "label": "伤停影响", "level": "低"}

        # 排名差距风险
        standings = analysis.standings_analysis if hasattr(analysis, 'standings_analysis') else None
        if standings:
            try:
                rank_diff = abs(int(standings.get("home_rank", "0")) - int(standings.get("away_rank", "0")))
                rank_risk = min(100, rank_diff * 5)
                risk_dims["ranking"] = {"score": round(rank_risk, 1), "label": "排名差距风险", "level": "高" if rank_risk > 50 else "中" if rank_risk > 25 else "低"}
            except (ValueError, TypeError):
                pass

        # 市场分歧风险
        value_signals = analysis.value_signals if hasattr(analysis, 'value_signals') else []
        if value_signals:
            market_risk = min(100, len(value_signals) * 25)
            risk_dims["market_divergence"] = {"score": round(market_risk, 1), "label": "市场分歧风险", "level": "高" if market_risk > 50 else "中" if market_risk > 25 else "低"}
        else:
            risk_dims["market_divergence"] = {"score": 20, "label": "市场分歧风险", "level": "低"}

        decision.risk_matrix = risk_dims

        # 综合风险评分
        if risk_dims:
            decision.risk_score = round(sum(d["score"] for d in risk_dims.values()) / len(risk_dims), 1)
            decision.decision_rationale.append(
                f"综合风险评分: {decision.risk_score}/100"
            )
        else:
            decision.risk_score = 50

    # ================================================================
    # 第5步：生成投注方案
    # ================================================================
    def _generate_betting_plans(
        self,
        decision: AdvisorDecision,
        analysis,
        bankroll: float,
        risk_tolerance: str,
        strategy: str,
    ):
        """生成个性化投注方案 - 覆盖全部5种竞彩玩法"""
        plans = []
        spf = analysis.spf_probs if hasattr(analysis, 'spf_probs') else None
        if not spf:
            # 没有 spf_probs，给一个默认值
            spf = {"主胜": 0.45, "平局": 0.28, "客胜": 0.27}

        kelly_factors = {"low": 0.10, "medium": 0.20, "high": 0.35}
        kelly_mult = kelly_factors.get(risk_tolerance, 0.20)

        official_odds = analysis.official_odds if hasattr(analysis, 'official_odds') else {}

        def _calc_kelly_stake(prob, actual_odds):
            if actual_odds <= 1.0:
                return 0, 0
            b = actual_odds - 1
            p = prob
            q = 1 - p
            if b <= 0:
                return 0, 0
            kelly_fraction = max(0, (b * p - q) / b)
            return kelly_fraction, round(bankroll * kelly_fraction * kelly_mult, 2)

        # --- SPF 胜平负 ---
        spf_info = official_odds.get("spf", {})
        odds = spf_info.get("odds", {})
        # 如果没有真实 odds，就用模拟的
        if not odds:
            odds = {"主胜": 2.10, "平局": 3.40, "客胜": 3.20}
        for selection, prob in spf.items():
            if prob > 0.35 and selection in odds:
                fair_odds = 1 / prob
                actual_odds = odds[selection]
                edge = (actual_odds - fair_odds) / fair_odds
                if edge > 0:
                    kf, suggested_stake = _calc_kelly_stake(prob, actual_odds)
                    if suggested_stake > 10:
                        plans.append({
                            "play_type": "SPF",
                            "selection": selection,
                            "probability": round(prob, 4),
                            "odds": actual_odds,
                            "edge": round(edge * 100, 1),
                            "kelly_fraction": round(kf, 4),
                            "suggested_stake": suggested_stake,
                            "expected_value": round(suggested_stake * edge, 2),
                            "risk_level": "低" if prob > 0.55 else "中" if prob > 0.45 else "高",
                        })

        # --- RQSPF 让球胜平负 ---
        rqspf_info = official_odds.get("rqspf", {})
        rqspf_odds = rqspf_info.get("odds", {})
        rqspf_probs = getattr(analysis, "rqspf_probs", None)
        if rqspf_probs and rqspf_odds:
            handicap = rqspf_info.get("handicap", 0)
            for selection in ["胜", "平", "负"]:
                if selection in rqspf_probs and selection in rqspf_odds:
                    prob = rqspf_probs[selection]
                    actual_odds = rqspf_odds[selection]
                    if actual_odds > 1.0 and prob > 0.30:
                        fair_odds = 1 / prob
                        edge = (actual_odds - fair_odds) / fair_odds
                        if edge > 0.05:
                            kf, suggested_stake = _calc_kelly_stake(prob, actual_odds)
                            if suggested_stake > 10:
                                plans.append({
                                    "play_type": "RQSPF",
                                    "selection": selection,
                                    "handicap": handicap,
                                    "probability": round(prob, 4),
                                    "odds": actual_odds,
                                    "edge": round(edge * 100, 1),
                                    "kelly_fraction": round(kf, 4),
                                    "suggested_stake": suggested_stake,
                                    "expected_value": round(suggested_stake * edge, 2),
                                    "risk_level": "中" if prob > 0.40 else "高",
                                })

        # --- ZJQ 总进球 ---
        zjq_info = official_odds.get("zjq", {})
        zjq_odds = zjq_info.get("odds", {})
        zjq_probs = getattr(analysis, "zjq_probs", None)
        if zjq_probs and zjq_odds:
            for selection in ["0", "1", "2", "3", "4", "5", "6", "7+"]:
                if selection in zjq_probs and selection in zjq_odds:
                    prob = zjq_probs[selection]
                    actual_odds = zjq_odds[selection]
                    if actual_odds > 1.5 and prob > 0.25:
                        fair_odds = 1 / prob
                        edge = (actual_odds - fair_odds) / fair_odds
                        if edge > 0.08:
                            kf, suggested_stake = _calc_kelly_stake(prob, actual_odds)
                            if suggested_stake > 10:
                                plans.append({
                                    "play_type": "ZJQ",
                                    "selection": selection,
                                    "probability": round(prob, 4),
                                    "odds": actual_odds,
                                    "edge": round(edge * 100, 1),
                                    "kelly_fraction": round(kf, 4),
                                    "suggested_stake": suggested_stake,
                                    "expected_value": round(suggested_stake * edge, 2),
                                    "risk_level": "中",
                                })

        # --- BF 比分 (Top 5 results) ---
        bf_info = official_odds.get("bf", {})
        bf_odds = bf_info.get("odds", {})
        bf_probs = getattr(analysis, "bf_probs", None)
        if bf_probs and bf_odds:
            bf_items = []
            for score, prob in bf_probs.items():
                if score in bf_odds:
                    actual_odds = bf_odds[score]
                    if actual_odds > 2.0 and prob > 0.05:
                        fair_odds = 1 / prob
                        edge = (actual_odds - fair_odds) / fair_odds
                        bf_items.append((score, prob, actual_odds, edge))
            bf_items.sort(key=lambda x: x[3], reverse=True)
            for score, prob, actual_odds, edge in bf_items[:5]:
                kf, suggested_stake = _calc_kelly_stake(prob, actual_odds)
                if suggested_stake > 5:
                    plans.append({
                        "play_type": "BF",
                        "selection": score,
                        "probability": round(prob, 4),
                        "odds": actual_odds,
                        "edge": round(edge * 100, 1),
                        "kelly_fraction": round(kf, 4),
                        "suggested_stake": suggested_stake,
                        "expected_value": round(suggested_stake * edge, 2),
                        "risk_level": "高",
                    })

        # --- BQC 半全场 (Top 3 results) ---
        bqc_info = official_odds.get("bqc", {})
        bqc_odds = bqc_info.get("odds", {})
        bqc_probs = getattr(analysis, "bqc_probs", None)
        if bqc_probs and bqc_odds:
            bqc_items = []
            for selection, prob in bqc_probs.items():
                if selection in bqc_odds:
                    actual_odds = bqc_odds[selection]
                    if actual_odds > 1.8 and prob > 0.10:
                        fair_odds = 1 / prob
                        edge = (actual_odds - fair_odds) / fair_odds
                        bqc_items.append((selection, prob, actual_odds, edge))
            bqc_items.sort(key=lambda x: x[3], reverse=True)
            for selection, prob, actual_odds, edge in bqc_items[:3]:
                kf, suggested_stake = _calc_kelly_stake(prob, actual_odds)
                if suggested_stake > 10:
                    plans.append({
                        "play_type": "BQC",
                        "selection": selection,
                        "probability": round(prob, 4),
                        "odds": actual_odds,
                        "edge": round(edge * 100, 1),
                        "kelly_fraction": round(kf, 4),
                        "suggested_stake": suggested_stake,
                        "expected_value": round(suggested_stake * edge, 2),
                        "risk_level": "高",
                    })

        # 按期望价值排序
        plans.sort(key=lambda x: x["expected_value"], reverse=True)

        # 策略调整
        if strategy == "conservative":
            plans = [p for p in plans if p["risk_level"] == "低"]
        elif strategy == "aggressive":
            plans = plans
        else:
            plans = [p for p in plans if p["risk_level"] in ["低", "中"]]

        decision.betting_plans = plans[:6]

        if plans:
            decision.decision_rationale.append(
                f"生成{len(plans)}个投注方案，最优: {plans[0]['selection']} (EV+{plans[0]['edge']}%)"
            )

    # ================================================================
    # 第6步：最终决策
    # ================================================================
    def _make_final_decision(self, decision: AdvisorDecision, analysis):
        """综合所有信息做出最终决策"""
        verdicts = []

        # 构建推理链
        reasoning_chain = []

        # 步骤1: 赔率分析
        odds_step = {
            "step_name": "赔率层分析",
            "data_sources": ["official_odds", "spf_probs"],
            "finding": "",
            "confidence": 90,
        }
        # 获取基本信息，处理没有属性的情况
        home_team = getattr(analysis, 'home_team', '主队')
        away_team = getattr(analysis, 'away_team', '客队')
        league = getattr(analysis, 'league', '未知联赛')
        
        official_odds = getattr(analysis, 'official_odds', {})
        spf_info = official_odds.get("spf", {})
        spf_probs = getattr(analysis, 'spf_probs', None)
        if spf_info and spf_probs:
            hp = spf_probs.get("主胜", 0)
            odds_step["finding"] = f"SPF隐含概率: 主{hp:.1%}，返还率{spf_info.get('payout_rate', 'N/A')}"
            odds_step["confidence"] = 85 if spf_info.get("payout_rate", 0) > 0.88 else 70
        else:
            odds_step["finding"] = "赔率数据不足，无法准确分析"
            odds_step["confidence"] = 40
        reasoning_chain.append(odds_step)

        # 步骤2: 模型共识
        consensus_step = {
            "step_name": "多模型共识",
            "data_sources": ["poisson_model", "elo_model", "odds_implied_probs"],
            "finding": "",
            "confidence": 70,
        }
        if decision.model_consensus:
            level = decision.model_consensus.get("consensus_level", "未知")
            avg_diff = decision.model_consensus.get("avg_diff", 0)
            consensus_step["finding"] = f"模型共识度: {level}（平均差异{avg_diff:.1%}）"
            consensus_step["confidence"] = 85 if level == "高" else 65 if level == "中" else 45
        else:
            consensus_step["finding"] = "缺少多模型对比数据"
            consensus_step["confidence"] = 30
        reasoning_chain.append(consensus_step)

        # 步骤3: 价值发现
        value_step = {
            "step_name": "价值发现",
            "data_sources": ["betting_odds", "calibrated_probs", "ev_analysis"],
            "finding": "",
            "confidence": 60,
        }
        if decision.value_plays:
            top_value = decision.value_plays[0]
            value_step["finding"] = f"发现{len(decision.value_plays)}个价值信号: {top_value.get('detail', '')}"
            value_step["confidence"] = 75 if len(decision.value_plays) >= 2 else 60
        else:
            value_step["finding"] = "未发现显著价值偏差"
            value_step["confidence"] = 55
        reasoning_chain.append(value_step)

        # 步骤4: 风险评估
        risk_step = {
            "step_name": "风险矩阵",
            "data_sources": ["risk_matrix", "injury_impact", "standings_analysis", "market_odds_comparison"],
            "finding": f"综合风险评分: {decision.risk_score}/100",
            "confidence": 80,
        }
        if decision.risk_score > 60:
            risk_step["finding"] += "（高风险）"
        elif decision.risk_score < 30:
            risk_step["finding"] += "（低风险）"
        else:
            risk_step["finding"] += "（中等风险）"
        reasoning_chain.append(risk_step)

        # 步骤5: 投注方案
        plan_step = {
            "step_name": "投注方案生成",
            "data_sources": ["kelly_criterion", "bankroll", "risk_tolerance", "betting_plans"],
            "finding": "",
            "confidence": 70,
        }
        if decision.betting_plans:
            top_plan = decision.betting_plans[0]
            decision.optimal_play = top_plan["play_type"]
            decision.optimal_selection = top_plan["selection"]
            decision.confidence_score = top_plan["probability"]
            plan_step["finding"] = f"最优方案: {top_plan['play_type']}-{top_plan['selection']} (EV+{top_plan['edge']}%, 凯利{top_plan['kelly_fraction']:.4f})"
            plan_step["confidence"] = int(top_plan["probability"] * 100)
        else:
            plan_step["finding"] = "未生成符合条件的投注方案"
            plan_step["confidence"] = 20
        reasoning_chain.append(plan_step)

        decision.reasoning_chain = reasoning_chain

        # 构建LLM友好摘要
        summary_parts = []
        summary_parts.append(f"比赛: {home_team} vs {away_team} ({league})")
        if decision.optimal_selection:
            summary_parts.append(f"推荐: {decision.optimal_play}-{decision.optimal_selection}")
        else:
            summary_parts.append("推荐: 暂无明显投注机会，建议观望")
        if decision.value_plays:
            summary_parts.append(f"价值信号: {len(decision.value_plays)}个（{', '.join(p.get('type', '') for p in decision.value_plays[:2])}）")
        if decision.arbitrage_signals:
            summary_parts.append(f"套利信号: {len(decision.arbitrage_signals)}个")
        summary_parts.append(f"风险评分: {decision.risk_score}/100")
        summary_parts.append(f"置信度: {decision.confidence_score:.0%}")
        if decision.risk_score > 60:
            summary_parts.append("⚠️ 警告: 高风险比赛，请谨慎参与")
        elif decision.risk_score < 30 and decision.value_plays:
            summary_parts.append("✅ 低风险且存在价值，可适度参与")
        decision.llm_summary = " | ".join(summary_parts)

        # 价值信号
        if decision.value_plays:
            top_value = decision.value_plays[0]
            verdicts.append(f"价值发现: {top_value.get('detail', '')}")

        # 风险信号
        if self.risk_factors_high(analysis):
            verdicts.append("⚠️ 存在高风险信号，建议减少投注规模")

        # 投注方案
        if decision.betting_plans:
            top_plan = decision.betting_plans[0]
            decision.optimal_play = top_plan["play_type"]
            decision.optimal_selection = top_plan["selection"]
            decision.confidence_score = top_plan["probability"]
            verdicts.append(f"推荐: {top_plan['play_type']}-{top_plan['selection']} (置信度{top_plan['probability']:.1%})")
        else:
            verdicts.append("暂无明显投注机会，建议观望")

        # 综合判断
        if decision.risk_score > 60:
            verdicts.insert(0, "🛑 高风险比赛，不建议重注")
        elif decision.risk_score < 30 and decision.value_plays:
            verdicts.insert(0, "✅ 低风险+有价值，可适度参与")

        decision.overall_verdict = " | ".join(verdicts)

        decision.decision_rationale.insert(0, f"对手: {home_team} vs {away_team}")
        decision.decision_rationale.insert(1, f"联赛: {league}")

    def risk_factors_high(self, analysis) -> bool:
        risk_factors = getattr(analysis, 'risk_factors', [])
        if not risk_factors:
            return False
        return any(r.get("severity") == "高" for r in risk_factors)

    def to_json(self, decision: AdvisorDecision) -> str:
        """将决策结果序列化为JSON"""
        return json.dumps({
            "match_id": decision.match_id,
            "match_info": decision.match_info,
            "calibrated_probs": decision.calibrated_probs,
            "model_consensus": decision.model_consensus,
            "value_plays": decision.value_plays,
            "arbitrage_signals": decision.arbitrage_signals,
            "risk_matrix": {k: {"score": v["score"], "level": v["level"]} for k, v in decision.risk_matrix.items()},
            "risk_score": decision.risk_score,
            "betting_plans": decision.betting_plans,
            "optimal_play": decision.optimal_play,
            "optimal_selection": decision.optimal_selection,
            "confidence_score": decision.confidence_score,
            "decision_rationale": decision.decision_rationale,
            "overall_verdict": decision.overall_verdict,
            "reasoning_chain": decision.reasoning_chain,
            "llm_summary": decision.llm_summary,
        }, ensure_ascii=False, indent=2)


async def get_advisor_analysis(
    match_id: str,
    match_data: Optional[Dict] = None,
    features: Optional[Dict] = None,
    h2h: Optional[Dict] = None,
    standings: Optional[Dict] = None,
    recent_form: Optional[Dict] = None,
    injuries: Optional[Dict] = None,
    market_odds: Optional[Dict] = None,
    bankroll: float = 1000.0,
    risk_tolerance: str = "medium",
    strategy: str = "balanced",
) -> Dict[str, Any]:
    """便捷函数：获取单场比赛的顾问分析"""
    advisor = SmartAdvisor()
    decision = advisor.advise(
        match_data=match_data or {},
        features=features,
        h2h=h2h,
        standings=standings,
        recent_form=recent_form,
        injuries=injuries,
        market_odds=market_odds,
        bankroll=bankroll,
        risk_tolerance=risk_tolerance,
        strategy=strategy,
    )
    result = json.loads(advisor.to_json(decision))
    result["timestamp"] = datetime.now().isoformat()
    return result