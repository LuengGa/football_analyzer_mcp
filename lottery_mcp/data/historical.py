"""
历史足球数据管理模块

管理 football_data.zip 中的历史比赛数据：
- 27个联赛
- 2020-2026赛季
- 86,040场比赛
- 80+字段包含赔率、统计等
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger("lottery_mcp")

_ARCHIVE_DIR = Path(__file__).resolve().parent.parent.parent / ".archive"
_DATA_ZIP = _ARCHIVE_DIR / "football_data.zip"

_LEAGUE_ALIASES = {
    "premier league": ["premier league", "premier-league", "epl", "english premier league", "英超"],
    "la liga": ["la liga", "laliga", "liga", "spanish league", "西甲"],
    "serie a": ["serie a", "serie-a", "italian league", "意甲"],
    "bundesliga 1": ["bundesliga 1", "bundesliga", "bundesliga i", "german league", "德甲"],
    "ligue 1": ["ligue 1", "ligue1", "french league", "法甲"],
    "championship": ["championship", "english championship", "英冠"],
    "league one": ["league one", "league 1", "english league one", "英甲"],
    "league two": ["league two", "league 2", "english league two", "英乙"],
    "segunda division": ["segunda division", "la liga 2", "laliga2", "西班牙乙级联赛", "西乙"],
    "serie b": ["serie b", "serie-b", "italian serie b", "意乙"],
    "bundesliga 2": ["bundesliga 2", "2. bundesliga", "德乙"],
    "eredivisie": ["eredivisie", "dutch eredivisie", "荷兰甲级联赛", "荷甲"],
    "jupiler league": ["jupiler league", "belgian league", "比利时甲级联赛", "比甲"],
    "primeira liga": ["primeira liga", "liga NOS", "portuguese league", "葡超"],
    "turkish super lig": ["turkish super lig", "super lig", "土超"],
    "scottish premiership": ["scottish premiership", "scottish premier league", "苏超"],
    "denmark superliga": ["denmark superliga", "danish superliga", "丹超"],
    "sweden allsvenskan": ["sweden allsvenskan", "swedish allsvenskan", "瑞典超"],
    "japan j1 league": ["japan j1 league", "j-league 1", "j1 league", "日本J1联赛", "日职"],
    "greek super league": ["greek super league", "super league greece", "希腊超"],
    "conference national": ["conference national", "national league", "英格兰第五级联赛"],
    "scottish championship": ["scottish championship", "苏冠"],
    "scottish league one": ["scottish league one", "苏甲"],
    "scottish league two": ["scottish league two", "苏乙"],
    "liga portugal 2": ["liga portugal 2", "portuguese second division", "葡甲B"],
    "greek super league 2": ["greek super league 2", "希腊超B"],
}


@dataclass
class LeagueInfo:
    """联赛信息"""
    id: str
    name: str
    country: str = ""
    tier: str = ""
    seasons: Dict[str, int] = field(default_factory=dict)
    total_matches: int = 0


@dataclass
class MatchRecord:
    """比赛记录"""
    match_id: str
    league: str
    season: str
    date: str
    time: str
    home_team: str
    away_team: str
    full_time_home_goals: int
    full_time_away_goals: int
    half_time_home_goals: int = 0
    half_time_away_goals: int = 0
    odds: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)


class HistoricalDataManager:
    """历史数据管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._data_zip_path = _DATA_ZIP
        self._leagues: Dict[str, LeagueInfo] = {}
        self._team_index: Dict[str, List[Dict]] = {}
        self._match_index: Dict[str, Dict] = {}
        self._loaded = False
        self._initialized = True
        
        logger.info("历史数据管理器初始化完成")
    
    def load_data(self, force_reload: bool = False) -> bool:
        """加载历史数据
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            加载是否成功
        """
        if self._loaded and not force_reload:
            return True
        
        if not self._data_zip_path.exists():
            logger.error(f"历史数据文件不存在: {self._data_zip_path}")
            return False
        
        try:
            logger.info(f"开始加载历史数据: {self._data_zip_path}")
            
            with zipfile.ZipFile(self._data_zip_path, 'r') as zf:
                json_files = [n for n in zf.namelist() 
                            if n.endswith('.json') and not n.startswith('__MACOSX')]
                
                total_loaded = 0
                
                for json_file in json_files:
                    try:
                        content = zf.read(json_file).decode('utf-8')
                        data = json.loads(content)
                        
                        if isinstance(data, dict) and 'matches' in data:
                            league_name = data.get('league', '')
                            season = data.get('season', '')
                            matches = data.get('matches', [])
                            
                            if league_name and matches:
                                self._process_league_data(league_name, season, matches)
                                total_loaded += len(matches)
                                
                    except Exception as e:
                        logger.warning(f"加载文件失败 {json_file}: {e}")
            
            self._build_indexes()
            self._loaded = True
            
            logger.info(f"历史数据加载完成: {total_loaded} 场比赛, {len(self._leagues)} 个联赛")
            return True
            
        except Exception as e:
            logger.error(f"加载历史数据失败: {e}")
            return False
    
    def _process_league_data(self, league: str, season: str, matches: List[Dict]):
        """处理联赛数据"""
        league_lower = league.lower()
        
        if league not in self._leagues:
            self._leagues[league] = LeagueInfo(
                id=league.lower().replace(' ', '_'),
                name=league
            )
        
        self._leagues[league].seasons[season] = len(matches)
        self._leagues[league].total_matches += len(matches)
        
        for match in matches:
            match_id = match.get('id', '')
            if match_id:
                home_team = match.get('home_team', '')
                away_team = match.get('away_team', '')
                
                record = {
                    'match_id': match_id,
                    'league': league,
                    'season': season,
                    'date': match.get('date', ''),
                    'time': match.get('time', ''),
                    'home_team': home_team,
                    'away_team': away_team,
                    'full_time_home_goals': match.get('full_time_home_goals'),
                    'full_time_away_goals': match.get('full_time_away_goals'),
                    'half_time_home_goals': match.get('half_time_home_goals'),
                    'half_time_away_goals': match.get('half_time_away_goals'),
                    'full_time_result': match.get('full_time_result', ''),
                    'half_time_result': match.get('half_time_result', ''),
                    'referee': match.get('referee', ''),
                    'odds': {},
                    'stats': {},
                }
                
                self._match_index[match_id] = record
                
                if home_team:
                    if home_team not in self._team_index:
                        self._team_index[home_team] = []
                    self._team_index[home_team].append(record)
                
                if away_team:
                    if away_team not in self._team_index:
                        self._team_index[away_team] = []
                    self._team_index[away_team].append(record)
    
    def _build_indexes(self):
        """构建索引"""
        logger.info("构建数据索引...")
        
        for team, matches in self._team_index.items():
            matches.sort(key=lambda x: (x.get('season', ''), x.get('date', '')), reverse=True)
    
    def get_league_list(self) -> List[Dict[str, Any]]:
        """获取联赛列表"""
        if not self._loaded:
            self.load_data()
        
        return [
            {
                'id': league.id,
                'name': league.name,
                'total_matches': league.total_matches,
                'seasons': len(league.seasons),
                'season_range': f"{min(league.seasons.keys())} - {max(league.seasons.keys())}" if league.seasons else ""
            }
            for league in self._leagues.values()
        ]
    
    def search_league(self, query: str) -> List[Dict[str, Any]]:
        """搜索联赛"""
        if not self._loaded:
            self.load_data()
        
        query_lower = query.lower()
        results = []
        
        for league in self._leagues.values():
            if (query_lower in league.name.lower() or 
                query_lower in league.id.lower()):
                results.append({
                    'id': league.id,
                    'name': league.name,
                    'total_matches': league.total_matches,
                    'seasons': list(league.seasons.keys())
                })
            
            for alias_list in _LEAGUE_ALIASES.values():
                if query_lower in alias_list and league.name.lower() not in results:
                    results.append({
                        'id': league.id,
                        'name': league.name,
                        'total_matches': league.total_matches,
                        'seasons': list(league.seasons.keys())
                    })
                    break
        
        return results
    
    def get_league_matches(
        self, 
        league: str, 
        season: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取联赛比赛"""
        if not self._loaded:
            self.load_data()
        
        league_matches = []
        
        for match in self._match_index.values():
            if match['league'].lower() == league.lower():
                if season is None or match['season'] == season:
                    league_matches.append(match)
        
        league_matches.sort(key=lambda x: (x.get('season', ''), x.get('date', '')), reverse=True)
        return league_matches[:limit]
    
    def _find_team(self, team_name: str) -> Optional[str]:
        """查找球队名称（支持模糊匹配）
        
        Args:
            team_name: 球队名称
            
        Returns:
            实际球队名称或None
        """
        team_lower = team_name.lower()
        
        if team_name in self._team_index:
            return team_name
        
        for actual_name in self._team_index.keys():
            if actual_name.lower() == team_lower:
                return actual_name
        
        for actual_name in self._team_index.keys():
            if team_lower in actual_name.lower() or actual_name.lower() in team_lower:
                return actual_name
        
        return None
    
    def get_team_history(
        self,
        team_name: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取球队历史战绩"""
        if not self._loaded:
            self.load_data()
        
        actual_name = self._find_team(team_name)
        if not actual_name:
            return []
        
        matches = self._team_index.get(actual_name, [])
        
        matches.sort(key=lambda x: (x.get('season', ''), x.get('date', '')), reverse=True)
        return matches[:limit]
    
    def get_head_to_head(
        self,
        team1: str,
        team2: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取两队历史交锋"""
        if not self._loaded:
            self.load_data()
        
        actual_team1 = self._find_team(team1)
        actual_team2 = self._find_team(team2)
        
        if not actual_team1 or not actual_team2:
            return []
        
        h2h = []
        
        team1_matches = {m['match_id']: m for m in self._team_index.get(actual_team1, [])}
        team2_matches = {m['match_id']: m for m in self._team_index.get(actual_team2, [])}
        
        common_match_ids = set(team1_matches.keys()) & set(team2_matches.keys())
        
        for match_id in common_match_ids:
            h2h.append(team1_matches[match_id])
        
        h2h.sort(key=lambda x: (x.get('season', ''), x.get('date', '')), reverse=True)
        return h2h[:limit]
    
    def search_matches(
        self,
        team: Optional[str] = None,
        league: Optional[str] = None,
        season: Optional[str] = None,
        result: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """搜索比赛"""
        if not self._loaded:
            self.load_data()
        
        results = []
        
        for match in self._match_index.values():
            if team:
                if team.lower() not in match['home_team'].lower() and \
                   team.lower() not in match['away_team'].lower():
                    continue
            
            if league and match['league'].lower() != league.lower():
                continue
            
            if season and match['season'] != season:
                continue
            
            if result:
                ft_result = match.get('full_time_result', '').upper()
                if result.upper() == 'H' and 'H' not in ft_result:
                    continue
                elif result.upper() == 'D' and 'D' not in ft_result:
                    continue
                elif result.upper() == 'A' and 'A' not in ft_result:
                    continue
            
            results.append(match)
        
        results.sort(key=lambda x: (x.get('season', ''), x.get('date', '')), reverse=True)
        return results[:limit]
    
    def get_match_stats(self, match_id: str) -> Optional[Dict[str, Any]]:
        """获取比赛详细统计"""
        if not self._loaded:
            self.load_data()
        
        return self._match_index.get(match_id)
    
    def get_team_stats(self, team_name: str) -> Dict[str, Any]:
        """获取球队统计"""
        if not self._loaded:
            self.load_data()
        
        actual_name = self._find_team(team_name)
        if not actual_name:
            return {'error': f'球队 {team_name} 未找到'}
        
        matches = self._team_index.get(actual_name, [])
        
        if not matches:
            return {'error': f'球队 {team_name} 未找到'}
        
        total = len(matches)
        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        
        for match in matches:
            ft = match.get('full_time_result', '').upper()
            home = match.get('full_time_home_goals', 0) or 0
            away = match.get('full_time_away_goals', 0) or 0
            
            if actual_name == match.get('home_team'):
                goals_for += home
                goals_against += away
                if 'H' in ft:
                    wins += 1
                elif 'D' in ft:
                    draws += 1
                else:
                    losses += 1
            else:
                goals_for += away
                goals_against += home
                if 'A' in ft:
                    wins += 1
                elif 'D' in ft:
                    draws += 1
                else:
                    losses += 1
        
        return {
            'team': team_name,
            'total_matches': total,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'win_rate': f"{wins/total*100:.1f}%" if total > 0 else "0%",
            'goals_for': goals_for,
            'goals_against': goals_against,
            'goal_diff': int(goals_for - goals_against),
            'avg_goals_for': round(goals_for/total, 2) if total > 0 else 0.0,
            'avg_goals_against': round(goals_against/total, 2) if total > 0 else 0.0,
        }
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        if not self._loaded:
            self.load_data()
        
        return {
            'total_leagues': len(self._leagues),
            'total_matches': len(self._match_index),
            'total_teams': len(self._team_index),
            'seasons': sorted(list(set(
                m['season'] for m in self._match_index.values()
            ))),
            'loaded': self._loaded
        }


_manager = None

def get_historical_manager() -> HistoricalDataManager:
    """获取历史数据管理器单例"""
    global _manager
    if _manager is None:
        _manager = HistoricalDataManager()
    return _manager
