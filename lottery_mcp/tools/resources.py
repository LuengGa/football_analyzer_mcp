"""
MCP Server Resources - 规则知识库资源 & 动态数据资源

Resources 是只读数据源，为 LLM 提供上下文。
本模块暴露彩票规则知识库供 LLM 直接读取，并提供动态资源模板供 LLM 读取实时数据快照。

资源 URI 格式:
- lottery://rules/jingcai - 竞彩足球完整规则
- lottery://rules/beidan - 北京单场完整规则
- lottery://rules/ctzc - 传统足彩完整规则
- lottery://rules/play/{play_type} - 各玩法详细规则
- lottery://rules/errors - 错误码映射
- lottery://rules/mixed_parlay - 混合过关专项规则
- lottery://data/today_summary - 今日竞彩足球比赛摘要（动态）
- lottery://analysis/{match_id} - 单场比赛分析快照（动态）
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lottery_mcp")

# 知识库根目录（支持环境变量覆盖）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_PATH = Path(os.environ.get("LOTTERY_RULES_PATH",
    _PROJECT_ROOT / "knowledge"))


def _load_json_file(relative_path: str) -> Optional[Dict[str, Any]]:
    """加载 JSON 文件"""
    try:
        file_path = KNOWLEDGE_BASE_PATH / relative_path
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载资源失败 {relative_path}: {e}")
    return None


def register_resources(mcp):
    """注册所有资源
    
    Args:
        mcp: FastMCP 实例
    """
    
    # ============================================================
    # 竞彩足球完整规则
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/jingcai",
        name="竞彩足球完整规则",
        description="竞彩足球游戏完整规则，包含返还率、串关方式、奖金公式、各玩法详情等",
        mime_type="application/json",
    )
    def get_jingcai_rules() -> str:
        data = _load_json_file("jingcai-rules.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "规则文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 北京单场完整规则
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/beidan",
        name="北京单场完整规则",
        description="北京单场游戏完整规则，包含返还率65%、最大15关、独有玩法等",
        mime_type="application/json",
    )
    def get_beidan_rules() -> str:
        data = _load_json_file("beidan-rules.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "规则文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 传统足彩完整规则
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/ctzc",
        name="传统足彩完整规则",
        description="传统足彩游戏规则，包含胜负彩14场、任选9场、6场半全场、4场进球",
        mime_type="application/json",
    )
    def get_ctzc_rules() -> str:
        data = _load_json_file("ctzc-rules.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "规则文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 彩票规则总览
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/overview",
        name="彩票规则总览",
        description="三大彩种规则总览和对比，包含返还率、销售区域、玩法列表等",
        mime_type="application/json",
    )
    def get_lottery_overview() -> str:
        data = _load_json_file("lottery-rules.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "规则文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 错误码映射
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/errors",
        name="错误码映射表",
        description="体育彩票常见错误码映射与解决方案，供Agent快速定位问题",
        mime_type="application/json",
    )
    def get_error_codes() -> str:
        data = _load_json_file("error-codes.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "错误码文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 混合过关专项规则
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/mixed_parlay",
        name="混合过关专项规则",
        description="混合过关玩法详细规则，包含木桶原则、可混合玩法、限制条件等",
        mime_type="application/json",
    )
    def get_mixed_parlay_rules() -> str:
        data = _load_json_file("jingcai/play_types/06_mixed_parlay.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "混合过关规则文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 竞彩各玩法规则
    # ============================================================
    PLAY_TYPE_FILES = {
        "win_draw_loss": ("jingcai/play_types/01_win_draw_loss.json", "胜平负玩法规则"),
        "handicap_win_draw_loss": ("jingcai/play_types/02_handicap_win_draw_loss.json", "让球胜平负玩法规则"),
        "score": ("jingcai/play_types/03_score.json", "比分玩法规则"),
        "total_goals": ("jingcai/play_types/04_total_goals.json", "总进球玩法规则"),
        "half_full": ("jingcai/play_types/05_half_full.json", "半全场玩法规则"),
    }

    def _create_play_type_resource(play_id: str, file_info: tuple):
        """动态创建玩法规则资源"""
        file_path, description = file_info
        
        def get_play_rules() -> str:
            data = _load_json_file(file_path)
            if data:
                return json.dumps(data, ensure_ascii=False, indent=2)
            return json.dumps({"error": f"玩法规则文件未找到: {file_path}"}, ensure_ascii=False)
        
        get_play_rules.__name__ = f"get_{play_id}_rules"
        get_play_rules.__doc__ = description
        return get_play_rules

    # 注册各玩法资源
    for play_id, file_info in PLAY_TYPE_FILES.items():
        resource_func = _create_play_type_resource(play_id, file_info)
        
        mcp.resource(
            uri=f"lottery://rules/play/{play_id}",
            name=file_info[1],
            description=f"竞彩{file_info[1]}，包含选项、过关限制、示例等",
            mime_type="application/json",
        )(resource_func)

    # ============================================================
    # Agent 指南
    # ============================================================
    @mcp.resource(
        uri="lottery://agent/guidelines",
        name="Agent行为指南",
        description="彩票投注Agent行为规范和决策流程指南",
        mime_type="application/json",
    )
    def get_agent_guidelines() -> str:
        data = _load_json_file("agent-guidelines.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "Agent指南文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 玩法索引
    # ============================================================
    @mcp.resource(
        uri="lottery://rules/play_index",
        name="玩法索引",
        description="所有彩种玩法索引，快速查找玩法规则文件",
        mime_type="application/json",
    )
    def get_play_index() -> str:
        data = _load_json_file("play-index.json")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"error": "玩法索引文件未找到"}, ensure_ascii=False)

    # ============================================================
    # 动态资源模板：今日比赛摘要
    # ============================================================
    @mcp.resource(
        uri="lottery://data/today_summary",
        name="今日比赛摘要",
        description="今日竞彩足球比赛摘要，含赔率、分析评分，实时从缓存读取",
        mime_type="text/markdown",
    )
    async def get_today_summary() -> str:
        """获取今日比赛摘要（Markdown 格式）"""
        from .data_tools import get_cached_matches, _get_manager

        matches = get_cached_matches()
        if not matches:
            return (
                "# 今日比赛摘要\n\n"
                "> 暂无比赛数据。请先调用 `lottery_fetch_today_matches` 获取今日比赛列表。\n"
            )

        lines = [
            f"# 今日比赛摘要（共 {len(matches)} 场）\n",
            f"> 数据时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        ]

        for i, match in enumerate(matches, 1):
            match_id = match.get("match_id", f"match_{i}")
            league = match.get("league", "未知联赛")
            home_team = match.get("home_team", "主队")
            away_team = match.get("away_team", "客队")
            match_time = match.get("match_time", "")

            lines.append(f"## {i}. [{league}] {home_team} vs {away_team}")
            if match_time:
                lines.append(f"- **开赛时间**：{match_time}")
            lines.append(f"- **比赛ID**：`{match_id}`")

            # 尝试获取赔率数据
            odds = match.get("odds", {})
            if odds:
                home_odds = odds.get("home_win", "-")
                draw_odds = odds.get("draw", "-")
                away_odds = odds.get("away_win", "-")
                lines.append(
                    f"- **欧赔**：主胜 {home_odds} / 平局 {draw_odds} / 客胜 {away_odds}"
                )
            else:
                # 尝试从 manager 获取赔率
                try:
                    manager = _get_manager()
                    odds_result = await manager.get_lottery_odds_change(match_id)
                    if odds_result and odds_result.get("data"):
                        od = odds_result["data"]
                        lines.append(
                            f"- **欧赔（实时）**：{od}"
                        )
                except Exception:
                    lines.append("- **欧赔**：暂无数据")

            lines.append("")

        return "\n".join(lines)

    # ============================================================
    # 动态资源模板：单场比赛分析快照
    # ============================================================
    @mcp.resource(
        uri="lottery://analysis/{match_id}",
        name="单场比赛分析快照",
        description="单场比赛分析快照，包含泊松模型、Elo评分、综合推荐等",
        mime_type="text/markdown",
    )
    def get_match_analysis(match_id: str) -> str:
        """获取单场比赛分析报告（Markdown 格式）

        Args:
            match_id: 比赛ID（从URI路径提取）
        """
        from .analysis_tools import get_analysis_engine

        if not match_id:
            return (
                "# 比赛分析\n\n"
                "> 错误：请在 URI 中指定比赛ID，例如 `lottery://analysis/match_001`\n"
            )

        try:
            engine = get_analysis_engine()
            analysis = engine.analyze_match(match_id)
        except ValueError as e:
            return (
                f"# 比赛分析：`{match_id}`\n\n"
                f"> 错误：{e}\n"
            )
        except Exception as e:
            return (
                f"# 比赛分析：`{match_id}`\n\n"
                f"> 分析失败：{e}\n"
            )

        # 将分析结果格式化为 Markdown
        match_data = analysis.get("match_data", {})
        home_team = match_data.get("home_team", "主队")
        away_team = match_data.get("away_team", "客队")
        league = match_data.get("league", "未知联赛")
        lottery_type = analysis.get("lottery_type", "竞彩足球")

        lines = [
            f"# 比赛分析：{home_team} vs {away_team}\n",
            f"- **联赛**：{league}",
            f"- **彩种**：{lottery_type}",
            f"- **比赛ID**：`{match_id}`",
            f"- **分析时间**：{analysis.get('timestamp', datetime.now().isoformat())}",
            "",
        ]

        # 综合评分
        combined_score = analysis.get("combined_score", 0)
        risk_level = analysis.get("risk_level", "未知")
        agreement_level = analysis.get("agreement_level", "未知")
        recommendation = analysis.get("recommendation", "暂无推荐")

        lines.append("## 综合评估\n")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 综合评分 | {combined_score:.1f} |")
        lines.append(f"| 风险等级 | {risk_level} |")
        lines.append(f"| 模型一致性 | {agreement_level} |")
        lines.append(f"| 推荐方向 | {recommendation} |")
        lines.append("")

        # 统计模型详情
        models = analysis.get("statistical_models", {})
        if models:
            lines.append("## 统计模型\n")
            for model_name, model_data in models.items():
                if isinstance(model_data, dict):
                    lines.append(f"### {model_name.upper()} 模型\n")
                    for key, value in model_data.items():
                        if isinstance(value, float):
                            lines.append(f"- **{key}**：{value:.4f}")
                        else:
                            lines.append(f"- **{key}**：{value}")
                    lines.append("")

        return "\n".join(lines)

    logger.info("已注册 %d 个 MCP Resources（含 %d 个动态资源模板）", 14, 2)
