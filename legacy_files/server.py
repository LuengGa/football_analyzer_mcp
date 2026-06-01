"""
Lottery MCP Server - MCP 服务器核心模块

提供 MCP 服务器的创建、配置和运行功能。
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict

from mcp.server.fastmcp import FastMCP

# ============================================================
# System Instructions
# ============================================================

SYSTEM_INSTRUCTIONS = """# 竞彩足球分析 MCP 服务器

## 角色
你是专业的竞彩足球分析助手，提供规则验证、数据分析、投注建议和风控服务。

## 核心能力
- 规则验证: 投注/串关合法性验证、奖金精确计算
- 数据分析: 泊松/Elo/xG三模型、五大玩法概率计算
- 投注建议: 每日推荐、凯利公式、价值投注识别
- 风控守卫: 多阶段规则检查、强制拒绝违规操作

## 风控红线
- 绝对禁止: 单日/单注超10000元、串关超8场、未成年人投注
- 需要确认: 单日超1000元、连续追号超5期
- 所有分析仅供参考，彩票有风险，投注需理性

## 工具选用
- 投注记录: lottery_track_bet（持久化）
- 投注统计: lottery_get_bet_statistics（完整统计）
- 串关方案: lottery_smart_parlay（专业版含容错+Kelly）
- 赔率监控: lottery_monitor_odds_changes（专业版含价值窗口）

## 最佳实践
1. 先验证后投注，始终先调用 lottery_validate_bet
2. 分散风险，避免资金集中在少数比赛
3. 理性投注，凯利公式控制投注额不超过资金5%
4. 关注赔率异动和阵容变化等风险信号
"""


# ============================================================
# Logging Configuration
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("lottery_mcp")


# ============================================================
# Application State
# ============================================================

class AppState:
    """应用程序状态管理"""
    
    def __init__(self):
        self.startup_time: str = ""
        self.request_count: int = 0
        self.error_count: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.active_sessions: int = 0
        self.config: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "startup_time": self.startup_time,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "active_sessions": self.active_sessions,
        }


# 全局应用状态实例
app_state = AppState()


# ============================================================
# Lifespan Management
# ============================================================

@asynccontextmanager
async def app_lifespan(server: Any) -> AsyncIterator[AppState]:
    """MCP应用生命周期管理
    
    处理应用的启动和关闭逻辑。
    
    Args:
        server: MCP服务器实例
        
    Yields:
        AppState: 应用状态对象
    """
    from datetime import datetime
    
    # 启动逻辑
    logger.info("=" * 60)
    logger.info("彩票规则验证 MCP 服务器启动")
    logger.info("=" * 60)
    
    # 初始化应用状态
    app_state.startup_time = datetime.now().isoformat()
    app_state.request_count = 0
    app_state.error_count = 0
    app_state.cache_hits = 0
    app_state.cache_misses = 0
    app_state.active_sessions = 0
    
    # 记录启动信息
    logger.info(f"启动时间: {app_state.startup_time}")
    logger.info(f"系统指令版本: 1.0.0")
    logger.info(f"支持彩种: 竞彩足球, 北京单场, 传统足彩")
    
    try:
        # 初始化缓存
        logger.info("初始化缓存系统...")
        _init_cache()
        
        # 加载规则引擎
        logger.info("加载规则引擎...")
        _init_rules_engine()
        
        # 初始化数据源
        logger.info("初始化数据源...")
        _init_data_sources()
        
        # 初始化统一分析流水线
        logger.info("初始化统一分析流水线...")
        _init_analysis_pipeline()
        
        logger.info("启动完成，等待连接...")
        logger.info("-" * 60)
        
        yield app_state
        
    finally:
        # 关闭逻辑
        logger.info("-" * 60)
        logger.info("MCP 服务器关闭中...")
        
        # 记录运行统计
        logger.info(f"运行统计:")
        logger.info(f"  - 总请求数: {app_state.request_count}")
        logger.info(f"  - 错误数: {app_state.error_count}")
        logger.info(f"  - 缓存命中: {app_state.cache_hits}")
        logger.info(f"  - 缓存未命中: {app_state.cache_misses}")
        
        # 清理资源
        logger.info("清理资源...")
        _cleanup_resources()
        
        logger.info("服务器已关闭")
        logger.info("=" * 60)


def _init_cache():
    """初始化缓存系统"""
    import os
    from pathlib import Path

    cache_dir = Path(os.environ.get("LOTTERY_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / ".cache" / "lottery_data")))
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"缓存目录: {cache_dir} (存在: {cache_dir.exists()})")


def _init_rules_engine():
    """初始化规则引擎"""
    try:
        from lottery_mcp.tools.rules_tools import RulesEngine
        engine = RulesEngine()
        supported_lotteries = list(engine.PLAY_LIMITS.keys())
        logger.info(f"规则引擎初始化成功，支持彩种: {supported_lotteries}")
        for lottery, limits in engine.PLAY_LIMITS.items():
            logger.info(f"  {lottery} 玩法: {list(limits.keys())}")
    except Exception as e:
        logger.warning(f"规则引擎初始化失败（将使用内置默认值）: {e}")


def _init_data_sources():
    """初始化数据源"""
    try:
        from lottery_mcp.data.sources import FreeDataSourceManager
        manager = FreeDataSourceManager()
        logger.info(f"数据源管理器初始化成功，已加载 {len(manager.api_keys)} 个API密钥")
        cache_info = manager.cache.info()
        logger.info(f"  缓存状态: {cache_info['total_entries']} 条目, TTL={cache_info['ttl_seconds']}s")
    except Exception as e:
        logger.warning(f"数据源初始化失败（将在首次请求时重试）: {e}")


def _init_analysis_pipeline():
    """初始化统一分析流水线
    
    使用延迟导入避免循环导入问题。
    """
    try:
        # 延迟导入避免循环导入
        from lottery_mcp import initialize, get_pipeline
        initialize()
        pipeline = get_pipeline()
        logger.info(f"统一分析流水线初始化成功:")
        logger.info(f"  已注册插件: {pipeline.get_registered_plays()}")
        logger.info(f"  验证规则数: {pipeline.synergy_validator.rule_count}")
    except ImportError as e:
        logger.warning(f"统一分析流水线导入失败: {e}")
    except RuntimeError as e:
        logger.warning(f"统一分析流水线运行时错误: {e}")
    except AttributeError as e:
        logger.warning(f"统一分析流水线属性错误: {e}")


async def _cleanup_resources_async():
    """异步清理资源
    
    使用独立的异步函数避免在运行中的事件循环上调用 run_until_complete。
    """
    try:
        from lottery_mcp.data.sources import get_manager
        manager = get_manager()
        # 使用 aclose() 替代 close() 进行异步关闭
        await manager.http.aclose()
        logger.info("HTTP客户端已关闭")
    except (ImportError, AttributeError, RuntimeError) as e:
        logger.warning(f"清理HTTP客户端时出错: {e}")

    try:
        from lottery_mcp.data.sources import get_manager
        manager = get_manager()
        manager.cache.clear()
        logger.info("缓存已清理")
    except (ImportError, AttributeError) as e:
        logger.warning(f"清理缓存时出错: {e}")


def _cleanup_resources():
    """清理资源 - 同步入口
    
    创建新的事件循环来执行异步清理，避免与现有事件循环冲突。
    """
    import asyncio
    try:
        # 使用 asyncio.run() 创建新的事件循环执行清理
        asyncio.run(_cleanup_resources_async())
    except RuntimeError as e:
        # 如果无法创建新事件循环，记录错误但不抛出
        logger.warning(f"资源清理时事件循环错误: {e}")


# ============================================================
# Health Check
# ============================================================

def startup_health_check() -> Dict[str, Any]:
    """启动健康检查
    
    检查所有依赖项是否正常工作。
    
    Returns:
        健康检查结果
    """
    checks = []
    overall_status = "ok"
    
    # 检查 numpy
    try:
        import numpy as np
        checks.append({
            "name": "numpy",
            "status": "ok",
            "message": f"版本 {np.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "numpy",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 scipy
    try:
        import scipy
        checks.append({
            "name": "scipy",
            "status": "ok",
            "message": f"版本 {scipy.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "scipy",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 pydantic
    try:
        import pydantic
        checks.append({
            "name": "pydantic",
            "status": "ok",
            "message": f"版本 {pydantic.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "pydantic",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 mcp
    try:
        import mcp
        checks.append({
            "name": "mcp",
            "status": "ok",
            "message": "已安装"
        })
    except ImportError as e:
        checks.append({
            "name": "mcp",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    return {
        "overall_status": overall_status,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# Server Creation
# ============================================================

def create_mcp_server() -> FastMCP:
    """创建 MCP 服务器实例
    
    Returns:
        配置好的 FastMCP 实例
    """
    mcp = FastMCP(
        "lottery_mcp",
        lifespan=app_lifespan,
        instructions=SYSTEM_INSTRUCTIONS,
    )
    
    # 注册所有工具、资源、提示词
    _register_all_components(mcp)
    
    return mcp


def _register_all_components(mcp: FastMCP):
    """注册所有 MCP 组件
    
    Args:
        mcp: FastMCP 实例
    """
    # 注册工具
    from .tools import register_all_tools
    register_all_tools(mcp)
    
    # 注册资源
    from .tools.resources import register_resources
    register_resources(mcp)
    
    # 注册提示词
    from .tools.prompts import register_prompts
    register_prompts(mcp)


def run_mcp_server():
    """运行 MCP 服务器（入口点函数）"""
    health = startup_health_check()
    logger.info(f"[启动] MCP健康检查: {health['overall_status']}")
    for check in health["checks"]:
        status = check["status"]
        icon = "OK" if status == "ok" else "WARN" if status == "warning" else "FAIL"
        logger.info(f"  [{icon}] {check['name']}: {check['message']}")
    
    mcp = create_mcp_server()
    mcp.run(transport="stdio")
