"""
历史数据查询工具

提供对 football_data.zip 历史数据的查询接口：
- 27个联赛 86,040场比赛
- 2020-2026赛季
- 包含赔率、统计等80+字段
"""

import logging
from typing import Any, Dict, List, Optional

from lottery_mcp.data.historical import get_historical_manager

logger = logging.getLogger("lottery_mcp")


def register_historical_tools(mcp):
    """注册历史数据查询工具"""
    
    @mcp.tool(
        name="lottery_get_historical_data_summary",
        description="""获取历史数据总览 - 查看football_data.zip中所有可用的历史数据统计

功能：
- 27个联赛
- 86,040场比赛
- 2020-2026赛季
- 包含赔率、统计等80+字段

示例调用：
- lottery_get_historical_data_summary()
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def get_historical_data_summary() -> str:
        """获取历史数据总览"""
        try:
            manager = get_historical_manager()
            summary = manager.get_data_summary()
            
            leagues = manager.get_league_list()
            
            # 安全地处理赛季
            seasons_list = summary['seasons']
            season_range = ""
            if seasons_list:
                try:
                    season_range = f"{min(seasons_list)} - {max(seasons_list)}"
                except (TypeError, ValueError):
                    season_range = seasons_list[0] if seasons_list else "未知"
            
            output = [
                "📊 历史数据总览",
                "=" * 60,
                f"总联赛数: {summary['total_leagues']}",
                f"总比赛数: {summary['total_matches']:,}",
                f"总球队数: {summary['total_teams']}",
                f"赛季范围: {season_range}",
                "",
                "🏆 联赛列表:",
                "-" * 60,
            ]
            
            for league in sorted(leagues, key=lambda x: x['total_matches'], reverse=True):
                seasons_val = league.get('seasons', 0)
                if isinstance(seasons_val, (list, tuple, set)):
                    seasons_str = f"({len(seasons_val)}个赛季)"
                else:
                    seasons_str = f"({seasons_val}个赛季)"
                
                output.append(
                    f"  • {league['name']}: {league['total_matches']:,}场比赛 {seasons_str}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"获取历史数据总览失败: {e}")
            return f"获取历史数据总览失败: {e}"
    
    @mcp.tool(
        name="lottery_search_league",
        description="""搜索联赛 - 根据名称或别名搜索联赛，返回匹配结果

参数：
- query: 联赛名称或别名，支持中文、英文、简称等
  例如: 'premier league', '英超', 'epl', 'bundesliga'

示例调用：
- lottery_search_league(query="premier")
- lottery_search_league(query="英超")
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def search_league(query: str) -> str:
        """搜索联赛
        
        Args:
            query: 联赛名称或别名
        """
        try:
            manager = get_historical_manager()
            results = manager.search_league(query)
            
            if not results:
                return f"未找到匹配 '{query}' 的联赛"
            
            output = [f"🔍 搜索 '{query}' 结果:", ""]
            
            for league in results:
                seasons_list = sorted(league['seasons'], reverse=True)
                output.append(
                    f"📌 {league['name']}\n"
                    f"   ID: {league['id']}\n"
                    f"   比赛数: {league['total_matches']:,}\n"
                    f"   赛季: {', '.join(seasons_list[:5])}"
                )
                if len(league['seasons']) > 5:
                    output[-1] += f" ... +{len(league['seasons'])-5}个"
                output.append("")
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"搜索联赛失败: {e}")
            return f"搜索联赛失败: {e}"
    
    @mcp.tool(
        name="lottery_get_league_matches",
        description="""获取联赛比赛列表 - 查看特定联赛的比赛历史

参数：
- league: 联赛名称，如 'premier league', 'la liga'
- season: 赛季（可选），如 '2324', '2023-2024'
- limit: 返回数量限制（默认50，最大500）

示例调用：
- lottery_get_league_matches(league="premier league", limit=100)
- lottery_get_league_matches(league="la liga", season="2324")
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def get_league_matches(league: str, season: Optional[str] = None, limit: int = 50) -> str:
        """获取联赛比赛列表
        
        Args:
            league: 联赛名称
            season: 赛季（可选）
            limit: 返回数量限制
        """
        try:
            manager = get_historical_manager()
            matches = manager.get_league_matches(league, season, limit)
            
            if not matches:
                return f"未找到 {league} 的比赛数据"
            
            output = [
                f"📋 {league} 比赛列表",
                f"{'赛季: ' + season if season else '所有赛季'}",
                f"共 {len(matches)} 场比赛",
                "=" * 80,
            ]
            
            for i, match in enumerate(matches, 1):
                home = match.get('home_team', '')
                away = match.get('away_team', '')
                home_goals = match.get('full_time_home_goals', '-')
                away_goals = match.get('full_time_away_goals', '-')
                date = match.get('date', '')
                match_season = match.get('season', '')
                
                output.append(
                    f"{i:3}. [{match_season}] {date} | {home} {home_goals}-{away_goals} {away}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"获取联赛比赛失败: {e}")
            return f"获取联赛比赛失败: {e}"
    
    @mcp.tool(
        name="lottery_get_team_history",
        description="""获取球队历史战绩 - 查看特定球队的历史比赛记录

参数：
- team_name: 球队名称，如 'Manchester United', 'Liverpool'
- limit: 返回数量限制（默认50，最大200）

示例调用：
- lottery_get_team_history(team_name="Manchester United")
- lottery_get_team_history(team_name="Liverpool", limit=100)
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def get_team_history(team_name: str, limit: int = 50) -> str:
        """获取球队历史战绩
        
        Args:
            team_name: 球队名称
            limit: 返回数量限制
        """
        try:
            manager = get_historical_manager()
            
            stats = manager.get_team_stats(team_name)
            matches = manager.get_team_history(team_name, limit)
            
            if 'error' in stats:
                return stats['error']
            
            output = [
                f"📊 {stats['team']} 历史战绩统计",
                "=" * 60,
                f"总比赛: {stats['total_matches']}",
                f"胜/平/负: {stats['wins']}/{stats['draws']}/{stats['losses']}",
            ]
            
            # 安全地处理可选字段
            if 'win_rate' in stats:
                output.append(f"胜率: {stats['win_rate']}")
            if 'goals_for' in stats and 'goals_against' in stats:
                line = f"进球/失球: {stats['goals_for']}/{stats['goals_against']}"
                if 'goal_diff' in stats:
                    try:
                        goal_diff = int(stats['goal_diff'])
                        line += f" (净{goal_diff:+d})"
                    except (TypeError, ValueError):
                        line += f" (净{stats['goal_diff']:+f})"
                output.append(line)
            if 'avg_goals_for' in stats and 'avg_goals_against' in stats:
                output.append(f"场均进球/失球: {stats['avg_goals_for']}/{stats['avg_goals_against']}")
            
            output.extend([
                "",
                f"📅 最近比赛 (共显示{len(matches)}场):",
                "-" * 60,
            ])
            
            for i, match in enumerate(matches, 1):
                is_home = match['home_team'].lower() == team_name.lower()
                opp = match['away_team'] if is_home else match['home_team']
                prefix = "主" if is_home else "客"
                
                home_goals = match.get('full_time_home_goals', '-')
                away_goals = match.get('full_time_away_goals', '-')
                
                result = match.get('full_time_result', '')
                
                if is_home:
                    if 'H' in result.upper():
                        outcome = "胜 ✓"
                    elif 'D' in result.upper():
                        outcome = "平"
                    else:
                        outcome = "负 ✗"
                    score = f"{home_goals}-{away_goals}"
                else:
                    if 'A' in result.upper():
                        outcome = "胜 ✓"
                    elif 'D' in result.upper():
                        outcome = "平"
                    else:
                        outcome = "负 ✗"
                    score = f"{away_goals}-{home_goals}"
                
                output.append(
                    f"  {i:2}. [{match.get('season', '')}] {match.get('date', '')} "
                    f"| {prefix}vs {opp} | {score} | {outcome}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"获取球队历史战绩失败: {e}")
            return f"获取球队历史战绩失败: {e}"
    
    @mcp.tool(
        name="lottery_get_head_to_head",
        description="""获取历史交锋记录 - 查看两支球队的历史对战记录

参数：
- team1: 球队1名称
- team2: 球队2名称
- limit: 返回数量限制（默认20，最大100）

示例调用：
- lottery_get_head_to_head(team1="Liverpool", team2="Manchester United")
- lottery_get_head_to_head(team1="Real Madrid", team2="Barcelona", limit=50)
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def get_head_to_head(team1: str, team2: str, limit: int = 20) -> str:
        """获取历史交锋记录
        
        Args:
            team1: 球队1名称
            team2: 球队2名称
            limit: 返回数量限制
        """
        try:
            manager = get_historical_manager()
            h2h = manager.get_head_to_head(team1, team2, limit)
            
            if not h2h:
                return f"未找到 {team1} vs {team2} 的交锋记录"
            
            t1_wins = 0
            t2_wins = 0
            draws = 0
            t1_goals = 0
            t2_goals = 0
            
            for match in h2h:
                home = match.get('home_team', '')
                away = match.get('away_team', '')
                home_goals = match.get('full_time_home_goals', 0) or 0
                away_goals = match.get('full_time_away_goals', 0) or 0
                
                if home.lower() == team1.lower():
                    t1_goals += home_goals
                    t2_goals += away_goals
                    if home_goals > away_goals:
                        t1_wins += 1
                    elif home_goals < away_goals:
                        t2_wins += 1
                    else:
                        draws += 1
                else:
                    t1_goals += away_goals
                    t2_goals += home_goals
                    if away_goals > home_goals:
                        t1_wins += 1
                    elif away_goals < home_goals:
                        t2_wins += 1
                    else:
                        draws += 1
            
            output = [
                f"⚔️ {team1} vs {team2} 历史交锋",
                "=" * 60,
                f"总交锋: {len(h2h)} 场",
                f"比分统计: {team1} {t1_goals} - {t2_goals} {team2}",
                f"胜负记录: {team1} {t1_wins}胜 / {draws}平 / {t2_wins}胜 {team2}",
                "",
                "📅 交锋记录:",
                "-" * 60,
            ]
            
            for i, match in enumerate(h2h, 1):
                home = match.get('home_team', '')
                away = match.get('away_team', '')
                home_goals = match.get('full_time_home_goals', '-')
                away_goals = match.get('full_time_away_goals', '-')
                
                output.append(
                    f"  {i:2}. [{match.get('season', '')}] {match.get('date', '')} | "
                    f"{home} {home_goals}-{away_goals} {away}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"获取历史交锋失败: {e}")
            return f"获取历史交锋失败: {e}"
    
    @mcp.tool(
        name="lottery_search_historical_matches",
        description="""搜索历史比赛 - 根据条件搜索比赛

参数：
- team: 球队名称（可选）
- league: 联赛名称（可选）
- season: 赛季（可选）
- result: 比赛结果 H/D/A（可选）
- limit: 返回数量限制（默认50，最大200）

示例调用：
- lottery_search_historical_matches(team="Chelsea", limit=100)
- lottery_search_historical_matches(league="premier league", result="H")
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def search_historical_matches(
        team: Optional[str] = None,
        league: Optional[str] = None,
        season: Optional[str] = None,
        result: Optional[str] = None,
        limit: int = 50
    ) -> str:
        """搜索历史比赛
        
        Args:
            team: 球队名称（可选）
            league: 联赛名称（可选）
            season: 赛季（可选）
            result: 比赛结果 H/D/A（可选）
            limit: 返回数量限制
        """
        try:
            manager = get_historical_manager()
            matches = manager.search_matches(team, league, season, result, limit)
            
            if not matches:
                return "未找到符合条件的比赛"
            
            conditions = []
            if team:
                conditions.append(f"球队={team}")
            if league:
                conditions.append(f"联赛={league}")
            if season:
                conditions.append(f"赛季={season}")
            if result:
                conditions.append(f"结果={result}")
            
            output = [
                f"🔍 搜索条件: {', '.join(conditions)}",
                f"找到 {len(matches)} 场比赛:",
                "=" * 80,
            ]
            
            for i, match in enumerate(matches, 1):
                home = match.get('home_team', '')
                away = match.get('away_team', '')
                home_goals = match.get('full_time_home_goals', '-')
                away_goals = match.get('full_time_away_goals', '-')
                
                output.append(
                    f"{i:3}. [{match.get('league', '')}] [{match.get('season', '')}] "
                    f"{match.get('date', '')} | {home} {home_goals}-{away_goals} {away}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"搜索历史比赛失败: {e}")
            return f"搜索历史比赛失败: {e}"
    
    @mcp.tool(
        name="lottery_get_team_stats",
        description="""获取球队详细统计 - 获取球队的胜率、进球等详细统计

参数：
- team_name: 球队名称

示例调用：
- lottery_get_team_stats(team_name="Manchester City")
- lottery_get_team_stats(team_name="Bayern Munich")
""",
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    def get_team_stats(team_name: str) -> str:
        """获取球队详细统计
        
        Args:
            team_name: 球队名称
        """
        try:
            manager = get_historical_manager()
            stats = manager.get_team_stats(team_name)
            
            if 'error' in stats:
                return stats['error']
            
            output = [
                f"📊 {stats['team']} 详细统计",
                "=" * 60,
                f"总比赛数: {stats['total_matches']}",
                "",
                "📈 战绩:",
                f"  胜: {stats['wins']} ({stats['win_rate']})",
                f"  平: {stats['draws']}",
                f"  负: {stats['losses']}",
                "",
                "⚽ 进球:",
                f"  总进球: {stats['goals_for']}",
                f"  总失球: {stats['goals_against']}",
                f"  净胜球: {stats['goal_diff']:+d}",
                f"  场均进球: {stats['avg_goals_for']}",
                f"  场均失球: {stats['avg_goals_against']}",
            ]
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"获取球队统计失败: {e}")
            return f"获取球队统计失败: {e}"
    
    logger.info("历史数据工具注册完成: 7个工具")


def get_historical_tools() -> list:
    """获取历史数据工具列表"""
    return [
        "lottery_get_historical_data_summary",
        "lottery_search_league",
        "lottery_get_league_matches",
        "lottery_get_team_history",
        "lottery_get_head_to_head",
        "lottery_search_historical_matches",
        "lottery_get_team_stats",
    ]
