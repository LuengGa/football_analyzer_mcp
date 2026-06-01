# -*- coding: utf-8 -*-
"""
Annotations 精确化测试 (P1-8)

测试 MCP 工具注册时的 annotations 属性：
- 调用外部 API 的工具: openWorldHint=True
- 规则守卫工具: readOnlyHint=False
- 系统状态工具: destructiveHint=True

通过解析源代码中的工具注册函数来验证注解设置。
"""

import ast
import re
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 源文件路径 - 使用正确的模块路径
LOTTERY_MCP_TOOLS_DIR = Path(__file__).parent.parent / "lottery_mcp" / "tools"


def _extract_tool_annotations(source_code: str) -> dict:
    """从源代码中提取工具名称和对应的 annotations 字典。

    通过简单的文本解析，找到所有 @mcp.tool(...) 装饰器中的
    name= 和 annotations={...} 部分。
    """
    results = {}

    # 找到所有 @mcp.tool( 块
    # 策略：逐行扫描，找到 name= 和 annotations= 的配对
    lines = source_code.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 检测 @mcp.tool( 的开始
        if "@mcp.tool(" in line or (i > 0 and "@mcp.tool(" in lines[i - 1]):
            # 收集整个装饰器块（可能跨多行）
            block = line
            j = i + 1
            while ")" not in block and j < len(lines):
                block += "\n" + lines[j].strip()
                j += 1

            # 提取 name
            name_match = re.search(r'name="([^"]+)"', block)
            if not name_match:
                i = j
                continue
            tool_name = name_match.group(1)

            # 提取 annotations 字典
            annotations_match = re.search(r'annotations=(\{[^}]+\})', block)
            if annotations_match:
                annotations_str = annotations_match.group(1)
                # 解析 key-value 对
                annotations = {}
                for kv_match in re.finditer(
                    r'"(\w+)":\s*(True|False)', annotations_str
                ):
                    key = kv_match.group(1)
                    value = kv_match.group(2) == "True"
                    annotations[key] = value

                results[tool_name] = annotations

            i = j
        else:
            i += 1

    return results


class TestExternalAPIToolsOpenWorld:
    """验证调用外部 API 的工具 openWorldHint=True"""

    def _get_data_tools_annotations(self):
        """获取 data_tools.py 中的工具注解"""
        source = (LOTTERY_MCP_TOOLS_DIR / "data_tools.py").read_text()
        return _extract_tool_annotations(source)

    def test_external_api_tools_openworld(self):
        """验证调用外部API的5个工具 openWorldHint=True"""
        annotations = self._get_data_tools_annotations()

        # 以下5个工具调用外部API，应设置 openWorldHint=True
        external_api_tools = [
            "lottery_fetch_today_matches",
            "lottery_verify_results",
            "lottery_query_history",
            "lottery_get_live_scores",
            "lottery_get_market_odds",
        ]

        for tool_name in external_api_tools:
            assert tool_name in annotations, (
                f"工具 {tool_name} 未在 data_tools.py 中找到"
            )
            assert annotations[tool_name].get("openWorldHint") is True, (
                f"工具 {tool_name} 的 openWorldHint 应为 True，"
                f"实际为 {annotations[tool_name].get('openWorldHint')}"
            )

    def test_non_external_api_tools_not_openworld(self):
        """验证不调用外部API的工具 openWorldHint=False"""
        annotations = self._get_data_tools_annotations()

        # track_odds_changes 使用缓存数据，不直接调用外部API
        if "lottery_track_odds_changes" in annotations:
            assert annotations["lottery_track_odds_changes"].get("openWorldHint") is False

        # get_match_data 使用缓存数据
        if "lottery_get_match_data" in annotations:
            assert annotations["lottery_get_match_data"].get("openWorldHint") is False


class TestRuleGuardNotReadonly:
    """验证 rule_guard 的 readOnlyHint=False"""

    def _get_guardrails_tools_annotations(self):
        """获取 guardrails_tools.py 中的工具注解"""
        source = (LOTTERY_MCP_TOOLS_DIR / "guardrails_tools.py").read_text()
        return _extract_tool_annotations(source)

    def test_rule_guard_not_readonly(self):
        """验证 rule_guard 的 readOnlyHint=False"""
        annotations = self._get_guardrails_tools_annotations()

        assert "lottery_rule_guard" in annotations, (
            "工具 lottery_rule_guard 未在 guardrails_tools.py 中找到"
        )
        assert annotations["lottery_rule_guard"].get("readOnlyHint") is False, (
            "lottery_rule_guard 的 readOnlyHint 应为 False"
        )

    def test_rule_guard_destructive_hint(self):
        """验证 rule_guard 的 destructiveHint=False（守卫检查不产生破坏性副作用）"""
        annotations = self._get_guardrails_tools_annotations()

        assert annotations["lottery_rule_guard"].get("destructiveHint") is False, (
            "lottery_rule_guard 的 destructiveHint 应为 False"
        )

    def test_rule_guard_idempotent(self):
        """验证 rule_guard 的 idempotentHint=True（重复检查结果一致）"""
        annotations = self._get_guardrails_tools_annotations()

        assert annotations["lottery_rule_guard"].get("idempotentHint") is True, (
            "lottery_rule_guard 的 idempotentHint 应为 True"
        )


class TestSystemStatusDestructive:
    """验证 get_system_status 的 destructiveHint=True"""

    def _get_system_tools_annotations(self):
        """获取 system_tools.py 中的工具注解"""
        source = (LOTTERY_MCP_TOOLS_DIR / "system_tools.py").read_text()
        return _extract_tool_annotations(source)

    def test_system_status_destructive(self):
        """验证 get_system_status 的 destructiveHint=True"""
        annotations = self._get_system_tools_annotations()

        assert "lottery_get_system_status" in annotations, (
            "工具 lottery_get_system_status 未在 system_tools.py 中找到"
        )
        assert annotations["lottery_get_system_status"].get("destructiveHint") is True, (
            "lottery_get_system_status 的 destructiveHint 应为 True"
        )

    def test_system_status_readonly(self):
        """验证 get_system_status 的 readOnlyHint=False（clear_cache 操作会修改状态）"""
        annotations = self._get_system_tools_annotations()

        assert annotations["lottery_get_system_status"].get("readOnlyHint") is False, (
            "lottery_get_system_status 的 readOnlyHint 应为 False"
        )

    def test_system_status_not_openworld(self):
        """验证 get_system_status 的 openWorldHint=False"""
        annotations = self._get_system_tools_annotations()

        assert annotations["lottery_get_system_status"].get("openWorldHint") is False, (
            "lottery_get_system_status 的 openWorldHint 应为 False"
        )
