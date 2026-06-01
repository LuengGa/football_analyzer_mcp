"""
比赛分析数据准备器 - 为 LLM 提供结构化的比赛分析数据

设计理念：
  本 MCP Server 的使用者本身就是 LLM（如 Claude），不需要 MCP 内部调用 LLM API。
  本模块的职责是：从原始比赛数据中提取、整理、结构化所有分析维度，
  以清晰的格式呈现给 LLM，让 LLM 自行完成推理和判断。

  LLM 拿到这些结构化数据后，可以：
  - 结合自身知识进行深度推理
  - 发现规则引擎无法捕捉的微妙模式
  - 给出更自然、更有洞察力的分析
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class MatchAnalysisData:
    """比赛分析数据 - 结构化呈现给 LLM 的完整分析素材"""

    # === 基本信息 ===
    match_id: str = ""
    match_name: str = ""
    league: str = ""
    match_time: str = ""

    # === 基本面数据 ===
    home_team: str = ""
    away_team: str = ""
    fundamentals: Dict = field(default_factory=dict)
    # 包含: home_rank, away_rank, home_win_rate, away_win_rate,
    #       home_injury_count, away_injury_count, home_injury_list, away_injury_list,
    #       home_net_goal, away_net_goal, home_recent_results, away_recent_results

    # === 竞彩赔率 ===
    jc_odds: Dict = field(default_factory=dict)
    # 包含: win(主胜), draw(平局), lose(客胜), handicap(让球数)
    # 以及 hhad(让球胜平负), crs(比分), ttg(总进球), hafu(半全场) 的赔率

    # === 国际市场数据 ===
    european_odds: List[Dict] = field(default_factory=list)
    # 每项: {bookmaker, home_win, draw, away_win}
    consensus: Dict = field(default_factory=dict)
    # 包含: avg_home_win, avg_draw, avg_away_win, max_home_win, min_home_win 等
    asian_handicap: List[Dict] = field(default_factory=list)
    # 每项: {bookmaker, home_handicap, home_odds, away_odds}

    # === 模型分析结果 ===
    model_analysis: Dict = field(default_factory=dict)
    # 包含: recommendation(推荐), statistical_models(泊松/Elo/xG),
    #       combined_score, agreement_level, risk_level

    # === 比赛特征画像 ===
    profile: Dict = field(default_factory=dict)
    # 包含: league_tier, odds_pattern, data_quality, tags,
    #       home_rank, away_rank, home_win_rate, away_win_rate,
    #       jc_vs_euro_diff, asian_handicap_line

    # === 价值发现结果 ===
    value_discovery: Dict = field(default_factory=dict)
    # 包含: 每个选项(主胜/平局/客胜)的 VR, EV, value_rating, signals, risk_factors

    # === 策略配置 ===
    strategy: Dict = field(default_factory=dict)
    # 包含: strategy_name, reasoning, low_odds_handling, value_threshold, 权重分配

    # === 数据完整度评估 ===
    data_completeness: Dict = field(default_factory=dict)
    # 包含: has_rank, has_form, has_injury, has_european_odds, has_asian_handicap,
    #       overall_quality, missing_items


class MatchDataPreparer:
    """
    比赛数据准备器

    职责：从原始比赛数据中提取、整理所有分析维度的结构化数据，
    供 LLM 进行推理判断。不做任何"AI推理"，只做数据整理。
    """

    @staticmethod
    def prepare(match_data: Dict, profile: Any = None,
                value_results: Dict = None, strategy: Any = None) -> MatchAnalysisData:
        """
        从原始比赛数据准备完整的结构化分析数据

        Args:
            match_data: 原始比赛数据（来自竞彩网API）
            profile: MatchProfiler 生成的比赛特征画像（可选）
            value_results: 价值发现结果（可选）
            strategy: StrategySelector 生成的策略配置（可选）

        Returns:
            MatchAnalysisData 结构化分析数据
        """
        data = MatchAnalysisData()

        # === 基本信息 ===
        data.match_id = match_data.get("match_id", "")
        data.home_team = match_data.get("home_team", "")
        data.away_team = match_data.get("away_team", "")
        data.match_name = match_data.get("match_name", "") or f"{data.home_team} vs {data.away_team}"
        data.league = match_data.get("league", "")
        data.match_time = match_data.get("match_time", "")

        # === 基本面数据 ===
        data.fundamentals = match_data.get("fundamentals", {})

        # === 竞彩赔率 ===
        # 竞彩API返回的赔率数据可能在顶层（had/hhad/crs/ttg/hafu），而非嵌套在 odds 下
        odds = match_data.get("odds", {})
        if not odds:
            odds = {}
            if match_data.get("had"):
                odds["had"] = match_data["had"]
            if match_data.get("hhad"):
                odds["hhad"] = match_data["hhad"]
            if match_data.get("crs"):
                odds["crs"] = match_data["crs"]
            if match_data.get("ttg"):
                odds["ttg"] = match_data["ttg"]
            if match_data.get("hafu"):
                odds["hafu"] = match_data["hafu"]
        data.jc_odds = MatchDataPreparer._extract_jc_odds(odds)

        # === 国际市场数据 ===
        data.european_odds = match_data.get("european_odds", [])
        data.consensus = match_data.get("consensus", {})
        data.asian_handicap = match_data.get("asian_handicap", [])

        # === 模型分析结果 ===
        data.model_analysis = MatchDataPreparer._extract_model_analysis(match_data)

        # === 比赛特征画像 ===
        if profile:
            data.profile = {
                "league_tier": profile.league_tier.value,
                "odds_pattern": profile.odds_pattern.value,
                "data_quality": profile.data_quality.value,
                "tags": profile.tags,
                "home_rank": profile.home_rank,
                "away_rank": profile.away_rank,
                "home_win_rate": profile.home_win_rate,
                "away_win_rate": profile.away_win_rate,
                "home_injury_count": profile.home_injury_count,
                "away_injury_count": profile.away_injury_count,
                "jc_vs_euro_diff": round(profile.jc_vs_euro_diff, 3),
                "asian_handicap_line": profile.asian_handicap_line,
            }

        # === 价值发现结果 ===
        if value_results:
            data.value_discovery = value_results

        # === 策略配置 ===
        if strategy:
            data.strategy = {
                "strategy_name": strategy.strategy_name,
                "reasoning": strategy.reasoning,
                "low_odds_handling": strategy.low_odds_handling,
                "low_odds_threshold": strategy.low_odds_threshold,
                "value_threshold": strategy.value_threshold,
                "weights": {
                    "fundamentals": round(strategy.fundamentals_weight, 2),
                    "market_odds": round(strategy.market_odds_weight, 2),
                    "model": round(strategy.model_weight, 2),
                    "jc_odds": round(strategy.jc_odds_weight, 2),
                },
                "max_selections_per_play": strategy.max_selections_per_play,
                "max_parlay_size": strategy.max_parlay_size,
            }

        # === 数据完整度评估 ===
        data.data_completeness = MatchDataPreparer._assess_data_completeness(
            match_data, profile
        )

        return data

    @staticmethod
    def _extract_jc_odds(odds: Dict) -> Dict:
        """提取竞彩赔率，统一格式"""
        result = {}

        # 胜平负
        had = odds.get("had", {})
        if had:
            result["spf"] = {
                "主胜": float(had.get("win", 0) or 0),
                "平局": float(had.get("draw", 0) or 0),
                "客胜": float(had.get("lose", 0) or 0),
            }
        else:
            w = odds.get("win") or odds.get("had_w")
            d = odds.get("draw") or odds.get("had_d")
            l = odds.get("lose") or odds.get("had_l")
            if w and d and l:
                result["spf"] = {
                    "主胜": float(w),
                    "平局": float(d),
                    "客胜": float(l),
                }

        # 让球胜平负
        hhad = odds.get("hhad", {})
        if hhad:
            result["rqspf"] = {
                "让球数": hhad.get("handicap", "0"),
                "让球主胜": float(hhad.get("win", 0) or 0),
                "让球平局": float(hhad.get("draw", 0) or 0),
                "让球客胜": float(hhad.get("lose", 0) or 0),
            }

        # 比分
        crs = odds.get("crs", {})
        if crs:
            if isinstance(crs, dict) and "options" in crs:
                result["bf"] = {
                    opt.get("score", ""): float(opt.get("odds", 0) or 0)
                    for opt in crs["options"]
                    if opt.get("odds", 0)
                }
            elif isinstance(crs, dict):
                result["bf"] = {
                    k: float(v) for k, v in crs.items()
                    if isinstance(v, (int, float, str)) and str(v).replace(".", "").isdigit()
                }

        # 总进球
        ttg = odds.get("ttg", {})
        if ttg:
            result["zjq"] = {}
            for goal_count in range(8):
                key = f"goals_{goal_count}"
                val = ttg.get(key) or ttg.get(f"ttg_{goal_count}")
                if val:
                    result["zjq"][f"{goal_count}球"] = float(val)

        # 半全场
        hafu = odds.get("hafu", {})
        if hafu:
            result["bqc"] = {}
            for combo in ["胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负"]:
                val = hafu.get(combo)
                if val:
                    result["bqc"][combo] = float(val)

        return result

    @staticmethod
    def _extract_model_analysis(match_data: Dict) -> Dict:
        """提取模型分析结果"""
        analysis = match_data.get("analysis", {})
        if not analysis:
            return {}

        result = {}

        # 推荐结果
        rec = analysis.get("recommendation", {})
        if rec:
            result["recommendation"] = {
                "pick": rec.get("pick", ""),
                "probability": rec.get("probability", 0),
                "confidence": rec.get("confidence", ""),
                "implied_probs": rec.get("implied_probs", {}),
            }

        # 统计模型
        models = analysis.get("statistical_models", {})
        if models:
            result["models"] = {}
            for model_name, model_data in models.items():
                if isinstance(model_data, dict):
                    result["models"][model_name] = {
                        k: v for k, v in model_data.items()
                        if k not in ("score_probabilities",)  # 排除过大的数据
                    }

        # 综合评分
        if analysis.get("combined_score"):
            result["combined_score"] = analysis["combined_score"]
        if analysis.get("agreement_level"):
            result["agreement_level"] = analysis["agreement_level"]
        if analysis.get("risk_level"):
            result["risk_level"] = analysis["risk_level"]

        return result

    @staticmethod
    def _assess_data_completeness(match_data: Dict, profile: Any = None) -> Dict:
        """评估数据完整度"""
        completeness = {
            "has_rank": False,
            "has_form": False,
            "has_injury": False,
            "has_european_odds": False,
            "has_asian_handicap": False,
            "has_model_analysis": False,
            "has_consensus": False,
            # 赔率数据完整性指标
            "has_spf_odds": False,
            "has_rqspf_odds": False,
            "has_crs_odds": False,
            "has_ttg_odds": False,
            "has_hafu_odds": False,
        }

        fundamentals = match_data.get("fundamentals", {})
        completeness["has_rank"] = bool(fundamentals.get("home_rank", 0))
        completeness["has_form"] = bool(fundamentals.get("home_win_rate", 0))
        completeness["has_injury"] = bool(
            fundamentals.get("home_injury_count") is not None
            or fundamentals.get("home_injury_list")
        )
        completeness["has_european_odds"] = bool(match_data.get("european_odds"))
        completeness["has_asian_handicap"] = bool(match_data.get("asian_handicap"))
        completeness["has_model_analysis"] = bool(match_data.get("analysis"))
        completeness["has_consensus"] = bool(match_data.get("consensus"))

        # 赔率数据完整性检查（从顶层检查，兼容竞彩API直接返回的格式）
        had = match_data.get("had", {})
        if had and had.get("win") and had.get("draw") and had.get("lose"):
            completeness["has_spf_odds"] = True
        if match_data.get("hhad"):
            completeness["has_rqspf_odds"] = True
        if match_data.get("crs"):
            completeness["has_crs_odds"] = True
        if match_data.get("ttg"):
            completeness["has_ttg_odds"] = True
        if match_data.get("hafu"):
            completeness["has_hafu_odds"] = True

        # 计算总体质量（基础指标 + 赔率指标共同决定）
        available = sum(1 for v in completeness.values() if v)
        total = len(completeness)

        # 额外提升：如果赔率数据覆盖全面（5种玩法都有），直接提升质量等级
        odds_available = sum(1 for k in completeness
                             if k.startswith("has_") and k.endswith("_odds") and completeness[k])
        has_full_odds = odds_available >= 5
        has_model = completeness["has_model_analysis"]

        if available >= 10:
            quality = "完整"
        elif available >= 7:
            quality = "较好"
        elif available >= 4 or (has_full_odds and has_model):
            quality = "部分"
        else:
            quality = "不足"

        # 列出缺失项
        missing = [
            name for name, has in completeness.items()
            if not has
        ]

        completeness["overall_quality"] = quality
        completeness["available_count"] = available
        completeness["total_count"] = total
        completeness["missing_items"] = missing

        return completeness

    @staticmethod
    def to_dict(data: MatchAnalysisData) -> Dict:
        """转换为字典（用于 JSON 序列化）"""
        import dataclasses
        return dataclasses.asdict(data)

    @staticmethod
    def to_llm_context(data: MatchAnalysisData) -> str:
        """
        生成给 LLM 的结构化文本上下文

        这个方法生成一段结构化的文本，嵌入到 MCP tool 返回值中，
        让 LLM 能快速理解比赛全貌并自行推理。
        """
        lines = []
        lines.append(f"## 比赛: {data.match_name}")
        lines.append(f"联赛: {data.league} | 时间: {data.match_time}")
        lines.append("")

        # 基本面
        fund = data.fundamentals
        if fund:
            lines.append("### 基本面")
            if fund.get("home_rank") and fund.get("away_rank"):
                lines.append(f"- 排名: {data.home_team}第{fund['home_rank']}名 vs {data.away_team}第{fund['away_rank']}名")
            if fund.get("home_win_rate") and fund.get("away_win_rate"):
                lines.append(f"- 近期胜率: {data.home_team}{fund['home_win_rate']:.0%} vs {data.away_team}{fund['away_win_rate']:.0%}")
            if fund.get("home_injury_count"):
                lines.append(f"- {data.home_team}伤停: {fund['home_injury_count']}人")
            if fund.get("away_injury_count"):
                lines.append(f"- {data.away_team}伤停: {fund['away_injury_count']}人")
            lines.append("")

        # 竞彩赔率
        spf = data.jc_odds.get("spf", {})
        if spf:
            lines.append("### 竞彩赔率")
            lines.append(f"- 胜平负: 主胜{spf.get('主胜', 0):.2f} / 平局{spf.get('平局', 0):.2f} / 客胜{spf.get('客胜', 0):.2f}")
        rqspf = data.jc_odds.get("rqspf", {})
        if rqspf:
            lines.append(f"- 让球胜平负(让{rqspf.get('让球数', 0)}球): 让球主胜{rqspf.get('让球主胜', 0):.2f} / 让球平局{rqspf.get('让球平局', 0):.2f} / 让球客胜{rqspf.get('让球客胜', 0):.2f}")
        lines.append("")

        # 国际市场
        if data.consensus:
            c = data.consensus
            lines.append("### 国际市场(欧指均値)")
            lines.append(f"- 主胜{c.get('avg_home_win', 0):.2f} / 平局{c.get('avg_draw', 0):.2f} / 客胜{c.get('avg_away_win', 0):.2f}")
        if data.asian_handicap:
            ah = data.asian_handicap[0]
            lines.append(f"- 亚盘: 主让{ah.get('home_handicap', 0)}球 (主{ah.get('home_odds', 0):.2f} / 客{ah.get('away_odds', 0):.2f})")
        lines.append("")

        # 竞彩vs欧指差异
        if data.profile.get("jc_vs_euro_diff"):
            diff = data.profile["jc_vs_euro_diff"]
            if abs(diff) > 0.05:
                direction = "偏高" if diff > 0 else "偏低"
                lines.append(f"### 赔率差异")
                lines.append(f"- 竞彩主胜赔率相对欧指{direction}{abs(diff):.2f}")
                lines.append("")

        # 比赛特征
        if data.profile:
            lines.append("### 比赛特征")
            lines.append(f"- 联赛级别: {data.profile.get('league_tier', '未知')}")
            lines.append(f"- 赔率形态: {data.profile.get('odds_pattern', '未知')}")
            lines.append(f"- 标签: {', '.join(data.profile.get('tags', []))}")
            lines.append("")

        # 策略
        if data.strategy:
            lines.append("### 当前策略")
            lines.append(f"- 策略: {data.strategy.get('strategy_name', '默认')}")
            lines.append(f"- 依据: {data.strategy.get('reasoning', '')}")
            lines.append("")

        # 价值发现
        if data.value_discovery:
            lines.append("### 价值发现")
            vd = data.value_discovery
            if isinstance(vd, dict):
                for selection, info in vd.items():
                    if isinstance(info, dict):
                        rating = info.get("value_rating", "N")
                        vr = info.get("value_ratio", 0)
                        ev = info.get("expected_value", 0)
                        signals = info.get("signals", [])
                        signal_str = "; ".join(
                            f"{s.get('type', '')}({s.get('description', '')})"
                            for s in signals[:3]
                        )
                        lines.append(f"- {selection}: 评级{rating}, VR={vr:.2f}, EV={ev:+.3f}")
                        if signal_str:
                            lines.append(f"  信号: {signal_str}")
            lines.append("")

        # 数据完整度
        dc = data.data_completeness
        if dc:
            lines.append("### 数据完整度")
            lines.append(f"- 总体: {dc.get('overall_quality', '未知')} ({dc.get('available_count', 0)}/{dc.get('total_count', 0)})")
            if dc.get("missing_items"):
                lines.append(f"- 缺失: {', '.join(dc['missing_items'])}")
            lines.append("")

        return "\n".join(lines)


def batch_prepare(match_data_list: List[Dict],
                  profile_map: Dict = None,
                  value_map: Dict = None,
                  strategy_map: Dict = None) -> List[MatchAnalysisData]:
    """批量准备多个比赛的分析数据"""
    results = []
    for match_data in match_data_list:
        match_id = match_data.get("match_id", "")
        profile = profile_map.get(match_id) if profile_map else None
        value_results = value_map.get(match_id) if value_map else None
        strategy = strategy_map.get(match_id) if strategy_map else None

        data = MatchDataPreparer.prepare(
            match_data, profile, value_results, strategy
        )
        results.append(data)
    return results


# ============================================================
# 向后兼容：保留 AIInsight 接口
# ============================================================

@dataclass
class AIInsight:
    """AI分析洞察 - 向后兼容接口

    注意：此接口已废弃，新代码应直接使用 MatchAnalysisData。
    保留此接口仅为确保 betting_tools.py 中的调用不会中断。
    内部实现已改为调用 MatchDataPreparer。
    """
    match_id: str = ""
    match_name: str = ""
    match_summary: str = ""
    key_factors: List[str] = field(default_factory=list)
    odds_analysis: str = ""
    value_opportunities: List[str] = field(default_factory=list)
    risk_assessment: str = ""
    risk_factors: List[str] = field(default_factory=list)
    strategy_advice: str = ""
    recommended_plays: List[str] = field(default_factory=list)
    confidence_level: str = "中"
    betting_suggestion: str = ""
    suggested_stake: str = ""
    reasoning: str = ""
    model_used: str = "data_preparer"
    # 新增：结构化数据，供 LLM 深度分析
    structured_data: Dict = field(default_factory=dict)


class AIAnalyzer:
    """分析器 - 向后兼容接口

    内部已重构为数据准备器，不再模拟 AI 推理。
    返回的 AIInsight 包含结构化数据字段（structured_data），
    LLM 可直接使用这些数据进行推理。
    """

    @staticmethod
    def analyze_match(match_data: Dict, profile: Any = None) -> AIInsight:
        """
        准备比赛分析数据，返回结构化结果供 LLM 推理

        不再模拟 AI 分析，而是提取所有维度的结构化数据，
        让使用此 MCP 的 LLM 自行完成推理。
        """
        # 使用新的数据准备器
        prepared = MatchDataPreparer.prepare(match_data, profile)

        # 构建向后兼容的 AIInsight
        insight = AIInsight()
        insight.match_id = prepared.match_id
        insight.match_name = prepared.match_name
        insight.structured_data = MatchDataPreparer.to_dict(prepared)

        # 从结构化数据生成简要摘要（供快速参考，LLM 应以 structured_data 为准）
        insight.match_summary = AIAnalyzer._build_summary(prepared)
        insight.key_factors = AIAnalyzer._extract_key_factors(prepared)
        insight.odds_analysis = AIAnalyzer._build_odds_summary(prepared)
        insight.value_opportunities = AIAnalyzer._extract_value_opps(prepared)
        insight.risk_assessment, insight.risk_factors = AIAnalyzer._assess_risks(prepared)
        insight.strategy_advice = AIAnalyzer._build_strategy_note(prepared)
        insight.recommended_plays = AIAnalyzer._suggest_plays(prepared)
        insight.confidence_level = AIAnalyzer._assess_confidence(prepared)
        insight.betting_suggestion, insight.suggested_stake = AIAnalyzer._build_suggestion(prepared)
        insight.reasoning = MatchDataPreparer.to_llm_context(prepared)

        return insight

    @staticmethod
    def _build_summary(data: MatchAnalysisData) -> str:
        """构建简要比赛摘要"""
        parts = [f"{data.league}：{data.match_name}"]

        profile = data.profile
        if profile:
            parts.append(f"（{profile.get('league_tier', '')}联赛，{profile.get('odds_pattern', '')}）")

        fund = data.fundamentals
        if fund.get("home_rank") and fund.get("away_rank"):
            hr, ar = fund["home_rank"], fund["away_rank"]
            if abs(hr - ar) >= 8:
                stronger = data.home_team if hr < ar else data.away_team
                parts.append(f"，{stronger}排名领先")
            elif abs(hr - ar) <= 3:
                parts.append("，排名接近")

        return "".join(parts)

    @staticmethod
    def _extract_key_factors(data: MatchAnalysisData) -> List[str]:
        """提取关键因素（数据点，不是判断）"""
        factors = []
        fund = data.fundamentals
        profile = data.profile

        if fund.get("home_rank") and fund.get("away_rank"):
            factors.append(f"排名: {data.home_team}第{fund['home_rank']} vs {data.away_team}第{fund['away_rank']}")
        if fund.get("home_win_rate"):
            factors.append(f"{data.home_team}近期胜率{fund['home_win_rate']:.0%}")
        if fund.get("away_win_rate"):
            factors.append(f"{data.away_team}近期胜率{fund['away_win_rate']:.0%}")
        if fund.get("home_injury_count", 0) > 0:
            factors.append(f"{data.home_team}伤停{fund['home_injury_count']}人")
        if fund.get("away_injury_count", 0) > 0:
            factors.append(f"{data.away_team}伤停{fund['away_injury_count']}人")
        if data.consensus:
            factors.append("有欧指参考")
        if data.asian_handicap:
            factors.append(f"亚盘主让{data.asian_handicap[0].get('home_handicap', 0)}球")
        if profile and profile.get("jc_vs_euro_diff", 0) > 0.1:
            factors.append(f"竞彩主胜赔率高于欧指{profile['jc_vs_euro_diff']:.2f}")

        return factors

    @staticmethod
    def _build_odds_summary(data: MatchAnalysisData) -> str:
        """构建赔率摘要（数据呈现，不做判断）"""
        parts = []
        spf = data.jc_odds.get("spf", {})
        if spf:
            parts.append(f"竞彩: 主胜{spf.get('主胜', 0):.2f}/平局{spf.get('平局', 0):.2f}/客胜{spf.get('客胜', 0):.2f}")

        if data.consensus:
            c = data.consensus
            parts.append(f"欧指均值: 主胜{c.get('avg_home_win', 0):.2f}/平局{c.get('avg_draw', 0):.2f}/客胜{c.get('avg_away_win', 0):.2f}")

        return " | ".join(parts) if parts else "赔率数据不足"

    @staticmethod
    def _extract_value_opps(data: MatchAnalysisData) -> List[str]:
        """提取价值机会（数据呈现）"""
        opps = []
        vd = data.value_discovery
        if not vd or not isinstance(vd, dict):
            return opps

        for selection, info in vd.items():
            if isinstance(info, dict):
                rating = info.get("value_rating", "N")
                vr = info.get("value_ratio", 0)
                ev = info.get("expected_value", 0)
                if rating in ("S", "A") or vr > 1.1:
                    opps.append(f"{selection}: 评级{rating}, VR={vr:.2f}, EV={ev:+.3f}")

        return opps if opps else ["结构化数据已准备，请自行分析价值"]

    @staticmethod
    def _assess_risks(data: MatchAnalysisData) -> tuple:
        """列出已知风险因素（数据呈现）"""
        risks = []
        dc = data.data_completeness

        if dc.get("missing_items"):
            missing = dc["missing_items"]
            name_map = {
                "has_rank": "排名数据",
                "has_form": "近期战绩",
                "has_injury": "伤停信息",
                "has_european_odds": "欧指数据",
                "has_asian_handicap": "亚盘数据",
                "has_model_analysis": "模型分析",
                "has_consensus": "共识赔率",
            }
            for item in missing:
                risks.append(f"缺少{name_map.get(item, item)}")

        fund = data.fundamentals
        if fund.get("home_injury_count", 0) >= 3:
            risks.append(f"{data.home_team}伤停严重({fund['home_injury_count']}人)")
        if fund.get("away_injury_count", 0) >= 3:
            risks.append(f"{data.away_team}伤停严重({fund['away_injury_count']}人)")

        spf = data.jc_odds.get("spf", {})
        if spf and spf.get("主胜", 99) < 1.4:
            risks.append("主胜赔率极低(<1.4)")

        if not risks:
            assessment = "已知风险因素较少"
        elif len(risks) <= 2:
            assessment = "存在部分风险因素"
        else:
            assessment = "风险因素较多，需谨慎"

        return assessment, risks

    @staticmethod
    def _build_strategy_note(data: MatchAnalysisData) -> str:
        """构建策略说明"""
        strategy = data.strategy
        if not strategy:
            return "使用默认策略"

        return f"{strategy.get('strategy_name', '默认')}：{strategy.get('reasoning', '')}"

    @staticmethod
    def _suggest_plays(data: MatchAnalysisData) -> List[str]:
        """建议关注的玩法（基于数据特征）"""
        plays = []
        profile = data.profile

        if not profile:
            return ["胜平负"]

        pattern = profile.get("odds_pattern", "")
        if pattern == "均势":
            plays = ["胜平负", "总进球"]
        elif pattern in ("深盘主让", "深盘客让"):
            plays = ["让球胜平负", "总进球"]
        else:
            plays = ["胜平负"]

        # 如果有比分赔率数据，也建议关注
        if data.jc_odds.get("bf"):
            plays.append("比分")

        return plays

    @staticmethod
    def _assess_confidence(data: MatchAnalysisData) -> str:
        """基于数据完整度评估分析可信度"""
        dc = data.data_completeness
        quality = dc.get("overall_quality", "不足")

        if quality == "完整":
            return "高"
        elif quality in ("较好", "部分"):
            return "中"
        else:
            return "低"

    @staticmethod
    def _build_suggestion(data: MatchAnalysisData) -> tuple:
        """构建投注建议框架（不做具体推荐，留给 LLM 判断）"""
        dc = data.data_completeness
        quality = dc.get("overall_quality", "不足")

        if quality == "完整":
            return "数据完整，可进行多维度分析", "参考模型推荐"
        elif quality == "较好":
            return "数据较好，可适度分析", "参考模型推荐"
        elif quality == "部分":
            return "数据部分缺失，分析需谨慎", "降低预期"
        else:
            return "数据不足，建议谨慎", "以竞彩赔率为主要参考"


def batch_analyze(match_data_list: List[Dict],
                  profile_map: Dict = None) -> List[AIInsight]:
    """批量准备多个比赛的分析数据"""
    results = []
    for match_data in match_data_list:
        match_id = match_data.get("match_id", "")
        profile = profile_map.get(match_id) if profile_map else None
        insight = AIAnalyzer.analyze_match(match_data, profile)
        results.append(insight)
    return results


# 导出模块接口
__all__ = [
    "MatchDataPreparer",
    "MatchAnalysisData",
    "AIAnalyzer",
    "AIInsight",
    "batch_analyze",
    "batch_prepare",
]
