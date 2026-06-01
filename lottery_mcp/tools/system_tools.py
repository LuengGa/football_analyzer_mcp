"""
MCP Server System Tools - System management and monitoring tools.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from mcp.server.fastmcp import Context

from .data_tools import set_cached_matches
from .helpers import raise_tool_error, _to_json
from lottery_mcp.server import app_state, startup_health_check
from lottery_mcp.models import GetSystemStatusInput, ManageConfigInput

logger = logging.getLogger("lottery_mcp")

# 配置文件路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = Path(os.environ.get("LOTTERY_DATA_DIR", str(_PROJECT_ROOT / ".cache" / "lottery_data")))
_CONFIG_FILE = _CONFIG_DIR / "user_config.json"

# 确保目录存在
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# 默认配置
_DEFAULT_CONFIG: Dict[str, Any] = {
    "max_daily_stake": 10000,
    "max_single_stake": 10000,
    "risk_preference": "balanced",
    "warning_threshold": 1000,
}

# 配置项元信息
_CONFIG_META: Dict[str, dict] = {
    "max_daily_stake": {"label": "单日最大投注", "type": "number"},
    "max_single_stake": {"label": "单注最大投注", "type": "number"},
    "risk_preference": {"label": "风险偏好", "type": "string", "options": ["conservative", "balanced", "aggressive"]},
    "warning_threshold": {"label": "警告阈值", "type": "number"},
}


def _load_user_config() -> Dict[str, Any]:
    """从 JSON 文件加载用户配置，文件不存在则使用默认值"""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 合并：确保新增的配置项有默认值
            config = {**_DEFAULT_CONFIG, **saved}
            return config
        except Exception as e:
            logger.warning(f"加载配置文件失败，使用默认值: {e}")
    return dict(_DEFAULT_CONFIG)


def _save_user_config(config: Dict[str, Any]) -> bool:
    """保存用户配置到 JSON 文件"""
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


# 用户配置（启动时从文件加载，运行时在内存中操作，修改时同步到文件）
_user_config: Dict[str, Any] = _load_user_config()


# ============================================================
# Tool Functions
# ============================================================

async def lottery_get_system_status(params: GetSystemStatusInput, ctx: Context) -> str:
    """获取系统状态
    
    根据 action 参数执行不同操作:
    - status: 获取系统状态（默认）
    - health: 执行健康检查
    - clear_cache: 清除缓存
    """
    try:
        action = params.action
        
        if action == "health":
            return await _do_health_check(ctx)
        elif action == "clear_cache":
            return await _do_clear_cache(params.cache_type, ctx)
        else:  # status (default)
            return await _do_get_status(params.include_details, ctx)
        
    except Exception as e:
        logger.error(f"系统操作失败: {e}")
        raise_tool_error(f"系统操作失败: {str(e)}")


async def _do_get_status(include_details: bool, ctx: Context) -> str:
    """获取系统状态"""
    await ctx.report_progress(0.5, "正在获取系统状态...")
    
    from .data_tools import get_cache_stats
    cache_stats = get_cache_stats()
    
    status = {
        "status": "running",
        "startup_time": app_state.startup_time,
        "request_count": app_state.request_count,
        "error_count": app_state.error_count,
        "cache_hits": app_state.cache_hits,
        "cache_misses": app_state.cache_misses,
        "active_sessions": app_state.active_sessions,
        "data_cache_stats": cache_stats,
    }
    
    if include_details:
        status["details"] = {
            "version": "2.0.0",
            "supported_lotteries": ["竞彩足球", "北京单场"],
            "features": [
                "规则验证",
                "强制风控",
                "数据分析",
                "投注建议",
                "统一流水线 (Phase 2)",
            ],
        }
    
    await ctx.report_progress(1.0, "状态获取完成")
    
    return _to_json({
        "success": True,
        "data": status,
        "timestamp": datetime.now().isoformat(),
    })


async def _do_health_check(ctx: Context) -> str:
    """执行健康检查"""
    await ctx.report_progress(0.5, "正在执行健康检查...")
    
    result = startup_health_check()
    
    await ctx.report_progress(1.0, "健康检查完成")
    
    return _to_json({
        "success": True,
        "data": result,
        "timestamp": datetime.now().isoformat(),
    })


async def _do_clear_cache(cache_type: str, ctx: Context) -> str:
    """清除缓存"""
    await ctx.report_progress(0.5, f"正在清除{cache_type}缓存...")
    await ctx.log_info(f"[系统] 清除缓存: {cache_type}")
    
    if cache_type == "all":
        set_cached_matches([])
        from .prediction_tools import invalidate_pipeline_cache
        invalidate_pipeline_cache()
        message = "所有缓存已清除"
    elif cache_type == "matches":
        set_cached_matches([])
        from .prediction_tools import invalidate_pipeline_cache
        invalidate_pipeline_cache()
        message = "比赛缓存已清除"
    elif cache_type == "odds":
        message = "赔率缓存已清除"
    else:
        message = f"缓存类型 {cache_type} 已清除"
    
    await ctx.report_progress(1.0, "缓存清除完成")
    
    return _to_json({
        "success": True,
        "data": {
            "cache_type": cache_type,
            "message": message,
        },
        "timestamp": datetime.now().isoformat(),
    })


async def lottery_manage_config(params: ManageConfigInput, ctx: Context) -> str:
    """管理用户配置

    根据 action 参数执行不同操作:
    - get: 获取配置（可指定 config_key，不指定则返回全部）
    - set: 修改配置（需要 config_key 和 config_value）
    - reset: 重置配置为默认值（可指定 config_key，不指定则重置全部）
    """
    try:
        action = params.action

        if action == "get":
            return await _do_get_config(params.config_key, ctx)
        elif action == "set":
            return await _do_set_config(params.config_key, params.config_value, ctx)
        elif action == "reset":
            return await _do_reset_config(params.config_key, ctx)
        else:
            raise_tool_error(f"不支持的操作类型: {action}，支持: get/set/reset")

    except Exception as e:
        logger.error(f"配置管理失败: {e}")
        raise_tool_error(f"配置管理失败: {str(e)}")


async def _do_get_config(config_key: str | None, ctx: Context) -> str:
    """获取配置"""
    await ctx.report_progress(0.5, "正在获取配置...")

    if config_key is not None:
        if config_key not in _user_config:
            raise_tool_error(f"未知配置项: {config_key}，可选: {', '.join(_user_config.keys())}")
        data = {
            "config_key": config_key,
            "config_value": _user_config[config_key],
            "meta": _CONFIG_META.get(config_key, {}),
        }
    else:
        data = {
            "configs": {
                key: {
                    "value": value,
                    "meta": _CONFIG_META.get(key, {}),
                }
                for key, value in _user_config.items()
            }
        }

    await ctx.report_progress(1.0, "配置获取完成")
    await ctx.log_info(f"[配置] 获取配置: {config_key or '全部'}")

    return _to_json({
        "success": True,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    })


async def _do_set_config(config_key: str | None, config_value: str | None, ctx: Context) -> str:
    """修改配置"""
    if config_key is None:
        raise_tool_error("修改配置需要指定 config_key")
    if config_value is None:
        raise_tool_error("修改配置需要指定 config_value")

    if config_key not in _user_config:
        raise_tool_error(f"未知配置项: {config_key}，可选: {', '.join(_user_config.keys())}")

    await ctx.report_progress(0.5, f"正在修改配置 {config_key}...")

    # 类型转换
    meta = _CONFIG_META.get(config_key, {})
    if meta.get("type") == "number":
        try:
            config_value = float(config_value)
        except ValueError:
            raise_tool_error(f"配置项 {config_key} 需要数值类型，收到: {config_value}")

    # 枚举校验
    if "options" in meta and config_value not in meta["options"]:
        raise_tool_error(f"配置项 {config_key} 的值必须是: {', '.join(meta['options'])}，收到: {config_value}")

    old_value = _user_config[config_key]
    _user_config[config_key] = config_value
    _save_user_config(_user_config)  # 持久化到文件

    await ctx.report_progress(1.0, "配置修改完成")
    await ctx.log_info(f"[配置] 修改 {config_key}: {old_value} -> {config_value}")

    return _to_json({
        "success": True,
        "data": {
            "config_key": config_key,
            "old_value": old_value,
            "new_value": config_value,
            "message": f"配置项 {config_key} 已更新",
        },
        "timestamp": datetime.now().isoformat(),
    })


async def _do_reset_config(config_key: str | None, ctx: Context) -> str:
    """重置配置为默认值"""
    defaults = {
        "max_daily_stake": 10000,
        "max_single_stake": 10000,
        "risk_preference": "balanced",
        "warning_threshold": 1000,
    }

    await ctx.report_progress(0.5, f"正在重置配置{config_key or ''}...")

    if config_key is not None:
        if config_key not in defaults:
            raise_tool_error(f"未知配置项: {config_key}，可选: {', '.join(defaults.keys())}")
        old_value = _user_config[config_key]
        _user_config[config_key] = defaults[config_key]
        reset_items = {config_key: {"old_value": old_value, "new_value": defaults[config_key]}}
    else:
        reset_items = {}
        for key, default_val in defaults.items():
            old_value = _user_config[key]
            _user_config[key] = default_val
            reset_items[key] = {"old_value": old_value, "new_value": default_val}
    _save_user_config(_user_config)  # 持久化到文件

    await ctx.report_progress(1.0, "配置重置完成")
    await ctx.log_info(f"[配置] 重置配置: {config_key or '全部'}")

    return _to_json({
        "success": True,
        "data": {
            "reset_items": reset_items,
            "message": f"配置{config_key or ''}已重置为默认值",
        },
        "timestamp": datetime.now().isoformat(),
    })





# ============================================================
# Tool Registration
# ============================================================

def register_system_tools(mcp):
    """注册系统管理工具"""
    from mcp.server.fastmcp import Context
    
    @mcp.tool(
        name="lottery_get_system_status",
        description="""获取系统运行状态

支持三种操作模式（action参数）：
- status: 获取系统状态（默认，只读操作）
  - 启动时间、请求统计、缓存命中率、活动会话数
- health: 执行健康检查（只读操作）
  - 检查所有依赖项是否正常工作
- clear_cache: 清除系统缓存（⚠ 破坏性操作，会清除数据）
  - 清除指定类型的缓存（all/matches/odds）

Use when: 需要了解系统运行状况、验证健康状态或管理缓存时。

Workflow: 独立诊断工具，用于排查数据源和缓存问题。""",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_system_status(params: GetSystemStatusInput, ctx: Context) -> str:
        return await lottery_get_system_status(params, ctx)

    @mcp.tool(
        name="lottery_manage_config",
        description="""管理系统配置，包括自定义投注限额、风险偏好和警告阈值。配置仅在当前会话有效。

支持三种操作模式（action参数）：
- get: 获取配置
  - 不指定 config_key 返回全部配置及其说明
  - 指定 config_key 返回单个配置项的值和元信息
- set: 修改配置
  - 需要同时提供 config_key 和 config_value
  - 数值类型配置会自动转换，枚举类型会校验合法值
- reset: 重置配置为默认值
  - 不指定 config_key 重置全部配置
  - 指定 config_key 仅重置该配置项

可用配置项：
- max_daily_stake: 单日最大投注（默认10000）
- max_single_stake: 单注最大投注（默认10000）
- risk_preference: 风险偏好 conservative/balanced/aggressive（默认balanced）
- warning_threshold: 警告阈值（默认1000）

Use when: 需要查看或调整投注限额、风险偏好等个性化配置时。

Workflow: 修改配置后，guardrails_tools 会自动读取新配置进行风控检查。""",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_manage_config(params: ManageConfigInput, ctx: Context) -> str:
        return await lottery_manage_config(params, ctx)
