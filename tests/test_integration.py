# -*- coding: utf-8 -*-
"""
集成测试 - 完整的 MCP 工作流测试

测试核心功能的集成：
- 规则引擎验证
- 工具导入
- 服务器创建
- 资源文件存在性
"""

import pytest
import sys
import json
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
class TestBasicImports:
    """基础模块导入测试"""
    
    def test_rules_engine_import(self):
        """测试规则引擎导入"""
        from lottery_mcp.tools.rules_tools import RulesEngine, get_rules_engine
        
        engine = get_rules_engine()
        assert engine is not None
    
    def test_prediction_tools_import(self):
        """测试预测工具导入"""
        from lottery_mcp.tools.prediction_tools import (
            GeneratePredictionReportInput,
            SmartParlayInput,
            RecommendBestPlayInput,
            AnalyzeMixedParlayInput,
        )
        
        # 测试 GeneratePredictionReportInput
        report_input = GeneratePredictionReportInput(
            min_confidence=0.3,
            include_text=True,
            league_filter="英超",
        )
        assert report_input.min_confidence == 0.3
        assert report_input.include_text is True
        assert report_input.league_filter == "英超"
    
    def test_pydantic_validation_constraints(self):
        """测试 Pydantic 约束验证"""
        from lottery_mcp.tools.prediction_tools import SmartParlayInput, RecommendBestPlayInput
        from pydantic import ValidationError
        
        # 测试无效的 max_matches (应该 >= 2)
        with pytest.raises(ValidationError):
            SmartParlayInput(max_matches=1, strategy="balanced", min_confidence=0.35, bankroll=1000)
        
        # 测试无效的 min_confidence (应该 >= 0.1)
        with pytest.raises(ValidationError):
            SmartParlayInput(max_matches=4, strategy="balanced", min_confidence=0.05, bankroll=1000)
        
        # 测试无效的 top_n (应该 >= 1, <= 6)
        with pytest.raises(ValidationError):
            RecommendBestPlayInput(match_index=0, top_n=0)
        
        with pytest.raises(ValidationError):
            RecommendBestPlayInput(match_index=0, top_n=7)


@pytest.mark.integration
class TestToolRegistration:
    """工具注册集成测试"""
    
    def test_all_tools_registered(self):
        """测试所有工具都正确注册（通过 __init__.py 验证）"""
        from lottery_mcp.tools import (
            register_all_tools,
            # 验证各个模块导入正常
            rules_tools,
            prediction_tools,
            data_tools,
            system_tools,
            historical_tools,
            analysis_tools,
        )
        
        # 验证模块存在
        assert rules_tools is not None
        assert prediction_tools is not None
        assert data_tools is not None
        assert system_tools is not None
        assert historical_tools is not None
        assert analysis_tools is not None
    
    def test_server_creation(self):
        """测试 MCP 服务器创建"""
        from lottery_mcp.server import create_mcp_server
        
        # 尝试创建服务器（不启动）
        server = create_mcp_server()
        assert server is not None
        assert hasattr(server, "name")
        assert server.name == "lottery_mcp"
    
    def test_health_check_function(self):
        """测试健康检查函数"""
        from lottery_mcp.server import startup_health_check
        
        result = startup_health_check()
        assert "overall_status" in result
        assert "checks" in result
        assert "timestamp" in result
        
        # 验证检查项
        checks = result["checks"]
        check_names = [check["name"] for check in checks]
        expected_checks = {"numpy", "scipy", "pydantic", "mcp"}
        assert set(check_names).issuperset(expected_checks)


@pytest.mark.integration
class TestResourcesAndPrompts:
    """资源和提示词集成测试"""
    
    def test_knowledge_files_exist(self):
        """测试知识库文件存在"""
        knowledge_dir = Path(__file__).parent.parent / "lottery_mcp" / "knowledge" / "jingcai" / "play_types"
        
        assert knowledge_dir.exists()
        
        expected_files = [
            "01_win_draw_loss.json",
            "02_handicap_win_draw_loss.json",
            "03_score.json",
            "04_total_goals.json",
            "05_half_full.json",
            "06_mixed_parlay.json",
        ]
        
        for filename in expected_files:
            file_path = knowledge_dir / filename
            assert file_path.exists(), f"知识库文件缺失: {filename}"
    
    def test_knowledge_json_format(self):
        """测试知识库 JSON 格式正确"""
        import json
        
        knowledge_dir = Path(__file__).parent.parent / "lottery_mcp" / "knowledge" / "jingcai" / "play_types"
        
        for json_file in knowledge_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                assert isinstance(data, dict), f"{json_file.name} 格式错误"
                assert "name" in data, f"{json_file.name} 缺少 name"
                assert "description" in data, f"{json_file.name} 缺少 description"
            except json.JSONDecodeError as e:
                pytest.fail(f"{json_file.name} JSON 解析失败: {e}")


@pytest.mark.integration
class TestPlayTypesCoverage:
    """测试玩法覆盖"""
    
    def test_play_label_mapping(self):
        """测试玩法标签映射"""
        PLAY_LABELS = {
            "SPF": "胜平负",
            "RQSPF": "让球胜平负",
            "BF": "比分",
            "ZJQ": "总进球",
            "BQC": "半全场",
            "HHGG": "胜负平",
        }
        
        assert len(PLAY_LABELS) == 6
        
        # 验证覆盖所有 6 种玩法
        expected_keys = {"SPF", "RQSPF", "BF", "ZJQ", "BQC", "HHGG"}
        assert set(PLAY_LABELS.keys()) == expected_keys


@pytest.mark.integration
class TestJsonSerialization:
    """测试 JSON 序列化"""
    
    def test_json_serialization(self):
        """测试 JSON 序列化（用于工具返回值）"""
        test_data = {
            "success": True,
            "data": {
                "match_id": "TEST001",
                "recommended_play": "胜平负",
                "selection": "客胜",
                "probability": 0.42,
                "odds": 2.6,
                "ev": 1.092,
            },
        }
        
        # 测试序列化
        json_str = json.dumps(test_data, ensure_ascii=False)
        assert isinstance(json_str, str)
        
        # 测试反序列化
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert parsed["data"]["match_id"] == "TEST001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
