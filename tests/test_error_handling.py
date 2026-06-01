# -*- coding: utf-8 -*-
"""
错误处理升级测试 (P1-5)

测试 lottery_mcp.tools.helpers 中的错误处理功能：
- raise_tool_error: 抛出 MCP 协议级 ToolError 异常
- 模块导入验证
"""

import json
import pytest
import sys
import importlib
from pathlib import Path

# 直接导入子模块，避免触发 mcp_server/__init__.py 的完整导入链
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入 helpers 模块（无外部依赖问题）
helpers = importlib.import_module("lottery_mcp.tools.helpers")
raise_tool_error = helpers.raise_tool_error

from mcp.server.fastmcp.exceptions import ToolError


class TestRaiseToolError:
    """测试 raise_tool_error 函数"""

    def test_tool_error_raised(self):
        """验证 raise_tool_error 正确抛出 ToolError 异常"""
        with pytest.raises(ToolError):
            raise_tool_error("测试错误消息")

    def test_tool_error_message_format(self):
        """验证 ToolError 异常包含正确的错误码和消息"""
        with pytest.raises(ToolError) as exc_info:
            raise_tool_error("参数无效", code="VALIDATION_ERROR")

        error_msg = str(exc_info.value)
        assert "[VALIDATION_ERROR]" in error_msg
        assert "参数无效" in error_msg

    def test_tool_error_with_suggestion(self):
        """验证 ToolError 异常包含建议信息"""
        with pytest.raises(ToolError) as exc_info:
            raise_tool_error("投注金额超限", code="LIMIT_EXCEEDED", suggestion="请降低投注金额")

        error_msg = str(exc_info.value)
        assert "建议: 请降低投注金额" in error_msg

    def test_tool_error_with_details(self):
        """验证 ToolError 异常包含详细信息"""
        details = {"max_limit": 10000, "actual": 15000}
        with pytest.raises(ToolError) as exc_info:
            raise_tool_error("超出限额", code="LIMIT_EXCEEDED", details=details)

        error_msg = str(exc_info.value)
        assert "详情:" in error_msg
        assert "10000" in error_msg
        assert "15000" in error_msg

    def test_tool_error_default_code(self):
        """验证默认错误码为 VALIDATION_ERROR"""
        with pytest.raises(ToolError) as exc_info:
            raise_tool_error("默认错误码测试")

        error_msg = str(exc_info.value)
        assert "[VALIDATION_ERROR]" in error_msg


class TestHelpersImport:
    """测试 helpers 模块导入"""

    def test_helpers_import(self):
        """验证 from lottery_mcp.tools.helpers import raise_tool_error 可正常导入"""
        from lottery_mcp.tools.helpers import raise_tool_error as rte
        assert callable(rte)

    def test_format_error_removed(self):
        """验证 _format_error 已从 helpers 中移除"""
        with pytest.raises(ImportError):
            from lottery_mcp.tools.helpers import _format_error  # noqa: F401

    def test_tool_error_import_from_fastmcp(self):
        """验证 ToolError 可以从 fastmcp.exceptions 导入"""
        from mcp.server.fastmcp.exceptions import ToolError as TE
        assert TE is not None
