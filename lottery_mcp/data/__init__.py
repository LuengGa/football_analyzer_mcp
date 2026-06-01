"""
数据获取模块 (lottery_mcp.data)
==============================

提供竞彩足球、北京单场、传统足彩的数据获取功能。

模块结构:
    - fetcher: 核心数据获取（竞彩/北单/传统足彩官方API）
    - sources: 多源聚合数据（国际API + 国内网站）
    - team_mapping: 球队名称映射（中英文对照）

使用方法:
    from lottery_mcp.data import fetch_today_matches, FreeDataSourceManager
    
    # 获取今日比赛
    matches = fetch_today_matches("jingcai")
    
    # 多源数据管理器
    manager = FreeDataSourceManager()
    standings = await manager.get_standings("英超")
"""

# 从 fetcher 模块导入核心函数
from .fetcher import (
    # 主要接口
    fetch_today_matches,
    fetch_jingcai_matches,
    fetch_beidan_matches,
    fetch_ctzc_matches,
    
    # 数据标准化
    normalize_jingcai_match,
    normalize_beidan_match,
    normalize_ctzc_match,
    
    # 赔率提取
    extract_jingcai_odds,
    extract_beidan_odds,
    extract_ctzc_odds,
    
    # 赔率历史
    save_odds_snapshot,
    load_odds_history,
    get_matches_with_history,
    calculate_odds_change,
    
    # 工具函数
    parse_crs_field,
    parse_beidan_score_field,
    
    # 常量
    API_ENDPOINTS,
    CTZC_GAME_CODES,
    POOL_CODE_NAMES,
)

# 从 sources 模块导入多源数据管理器
from .sources import (
    FreeDataSourceManager,
    DataCache,
    QuotaTracker,
    AsyncHTTPClient,
    make_response,
    get_manager,
    
    # 常量
    LEAGUE_CODE_MAP,
    LEAGUE_ID_MAP,
    THE_ODDS_API_LEAGUE_MAP,
)

# 从 team_mapping 模块导入名称映射
from .team_mapping import (
    TEAM_NAME_MAPPING,
    normalize_team_name,
    normalize_league_name,
    match_team_name,
    team_to_chinese,
    league_to_chinese,
)

__all__ = [
    # 核心接口
    "fetch_today_matches",
    "fetch_jingcai_matches", 
    "fetch_beidan_matches",
    "fetch_ctzc_matches",
    
    # 数据标准化
    "normalize_jingcai_match",
    "normalize_beidan_match",
    "normalize_ctzc_match",
    
    # 赔率提取
    "extract_jingcai_odds",
    "extract_beidan_odds",
    "extract_ctzc_odds",
    
    # 赔率历史
    "save_odds_snapshot",
    "load_odds_history",
    "get_matches_with_history",
    "calculate_odds_change",
    
    # 工具函数
    "parse_crs_field",
    "parse_beidan_score_field",
    
    # 多源数据管理器
    "FreeDataSourceManager",
    "DataCache",
    "QuotaTracker",
    "AsyncHTTPClient",
    "make_response",
    "get_manager",
    
    # 名称映射
    "TEAM_NAME_MAPPING",
    "normalize_team_name",
    "normalize_league_name",
    "match_team_name",
    "team_to_chinese",
    "league_to_chinese",
    
    # 常量
    "API_ENDPOINTS",
    "CTZC_GAME_CODES",
    "POOL_CODE_NAMES",
    "LEAGUE_CODE_MAP",
    "LEAGUE_ID_MAP",
    "THE_ODDS_API_LEAGUE_MAP",
]
