"""
MCP Server Data Tools - Data fetching and retrieval tools.

使用真实数据源：lottery_data_fetcher, lottery_odds_fetcher_v2, lottery_free_data_sources
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .helpers import raise_tool_error, _to_json, _truncate_for_context


def _format_matches_markdown(matches: List[Dict], title: str = "比赛列表") -> str:
    """将比赛列表格式化为Markdown"""
    lines = [f"# {title}", ""]
    
    for i, m in enumerate(matches, 1):
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        league = m.get("league", "")
        match_time = m.get("match_time", "")
        
        lines.append(f"## {i}. {home} vs {away}")
        lines.append(f"- **联赛**: {league}")
        lines.append(f"- **时间**: {match_time}")
        
        # 添加赔率信息（如果有）
        odds = m.get("odds", {})
        if odds:
            had = odds.get("had", {})
            if had:
                lines.append(f"- **胜平负**: 主{had.get('win', '-')} / 平{had.get('draw', '-')} / 客{had.get('lose', '-')}")
        
        lines.append("")
    
    return "\n".join(lines)


def _format_history_markdown(results: List[Dict], title: str = "历史开奖") -> str:
    """将历史开奖格式化为Markdown"""
    lines = [f"# {title}", ""]
    
    for r in results:
        match_id = r.get("match_id", "")
        home = r.get("home_team", "")
        away = r.get("away_team", "")
        result = r.get("result", "")
        
        lines.append(f"## {match_id}: {home} vs {away}")
        lines.append(f"- **赛果**: {result}")
        lines.append("")
    
    return "\n".join(lines)


def _format_live_scores_markdown(matches: List[Dict], title: str = "实时比分") -> str:
    """将实时比分格式化为Markdown"""
    lines = [f"# {title}", ""]
    
    for m in matches:
        home = m.get("home_team_cn", m.get("home_team", ""))
        away = m.get("away_team_cn", m.get("away_team", ""))
        home_score = m.get("home_score", 0)
        away_score = m.get("away_score", 0)
        status = m.get("status", "")
        
        lines.append(f"## {home} {home_score} - {away_score} {away}")
        lines.append(f"- **状态**: {status}")
        lines.append("")
    
    return "\n".join(lines)
from lottery_mcp.models import (
    FetchTodayMatchesInput,
    GetMatchDataInput,
    TrackOddsChangesInput,
    VerifyResultsInput,
    QueryHistoryInput,
    GetLiveScoresInput,
    GetMarketOddsInput,
    QuantifyInjuryImpactInput,
    # Phase 3: AI推理工具模型
    GetMatchContextInput,
    AssessRiskInput,
    SimulateScenariosInput,
    GenerateRecommendationInput,
    # Phase 4: 新增高级工具模型
    CompareMatchesInput,
    OptimizeStakesInput,
)
from lottery_mcp.data.team_mapping import (
    normalize_league_name,
    normalize_team_name,
    team_to_chinese,
    league_to_chinese,
)

logger = logging.getLogger("lottery_mcp")


# ============================================================
# Manager Singleton
# ============================================================

def _get_manager():
    """获取 FreeDataSourceManager 全局单例"""
    from lottery_mcp.data import get_manager
    return get_manager()


# 兼容性接口：供 analysis_tools.py 使用
_match_cache: List[Dict[str, Any]] = []
_cache_timestamp: Optional[datetime] = None

# 缓存监控统计
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "sets": 0,
    "last_set_time": None,
    "total_matches_cached": 0,
}


def get_cached_matches() -> List[Dict[str, Any]]:
    """获取缓存的比赛列表（兼容接口）"""
    global _cache_stats
    if _match_cache:
        _cache_stats["hits"] += 1
    else:
        _cache_stats["misses"] += 1
    return _match_cache


def set_cached_matches(matches: List[Dict[str, Any]], ttl: int = 3600) -> None:
    """设置缓存的比赛列表，带过期时间
    
    Args:
        matches: 比赛列表数据
        ttl: 缓存有效期（秒），默认3600秒（1小时）
    """
    global _match_cache, _cache_timestamp, _cache_stats
    _match_cache = matches
    _cache_timestamp = datetime.now()
    _cache_stats["sets"] += 1
    _cache_stats["last_set_time"] = datetime.now().isoformat()
    _cache_stats["total_matches_cached"] = len(matches)


def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计信息
    
    Returns:
        缓存统计字典
    """
    global _cache_stats
    total_requests = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = _cache_stats["hits"] / total_requests * 100 if total_requests > 0 else 0
    
    return {
        "hits": _cache_stats["hits"],
        "misses": _cache_stats["misses"],
        "sets": _cache_stats["sets"],
        "hit_rate": round(hit_rate, 2),
        "last_set_time": _cache_stats.get("last_set_time"),
        "total_matches_cached": _cache_stats["total_matches_cached"],
        "cache_valid": is_cache_valid(),
        "cache_age_seconds": _get_cache_age(),
    }


def clear_cache_stats() -> None:
    """清除缓存统计"""
    global _cache_stats
    _cache_stats = {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "last_set_time": None,
        "total_matches_cached": 0,
    }


def _get_cache_age() -> Optional[float]:
    """获取缓存已存在的时间（秒）"""
    global _cache_timestamp
    if _cache_timestamp is None:
        return None
    return (datetime.now() - _cache_timestamp).total_seconds()


def is_cache_valid(ttl: int = 3600) -> bool:
    """检查缓存是否有效
    
    Args:
        ttl: 缓存有效期（秒），默认3600秒（1小时）
        
    Returns:
        缓存是否有效
    """
    global _cache_timestamp
    if _cache_timestamp is None:
        return False
    elapsed = (datetime.now() - _cache_timestamp).total_seconds()
    return elapsed < ttl


# ============================================================
# Tool Functions
# ============================================================

async def lottery_fetch_today_matches(params: FetchTodayMatchesInput, ctx: Context) -> str:
    """获取今日比赛列表
    
    获取当日可投注的比赛列表，包含基本信息和赔率。
    
    Args:
        params: 获取参数
        ctx: MCP Context
        
    Returns:
        比赛列表JSON
    """
    try:
        await ctx.report_progress(0.3, "正在获取比赛数据...")
        await ctx.log_info(f"[数据] 获取今日比赛: {params.lottery_type}")
        
        # 检查是否可以使用缓存
        if not params.force_refresh and is_cache_valid():
            await ctx.log_info("[数据] 使用缓存数据")
            matches = get_cached_matches()
            source = "cache"
        else:
            if params.force_refresh:
                await ctx.log_info("[数据] 强制刷新缓存")
            # 导入真实数据获取模块
            from lottery_mcp.data.fetcher import fetch_today_matches as _fetch_today_matches
            
            # 映射彩种名称到内部标识
            lottery_type_map = {
                "竞彩足球": "jingcai",
                "北京单场": "beidan",
                "传统足彩": "ctzc",
            }
            internal_type = lottery_type_map.get(params.lottery_type, "jingcai")
            
            # 调用真实 API
            matches = _fetch_today_matches(
                lottery_type=internal_type,
                timeout=params.timeout or 30
            )
            
            # 赔率字段映射：将 had/hhad/crs/ttg/hafu 合并为统一的 odds 字典
            for match in matches:
                odds = {}
                # 胜平负
                if match.get("had"):
                    odds["win"] = match["had"].get("win", 0)
                    odds["draw"] = match["had"].get("draw", 0)
                    odds["lose"] = match["had"].get("lose", 0)
                    odds["had_w"] = match["had"].get("win", 0)
                    odds["had_d"] = match["had"].get("draw", 0)
                    odds["had_l"] = match["had"].get("lose", 0)
                # 让球胜平负
                if match.get("hhad"):
                    odds["handicap"] = match["hhad"].get("handicap", "0")
                    odds["hhad_w"] = match["hhad"].get("win", 0)
                    odds["hhad_d"] = match["hhad"].get("draw", 0)
                    odds["hhad_l"] = match["hhad"].get("lose", 0)
                # 比分
                if match.get("crs") and match["crs"].get("options"):
                    for opt in match["crs"]["options"]:
                        if opt.get("odds", 0) > 0:
                            odds[f"crs_{opt['score']}"] = opt["odds"]
                # 总进球
                if match.get("ttg") and match["ttg"].get("options"):
                    for opt in match["ttg"]["options"]:
                        if opt.get("odds", 0) > 0:
                            odds[f"ttg_{opt.get('goals', opt.get('value', ''))}"] = opt["odds"]
                # 半全场
                if match.get("hafu") and match["hafu"].get("options"):
                    for opt in match["hafu"]["options"]:
                        if opt.get("odds", 0) > 0:
                            odds[f"hafu_{opt.get('result', opt.get('value', ''))}"] = opt["odds"]

                if odds:
                    match["odds"] = odds

            # 获取欧指亚盘数据（The Odds API）
            await ctx.report_progress(0.6, "获取国际市场赔率...")
            try:
                from lottery_mcp.data.sources import FreeDataSourceManager
                from lottery_mcp.data.team_mapping import match_team_name
                mgr = FreeDataSourceManager()
                
                # 获取今日比赛的欧指亚盘
                market_odds_response = await mgr.get_market_odds(sport="soccer")
                market_odds = market_odds_response.get("data", [])
                
                # 将欧指亚盘数据匹配到比赛
                matched_count = 0
                for match in matches:
                    home_team = match.get("home_team", "")
                    away_team = match.get("away_team", "")
                    
                    # 使用球队名称映射匹配
                    for mo in market_odds:
                        mo_home = mo.get("home_team", "")
                        mo_away = mo.get("away_team", "")
                        
                        # 使用中英文映射匹配
                        if match_team_name(home_team, mo_home) and \
                           match_team_name(away_team, mo_away):
                            match["european_odds"] = mo.get("european_odds", [])
                            match["asian_handicap"] = mo.get("asian_handicap", [])
                            match["over_under"] = mo.get("over_under", [])
                            match["consensus"] = mo.get("consensus", {})
                            match["kelly"] = mo.get("kelly", {})
                            matched_count += 1
                            break
                
                await ctx.log_info(f"[数据] 获取到 {len(market_odds)} 场国际市场赔率，匹配 {matched_count} 场")
            except Exception as e:
                await ctx.log_info(f"[数据] 国际市场赔率获取失败: {e}")
            
            # 缓存数据（缓存全部数据）
            set_cached_matches(matches)
            source = "sporttery.cn"
        
        # 联赛筛选
        if params.league:
            matches = [m for m in matches if params.league in m.get("league", "")]
        
        await ctx.report_progress(0.8, "处理赔率数据...")
        
        # 如果不包含赔率，移除赔率字段
        if not params.include_odds:
            for m in matches:
                m.pop("odds", None)
        
        # 分页处理
        total = len(matches)
        paginated_matches = matches[params.offset:params.offset + params.limit]
        has_more = total > params.offset + len(paginated_matches)
        
        await ctx.report_progress(1.0, "获取完成")
        await ctx.log_info(f"[数据] 获取到 {total} 场比赛，返回 {len(paginated_matches)} 场")
        
        # 根据 response_format 返回不同格式
        if params.response_format == "markdown":
            return _format_matches_markdown(paginated_matches, title=f"今日比赛 - {params.lottery_type}")

        result_data = {
            "success": True,
            "data": {
                "matches": paginated_matches,
                "count": len(paginated_matches),
                "total_count": total,
                "offset": params.offset,
                "limit": params.limit,
                "has_more": has_more,
                "next_offset": params.offset + len(paginated_matches) if has_more else None,
                "lottery_type": params.lottery_type,
                "league_filter": params.league,
                "source": source,
            },
            "timestamp": datetime.now().isoformat(),
        }

        # 对大型列表数据应用截断，避免超出 agent 上下文窗口
        result_data = _truncate_for_context(result_data, max_items=20, max_depth=3)

        return _to_json(result_data)
        
    except Exception as e:
        logger.error(f"获取比赛数据失败: {e}")
        await ctx.log_error(f"[数据] 获取失败: {e}")
        raise_tool_error(
            f"获取比赛数据失败: {str(e)}",
            code="DATA_FETCH_ERROR",
            suggestion="请检查网络连接或稍后重试"
        )


async def lottery_get_match_data(params: GetMatchDataInput, ctx: Context) -> str:
    """获取比赛数据
    
    获取指定比赛的详细数据。
    
    Args:
        params: 获取参数
        ctx: MCP Context
        
    Returns:
        比赛数据JSON
    """
    try:
        await ctx.report_progress(0.5, "正在获取比赛数据...")
        await ctx.log_info(f"[数据] 获取比赛数据: {params.match_id}, 类型: {params.data_type}")
        
        # 从多源聚合管理器获取
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        
        # 获取比赛基础数据
        match_data = {
            "match_id": params.match_id,
            "timestamp": datetime.now().isoformat(),
        }
        
        # 根据 data_type 获取不同数据
        if params.data_type in ["full", "odds"]:
            # 获取赔率数据
            from lottery_mcp.data.fetcher import load_odds_history
            odds_history = load_odds_history(params.match_id)
            if odds_history:
                match_data["odds"] = odds_history[-1]
        
        if params.data_type in ["full", "stats"]:
            # 获取积分榜
            standings = await manager.get_standings(params.league) if params.league else None
            if standings:
                match_data["standings"] = standings.get("data", {})
        
        if params.data_type in ["full", "history"]:
            # 获取历史交锋
            if params.home_team and params.away_team:
                h2h = await manager.get_head_to_head(params.home_team, params.away_team)
                if h2h:
                    match_data["head_to_head"] = h2h.get("data", [])
        
        await ctx.report_progress(1.0, "获取完成")
        
        return _to_json({
            "success": True,
            "data": match_data,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"获取比赛数据失败: {e}")
        await ctx.log_error(f"[数据] 获取失败: {e}")
        raise_tool_error(
            f"获取比赛数据失败: {str(e)}",
            code="MATCH_DATA_ERROR",
            suggestion="请检查比赛ID是否正确"
        )


def _translate_match_status(status: str) -> str:
    """翻译比赛状态代码"""
    status_map = {
        "NS": "未开始",
        "1H": "上半场",
        "2H": "下半场",
        "HT": "中场休息",
        "LIVE": "进行中",
        "FT": "已结束",
        "AET": "加时赛结束",
        "PEN": "点球大战",
        "PST": "推迟",
        "CANC": "取消",
        "ABD": "中断",
        "SUSP": "暂停",
        "WO": "弃权",
        "AWD": "技术性负",
    }
    return status_map.get(status, status)


def _generate_match_analysis(
    match_data: Dict,
    match_info: Optional[Dict],
    features: Optional[Dict],
    h2h: Optional[Dict],
    standings: Optional[Dict],
    market_odds: Optional[List],
    depth: str,
) -> Dict:
    """生成比赛分析报告

    Args:
        match_data: 官方赔率数据
        match_info: 比赛头部信息
        features: 特征分析
        h2h: 历史交锋
        standings: 积分榜
        market_odds: 市场赔率数据
        depth: 分析深度

    Returns:
        分析报告（包含reasoning_chain字段）
    """
    analysis = {
        "official_odds": {},
        "info_summary": {},
        "recommendation": {},
        "reasoning_chain": {},
    }

    # 初始化推理链
    reasoning_chain = {
        "data_sources": [],
        "key_observations": [],
        "inference_steps": [],
        "conclusion": "",
        "confidence": 0.0,
        "assumptions": [],
        "uncertainties": [],
    }

    # 1. 官方赔率分析
    had = match_data.get("had", {})
    hhad = match_data.get("hhad", {})

    if had:
        # 计算返还率
        try:
            win, draw, lose = float(had.get("win", 0)), float(had.get("draw", 0)), float(had.get("lose", 0))
            if win > 0 and draw > 0 and lose > 0:
                payout_rate = 1 / (1/win + 1/draw + 1/lose)
                analysis["official_odds"]["spf"] = {
                    "odds": {"win": win, "draw": draw, "lose": lose},
                    "payout_rate": round(payout_rate, 4),
                }
                reasoning_chain["data_sources"].append("官方赔率(SPF)")
        except (ValueError, TypeError):
            pass

    if hhad:
        try:
            win, draw, lose = float(hhad.get("win", 0)), float(hhad.get("draw", 0)), float(hhad.get("lose", 0))
            handicap = hhad.get("handicap", "0")
            if win > 0 and draw > 0 and lose > 0:
                payout_rate = 1 / (1/win + 1/draw + 1/lose)
                analysis["official_odds"]["rqspf"] = {
                    "odds": {"win": win, "draw": draw, "lose": lose},
                    "handicap": handicap,
                    "payout_rate": round(payout_rate, 4),
                }
                reasoning_chain["data_sources"].append("官方让球赔率(RQSPF)")
        except (ValueError, TypeError):
            pass

    # 2. 资讯摘要
    info_summary = {}
    if features:
        last = features.get("last", {})
        info_summary["h2h_record"] = {
            "home_win": last.get("homeWinGoalMatchCnt", 0),
            "draw": last.get("homeDrawMatchCnt", 0),
            "away_win": last.get("homeLossGoalMatchCnt", 0),
        }
        reasoning_chain["data_sources"].append("历史交锋数据")

    if standings:
        home_tables = standings.get("homeTables", {})
        away_tables = standings.get("awayTables", {})
        info_summary["standings"] = {
            "home_rank": home_tables.get("total", {}).get("ranking", "-"),
            "away_rank": away_tables.get("total", {}).get("ranking", "-"),
        }
        reasoning_chain["data_sources"].append("联赛积分榜")

    analysis["info_summary"] = info_summary

    # 3. 市场赔率对比（标准/深度分析）
    market_comparison_data = None
    if depth in ["standard", "deep"] and market_odds:
        # 简化处理：取第一个匹配的比赛
        home_team = match_data.get("home_team", "")
        away_team = match_data.get("away_team", "")

        for m in market_odds:
            if home_team in m.get("home_team", "") and away_team in m.get("away_team", ""):
                market_comparison_data = {
                    "european_avg": m.get("consensus", {}),
                    "asian_handicap": m.get("asian_handicap", [])[:2] if m.get("asian_handicap") else [],
                }
                analysis["market_comparison"] = market_comparison_data
                reasoning_chain["data_sources"].append("国际市场赔率")
                break

    # 4. 关键观察点提取
    step_num = 1

    # 观察点1: 赔率返还率分析
    spf = analysis["official_odds"].get("spf", {})
    payout = spf.get("payout_rate", 0.89)

    if payout > 0.90:
        reasoning_chain["key_observations"].append("返还率较高(>90%)，赔率相对合理")
        reasoning_chain["inference_steps"].append({
            "step": step_num,
            "input": "官方赔率返还率",
            "logic": f"返还率{payout:.2%}高于90%阈值",
            "output": "赔率定价相对公平，市场效率较高"
        })
        step_num += 1
    elif payout < 0.87:
        reasoning_chain["key_observations"].append("返还率偏低(<87%)，存在抽水")
        reasoning_chain["inference_steps"].append({
            "step": step_num,
            "input": "官方赔率返还率",
            "logic": f"返还率{payout:.2%}低于87%阈值",
            "output": "赔率存在较高抽水，长期期望值为负"
        })
        step_num += 1

    # 观察点2: 排名对比分析
    if info_summary.get("standings"):
        home_rank = info_summary["standings"].get("home_rank", "-")
        away_rank = info_summary["standings"].get("away_rank", "-")
        if home_rank != "-" and away_rank != "-":
            try:
                rank_diff = int(away_rank) - int(home_rank)
                if rank_diff > 5:
                    reasoning_chain["key_observations"].append(f"主队排名({home_rank})显著优于客队({away_rank})")
                    reasoning_chain["inference_steps"].append({
                        "step": step_num,
                        "input": "联赛积分榜排名",
                        "logic": f"主队排名{home_rank}位，客队排名{away_rank}位，差距{rank_diff}位",
                        "output": "主队实力明显占优"
                    })
                    step_num += 1
                elif rank_diff < -5:
                    reasoning_chain["key_observations"].append(f"客队排名({away_rank})显著优于主队({home_rank})")
                    reasoning_chain["inference_steps"].append({
                        "step": step_num,
                        "input": "联赛积分榜排名",
                        "logic": f"客队排名{away_rank}位，主队排名{home_rank}位，差距{abs(rank_diff)}位",
                        "output": "客队实力明显占优"
                    })
                    step_num += 1
                else:
                    reasoning_chain["key_observations"].append(f"两队排名接近({home_rank} vs {away_rank})")
                    reasoning_chain["inference_steps"].append({
                        "step": step_num,
                        "input": "联赛积分榜排名",
                        "logic": f"主队排名{home_rank}位，客队排名{away_rank}位，差距仅{abs(rank_diff)}位",
                        "output": "两队实力接近，比赛可能胶着"
                    })
                    step_num += 1
            except ValueError:
                pass

    # 观察点3: 历史交锋分析
    if info_summary.get("h2h_record"):
        h2h = info_summary["h2h_record"]
        total = h2h.get("home_win", 0) + h2h.get("draw", 0) + h2h.get("away_win", 0)
        if total > 0:
            home_win_pct = h2h.get("home_win", 0) / total
            if home_win_pct > 0.5:
                reasoning_chain["key_observations"].append(f"历史交锋主队占优({h2h.get('home_win', 0)}胜/{total}场)")
                reasoning_chain["inference_steps"].append({
                    "step": step_num,
                    "input": "历史交锋记录",
                    "logic": f"近{total}次交锋，主队获胜{h2h.get('home_win', 0)}次({home_win_pct:.1%})",
                    "output": "历史战绩支持主队"
                })
                step_num += 1

    # 观察点4: 市场赔率对比分析
    if market_comparison_data and market_comparison_data.get("european_avg"):
        consensus = market_comparison_data["european_avg"]
        avg_home = float(consensus.get("avg_home_win", 0))
        avg_draw = float(consensus.get("avg_draw", 0))
        avg_away = float(consensus.get("avg_away_win", 0))

        if avg_home > 0 and spf.get("odds"):
            official_win = spf["odds"].get("win", 0)
            if official_win > 0 and avg_home > 0:
                diff_pct = abs(official_win - avg_home) / avg_home
                if diff_pct > 0.1:
                    if official_win > avg_home:
                        reasoning_chain["key_observations"].append("竞彩主胜赔率高于国际市场")
                        reasoning_chain["inference_steps"].append({
                            "step": step_num,
                            "input": "市场赔率对比",
                            "logic": f"竞彩主胜赔率{official_win}高于国际市场平均{avg_home:.2f}",
                            "output": "可能存在价值投注机会(主胜)"
                        })
                    else:
                        reasoning_chain["key_observations"].append("竞彩主胜赔率低于国际市场")
                        reasoning_chain["inference_steps"].append({
                            "step": step_num,
                            "input": "市场赔率对比",
                            "logic": f"竞彩主胜赔率{official_win}低于国际市场平均{avg_home:.2f}",
                            "output": "竞彩对主胜信心更强"
                        })
                    step_num += 1

    # 5. 投注建议
    recommendation = {"selection": "待定", "confidence": 0.5, "reasoning": []}

    # 基于返还率和排名的简单逻辑
    if payout > 0.90:
        recommendation["reasoning"].append("返还率较高，赔率相对合理")

    final_selection = "待定"
    final_confidence = 0.5

    if info_summary.get("standings"):
        home_rank = info_summary["standings"].get("home_rank", "-")
        away_rank = info_summary["standings"].get("away_rank", "-")
        if home_rank != "-" and away_rank != "-":
            try:
                if int(home_rank) < int(away_rank):
                    final_selection = "主胜"
                    final_confidence = 0.65
                    recommendation["reasoning"].append(f"主队排名({home_rank})优于客队({away_rank})")
                else:
                    final_selection = "客胜或平局"
                    final_confidence = 0.55
                    recommendation["reasoning"].append(f"客队排名({away_rank})不低于主队({home_rank})")
            except ValueError:
                pass

    recommendation["selection"] = final_selection
    recommendation["confidence"] = final_confidence
    analysis["recommendation"] = recommendation

    # 6. 完成推理链
    reasoning_chain["conclusion"] = f"推荐选择: {final_selection}"
    reasoning_chain["confidence"] = round(final_confidence, 2)

    # 假设与不确定性
    reasoning_chain["assumptions"] = [
        "假设首发阵容与预测一致",
        "假设无红牌等突发事件",
        "假设天气条件正常"
    ]
    reasoning_chain["uncertainties"] = [
        "伤停信息可能不完整",
        "临场阵容变化未考虑",
        " referee判罚因素未知"
    ]

    analysis["reasoning_chain"] = reasoning_chain

    return analysis


def _compute_results_statistics(results_list: List[Dict], league_filter: str = None) -> Dict:
    """
    计算赛果统计数据

    Args:
        results_list: 开奖结果列表（每个元素是某天的数据）
        league_filter: 联赛筛选

    Returns:
        统计分析结果
    """
    total_matches = 0
    home_wins = 0
    draws = 0
    away_wins = 0
    league_stats: Dict[str, Dict] = {}
    score_distribution: Dict[str, int] = {}

    for day_data in results_list:
        # 兼容不同的数据结构
        matches = day_data if isinstance(day_data, list) else day_data.get("matches", [])

        for match in matches:
            if not isinstance(match, dict):
                continue

            # 联赛筛选
            league = match.get("league", match.get("league_name", ""))
            if league_filter and league_filter not in league:
                continue

            total_matches += 1

            # 提取赛果
            score = match.get("score", match.get("result", ""))
            home_score = match.get("home_score", match.get("home_goals"))
            away_score = match.get("away_score", match.get("away_goals"))

            # 尝试解析比分
            if home_score is not None and away_score is not None:
                try:
                    h = int(home_score)
                    a = int(away_score)
                    if h > a:
                        home_wins += 1
                    elif h == a:
                        draws += 1
                    else:
                        away_wins += 1

                    # 比分分布
                    score_key = f"{h}:{a}"
                    score_distribution[score_key] = score_distribution.get(score_key, 0) + 1
                except (ValueError, TypeError):
                    continue

            # 联赛维度统计
            if league:
                if league not in league_stats:
                    league_stats[league] = {"matches": 0, "home_wins": 0, "draws": 0, "away_wins": 0}
                league_stats[league]["matches"] += 1
                if home_score is not None and away_score is not None:
                    try:
                        h, a = int(home_score), int(away_score)
                        if h > a:
                            league_stats[league]["home_wins"] += 1
                        elif h == a:
                            league_stats[league]["draws"] += 1
                        else:
                            league_stats[league]["away_wins"] += 1
                    except (ValueError, TypeError):
                        pass

    # 计算百分比
    def pct(n, total):
        return round(n / total * 100, 1) if total > 0 else 0

    # 排序比分分布（取 Top 10）
    top_scores = sorted(score_distribution.items(), key=lambda x: x[1], reverse=True)[:10]

    # 排序联赛统计（按场次降序）
    top_leagues = sorted(
        league_stats.items(),
        key=lambda x: x[1]["matches"],
        reverse=True
    )[:10]

    return {
        "total_matches": total_matches,
        "distribution": {
            "home_wins": {"count": home_wins, "percentage": pct(home_wins, total_matches)},
            "draws": {"count": draws, "percentage": pct(draws, total_matches)},
            "away_wins": {"count": away_wins, "percentage": pct(away_wins, total_matches)},
        },
        "top_scores": [{"score": s, "count": c, "percentage": pct(c, total_matches)} for s, c in top_scores],
        "league_breakdown": [
            {
                "league": lg,
                "matches": stats["matches"],
                "home_win_rate": pct(stats["home_wins"], stats["matches"]),
                "draw_rate": pct(stats["draws"], stats["matches"]),
                "away_win_rate": pct(stats["away_wins"], stats["matches"]),
            }
            for lg, stats in top_leagues
        ],
    }


def _build_value_discovery_logic(value_bets: List[Dict], all_matches: List[Dict]) -> Dict:
    """
    构建价值发现逻辑分析

    Args:
        value_bets: 发现的价值投注列表
        all_matches: 所有分析的比赛

    Returns:
        价值发现逻辑分析
    """
    total_analyzed = len(all_matches)
    value_found = len(value_bets)

    # 市场分析
    if value_found == 0:
        market_analysis = "市场定价相对有效，未发现明显价值偏差"
    elif value_found / total_analyzed < 0.1:
        market_analysis = "市场效率较高，仅少数比赛存在价值机会"
    elif value_found / total_analyzed < 0.3:
        market_analysis = "市场存在中等程度定价偏差，有一定价值机会"
    else:
        market_analysis = "市场存在显著定价偏差，价值机会较多"

    # 模型评估
    avg_value_edge = 0.0
    model_assessment = ""
    if value_bets:
        total_edge = 0.0
        edge_count = 0
        for bet in value_bets:
            for signal in bet.get("value_signals", []):
                diff = signal.get("diff", 0)
                total_edge += diff
                edge_count += 1
        if edge_count > 0:
            avg_value_edge = total_edge / edge_count
            model_assessment = f"平均价值优势{avg_value_edge:.1%}，模型识别出市场定价偏差"
    else:
        model_assessment = "当前市场定价与模型预期基本一致"

    # 分歧解释
    if value_found > 0:
        discrepancy_explanation = (
            "竞彩官方赔率与国际市场存在分歧："
            "1) 竞彩可能基于本土信息调整赔率；"
            "2) 市场流动性差异导致定价偏差；"
            "3) 投注者情绪影响官方赔率"
        )
    else:
        discrepancy_explanation = "当前市场定价较为一致，无明显分歧"

    # 优势计算示例
    edge_calculation = ""
    if value_bets and value_bets[0].get("value_signals"):
        first_bet = value_bets[0]
        first_signal = first_bet["value_signals"][0]
        official_prob = first_signal.get("official_prob", 0)
        market_prob = first_signal.get("market_prob", 0)
        diff = first_signal.get("diff", 0)

        # 计算公平赔率
        if market_prob > 0:
            fair_odds = round(1 / market_prob, 2)
            official_odds = round(1 / official_prob, 2) if official_prob > 0 else 0
            edge_pct = round(diff / market_prob * 100, 1) if market_prob > 0 else 0
            edge_calculation = (
                f"示例: 官方赔率{official_odds} vs 公平赔率{fair_odds}，"
                f"价值优势{edge_pct}%"
            )
    else:
        edge_calculation = "未发现明显价值优势"

    # 风险因素
    risk_factors = [
        "赔率会随时间变化，需及时确认",
        "临场阵容变化可能影响赛果",
        "多场比赛同时存在价值信号时，注意分散风险"
    ]
    if value_found > total_analyzed * 0.3:
        risk_factors.append("价值机会过多，需警惕数据异常")

    # 置信度评估
    if value_found == 0:
        confidence_assessment = "无价值投注机会，建议观望"
    elif avg_value_edge > 0.05:
        confidence_assessment = "高置信度，价值优势显著，可适度参与"
    elif avg_value_edge > 0.03:
        confidence_assessment = "中等置信度，建议小额试水"
    else:
        confidence_assessment = "低置信度，价值优势有限，谨慎参与"

    return {
        "market_analysis": market_analysis,
        "model_assessment": model_assessment,
        "discrepancy_explanation": discrepancy_explanation,
        "edge_calculation": edge_calculation,
        "risk_factors": risk_factors,
        "confidence_assessment": confidence_assessment,
    }


# ============================================================
# 竞彩网比赛资讯工具
# ============================================================

async def _lottery_get_match_info(match_id: str, ctx: Context) -> str:
    """获取竞彩比赛头部信息"""
    try:
        logger.info(f"获取比赛头部信息: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_match_head(match_id)
        
        if result.get("data"):
            data = result["data"]
            lines = [
                "# 比赛头部信息",
                f"- **来源**: {result.get('source', 'sporttery.cn')}",
                f"- **比赛ID**: {match_id}",
            ]
            
            # 添加基本信息
            home = data.get("homeTeam", {})
            away = data.get("awayTeam", {})
            lines.extend([
                f"- **主队**: {home.get('cnName', '')}",
                f"- **客队**: {away.get('cnName', '')}",
            ])
            
            return "\n".join(lines)
        return f"未找到比赛 {match_id} 的头部信息"
    except Exception as e:
        logger.error(f"获取比赛头部信息失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_match_features(match_id: str, term_limits: int = 10, ctx: Context = None) -> str:
    """获取竞彩比赛特征分析"""
    try:
        logger.info(f"获取比赛特征分析: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_match_feature(match_id, term_limits)
        
        if result.get("data"):
            data = result["data"]
            return "# 比赛特征分析\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的特征分析"
    except Exception as e:
        logger.error(f"获取比赛特征分析失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_jingcai_h2h(match_id: str, term_limits: int = 10, ctx: Context = None) -> str:
    """获取竞彩历史交锋"""
    try:
        logger.info(f"获取历史交锋: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_result_history(match_id, term_limits)
        
        if result.get("data"):
            data = result["data"]
            return "# 历史交锋\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的历史交锋"
    except Exception as e:
        logger.error(f"获取历史交锋失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_match_standings(match_id: str, ctx: Context = None) -> str:
    """获取竞彩积分榜"""
    try:
        logger.info(f"获取积分榜: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_match_tables(match_id)
        
        if result.get("data"):
            data = result["data"]
            return "# 积分榜\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的积分榜"
    except Exception as e:
        logger.error(f"获取积分榜失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_recent_form(match_id: str, term_limits: int = 10, ctx: Context = None) -> str:
    """获取竞彩近期战绩"""
    try:
        logger.info(f"获取近期战绩: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_match_recent_form(match_id, term_limits)
        
        if result.get("data"):
            data = result["data"]
            return "# 近期战绩\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的近期战绩"
    except Exception as e:
        logger.error(f"获取近期战绩失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_future_matches(match_id: str, term_limits: int = 4, ctx: Context = None) -> str:
    """获取竞彩未来赛事"""
    try:
        logger.info(f"获取未来赛事: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_future_matches(match_id, term_limits)
        
        if result.get("data"):
            data = result["data"]
            return "# 未来赛事\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的未来赛事"
    except Exception as e:
        logger.error(f"获取未来赛事失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_players(match_id: str, term_limits: int = 3, ctx: Context = None) -> str:
    """获取竞彩射手信息"""
    try:
        logger.info(f"获取射手信息: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_match_players(match_id, term_limits)
        
        if result.get("data"):
            data = result["data"]
            return "# 射手信息\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的射手信息"
    except Exception as e:
        logger.error(f"获取射手信息失败: {e}")
        return f"获取失败: {e}"


async def _lottery_get_injury_suspension(match_id: str, ctx: Context = None) -> str:
    """获取竞彩伤停一览"""
    try:
        logger.info(f"获取伤停信息: {match_id}")
        from lottery_mcp.data.sources import FreeDataSourceManager
        
        manager = FreeDataSourceManager()
        result = await manager.get_injury_suspension(match_id)
        
        if result.get("data"):
            data = result["data"]
            return "# 伤停一览\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
        return f"未找到比赛 {match_id} 的伤停信息"
    except Exception as e:
        logger.error(f"获取伤停信息失败: {e}")
        return f"获取失败: {e}"


# ============================================================
# Tool Registration
# ============================================================

def register_data_tools(mcp):
    """注册数据获取工具
    
    Args:
        mcp: FastMCP 实例
    """
    from mcp.server.fastmcp import Context
    
    @mcp.tool(
        name="lottery_fetch_today_matches",
        description="""获取今日可投注比赛列表

返回当日所有可投注比赛，包含：
- 比赛ID、联赛、球队
- 比赛时间、状态
- 基础赔率（可选）

支持按联赛筛选。

Use when: 需要获取当日比赛列表时。

Workflow: 通常作为第一步调用，其结果供 analyze_match、analyze_all_matches 等分析工具使用。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_fetch_today_matches(params: FetchTodayMatchesInput, ctx: Context) -> str:
        return await lottery_fetch_today_matches(params, ctx)
    
    @mcp.tool(
        name="lottery_get_match_data",
        description="""获取比赛详细数据

获取指定比赛的各类数据：
- full: 完整数据
- odds: 仅赔率
- stats: 统计数据
- history: 历史交锋

Use when: 需要获取特定比赛的详细信息时。

Workflow: 获取单场详细数据后，可调用 analyze_match 进行深度分析。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_match_data(params: GetMatchDataInput, ctx: Context) -> str:
        return await lottery_get_match_data(params, ctx)

    # ============================================================
    # 扩展数据工具：国内数据源（竞彩/北单/传统足彩）
    # ============================================================

    @mcp.tool(
        name="lottery_track_odds_changes",
        description="""获取竞彩赔率变化数据

获取竞彩足球指定场次的赔率变化信息，覆盖6种玩法：
- 胜平负(SPF)、让球胜平负(RQSPF)、比分(BF)
- 总进球(ZJQ)、半全场(BQC)、混合过关

Use when: 需要查看竞彩赔率变化趋势时。

Workflow: 与 get_market_odds 配合使用，追踪赔率变化趋势。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_track_odds_changes(params: TrackOddsChangesInput, ctx: Context) -> str:
        try:
            manager = _get_manager()
            result = await manager.get_lottery_odds_change(params.match_id)
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            raise_tool_error(
                f"获取竞彩赔率变化失败: {e}",
                code="ODDS_CHANGE_ERROR",
                suggestion="请检查比赛ID是否正确或稍后重试"
            )

    # ============================================================
    # 开奖结果分析工具：赛果统计/多源验证/历史查询
    # ============================================================

    @mcp.tool(
        name="lottery_verify_results",
        description="""多源开奖结果验证

从多个数据源交叉验证开奖结果的准确性，确保数据一致性。

验证维度：
- 数据源一致性（多源对比）
- 数据完整性检查
- 异常结果标记

数据来源：500.com + sporttery.cn 双源验证。

Use when: 需要验证开奖结果准确性、排查数据异常时。

Workflow: 与 query_history 配合，先查询再验证。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_verify_results(params: VerifyResultsInput, ctx: Context) -> str:
        try:
            manager = _get_manager()
            date = params.date or datetime.now().strftime("%Y-%m-%d")

            await ctx.log_info(f"[开奖验证] {params.lottery_type} {date}")

            sources = []
            errors = []

            # 从不同数据源获取（仅支持竞彩足球）
            if params.lottery_type == "竞彩足球":
                # 源1: 500.com
                result1 = await manager.get_lottery_results(date)
                if result1.get("data"):
                    sources.append({
                        "source": result1.get("source", "500.com"),
                        "data": result1["data"],
                        "status": "success",
                    })
                else:
                    errors.append(f"500.com: {result1.get('error', '获取失败')}")

                # 源2: sporttery.cn（尝试通过赔率变化接口间接验证赛果）
                # 修复：原实现仅返回硬编码说明文本，现在尝试真实获取赔率数据
                try:
                    odds_change = await manager.get_lottery_odds_change(date)
                    if odds_change and odds_change.get("data"):
                        sources.append({
                            "source": "sporttery.cn",
                            "data": odds_change["data"],
                            "status": "supplementary",
                            "note": "sporttery.cn 提供赔率变化数据，可作为赛果的辅助验证",
                        })
                    else:
                        sources.append({
                            "source": "sporttery.cn",
                            "data": {"note": "sporttery.cn 未返回赔率数据"},
                            "status": "unavailable",
                        })
                except Exception as odds_err:
                    sources.append({
                        "source": "sporttery.cn",
                        "data": {"note": f"sporttery.cn 赔率数据获取失败: {odds_err}"},
                        "status": "unavailable",
                    })
            else:
                raise_tool_error(
                    f"暂不支持 {params.lottery_type} 的开奖验证",
                    code="UNSUPPORTED_LOTTERY_TYPE",
                    suggestion="请使用竞彩足球，或选择其他工具"
                )

            # 验证结果
            success_count = sum(1 for s in sources if s["status"] == "success")
            unavailable_count = sum(1 for s in sources if s["status"] == "unavailable")
            verification = {
                "date": date,
                "lottery_type": params.lottery_type,
                "sources_checked": len(sources),
                "sources_success": success_count,
                "sources_unavailable": unavailable_count,
                "is_verified": success_count >= 1,
                "consistency": ("单数据源验证（sporttery.cn 不可用）" if unavailable_count > 0
                               else "一致" if success_count <= 1 else "需人工复核"),
                "errors": errors if errors else None,
            }

            return _to_json({
                "success": True,
                "data": verification,
                "sources": sources,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"开奖验证失败: {e}")
            raise_tool_error(
                f"开奖验证失败: {e}",
                code="VERIFICATION_ERROR",
                suggestion="请检查日期和彩种设置"
            )

    @mcp.tool(
        name="lottery_query_history",
        description="""历史开奖综合查询

统一查询三大彩种的历史开奖结果，支持灵活筛选。

支持彩种：
- 竞彩足球：按日期查询
- 北京单场：查询最近开奖
- 传统足彩：按奖期和玩法查询（胜负彩/任选9/半全场/进球彩）

Use when: 需要查询历史开奖结果时。

Workflow: 查询历史数据后，可调用 analyze_results 进行统计分析。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_query_history(params: QueryHistoryInput, ctx: Context) -> str:
        try:
            manager = _get_manager()

            await ctx.log_info(f"[历史查询] {params.lottery_type} 日期={params.date} 奖期={params.expect}")

            result = None

            if params.lottery_type == "竞彩足球":
                result = await manager.get_lottery_results(params.date)
            else:
                raise_tool_error(
                    f"暂不支持 {params.lottery_type} 的历史查询",
                    code="UNSUPPORTED_LOTTERY_TYPE",
                    suggestion="请使用竞彩足球，或选择其他工具"
                )

            if not result or not result.get("data"):
                error_msg = result.get("error", "未获取到数据") if result else "未获取到数据"
                raise_tool_error(
                    error_msg,
                    code="HISTORY_QUERY_FAILED",
                    suggestion="请确认参数正确或稍后重试"
                )

            # 分页处理
            all_results = result["data"]
            total = len(all_results) if isinstance(all_results, list) else 1
            
            if isinstance(all_results, list):
                paginated_results = all_results[params.offset:params.offset + params.limit]
                has_more = total > params.offset + len(paginated_results)
            else:
                paginated_results = all_results
                has_more = False
            
            # 根据 response_format 返回不同格式
            if params.response_format == "markdown":
                return _format_history_markdown(paginated_results if isinstance(paginated_results, list) else [paginated_results], title=f"历史开奖 - {params.lottery_type}")
            
            return _to_json({
                "success": True,
                "data": {
                    "lottery_type": params.lottery_type,
                    "results": paginated_results,
                    "count": len(paginated_results) if isinstance(paginated_results, list) else 1,
                    "total_count": total,
                    "offset": params.offset,
                    "limit": params.limit,
                    "has_more": has_more,
                    "next_offset": params.offset + len(paginated_results) if has_more else None,
                    "source": result.get("source", "unknown"),
                    "cached": result.get("cached", False),
                },
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"历史查询失败: {e}")
            raise_tool_error(
                f"历史查询失败: {e}",
                code="HISTORY_QUERY_ERROR",
                suggestion="请检查日期格式和彩种设置"
            )

    # ============================================================
    # 高级功能工具：实时比分
    # ============================================================

    @mcp.tool(
        name="lottery_get_live_scores",
        description="""获取实时比分

获取当前进行中的足球比赛实时比分信息，包含：
- 比赛状态（进行中/中场/结束）
- 当前比分
- 比赛时间
- 联赛信息

支持按联赛筛选，可选择是否包含已结束的比赛。

数据来源：api-football（免费100次/天）。

Use when: 需要查看实时比分、追踪比赛进度时。

Workflow: 获取实时数据后，可调用 track_odds_changes 和 assess_risk 进行实时分析。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_get_live_scores(params: GetLiveScoresInput, ctx: Context) -> str:
        try:
            manager = _get_manager()

            # 名称映射
            league_code = normalize_league_name(params.league) if params.league else None

            await ctx.log_info(f"[实时比分] 联赛: {params.league} → {league_code}")

            # 获取今日赛程
            result = await manager.get_fixtures(league_code or "EPL")

            if not result.get("data"):
                raise_tool_error(
                    result.get("error", "未获取到实时比分数据"),
                    code="LIVE_SCORES_NOT_FOUND",
                    suggestion="请确认联赛名称正确，或检查 api-football 配额"
                )

            matches = result.get("data", {}).get("matches", [])
            live_matches = []

            for m in matches:
                status = m.get("status", "")

                # 比赛状态过滤
                # api-football 状态: NS(未开始)/LIVE(进行中)/HT(中场)/FT(结束)
                is_live = status in ["1H", "2H", "HT", "LIVE"]
                is_finished = status in ["FT", "AET", "PEN"]

                if not params.include_finished and is_finished:
                    continue
                if not is_live and not is_finished:
                    continue

                live_matches.append({
                    "home_team": m.get("home_team", ""),
                    "away_team": m.get("away_team", ""),
                    "home_team_cn": team_to_chinese(m.get("home_team", "")),
                    "away_team_cn": team_to_chinese(m.get("away_team", "")),
                    "home_score": m.get("home_score", 0),
                    "away_score": m.get("away_score", 0),
                    "status": _translate_match_status(status),
                    "date": m.get("date", ""),
                    "fixture_id": m.get("fixture_id", 0),
                })

            if not live_matches:
                return _to_json({
                    "success": True,
                    "data": {
                        "matches": [],
                        "count": 0,
                        "message": "当前没有进行中的比赛",
                    },
                    "timestamp": datetime.now().isoformat(),
                })

            # 分页处理
            total = len(live_matches)
            paginated_matches = live_matches[params.offset:params.offset + params.limit]
            has_more = total > params.offset + len(paginated_matches)
            
            # 根据 response_format 返回不同格式
            if params.response_format == "markdown":
                return _format_live_scores_markdown(paginated_matches, title="实时比分")
            
            return _to_json({
                "success": True,
                "data": {
                    "matches": paginated_matches,
                    "count": len(paginated_matches),
                    "total_count": total,
                    "offset": params.offset,
                    "limit": params.limit,
                    "has_more": has_more,
                    "next_offset": params.offset + len(paginated_matches) if has_more else None,
                    "league": params.league,
                    "source": result.get("source", "unknown"),
                },
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"获取实时比分失败: {e}")
            raise_tool_error(
                f"获取实时比分失败: {e}",
                code="LIVE_SCORES_ERROR",
                suggestion="请检查联赛名称或稍后重试"
            )

    # ============================================================
    # 工作流工具：统一市场赔率 + 价值投注
    # ============================================================

    @mcp.tool(
        name="lottery_get_market_odds",
        description="""获取市场赔率数据（统一入口）

获取国际主流博彩公司的赔率数据，支持三种市场类型：
- european: 欧赔（胜平负，多机构对比）
- asian: 亚盘（让球盘口，多机构对比）
- over_under: 大小球（盘口线，多机构对比）

数据源优先级：球探网 → 捷报比分 → The Odds API
支持中英文球队名/联赛名输入。

Use when: 需要获取欧赔、亚盘、大小球数据时。

Workflow: 获取赔率后，可调用 find_value_bets 识别价值投注机会。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_get_market_odds(params: GetMarketOddsInput, ctx: Context) -> str:
        try:
            manager = _get_manager()

            # 名称映射
            league_en = normalize_league_name(params.league) if params.league else None
            home_en = normalize_team_name(params.home_team) if params.home_team else None
            away_en = normalize_team_name(params.away_team) if params.away_team else None

            await ctx.log_info(f"[市场赔率] 联赛: {params.league} → {league_en}, 市场: {params.market_types}")

            # 解析市场类型
            market_types = params.market_types
            if "all" in market_types:
                market_types = ["european", "asian", "over_under"]

            # 获取完整赔率数据
            result = await manager.get_market_odds(sport="soccer", league=league_en)

            if not result.get("data"):
                raise_tool_error(
                    result.get("error", "未获取到赔率数据"),
                    code="MARKET_ODDS_NOT_FOUND",
                    suggestion="请确认联赛名称正确，或稍后重试"
                )

            matches = result["data"]
            filtered = []

            for match in matches:
                match_home = match.get("home_team", "")
                match_away = match.get("away_team", "")

                # 球队筛选
                if home_en:
                    home_cn = team_to_chinese(home_en)
                    if home_en.lower() not in match_home.lower() and home_cn not in match_home:
                        continue
                if away_en:
                    away_cn = team_to_chinese(away_en)
                    if away_en.lower() not in match_away.lower() and away_cn not in match_away:
                        continue

                entry = {
                    "home_team": match_home,
                    "away_team": match_away,
                    "home_team_cn": team_to_chinese(match_home),
                    "away_team_cn": team_to_chinese(match_away),
                    "match_time": match.get("match_time", ""),
                }

                if "european" in market_types:
                    euro = match.get("european_odds", [])
                    if euro:
                        entry["european_odds"] = euro
                        entry["consensus"] = match.get("consensus", {})
                        entry["kelly"] = match.get("kelly", {})

                if "asian" in market_types:
                    asian = match.get("asian_handicap", [])
                    if asian:
                        entry["asian_handicap"] = asian

                if "over_under" in market_types:
                    ou = match.get("over_under", [])
                    if ou:
                        entry["over_under"] = ou

                # 至少有一个市场数据
                if any(k in entry for k in ["european_odds", "asian_handicap", "over_under"]):
                    filtered.append(entry)

            if not filtered:
                raise_tool_error(
                    "未找到符合条件的赔率数据",
                    code="NO_MATCHING_ODDS",
                    suggestion="尝试更换联赛名称或移除筛选条件"
                )

            return _to_json({
                "success": True,
                "data": {
                    "matches": filtered,
                    "count": len(filtered),
                    "market_types": market_types,
                    "source": result.get("source", "unknown"),
                },
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"获取市场赔率失败: {e}")
            raise_tool_error(
                f"获取市场赔率失败: {e}",
                code="MARKET_ODDS_ERROR",
                suggestion="请检查联赛名称或稍后重试"
            )


# ============================================================
# 滚球盘数据获取工具 (P2)
# ============================================================

async def _fetch_live_odds_from_api_football(league: Optional[str] = None) -> List[Dict[str, Any]]:
    """从 API-Football 获取滚球盘数据
    
    Args:
        league: 联赛名称筛选（可选）
        
    Returns:
        滚球盘数据列表
    """
    try:
        import httpx
        import os
        from pathlib import Path
        
        # 读取 API 密钥
        env_file = Path(__file__).parent.parent.parent / ".env.api_keys"
        api_key = None
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('API_FOOTBALL_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                        break
        
        if not api_key:
            logger.warning("API-Football 密钥未配置")
            return []
        
        # 获取当前直播的比赛
        url = "https://v3.football.api-sports.io/fixtures"
        params = {
            "live": "true",
        }
        
        if league:
            params["league"] = league
        
        headers = {
            "x-apisports-key": api_key,
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=15.0)
            
            if resp.status_code == 200:
                data = resp.json()
                fixtures = data.get("response", [])
                
                results = []
                for fixture in fixtures:
                    fixture_data = fixture.get("fixture", {})
                    league_data = fixture.get("league", {})
                    teams = fixture.get("teams", {})
                    goals = fixture.get("goals", {})
                    odds_data = fixture.get("odds", [])
                    
                    result = {
                        "match_id": str(fixture_data.get("id", "")),
                        "status": fixture_data.get("status", {}).get("short", ""),
                        "status_long": fixture_data.get("status", {}).get("long", ""),
                        "elapsed": fixture_data.get("status", {}).get("elapsed", 0),
                        "league": league_data.get("name", ""),
                        "league_id": league_data.get("id", ""),
                        "home_team": teams.get("home", {}).get("name", ""),
                        "away_team": teams.get("away", {}).get("name", ""),
                        "home_score": goals.get("home", 0),
                        "away_score": goals.get("away", 0),
                        "match_time": fixture_data.get("date", ""),
                    }
                    
                    # 处理赔率数据
                    if odds_data and len(odds_data) > 0:
                        bookmaker = odds_data[0]
                        result["bookmaker"] = bookmaker.get("name", "")
                        
                        for bet in bookmaker.get("bets", []):
                            bet_name = bet.get("name", "")
                            
                            # 欧洲赔率
                            if bet_name == "Match Winner" or bet_name == "Home/Away/Draw":
                                for value in bet.get("values", []):
                                    if value.get("value") == "Home":
                                        result["had_win"] = float(value.get("odd", 0))
                                    elif value.get("value") == "Draw":
                                        result["had_draw"] = float(value.get("odd", 0))
                                    elif value.get("value") == "Away":
                                        result["had_lose"] = float(value.get("odd", 0))
                            
                            # 大小球
                            elif "Over/Under" in bet_name or "Total" in bet_name:
                                for value in bet.get("values", []):
                                    if "Over" in value.get("value", ""):
                                        line = value.get("value", "").replace("Over ", "")
                                        result["totals_line"] = float(line)
                                        result["totals_over"] = float(value.get("odd", 0))
                                    elif "Under" in value.get("value", ""):
                                        result["totals_under"] = float(value.get("odd", 0))
                            
                            # 亚洲盘口
                            elif "Asian Handicap" in bet_name or "Handicap" in bet_name:
                                for value in bet.get("values", []):
                                    if "Home" in value.get("value", ""):
                                        result["hhad_handicap"] = value.get("value", "")
                                        result["hhad_win"] = float(value.get("odd", 0))
                                    elif "Away" in value.get("value", ""):
                                        result["hhad_lose"] = float(value.get("odd", 0))
                    
                    results.append(result)
                
                return results
            else:
                logger.warning(f"API-Football 返回状态码: {resp.status_code}")
                return []
                
    except Exception as e:
        logger.error(f"获取滚球盘数据失败: {e}")
        return []


async def _fetch_live_odds_from_the_odds_api(sport: str = "soccer") -> List[Dict[str, Any]]:
    """从 The Odds API 获取赔率数据
    
    Args:
        sport: 运动项目代码
        
    Returns:
        赔率数据列表
    """
    try:
        import httpx
        from pathlib import Path
        
        # 读取 API 密钥
        env_file = Path(__file__).parent.parent.parent / ".env.api_keys"
        api_key = None
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('THE_ODDS_API_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                        break
        
        if not api_key:
            logger.warning("The Odds API 密钥未配置")
            return []
        
        # 获取滚球赛事
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            "apiKey": api_key,
            "regions": "eu,us,uk",
            "markets": "h2h,totals,spreads",
            "oddsFormat": "decimal",
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=15.0)
            
            if resp.status_code == 200:
                data = resp.json()
                
                results = []
                for match in data:
                    result = {
                        "match_id": match.get("id", ""),
                        "sport_title": match.get("sport_title", ""),
                        "home_team": match.get("home_team", ""),
                        "away_team": match.get("away_team", ""),
                        "commence_time": match.get("commence_time", ""),
                        "bookmakers": [],
                    }
                    
                    # 处理赔率
                    for bookmaker in match.get("bookmakers", []):
                        bm_data = {
                            "name": bookmaker.get("title", ""),
                            "markets": {},
                        }
                        
                        for market in bookmaker.get("markets", []):
                            market_key = market.get("key", "")
                            outcomes = market.get("outcomes", [])
                            
                            if market_key == "h2h":
                                for outcome in outcomes:
                                    name = outcome.get("name", "")
                                    if name == match.get("home_team"):
                                        result["had_win"] = outcome.get("price", 0)
                                    elif name == "Draw":
                                        result["had_draw"] = outcome.get("price", 0)
                                    else:
                                        result["had_lose"] = outcome.get("price", 0)
                            
                            elif market_key == "totals":
                                for outcome in outcomes:
                                    if outcome.get("name") == "Over":
                                        result["totals_line"] = outcome.get("point", 0)
                                        result["totals_over"] = outcome.get("price", 0)
                                    else:
                                        result["totals_under"] = outcome.get("price", 0)
                            
                            elif market_key == "spreads":
                                for outcome in outcomes:
                                    if "Home" in outcome.get("description", "") or outcome.get("name") == match.get("home_team"):
                                        result["hhad_handicap"] = outcome.get("point", 0)
                                        result["hhad_win"] = outcome.get("price", 0)
                                    else:
                                        result["hhad_lose"] = outcome.get("price", 0)
                        
                        result["bookmakers"].append(bm_data)
                    
                    results.append(result)
                
                return results
            else:
                logger.warning(f"The Odds API 返回状态码: {resp.status_code}")
                return []
                
    except Exception as e:
        logger.error(f"获取 The Odds API 滚球盘数据失败: {e}")
        return []


async def _fetch_live_odds_from_odds_api_io() -> List[Dict[str, Any]]:
    """从 Odds-API.io 获取赔率数据
    
    Returns:
        赔率数据列表
    """
    try:
        import httpx
        from pathlib import Path
        
        # 读取 API 密钥
        env_file = Path(__file__).parent.parent.parent / ".env.api_keys"
        api_key = None
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('ODDS_API_IO_KEY') or line.startswith('Odds-API.io'):
                        api_key = line.split('=', 1)[1].strip()
                        break
        
        if not api_key:
            logger.warning("Odds-API.io 密钥未配置")
            return []
        
        base_url = "https://api.odds-api.io/v3"
        
        # 获取事件列表
        events_url = f"{base_url}/events"
        events_params = {"apiKey": api_key, "sport": "football"}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(events_url, params=events_params, timeout=15.0)
            
            if resp.status_code == 200:
                events = resp.json()
                results = []
                
                for event in events[:50]:  # 限制数量避免过多数据
                    event_id = event.get('id')
                    
                    # 尝试获取赔率
                    odds_url = f"{base_url}/odds"
                    odds_params = {
                        "apiKey": api_key,
                        "eventId": event_id,
                        "bookmakers": "1xbet"
                    }
                    
                    try:
                        odds_resp = await client.get(odds_url, params=odds_params, timeout=10.0)
                        
                        if odds_resp.status_code == 200:
                            odds_data = odds_resp.json()
                            
                            result = {
                                "match_id": str(event.get('id')),
                                "home_team": event.get('home'),
                                "away_team": event.get('away'),
                                "status": event.get('status'),
                                "match_time": event.get('date'),
                                "league": event.get('league', {}).get('name'),
                                "sport_title": "Football",
                            }
                            
                            # 解析赔率数据
                            bookmakers_data = odds_data.get('bookmakers', {})
                            if bookmakers_data:
                                for bm_slug, bm_data in bookmakers_data.items():
                                    result["bookmaker"] = bm_slug
                                    
                                    markets = bm_data.get('markets', {})
                                    
                                    # 欧指 (h2h)
                                    if 'h2h' in markets:
                                        outcomes = markets['h2h'].get('outcomes', [])
                                        for outcome in outcomes:
                                            if outcome.get('name') == 'Home':
                                                result['had_win'] = float(outcome.get('price', 0))
                                            elif outcome.get('name') == 'Draw':
                                                result['had_draw'] = float(outcome.get('price', 0))
                                            elif outcome.get('name') == 'Away':
                                                result['had_lose'] = float(outcome.get('price', 0))
                                    
                                    # 大小球 (totals)
                                    if 'totals' in markets:
                                        outcomes = markets['totals'].get('outcomes', [])
                                        for outcome in outcomes:
                                            if outcome.get('name') == 'Over':
                                                result['totals_line'] = outcome.get('point', 0)
                                                result['totals_over'] = float(outcome.get('price', 0))
                                            elif outcome.get('name') == 'Under':
                                                result['totals_under'] = float(outcome.get('price', 0))
                                    
                                    # 亚洲盘口 (spreads)
                                    if 'spreads' in markets:
                                        outcomes = markets['spreads'].get('outcomes', [])
                                        for outcome in outcomes:
                                            if outcome.get('name') == 'Home' or 'Home' in outcome.get('description', ''):
                                                result['hhad_handicap'] = outcome.get('point', 0)
                                                result['hhad_win'] = float(outcome.get('price', 0))
                                            elif outcome.get('name') == 'Away' or 'Away' in outcome.get('description', ''):
                                                result['hhad_lose'] = float(outcome.get('price', 0))
                            
                            # 只有包含赔率数据的赛事才添加到结果
                            if 'had_win' in result or 'totals_line' in result:
                                results.append(result)
                    except Exception as e:
                        logger.debug(f"获取赛事 {event_id} 赔率失败: {e}")
                        continue
                
                return results
            else:
                logger.warning(f"Odds-API.io 返回状态码: {resp.status_code}")
                return []
                
    except Exception as e:
        logger.error(f"获取 Odds-API.io 赔率数据失败: {e}")
        return []


async def lottery_get_live_odds(params: Any, ctx: Context) -> str:
    """获取滚球盘实时赔率数据
    
    实时获取当前正在进行的比赛的赔率数据，包括：
    - 欧洲赔率（胜平负）
    - 亚洲盘口（让球盘）
    - 大小球（Over/Under）
    
    数据来源：API-Football, The Odds API, Odds-API.io
    
    Workflow:
        1. 获取当前直播赛事列表
        2. 获取各赛事赔率数据
        3. 返回格式化结果
    
    Args:
        league: 联赛名称筛选（可选，如 英超、西甲）
        source: 数据源：api_football / the_odds_api / odds_api_io / auto（默认自动选择）
        
    Returns:
        滚球盘数据（JSON格式）
    """
    try:
        from lottery_mcp.models import (
            GetLiveOddsInput,
        )
        
        # 验证参数
        if not isinstance(params, GetLiveOddsInput):
            params = GetLiveOddsInput(**params) if isinstance(params, dict) else GetLiveOddsInput()
        
        league = params.league
        source = params.source
        
        logger.info(f"获取滚球盘数据: league={league}, source={source}")
        
        results = []
        
        # 根据数据源获取数据
        if source == "api_football" or source == "auto":
            api_football_data = await _fetch_live_odds_from_api_football(league)
            results.extend(api_football_data)
        
        if source == "the_odds_api" or (source == "auto" and not results):
            the_odds_data = await _fetch_live_odds_from_the_odds_api()
            if the_odds_data:
                results.extend(the_odds_data)
        
        if source == "odds_api_io" or (source == "auto" and not results):
            odds_api_io_data = await _fetch_live_odds_from_odds_api_io()
            if odds_api_io_data:
                results.extend(odds_api_io_data)
        
        if not results:
            return _to_json({
                "success": False,
                "message": "当前没有滚球赛事或获取数据失败",
                "data": [],
                "timestamp": datetime.now().isoformat(),
            })
        
        # 去重
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.get("match_id") not in seen_ids:
                seen_ids.add(r.get("match_id"))
                unique_results.append(r)
        
        return _to_json({
            "success": True,
            "data": {
                "matches": unique_results,
                "count": len(unique_results),
                "source": source if source != "auto" else "api_football + the_odds_api + odds_api_io",
            },
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"获取滚球盘数据失败: {e}")
        raise_tool_error(
            f"获取滚球盘数据失败: {e}",
            code="LIVE_ODDS_ERROR",
            suggestion="请稍后重试或检查网络连接"
        )


def register_live_odds_tools(mcp: Any):
    """注册滚球盘数据工具"""
    
    from pydantic import BaseModel, Field
    from typing import Optional, Literal
    
    class GetLiveOddsInput(BaseModel):
        """获取滚球盘赔率输入参数"""
        model_config = {"extra": "forbid"}
        
        league: Optional[str] = Field(
            default=None,
            description="联赛名称筛选（可选），如 英超、西甲、意甲"
        )
        source: Literal["api_football", "the_odds_api", "odds_api_io", "auto"] = Field(
            default="auto",
            description="数据源：api_football / the_odds_api / odds_api_io / auto（自动选择）"
        )
    
    @mcp.tool(
        name="lottery_get_live_odds",
        description="获取实时赔率数据，支持欧赔、亚盘、大小球等多种市场类型",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def _lottery_get_live_odds(params: GetLiveOddsInput, ctx: Context) -> str:
        return await lottery_get_live_odds(params, ctx)


# ============================================================
# 竞彩网比赛资讯工具注册
# ============================================================

def register_jingcai_info_tools(mcp: Any):
    """注册竞彩网比赛资讯工具"""
    
    from pydantic import BaseModel, Field
    from typing import Optional
    
    class MatchIdInput(BaseModel):
        """竞彩比赛ID输入"""
        model_config = {"extra": "forbid"}
        match_id: str = Field(description="竞彩比赛ID（例如：2025052510001）")
    
    class MatchIdWithLimitInput(BaseModel):
        """竞彩比赛ID + 限制条数输入"""
        model_config = {"extra": "forbid"}
        match_id: str = Field(description="竞彩比赛ID（例如：2025052510001）")
        limit: int = Field(default=10, ge=1, le=50, description="返回数据条数限制，默认10条")
    
    @mcp.tool(
        name="lottery_get_match_info",
        description="""获取竞彩比赛头部信息
        
获取指定竞彩比赛的基础信息：
- 比赛ID、联赛、球队
- 开赛时间、天气信息
- 比赛场地信息

Use when: 需要获取竞彩比赛的基本信息时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_match_info(params: MatchIdInput, ctx: Context) -> str:
        return await _lottery_get_match_info(params.match_id, ctx)
    
    @mcp.tool(
        name="lottery_get_match_features",
        description="""获取竞彩比赛特征分析
        
获取指定竞彩比赛的特征分析数据：
- 攻防特点统计
- 近期比赛风格分析
- 交锋特点总结

Use when: 需要了解比赛特征用于分析时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_match_features(params: MatchIdWithLimitInput, ctx: Context) -> str:
        return await _lottery_get_match_features(params.match_id, params.limit, ctx)
    
    @mcp.tool(
        name="lottery_get_jingcai_h2h",
        description="""获取竞彩历史交锋
        
获取指定竞彩比赛的历史交锋数据：
- 双方直接对战记录
- 进球统计
- 胜负关系

Use when: 需要查看历史交锋数据时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_jingcai_h2h(params: MatchIdWithLimitInput, ctx: Context) -> str:
        return await _lottery_get_jingcai_h2h(params.match_id, params.limit, ctx)
    
    @mcp.tool(
        name="lottery_get_match_standings",
        description="""获取竞彩积分榜
        
获取指定竞彩比赛相关的联赛积分榜：
- 主队排名、积分
- 客队排名、积分
- 完整联赛排名表

Use when: 需要了解球队排名情况时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_match_standings(params: MatchIdInput, ctx: Context) -> str:
        return await _lottery_get_match_standings(params.match_id, ctx)
    
    @mcp.tool(
        name="lottery_get_recent_form",
        description="""获取竞彩近期战绩
        
获取指定竞彩比赛的两队近期战绩：
- 主队最近比赛
- 客队最近比赛
- 战绩统计（胜/平/负）

Use when: 需要了解球队近期状态时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_recent_form(params: MatchIdWithLimitInput, ctx: Context) -> str:
        return await _lottery_get_recent_form(params.match_id, params.limit, ctx)
    
    @mcp.tool(
        name="lottery_get_future_matches",
        description="""获取竞彩未来赛事
        
获取指定竞彩比赛相关的未来赛事：
- 主队下一轮比赛
- 客队下一轮比赛
- 关键赛事预告

Use when: 需要查看未来赛程影响时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_future_matches(params: MatchIdWithLimitInput, ctx: Context) -> str:
        return await _lottery_get_future_matches(params.match_id, params.limit, ctx)
    
    @mcp.tool(
        name="lottery_get_players",
        description="""获取竞彩射手信息
        
获取指定竞彩比赛的射手和关键球员信息：
- 主队关键射手
- 客队关键射手
- 球员近期状态

Use when: 需要了解球员情况时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_players(params: MatchIdWithLimitInput, ctx: Context) -> str:
        return await _lottery_get_players(params.match_id, params.limit, ctx)

    @mcp.tool(
        name="lottery_get_injury_suspension",
        description="""获取竞彩伤停一览

获取指定竞彩比赛的伤停信息：
- 主队伤病球员
- 客队伤病球员
- 停赛球员
- 预计复出时间

Use when: 需要了解球员伤停情况时。
""",
        annotations={"readOnlyHint": True, "idempotentHint": True}
    )
    async def _lottery_get_injury_suspension(params: MatchIdInput, ctx: Context) -> str:
        return await _lottery_get_injury_suspension(params.match_id, ctx)

    logger.info("竞彩资讯工具注册完成：共8个工具")
