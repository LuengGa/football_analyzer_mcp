
from typing import Dict, List, Type
from .interfaces import PlayPlugin, PlayType


class PluginRegistry:
    """玩法插件注册中心"""
    
    def __init__(self):
        self._plugins: Dict[PlayType, PlayPlugin] = {}
    
    def register(self, plugin: PlayPlugin):
        """注册插件"""
        self._plugins[plugin.play_type] = plugin
    
    def get(self, play_type: PlayType) -&gt; PlayPlugin:
        """获取插件"""
        return self._plugins.get(play_type)
    
    def list_all(self) -&gt; List[PlayType]:
        """列出所有已注册的玩法"""
        return list(self._plugins.keys())
    
    def has(self, play_type: PlayType) -&gt; bool:
        """检查是否已注册"""
        return play_type in self._plugins
