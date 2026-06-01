"""
增强工具 MCP 注册模块

注册经过验证的增强工具到 MCP 服务器。

保留的工具（已验证可工作）：
- 赔率监控：monitor_odds, get_odds_history, save_odds_snapshot
- 投注追踪：record_bet, update_bet_result, get_bet_statistics
- 止损管理：check_risk_status, should_stop_betting

移除的工具（无法工作或名不副实）：
- backtest_strategy：今日比赛无 result 字段，完全无法工作
- ml_predict：不是真正的 ML，是加权平均，名不副实
- analyze_sentiment：不是 NLP，是关键词匹配，名不副实
- analyze_handicap：字段名不匹配，无法消费真实数据
- compare_leagues / analyze_league_match：纯硬编码，价值有限
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .enhanced_tools import (
    get_odds_monitor,
    get_bet_tracker,
    get_stop_loss_manager,
)
from .helpers import _to_json, raise_tool_error

logger = logging.getLogger("lottery_mcp")


# ============================================================
# Pydantic 输入模型
# ============================================================

from pydantic import BaseModel, ConfigDict, Field


class MonitorOddsInput(BaseModel):
    """赔率监控输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(..., description="比赛ID")
    play_type: str = Field(default="SPF", description="玩法类型：SPF/RQSPF/BF/ZJQ/BQC")
    current_odds: Dict[str, float] = Field(
        ..., 
        description="当前赔率，支持多种格式："
        "{'主胜': 2.10, '平局': 3.20, '客胜': 3.50} 或 "
        "{'win': 2.10, 'draw': 3.20, 'lose': 3.50}，内部统一标准化为 win/draw/lose"
    )
    previous_odds: Optional[Dict[str, float]] = Field(
        default=None, 
        description="之前赔率（用于对比变化）"
    )


class GetOddsHistoryInput(BaseModel):
    """获取赔率历史输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(..., description="比赛ID")
    play_type: str = Field(default="SPF", description="玩法类型")
    hours: int = Field(default=24, ge=1, le=168, description="查询小时数（1-168）")


class SaveOddsSnapshotInput(BaseModel):
    """保存赔率快照输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(..., description="比赛ID")
    play_type: str = Field(default="SPF", description="玩法类型")
    odds: Dict[str, float] = Field(..., description="赔率数据")
    source: str = Field(default="manual", description="数据来源：manual/api/scheduled")


class RecordBetInput(BaseModel):
    """记录投注输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    bet_id: str = Field(..., description="投注ID（自定义唯一标识）")
    match_id: str = Field(..., description="比赛ID")
    match_name: str = Field(..., description="比赛名称，如 '曼联 vs 利物浦'")
    play_type: str = Field(..., description="玩法类型：SPF/RQSPF/BF/ZJQ/BQC")
    selection: str = Field(..., description="投注选项，如 '主胜'、'2:1'、'3球'")
    odds: float = Field(..., ge=1.01, description="投注赔率")
    stake: float = Field(..., ge=2, description="投注金额（元）")
    result: Optional[str] = Field(
        default="pending", 
        description="投注结果：pending（待开奖）/ won（中奖）/ lost（未中奖）"
    )
    notes: Optional[str] = Field(default=None, description="备注信息")


class UpdateBetResultInput(BaseModel):
    """更新投注结果输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    bet_id: str = Field(..., description="投注ID")
    result: str = Field(..., description="结果：won（中奖）/ lost（未中奖）/ void（取消）")
    actual_return: Optional[float] = Field(
        default=None, 
        description="实际返还金额（含本金）。如中奖 200 元投注赔率 2.10，则返还 420 元"
    )


class GetBetStatsInput(BaseModel):
    """获取投注统计输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    start_date: Optional[str] = Field(default=None, description="开始日期，格式 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期，格式 YYYY-MM-DD")
    play_type: Optional[str] = Field(default=None, description="按玩法类型过滤")


class CheckRiskStatusInput(BaseModel):
    """检查风险状态输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    daily_loss_limit: Optional[float] = Field(default=500, description="日亏损上限（元）")
    weekly_loss_limit: Optional[float] = Field(default=2000, description="周亏损上限（元）")
    monthly_loss_limit: Optional[float] = Field(default=5000, description="月亏损上限（元）")
    consecutive_loss_limit: Optional[int] = Field(default=5, description="连续亏损次数上限")


class ShouldStopBettingInput(BaseModel):
    """判断是否停止投注输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    daily_loss_limit: Optional[float] = Field(default=500, description="日亏损上限（元）")
    weekly_loss_limit: Optional[float] = Field(default=2000, description="周亏损上限（元）")
    monthly_loss_limit: Optional[float] = Field(default=5000, description="月亏损上限（元）")
    consecutive_loss_limit: Optional[int] = Field(default=5, description="连续亏损次数上限")


# ============================================================
# 赔率字段名标准化
# ============================================================

# 各种赔率字段名 → 标准英文键名（与内部分析引擎一致）
ODDS_KEY_MAP = {
    "主胜": "win", "胜": "win", "home": "win", "home_win": "win", "had_w": "win", "w": "win",
    "平局": "draw", "平": "draw", "had_d": "draw", "d": "draw",
    "客胜": "lose", "负": "lose", "away": "lose", "away_win": "lose", "had_l": "lose", "l": "lose",
}


def _normalize_odds_keys(odds: Dict[str, float]) -> Dict[str, float]:
    """标准化赔率字段名，统一为 win/draw/lose（与内部分析引擎一致）"""
    normalized = {}
    for key, value in odds.items():
        standard_key = ODDS_KEY_MAP.get(key.lower(), key.lower())
        if standard_key in ("win", "draw", "lose"):
            normalized[standard_key] = value
    return normalized


# ============================================================
# 工具注册
# ============================================================

def register_enhanced_tools(mcp):
    """注册增强工具到 MCP 服务器"""
    
    # --------------------------------------------------------
    # 工具1：赔率变化监控
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_monitor_odds",
        description=(
            "监控赔率变化，对比两组赔率数据检测价值窗口和市场异动。\n"
            "需要手动传入当前赔率和之前赔率进行对比分析。\n"
            "\n"
            "Use when: 有两组赔率数据需要对比分析时（如开盘赔率 vs 即时赔率）。\n"
            "Workflow: lottery_get_market_odds(获取赔率) → lottery_monitor_odds(对比分析)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_monitor_odds(params: MonitorOddsInput, ctx: Context) -> str:
        """监控赔率变化"""
        try:
            await ctx.log_info(f"监控赔率变化: match_id={params.match_id}, play_type={params.play_type}")
            
            monitor = get_odds_monitor()
            
            # 标准化赔率字段名
            current = _normalize_odds_keys(params.current_odds)
            previous = _normalize_odds_keys(params.previous_odds) if params.previous_odds else None
            
            if len(current) < 2:
                return _to_json({
                    "error": "赔率数据不足，至少需要2个选项",
                    "hint": "支持的字段名：win/draw/lose 或 主胜/平局/客胜",
                })
            
            result = monitor.monitor_odds_changes(
                match_id=params.match_id,
                play_type=params.play_type,
                current_odds=current,
                previous_odds=previous,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_monitor_odds failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具2：获取赔率历史
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_get_odds_history",
        description=(
            "获取指定比赛的赔率历史记录。\n"
            "\n"
            "Use when: 需要查看某场比赛的赔率变化趋势时。\n"
            "Workflow: lottery_save_odds_snapshot(保存快照) → lottery_get_odds_history(查看历史)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_odds_history(params: GetOddsHistoryInput, ctx: Context) -> str:
        """获取赔率历史"""
        try:
            await ctx.log_info(f"获取赔率历史: match_id={params.match_id}, hours={params.hours}")
            
            monitor = get_odds_monitor()
            result = monitor.get_odds_history(
                match_id=params.match_id,
                play_type=params.play_type,
                hours=params.hours,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_get_odds_history failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具3：保存赔率快照
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_save_odds_snapshot",
        description=(
            "保存当前赔率快照到历史记录，用于后续趋势分析。\n"
            "\n"
            "Use when: 获取到新赔率数据后，希望保存用于后续对比时。"
        ),
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def _lottery_save_odds_snapshot(params: SaveOddsSnapshotInput, ctx: Context) -> str:
        """保存赔率快照"""
        try:
            await ctx.log_info(f"保存赔率快照: match_id={params.match_id}")
            
            monitor = get_odds_monitor()
            odds = _normalize_odds_keys(params.odds)
            
            result = monitor.save_odds_snapshot(
                match_id=params.match_id,
                play_type=params.play_type,
                odds=odds,
                source=params.source,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_save_odds_snapshot failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具4：记录投注
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_track_bet",
        description=(
            "记录一注投注，用于追踪投注历史和统计分析。数据持久化存储，跨会话可用。\n"
            "\n"
            "Use when: 每次实际投注后记录投注信息。\n"
            "Workflow: lottery_smart_parlay(生成投注单) → lottery_track_bet(记录) → lottery_settle_bet(结算) → lottery_get_bet_statistics(统计)"
        ),
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def _lottery_track_bet(params: RecordBetInput, ctx: Context) -> str:
        """记录投注"""
        try:
            await ctx.log_info(f"记录投注: bet_id={params.bet_id}, match={params.match_name}")
            
            tracker = get_bet_tracker()
            result = tracker.record_bet(
                bet_id=params.bet_id,
                match_id=params.match_id,
                match_name=params.match_name,
                play_type=params.play_type,
                selection=params.selection,
                odds=params.odds,
                stake=params.stake,
                result=params.result,
                notes=params.notes,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_track_bet failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具5：更新投注结果
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_settle_bet",
        description=(
            "更新投注结果（开奖后调用），记录实际返还金额用于盈亏统计。\n"
            "\n"
            "Use when: 比赛结束后，需要记录开奖结果和实际盈亏时。\n"
            "Workflow: lottery_track_bet(记录) → lottery_settle_bet(结算)"
        ),
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_settle_bet(params: UpdateBetResultInput, ctx: Context) -> str:
        """更新投注结果"""
        try:
            await ctx.log_info(f"结算投注: bet_id={params.bet_id}, result={params.result}")
            
            tracker = get_bet_tracker()
            result = tracker.update_bet_result(
                bet_id=params.bet_id,
                result=params.result,
                actual_return=params.actual_return,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_settle_bet failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具6：获取投注统计
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_get_bet_statistics",
        description=(
            "获取投注统计（完整版，持久化存储）\n"
            "\n"
            "返回所有通过 lottery_track_bet 记录的投注统计数据，数据持久化到文件，跨会话可用。\n"
            "支持按周期筛选：all(全部)/today(今日)/week(本周)/month(本月)。\n"
            "\n"
            "Use when: 需要查看完整的投注历史统计时。\n"
            "Workflow: lottery_track_bet(记录) → lottery_get_bet_statistics(统计) → lottery_settle_bet(结算)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_bet_statistics(params: GetBetStatsInput, ctx: Context) -> str:
        """获取投注统计"""
        try:
            await ctx.log_info(f"获取投注统计: start={params.start_date}, end={params.end_date}")
            
            tracker = get_bet_tracker()
            result = tracker.get_statistics(
                start_date=params.start_date,
                end_date=params.end_date,
                play_type=params.play_type,
            )
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_get_bet_statistics failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具7：检查风险状态
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_check_risk_status",
        description=(
            "检查当前投注风险状态，包括连败次数、亏损额度等。\n"
            "\n"
            "Use when: 需要评估当前投注风险是否需要暂停时。\n"
            "Workflow: lottery_get_bet_statistics(统计) → lottery_check_risk_status(风险评估) → lottery_should_stop_betting(止损判断)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_check_risk_status(params: CheckRiskStatusInput, ctx: Context) -> str:
        """检查风险状态"""
        try:
            await ctx.log_info("检查风险状态")
            
            tracker = get_bet_tracker()
            manager = get_stop_loss_manager()
            
            custom_limits = {
                "daily_loss_limit": params.daily_loss_limit,
                "weekly_loss_limit": params.weekly_loss_limit,
                "monthly_loss_limit": params.monthly_loss_limit,
                "consecutive_loss_limit": params.consecutive_loss_limit,
            }
            
            result = manager.check_risk_status(tracker, custom_limits)
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_check_risk_status failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具8：判断是否停止投注
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_should_stop_betting",
        description=(
            "智能止损判断，基于连败次数、亏损额度、日亏损限额等综合判断是否应停止投注。\n"
            "\n"
            "Use when: 连续亏损后需要判断是否应该暂停投注时。\n"
            "Workflow: lottery_check_risk_status(风险评估) → lottery_should_stop_betting(止损判断)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_should_stop_betting(params: ShouldStopBettingInput, ctx: Context) -> str:
        """判断是否停止投注"""
        try:
            await ctx.log_info("判断是否停止投注")
            
            tracker = get_bet_tracker()
            manager = get_stop_loss_manager()
            
            custom_limits = {
                "daily_loss_limit": params.daily_loss_limit,
                "weekly_loss_limit": params.weekly_loss_limit,
                "monthly_loss_limit": params.monthly_loss_limit,
                "consecutive_loss_limit": params.consecutive_loss_limit,
            }
            
            result = manager.should_stop_betting(tracker, custom_limits)
            
            return _to_json({"success": True, "data": result, "timestamp": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"lottery_should_stop_betting failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # ============================================================
    # 新工具：本地赔率历史数据查询
    # ============================================================
    
    class ListLocalOddsMatchesInput(BaseModel):
        """列出本地有赔率历史的比赛输入"""
        model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
        
        lottery_type: str = Field(default="jingcai", description="彩种类型：jingcai/beidan")
        limit: int = Field(default=50, ge=1, le=200, description="返回结果数量限制")
    
    class GetLocalOddsHistoryInput(BaseModel):
        """获取本地赔率历史输入"""
        model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
        
        match_id: str = Field(..., description="比赛ID，如 '2039782' 或 'jingcai_2039782'")
        include_trend: bool = Field(default=True, description="是否包含趋势分析")
    
    class AnalyzeLocalOddsTrendInput(BaseModel):
        """分析本地赔率趋势输入"""
        model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
        
        match_id: str = Field(..., description="比赛ID")
        play_type: str = Field(default="SPF", description="玩法类型：SPF/RQSPF")
    
    # --------------------------------------------------------
    # 工具9：列出本地有赔率历史的比赛
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_list_local_odds_matches",
        description=(
            "列出本地 odds_history 目录中有赔率历史记录的比赛ID列表。\n"
            "\n"
            "Use when: 需要查询本地存储的历史赔率数据有哪些比赛时。\n"
            "Workflow: lottery_list_local_odds_matches(列表) → lottery_get_local_odds_history(详情)"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_list_local_odds_matches(params: ListLocalOddsMatchesInput, ctx: Context) -> str:
        """列出本地赔率历史比赛"""
        try:
            await ctx.log_info(f"列出本地赔率历史比赛: lottery_type={params.lottery_type}")
            
            # 导入增强工具获取数据目录
            from .enhanced_tools import _PROJECT_ROOT as ENHANCED_PROJECT_ROOT
            import json
            
            # 使用项目根目录下的 odds_history
            project_root = Path(__file__).resolve().parent.parent.parent
            odds_dir = project_root / "odds_history"
            
            if not odds_dir.exists():
                return _to_json({
                    "success": True, 
                    "data": {"matches": [], "total_count": 0, "message": "本地赔率历史目录不存在"},
                    "timestamp": datetime.now().isoformat()
                })
            
            # 扫描目录
            matches = []
            for file_path in odds_dir.glob("*.json"):
                filename = file_path.name
                if params.lottery_type == "jingcai" and not filename.startswith("jingcai_"):
                    continue
                if params.lottery_type == "beidan" and filename.startswith("jingcai_"):
                    continue
                
                # 提取 match_id
                match_id = filename.replace(".json", "")
                if filename.startswith("jingcai_"):
                    match_id = match_id[7:]  # 去掉 "jingcai_"
                
                matches.append({
                    "match_id": match_id,
                    "filename": filename,
                    "file_size_kb": round(file_path.stat().st_size / 1024, 2),
                    "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                })
            
            # 按修改时间倒序排列
            matches.sort(key=lambda x: x["modified_time"], reverse=True)
            matches = matches[:params.limit]
            
            return _to_json({
                "success": True,
                "data": {
                    "matches": matches,
                    "total_count": len(matches),
                    "lottery_type": params.lottery_type,
                },
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"lottery_list_local_odds_matches failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具10：获取本地赔率历史详情
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_get_local_odds_history",
        description=(
            "获取本地 odds_history 目录中某场比赛的完整赔率历史记录。\n"
            "\n"
            "Use when: 需要查看某场比赛的历史赔率变化时。\n"
            "Workflow: lottery_list_local_odds_matches → lottery_get_local_odds_history"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_local_odds_history(params: GetLocalOddsHistoryInput, ctx: Context) -> str:
        """获取本地赔率历史"""
        try:
            await ctx.log_info(f"获取本地赔率历史: match_id={params.match_id}")
            
            import json
            project_root = Path(__file__).resolve().parent.parent.parent
            odds_dir = project_root / "odds_history"
            
            # 尝试两个可能的文件名
            possible_filenames = [f"{params.match_id}.json", f"jingcai_{params.match_id}.json"]
            history_data = None
            used_filename = None
            
            for filename in possible_filenames:
                file_path = odds_dir / filename
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        history_data = json.load(f)
                    used_filename = filename
                    break
            
            if not history_data:
                return _to_json({
                    "success": False,
                    "data": {"message": f"未找到比赛 {params.match_id} 的赔率历史"},
                    "timestamp": datetime.now().isoformat(),
                })
            
            result = {
                "match_id": params.match_id,
                "filename": used_filename,
                "snapshot_count": len(history_data),
                "snapshots": history_data,
            }
            
            # 趋势分析
            if params.include_trend and len(history_data) >= 2:
                first = history_data[0]
                last = history_data[-1]
                
                # 分析胜平负变化
                if first.get("had") and last.get("had"):
                    result["trend_analysis"] = {
                        "start_time": first.get("timestamp"),
                        "end_time": last.get("timestamp"),
                        "had_changes": {},
                    }
                    
                    for option in ["win", "draw", "lose"]:
                        start_odds = first["had"].get(option)
                        end_odds = last["had"].get(option)
                        if start_odds and end_odds:
                            change_pct = ((end_odds - start_odds) / start_odds) * 100
                            result["trend_analysis"]["had_changes"][option] = {
                                "start": start_odds,
                                "end": end_odds,
                                "change_pct": round(change_pct, 2),
                                "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "stable"
                            }
            
            return _to_json({
                "success": True,
                "data": result,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"lottery_get_local_odds_history failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    # --------------------------------------------------------
    # 工具11：分析本地赔率趋势
    # --------------------------------------------------------
    @mcp.tool(
        name="lottery_analyze_local_odds_trend",
        description=(
            "深度分析某场比赛的本地赔率历史趋势，包括波动幅度、变化方向等。\n"
            "\n"
            "Use when: 需要深入了解赔率变化模式和识别异常波动时。\n"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_analyze_local_odds_trend(params: AnalyzeLocalOddsTrendInput, ctx: Context) -> str:
        """分析本地赔率趋势"""
        try:
            await ctx.log_info(f"分析本地赔率趋势: match_id={params.match_id}, play_type={params.play_type}")
            
            import json
            from statistics import mean, stdev
            project_root = Path(__file__).resolve().parent.parent.parent
            odds_dir = project_root / "odds_history"
            
            # 找到文件
            possible_filenames = [f"{params.match_id}.json", f"jingcai_{params.match_id}.json"]
            history_data = None
            
            for filename in possible_filenames:
                file_path = odds_dir / filename
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        history_data = json.load(f)
                    break
            
            if not history_data or len(history_data) < 2:
                return _to_json({
                    "success": False,
                    "data": {"message": f"比赛 {params.match_id} 的数据不足，无法分析趋势"},
                    "timestamp": datetime.now().isoformat(),
                })
            
            # 提取赔率数据
            odds_field = "had" if params.play_type == "SPF" else "hhad"
            all_odds = {"win": [], "draw": [], "lose": []}
            
            for snapshot in history_data:
                odds = snapshot.get(odds_field)
                if odds:
                    for option in ["win", "draw", "lose"]:
                        if option in odds:
                            all_odds[option].append(odds[option])
            
            # 分析趋势
            analysis = {
                "match_id": params.match_id,
                "play_type": params.play_type,
                "data_points": len(history_data),
                "time_span": None,
                "options": {},
            }
            
            if len(history_data) >= 1:
                analysis["time_span"] = {
                    "start": history_data[0].get("timestamp"),
                    "end": history_data[-1].get("timestamp"),
                }
            
            # 每个选项的统计
            for option in ["win", "draw", "lose"]:
                odds_list = all_odds[option]
                if len(odds_list) >= 2:
                    start = odds_list[0]
                    end = odds_list[-1]
                    change_pct = ((end - start) / start) * 100
                    
                    analysis["options"][option] = {
                        "min": round(min(odds_list), 2),
                        "max": round(max(odds_list), 2),
                        "mean": round(mean(odds_list), 2),
                        "std_dev": round(stdev(odds_list), 2) if len(odds_list) > 1 else 0.0,
                        "start": round(start, 2),
                        "end": round(end, 2),
                        "change_pct": round(change_pct, 2),
                        "volatility": round((stdev(odds_list) / mean(odds_list)) * 100, 2) if len(odds_list) > 1 else 0.0,
                    }
            
            return _to_json({
                "success": True,
                "data": analysis,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"lottery_analyze_local_odds_trend failed: {e}")
            raise_tool_error(f"操作失败: {str(e)}")
    
    logger.info("增强工具注册完成：11个工具（新增3个本地赔率历史工具）")
