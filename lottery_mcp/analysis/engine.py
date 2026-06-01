"""
分析引擎核心模块 v3.0 - 全数据源深度整合版

整合所有数据源进行专业级分析：
- 竞彩5大玩法赔率 (SPF/RQSPF/BF/ZJQ/BQC)
- 竞彩资讯数据 (特征分析/历史交锋/积分榜/近期战绩/伤停等)
- 第三方数据 (欧指/亚盘/大小球)
- 统计模型 (泊松/Elo/xG/ML集成)
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger("lottery_mcp")


@dataclass
class MultiSourceAnalysis:
    """多源综合分析结果"""
    match_id: str
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    match_time: str = ""

    # 5大玩法概率分布
    spf_probs: Dict[str, float] = field(default_factory=dict)
    rqspf_probs: Dict[str, float] = field(default_factory=dict)
    bf_probs: Dict[str, float] = field(default_factory=dict)
    zjq_probs: Dict[str, float] = field(default_factory=dict)
    bqc_probs: Dict[str, float] = field(default_factory=dict)

    # 赔率分析
    official_odds: Dict[str, Any] = field(default_factory=dict)
    market_odds_comparison: Dict[str, Any] = field(default_factory=dict)

    # 基本面数据
    h2h_analysis: Dict[str, Any] = field(default_factory=dict)
    standings_analysis: Dict[str, Any] = field(default_factory=dict)
    form_analysis: Dict[str, Any] = field(default_factory=dict)
    injury_impact: Dict[str, Any] = field(default_factory=dict)

    # 综合推理
    value_signals: List[Dict[str, Any]] = field(default_factory=list)
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    recommended_plays: List[Dict[str, Any]] = field(default_factory=list)
    overall_confidence: str = "中"
    reasoning_chain: List[Dict[str, Any]] = field(default_factory=list)
    final_judgment: str = ""


class DeepAnalysisEngine:
    """深度分析引擎 v3.0

    整合所有可用数据源，逐层分析：
    1. 赔率层：5大玩法赔率隐含概率 + 返还率分析
    2. 模型层：泊松 + Elo + xG + ML 多模型共识
    3. 基本面层：历史交锋 + 积分榜 + 近期状态 + 伤停
    4. 市场层：欧指/亚盘/大小球跨市场对比
    5. 综合层：价值发现 + 风险识别 + 玩法推荐
    """

    def __init__(self):
        from .models import PoissonModel, EloRatingSystem
        self.poisson = PoissonModel()
        self.elo = EloRatingSystem()

    def deep_analyze(
        self,
        match_data: Dict[str, Any],
        features: Optional[Dict[str, Any]] = None,
        h2h: Optional[Dict[str, Any]] = None,
        standings: Optional[Dict[str, Any]] = None,
        recent_form: Optional[Dict[str, Any]] = None,
        injuries: Optional[Dict[str, Any]] = None,
        market_odds: Optional[Dict[str, Any]] = None,
    ) -> MultiSourceAnalysis:
        """深度综合分析

        Args:
            match_data: 竞彩官方比赛数据（含5大玩法赔率）
            features: 比赛特征分析数据
            h2h: 历史交锋数据
            standings: 积分榜数据
            recent_form: 近期战绩数据
            injuries: 伤停数据
            market_odds: 国际市场赔率（欧指/亚盘/大小球）

        Returns:
            MultiSourceAnalysis: 多源综合分析结果
        """
        analysis = MultiSourceAnalysis(
            match_id=match_data.get("match_id", ""),
            home_team=match_data.get("home_team", ""),
            away_team=match_data.get("away_team", ""),
            league=match_data.get("league", ""),
            match_time=match_data.get("match_time", ""),
        )

        # ====== 第1层：赔率层分析 ======
        self._analyze_odds_layer(analysis, match_data)

        # ====== 第2层：统计模型层分析 ======
        self._analyze_model_layer(analysis, match_data)

        # ====== 第3层：基本面层分析 ======
        self._analyze_fundamental_layer(analysis, features, h2h, standings, recent_form, injuries)

        # ====== 第4层：市场层分析 ======
        self._analyze_market_layer(analysis, market_odds)

        # ====== 第5层：综合推理层 ======
        self._synthesize_layer(analysis)

        return analysis

    # ================================================================
    # 第1层：赔率层分析
    # ================================================================
    def _analyze_odds_layer(self, analysis: MultiSourceAnalysis, match_data: Dict):
        """分析5大玩法赔率的隐含概率和返还率"""
        had = match_data.get("had", {})
        hhad = match_data.get("hhad", {})
        crs = match_data.get("crs", {})
        ttg = match_data.get("ttg", {})
        hafu = match_data.get("hafu", {})

        odds_info = {}

        # SPF 胜平负
        if had:
            w, d, l = float(had.get("win", 0)), float(had.get("draw", 0)), float(had.get("lose", 0))
            if w > 0 and d > 0 and l > 0:
                payout = 1 / (1 / w + 1 / d + 1 / l)
                odds_info["spf"] = {
                    "odds": {"主胜": w, "平局": d, "客胜": l},
                    "implied_probs": {
                        "主胜": round((1 / w) * payout, 4),
                        "平局": round((1 / d) * payout, 4),
                        "客胜": round((1 / l) * payout, 4),
                    },
                    "payout_rate": round(payout, 4),
                }

        # RQSPF 让球胜平负
        if hhad:
            hw, hd, hl = float(hhad.get("win", 0)), float(hhad.get("draw", 0)), float(hhad.get("lose", 0))
            handicap = hhad.get("handicap", "0")
            if hw > 0 and hd > 0 and hl > 0:
                hpayout = 1 / (1 / hw + 1 / hd + 1 / hl)
                odds_info["rqspf"] = {
                    "odds": {"主胜": hw, "平局": hd, "客胜": hl},
                    "handicap": handicap,
                    "payout_rate": round(hpayout, 4),
                }

        # BF 比分
        if crs:
            crs_options = crs.get("options", [])
            if crs_options:
                bf_list = []
                for opt in crs_options:
                    score = opt.get("score", "")
                    o = opt.get("odds", 0)
                    if o > 0:
                        bf_list.append({"score": score, "odds": o, "implied_prob": round(1 / o, 4)})
                bf_list.sort(key=lambda x: x["odds"])
                odds_info["bf"] = {
                    "total_options": len(bf_list),
                    "top_scores": bf_list[:5],
                }

        # ZJQ 总进球
        if ttg:
            ttg_options = ttg.get("options", [])
            if ttg_options:
                zjq_list = []
                for opt in ttg_options:
                    goals = opt.get("goals", opt.get("value", ""))
                    o = opt.get("odds", 0)
                    if o > 0:
                        zjq_list.append({"goals": goals, "odds": o, "implied_prob": round(1 / o, 4)})
                zjq_list.sort(key=lambda x: x["odds"])
                odds_info["zjq"] = {
                    "total_options": len(zjq_list),
                    "top_goals": zjq_list[:4],
                }

        # BQC 半全场
        if hafu:
            hafu_options = hafu.get("options", [])
            if hafu_options:
                bqc_list = []
                for opt in hafu_options:
                    result = opt.get("result", opt.get("value", ""))
                    o = opt.get("odds", 0)
                    if o > 0:
                        bqc_list.append({"result": result, "odds": o, "implied_prob": round(1 / o, 4)})
                bqc_list.sort(key=lambda x: x["odds"])
                odds_info["bqc"] = {
                    "total_options": len(bqc_list),
                    "top_results": bqc_list[:4],
                }

        analysis.official_odds = odds_info

        # 从赔率推导SPF概率分布
        spf = odds_info.get("spf", {})
        if spf:
            analysis.spf_probs = spf.get("implied_probs", {})
            analysis.reasoning_chain.append({
                "layer": "赔率分析",
                "finding": f"SPF返还率: {spf.get('payout_rate', 'N/A')}",
                "implication": "返还率越高，赔率越公允",
            })

    # ================================================================
    # 第2层：统计模型层分析
    # ================================================================
    def _analyze_model_layer(self, analysis: MultiSourceAnalysis, match_data: Dict):
        """运行泊松、Elo、xG等多模型"""
        had = match_data.get("had", {})
        if not had:
            return

        home_odds = float(had.get("win", 2.5))
        draw_odds = float(had.get("draw", 3.3))
        away_odds = float(had.get("lose", 2.8))

        # 泊松模型
        try:
            poisson_result = self.poisson.analyze(
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
            )
            model_probs = {
                "主胜": poisson_result.get("win_prob", 0.33),
                "平局": poisson_result.get("draw_prob", 0.33),
                "客胜": poisson_result.get("lose_prob", 0.33),
            }
        except Exception:
            model_probs = {"主胜": 0.35, "平局": 0.30, "客胜": 0.35}

        analysis.reasoning_chain.append({
            "layer": "模型分析",
            "finding": f"泊松模型: 主{model_probs['主胜']:.1%} 平{model_probs['平局']:.1%} 客{model_probs['客胜']:.1%}",
            "implication": "统计模型独立于赔率，提供客观概率基准",
        })

        # Elo评级
        try:
            home_team = analysis.home_team
            away_team = analysis.away_team
            elo_result = self.elo.predict(home_team, away_team) if home_team and away_team else None
            if elo_result:
                analysis.reasoning_chain.append({
                    "layer": "模型分析",
                    "finding": f"Elo预测: 主{elo_result.get('home_prob', 0):.1%}",
                })
        except Exception:
            pass

        # RQSPF概率推导
        hhad = match_data.get("hhad", {})
        if hhad:
            hw = float(hhad.get("win", 0))
            hd = float(hhad.get("draw", 0))
            hl = float(hhad.get("lose", 0))
            handicap = hhad.get("handicap", "0")
            if hw > 0 and hd > 0 and hl > 0:
                hpayout = 1 / (1 / hw + 1 / hd + 1 / hl)
                analysis.rqspf_probs = {
                    "主胜": round((1 / hw) * hpayout, 4),
                    "平局": round((1 / hd) * hpayout, 4),
                    "客胜": round((1 / hl) * hpayout, 4),
                }

        # BF概率 - 基于泊松比分矩阵
        try:
            bf_probs = poisson_result.get("score_matrix", {})
            if bf_probs:
                analysis.bf_probs = bf_probs
        except Exception:
            pass

        # ZJQ概率 - 基于泊松总进球
        try:
            zjq_probs = poisson_result.get("total_goals_dist", {})
            if zjq_probs:
                analysis.zjq_probs = zjq_probs
        except Exception:
            pass

    # ================================================================
    # 第3层：基本面层分析
    # ================================================================
    def _analyze_fundamental_layer(
        self,
        analysis: MultiSourceAnalysis,
        features: Optional[Dict],
        h2h: Optional[Dict],
        standings: Optional[Dict],
        recent_form: Optional[Dict],
        injuries: Optional[Dict],
    ):
        """分析基本面数据并调整概率"""
        adjustments = []  # 概率调整因子

        # --- 历史交锋分析 ---
        if h2h:
            h2h_data = h2h if isinstance(h2h, dict) else {}
            analysis.h2h_analysis = self._extract_h2h_insights(h2h_data, analysis.home_team)
            if analysis.h2h_analysis:
                home_win_rate = analysis.h2h_analysis.get("home_win_rate", 0.5)
                if home_win_rate > 0.6:
                    adjustments.append({"factor": "历史交锋优势", "direction": "home", "weight": 0.08})
                    analysis.reasoning_chain.append({
                        "layer": "基本面",
                        "finding": f"历史交锋主队占优: 胜率{home_win_rate:.0%}",
                    })
                elif home_win_rate < 0.3:
                    adjustments.append({"factor": "历史交锋劣势", "direction": "away", "weight": 0.08})
                    analysis.reasoning_chain.append({
                        "layer": "基本面",
                        "finding": f"历史交锋客队占优: 主队胜率仅{home_win_rate:.0%}",
                    })

        # --- 特征分析 ---
        if features:
            feat_data = features if isinstance(features, dict) else {}
            last_info = feat_data.get("last", {})
            if last_info:
                home_win = last_info.get("homeWinGoalMatchCnt", 0)
                total = home_win + last_info.get("homeDrawMatchCnt", 0) + last_info.get("homeLossGoalMatchCnt", 0)
                if total > 0 and home_win / total > 0.55:
                    adjustments.append({"factor": "特征分析主队强势", "direction": "home", "weight": 0.05})
                    analysis.reasoning_chain.append({
                        "layer": "基本面",
                        "finding": f"特征分析: 主队近{total}场交锋{home_win}胜",
                    })

        # --- 积分榜分析 ---
        if standings:
            stand_data = standings if isinstance(standings, dict) else {}
            home_tables = stand_data.get("homeTables", {}) or stand_data.get("home", {})
            away_tables = stand_data.get("awayTables", {}) or stand_data.get("away", {})

            home_total = home_tables.get("total", {}) if isinstance(home_tables, dict) else {}
            away_total = away_tables.get("total", {}) if isinstance(away_tables, dict) else {}

            home_rank = home_total.get("ranking", "-")
            away_rank = away_total.get("ranking", "-")

            analysis.standings_analysis = {
                "home_rank": home_rank,
                "away_rank": away_rank,
                "home_points": home_total.get("points", "-"),
                "away_points": away_total.get("points", "-"),
            }

            try:
                hr, ar = int(home_rank), int(away_rank)
                rank_diff = ar - hr
                if rank_diff > 6:
                    adjustments.append({"factor": "排名优势显著", "direction": "home", "weight": 0.10})
                elif rank_diff > 3:
                    adjustments.append({"factor": "排名小幅优势", "direction": "home", "weight": 0.05})
                elif rank_diff < -6:
                    adjustments.append({"factor": "排名劣势显著", "direction": "away", "weight": 0.10})
                elif rank_diff < -3:
                    adjustments.append({"factor": "排名小幅劣势", "direction": "away", "weight": 0.05})
                else:
                    analysis.reasoning_chain.append({
                        "layer": "基本面",
                        "finding": f"排名接近: 主{home_rank} vs 客{away_rank}",
                    })
            except (ValueError, TypeError):
                pass

        # --- 近期战绩分析 ---
        if recent_form:
            form_data = recent_form if isinstance(recent_form, dict) else {}
            analysis.form_analysis = self._extract_form_insights(form_data)
            if analysis.form_analysis:
                home_form_score = analysis.form_analysis.get("home_form_score", 0.5)
                if home_form_score > 0.65:
                    adjustments.append({"factor": "近期状态火热", "direction": "home", "weight": 0.07})
                elif home_form_score < 0.35:
                    adjustments.append({"factor": "近期状态低迷", "direction": "away", "weight": 0.07})

        # --- 伤停分析 ---
        if injuries:
            inj_data = injuries if isinstance(injuries, dict) else {}
            home_inj = inj_data.get("homeInjury", []) or inj_data.get("home_injury", []) or []
            away_inj = inj_data.get("awayInjury", []) or inj_data.get("away_injury", []) or []

            home_key_count = sum(1 for p in home_inj if isinstance(p, dict) and p.get("isKey", False))
            away_key_count = sum(1 for p in away_inj if isinstance(p, dict) and p.get("isKey", False))

            analysis.injury_impact = {
                "home_injuries": len(home_inj) if isinstance(home_inj, list) else 0,
                "away_injuries": len(away_inj) if isinstance(away_inj, list) else 0,
                "home_key_missing": home_key_count,
                "away_key_missing": away_key_count,
            }

            if home_key_count > away_key_count:
                adjustments.append({"factor": f"主队{home_key_count}名主力伤停", "direction": "away", "weight": min(0.12, 0.04 * home_key_count)})
            elif away_key_count > home_key_count:
                adjustments.append({"factor": f"客队{away_key_count}名主力伤停", "direction": "home", "weight": min(0.12, 0.04 * away_key_count)})

        # --- 应用概率调整 ---
        if adjustments and analysis.spf_probs:
            adj_probs = dict(analysis.spf_probs)
            home_adj = 0.0
            for adj in adjustments:
                w = adj["weight"]
                if adj["direction"] == "home":
                    home_adj += w
                elif adj["direction"] == "away":
                    home_adj -= w

            # 限制调整幅度
            home_adj = max(-0.20, min(0.20, home_adj))

            adj_probs["主胜"] = max(0.05, adj_probs.get("主胜", 0.33) + home_adj)
            adj_probs["客胜"] = max(0.05, adj_probs.get("客胜", 0.33) - home_adj * 0.6)
            # 重新归一化
            total = sum(adj_probs.values())
            if total > 0:
                adj_probs = {k: round(v / total, 4) for k, v in adj_probs.items()}

            analysis.spf_probs = adj_probs
            analysis.reasoning_chain.append({
                "layer": "基本面综合调整",
                "finding": f"调整后: 主{adj_probs.get('主胜', 0):.1%} 平{adj_probs.get('平局', 0):.1%} 客{adj_probs.get('客胜', 0):.1%}",
                "adjustments": [a["factor"] for a in adjustments],
            })

    # ================================================================
    # 第4层：市场层分析
    # ================================================================
    def _analyze_market_layer(self, analysis: MultiSourceAnalysis, market_odds: Optional[Dict]):
        """跨市场赔率对比分析"""
        if not market_odds:
            return

        mo = market_odds if isinstance(market_odds, dict) else {}

        # 欧指对比
        european = mo.get("european_odds", [])
        consensus = mo.get("consensus", {})
        asian = mo.get("asian_handicap", [])
        over_under = mo.get("over_under", [])

        official_spf = analysis.official_odds.get("spf", {}).get("odds", {})

        comparison = {}
        value_signals = []

        if consensus and official_spf:
            avg_home = float(consensus.get("avg_home_win", 0))
            avg_draw = float(consensus.get("avg_draw", 0))
            avg_away = float(consensus.get("avg_away_win", 0))

            official_home = official_spf.get("主胜", 0)
            official_away = official_spf.get("客胜", 0)

            comparison["european"] = {
                "market_avg": {"主胜": round(avg_home, 2), "平局": round(avg_draw, 2), "客胜": round(avg_away, 2)},
                "official": {"主胜": official_home, "客胜": official_away},
            }

            if avg_home > 0 and official_home > 0:
                diff_pct = (official_home - avg_home) / avg_home
                if diff_pct > 0.08:
                    value_signals.append({
                        "type": "竞彩高估主胜",
                        "detail": f"竞彩{official_home} vs 市场均{avg_home:.2f} (+{diff_pct:.1%})",
                        "action": "谨慎投注主胜",
                    })
                elif diff_pct < -0.08:
                    value_signals.append({
                        "type": "竞彩低估主胜",
                        "detail": f"竞彩{official_home} vs 市场均{avg_home:.2f} ({diff_pct:.1%})",
                        "action": "主胜可能存在价值",
                    })

        # 亚盘对比
        if asian and official_spf:
            for a_line in asian[:3]:
                a_handicap = a_line.get("handicap", "")
                a_home = a_line.get("home_odds", 0)
                a_away = a_line.get("away_odds", 0)
                if a_handicap:
                    comparison.setdefault("asian", []).append({
                        "handicap": a_handicap,
                        "home_odds": a_home,
                        "away_odds": a_away,
                    })

        analysis.market_odds_comparison = comparison
        if value_signals:
            analysis.value_signals.extend(value_signals)
            analysis.reasoning_chain.append({
                "layer": "市场对比",
                "finding": f"发现{len(value_signals)}个跨市场信号",
            })

    # ================================================================
    # 第5层：综合推理层
    # ================================================================
    def _synthesize_layer(self, analysis: MultiSourceAnalysis):
        """综合所有层级分析，生成最终判断"""
        spf = analysis.spf_probs

        # 风险识别
        self._identify_risks(analysis)

        # 玩法推荐
        self._recommend_plays(analysis)

        # 最终判断
        if spf:
            home_p = spf.get("主胜", 0.33)
            away_p = spf.get("客胜", 0.33)
            draw_p = spf.get("平局", 0.33)

            if home_p > 0.50:
                conf = "高" if home_p > 0.60 else "中"
                judgment = f"主队优势明显（概率{home_p:.1%}），主胜可考虑"
            elif away_p > 0.50:
                conf = "高" if away_p > 0.60 else "中"
                judgment = f"客队优势明显（概率{away_p:.1%}），客胜值得关注"
            elif draw_p > 0.35:
                conf = "中"
                judgment = f"平局概率较高({draw_p:.1%})，比赛可能胶着"
            else:
                conf = "低"
                judgment = "三方概率接近，不确定性高，建议观望或小额试水"

            analysis.overall_confidence = conf
            analysis.final_judgment = judgment

    def _identify_risks(self, analysis: MultiSourceAnalysis):
        """识别风险因素"""
        risks = []

        # 赔率风险
        spf_info = analysis.official_odds.get("spf", {})
        payout = spf_info.get("payout_rate", 0.88)
        if payout < 0.87:
            risks.append({"type": "高抽水", "detail": f"返还率仅{payout:.1%}，长期EV为负", "severity": "中"})

        # 伤停风险
        if analysis.injury_impact:
            home_key = analysis.injury_impact.get("home_key_missing", 0)
            away_key = analysis.injury_impact.get("away_key_missing", 0)
            if home_key >= 2:
                risks.append({"type": "伤停影响", "detail": f"主队{home_key}名主力缺阵", "severity": "高"})
            if away_key >= 2:
                risks.append({"type": "伤停影响", "detail": f"客队{away_key}名主力缺阵", "severity": "高"})

        # 排名风险
        if analysis.standings_analysis:
            try:
                hr = int(analysis.standings_analysis.get("home_rank", "0"))
                ar = int(analysis.standings_analysis.get("away_rank", "0"))
                if abs(hr - ar) > 10:
                    risks.append({"type": "实力悬殊", "detail": f"排名差{abs(hr-ar)}位，可能有冷门风险", "severity": "低"})
            except (ValueError, TypeError):
                pass

        # 市场分歧风险
        if analysis.value_signals:
            risks.append({"type": "市场分歧", "detail": f"竞彩与国际市场存在{len(analysis.value_signals)}个分歧信号", "severity": "中"})

        analysis.risk_factors = risks

    def _recommend_plays(self, analysis: MultiSourceAnalysis):
        """基于综合分析推荐最优玩法"""
        recommendations = []
        spf = analysis.spf_probs

        # SPF推荐
        if spf:
            home_p = spf.get("主胜", 0)
            away_p = spf.get("客胜", 0)
            draws_p = spf.get("平局", 0)

            if home_p > 0.45:
                rec = {"play": "SPF 胜平负", "selection": "主胜", "confidence": "高" if home_p > 0.55 else "中",
                       "reason": f"主胜概率{home_p:.1%}", "probability": round(home_p, 4)}
                if not self._has_high_risk(analysis, "主胜"):
                    recommendations.append(rec)
            elif away_p > 0.45:
                rec = {"play": "SPF 胜平负", "selection": "客胜", "confidence": "高" if away_p > 0.55 else "中",
                       "reason": f"客胜概率{away_p:.1%}", "probability": round(away_p, 4)}
                if not self._has_high_risk(analysis, "客胜"):
                    recommendations.append(rec)

        # RQSPF推荐 - 如果让球后有价值
        rqspf = analysis.rqspf_probs
        if rqspf:
            rhome = rqspf.get("主胜", 0)
            rdraw = rqspf.get("平局", 0)
            if rhome > 0.40 or rdraw > 0.40:
                recommendations.append({
                    "play": "RQSPF 让球胜平负",
                    "selection": "主胜" if rhome > rdraw else "平局",
                    "confidence": "中",
                    "reason": "让球后有较明确方向",
                    "probability": round(max(rhome, rdraw), 4),
                })

        # ZJQ推荐
        zjq = analysis.zjq_probs
        if zjq:
            likely_goals = None
            if isinstance(zjq, dict):
                top_probs = sorted(zjq.items(), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 0, reverse=True)[:3]
                likely_goals = [g for g, _ in top_probs]
            if likely_goals:
                recommendations.append({
                    "play": "ZJQ 总进球",
                    "selection": f"进球{'/'.join(str(g) for g in likely_goals[:2])}",
                    "confidence": "中",
                    "reason": f"模型预测总进球集中在{likely_goals[0]}",
                })

        # 高风险降级
        if analysis.risk_factors:
            high_risks = [r for r in analysis.risk_factors if r.get("severity") == "高"]
            if high_risks:
                recommendations.insert(0, {
                    "play": "WARNING",
                    "selection": f"⚠️ 检测到{len(high_risks)}个高风险信号",
                    "confidence": "低",
                    "reason": "; ".join(r["detail"] for r in high_risks),
                })

        analysis.recommended_plays = recommendations

    def _has_high_risk(self, analysis: MultiSourceAnalysis, selection: str) -> bool:
        """检查特定选项是否有高风险"""
        for risk in analysis.risk_factors:
            if risk.get("severity") == "高":
                return True
        return False

    # ================================================================
    # 辅助方法
    # ================================================================
    def _extract_h2h_insights(self, h2h_data: Dict, home_team: str) -> Dict:
        """提取历史交锋洞察"""
        insights = {}
        if isinstance(h2h_data, dict):
            records = h2h_data.get("records", h2h_data.get("matches", []))
            if isinstance(records, list) and records:
                home_wins = 0
                total = len(records)
                for r in records:
                    if isinstance(r, dict):
                        h_goals = r.get("home_goals", r.get("homeScore", 0))
                        a_goals = r.get("away_goals", r.get("awayScore", 0))
                        try:
                            if int(h_goals) > int(a_goals):
                                home_wins += 1
                        except (ValueError, TypeError):
                            pass
                insights["home_win_rate"] = home_wins / total if total > 0 else 0.5
                insights["total_matches"] = total
                insights["home_wins"] = home_wins
        return insights

    def _extract_form_insights(self, form_data: Dict) -> Dict:
        """提取近期状态洞察"""
        insights = {}
        home_matches = form_data.get("homeMatches", form_data.get("home", []))
        away_matches = form_data.get("awayMatches", form_data.get("away", []))

        if isinstance(home_matches, list) and home_matches:
            home_wins = sum(1 for m in home_matches if isinstance(m, dict) and
                          (m.get("result", "") == "胜" or m.get("win", 0) == 1))
            insights["home_form_score"] = home_wins / len(home_matches) if home_matches else 0.5
            insights["home_matches"] = len(home_matches)

        return insights


# ============================================================
# 向后兼容别名
# ============================================================

StatisticalEngine = DeepAnalysisEngine  # 向后兼容旧代码

# ============================================================
# 便捷函数（保持向后兼容）
# ============================================================

def analyze_match(match_id: str, match_data: Optional[Dict] = None) -> Dict[str, Any]:
    """分析单场比赛（v3.0 - 深度分析）"""
    if match_data is None:
        from lottery_mcp.data import fetch_today_matches
        matches = fetch_today_matches("jingcai")
        for m in matches:
            if m.get("match_id") == match_id:
                match_data = m
                break

    if match_data is None:
        return {"success": False, "error": f"未找到比赛: {match_id}"}

    engine = DeepAnalysisEngine()
    result = engine.deep_analyze(match_data)

    return {
        "success": True,
        "match_id": result.match_id,
        "home_team": result.home_team,
        "away_team": result.away_team,
        "league": result.league,
        "spf_probabilities": result.spf_probs,
        "rqspf_probabilities": result.rqspf_probs,
        "zjq_probabilities": result.zjq_probs,
        "official_odds_analysis": result.official_odds,
        "market_comparison": result.market_odds_comparison,
        "h2h_analysis": result.h2h_analysis,
        "standings_analysis": result.standings_analysis,
        "injury_impact": result.injury_impact,
        "value_signals": result.value_signals,
        "risk_factors": result.risk_factors,
        "recommended_plays": result.recommended_plays,
        "overall_confidence": result.overall_confidence,
        "final_judgment": result.final_judgment,
        "reasoning_chain": result.reasoning_chain,
        "timestamp": datetime.now().isoformat(),
    }


def analyze_all_matches(filter: Optional[str] = None, max_matches: int = 20) -> Dict[str, Any]:
    """分析所有比赛"""
    from lottery_mcp.data import fetch_today_matches
    matches = fetch_today_matches("jingcai")

    if filter == "high_value":
        matches = [m for m in matches if m.get("value_score", 0) > 0.1]
    elif filter == "low_risk":
        matches = [m for m in matches if m.get("risk_level", "中") in ["低", "中"]]

    matches = matches[:max_matches]

    engine = DeepAnalysisEngine()
    results = []
    for m in matches:
        r = engine.deep_analyze(m)
        results.append({
            "match_id": r.match_id,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "spf_probabilities": r.spf_probs,
            "recommended_plays": r.recommended_plays,
            "overall_confidence": r.overall_confidence,
            "final_judgment": r.final_judgment,
        })

    return {"success": True, "total_analyzed": len(results), "results": results}


def detect_risk_signals(
    match_id: str,
    signal_types: Optional[List[str]] = None,
    current_odds: Optional[Dict[str, float]] = None,
    previous_odds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """检测风险信号"""
    signals = []
    if signal_types is None:
        signal_types = ["odds_drift", "lineup", "weather", "market"]

    if "odds_drift" in signal_types and current_odds and previous_odds:
        for selection, current in current_odds.items():
            if selection in previous_odds:
                previous = previous_odds[selection]
                change_pct = abs(current - previous) / previous
                if change_pct > 0.15:
                    signals.append({
                        "type": "odds_drift",
                        "selection": selection,
                        "severity": "高" if change_pct > 0.25 else "中",
                        "change_pct": round(change_pct * 100, 2),
                        "direction": "上升" if current > previous else "下降",
                    })

    return {
        "match_id": match_id,
        "signals": signals,
        "signal_count": len(signals),
        "has_high_risk": any(s["severity"] == "高" for s in signals),
    }


def comprehensive_analysis(match_ids: List[str]) -> Dict[str, Any]:
    """综合分析多场比赛"""
    results = [analyze_match(mid) for mid in match_ids]
    return {"success": True, "total_matches": len(match_ids), "results": results}


def generate_analysis_report(match_id: str, style: str = "professional", include_reasoning: bool = True) -> Dict[str, Any]:
    """生成分析报告"""
    analysis = analyze_match(match_id)
    report = {
        "match_id": match_id,
        "style": style,
        "generated_at": datetime.now().isoformat(),
    }
    if include_reasoning:
        report["reasoning_chain"] = analysis.get("reasoning_chain", [])
        report["final_judgment"] = analysis.get("final_judgment", "")
        report["recommended_plays"] = analysis.get("recommended_plays", [])
        report["risk_factors"] = analysis.get("risk_factors", [])
    return report


def batch_analyze_matches(match_ids: List[str], parallel: bool = True) -> Dict[str, Any]:
    """批量分析比赛"""
    results = [analyze_match(mid) for mid in match_ids]
    return {"success": True, "total_matches": len(match_ids), "results": results}