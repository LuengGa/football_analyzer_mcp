#!/usr/bin/env python3
"""
Lottery MCP 架构守护脚本

用于自动检查代码是否符合架构约束文档。
在 CI/CD 或代码审查前运行此脚本。

使用方法:
    python scripts/architecture_guard.py

退出码:
    0 - 所有检查通过
    1 - 发现架构违规
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
LOTTERY_MCP_DIR = PROJECT_ROOT / "lottery_mcp"

# 颜色输出
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class ArchitectureViolation:
    """架构违规记录"""

    def __init__(self, file: str, line: int, message: str, severity: str = "error"):
        self.file = file
        self.line = line
        self.message = message
        self.severity = severity

    def __str__(self):
        color = RED if self.severity == "error" else YELLOW
        return f"{color}[{self.severity.upper()}]{RESET} {self.file}:{self.line} - {self.message}"


class ArchitectureGuard:
    """架构守卫"""

    def __init__(self):
        self.violations: List[ArchitectureViolation] = []

    def check_mcp_tool_outside_tools(self) -> None:
        """检查是否在 tools/ 目录外使用了 @mcp.tool"""
        for py_file in LOTTERY_MCP_DIR.rglob("*.py"):
            # 跳过 tools/ 目录和 __pycache__
            if "tools" in py_file.parts or "__pycache__" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                if "@mcp.tool" in line:
                    self.violations.append(
                        ArchitectureViolation(
                            file=str(py_file.relative_to(PROJECT_ROOT)),
                            line=i,
                            message="在 tools/ 目录外使用了 @mcp.tool 装饰器",
                            severity="error",
                        )
                    )

    def check_context_import_outside_tools(self) -> None:
        """检查是否在非 tools 模块导入了 Context"""
        for py_file in LOTTERY_MCP_DIR.rglob("*.py"):
            if "tools" in py_file.parts or "__pycache__" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                if "from mcp.server.fastmcp import" in line and "Context" in line:
                    self.violations.append(
                        ArchitectureViolation(
                            file=str(py_file.relative_to(PROJECT_ROOT)),
                            line=i,
                            message="在非 tools 模块导入了 Context",
                            severity="error",
                        )
                    )

    def check_tool_naming_convention(self) -> None:
        """检查工具命名规范（仅检查 @mcp.tool 装饰的工具）"""
        tools_dir = LOTTERY_MCP_DIR / "tools"

        for py_file in tools_dir.glob("*.py"):
            # 跳过非工具文件
            if py_file.name in ["__init__.py", "prompts.py", "resources.py", "helpers.py", "output_schemas.py"]:
                continue

            content = py_file.read_text(encoding="utf-8")

            # 使用正则表达式查找 @mcp.tool 装饰器中的 name 参数
            # 匹配 @mcp.tool(...) 中的 name="xxx"
            pattern = r'@mcp\.tool\([^)]*name\s*=\s*"([^"]+)"[^)]*\)'
            matches = list(re.finditer(pattern, content, re.DOTALL))

            for match in matches:
                tool_name = match.group(1)
                # 计算行号
                line_num = content[: match.start()].count("\n") + 1

                if not tool_name.startswith("lottery_"):
                    self.violations.append(
                        ArchitectureViolation(
                            file=str(py_file.relative_to(PROJECT_ROOT)),
                            line=line_num,
                            message=f"工具名称 '{tool_name}' 缺少 'lottery_' 前缀",
                            severity="error",
                        )
                    )

    def check_root_level_python_files(self) -> None:
        """检查根目录是否有不允许的 Python 文件"""
        allowed_root_files = {"__init__.py", "__main__.py", "server.py", "py.typed"}

        for item in LOTTERY_MCP_DIR.iterdir():
            if item.is_file() and item.suffix == ".py":
                if item.name not in allowed_root_files:
                    self.violations.append(
                        ArchitectureViolation(
                            file=str(item.relative_to(PROJECT_ROOT)),
                            line=0,
                            message=f"根目录不允许存在 '{item.name}'，请移动到适当子目录",
                            severity="error",
                        )
                    )

    def check_import_direction(self) -> None:
        """检查模块导入方向"""
        for module_name in ["data", "analysis", "betting", "rules", "models"]:
            module_dir = LOTTERY_MCP_DIR / module_name
            if not module_dir.exists():
                continue

            for py_file in module_dir.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                for i, line in enumerate(lines, 1):
                    if "from lottery_mcp.tools" in line or "import lottery_mcp.tools" in line:
                        self.violations.append(
                            ArchitectureViolation(
                                file=str(py_file.relative_to(PROJECT_ROOT)),
                                line=i,
                                message=f"{module_name}/ 模块不应导入 tools/",
                                severity="error",
                            )
                        )

    def check_pydantic_model_location(self) -> None:
        """检查 Pydantic 模型是否在正确的位置定义"""
        allowed_model_files = {
            LOTTERY_MCP_DIR / "models" / "schemas.py",
            LOTTERY_MCP_DIR / "tools" / "output_schemas.py",  # 输出模型例外
        }

        for py_file in LOTTERY_MCP_DIR.rglob("*.py"):
            if py_file in allowed_model_files:
                continue
            if "__pycache__" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8")

            # 检查是否定义了 BaseModel 子类
            if "from pydantic import" in content and "BaseModel" in content:
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            for base in node.bases:
                                if isinstance(base, ast.Name) and base.id == "BaseModel":
                                    self.violations.append(
                                        ArchitectureViolation(
                                            file=str(py_file.relative_to(PROJECT_ROOT)),
                                            line=node.lineno,
                                            message=f"Pydantic 模型 '{node.name}' 应在 models/schemas.py 中定义",
                                            severity="warning",
                                        )
                                    )
                except SyntaxError:
                    pass

    def run_all_checks(self) -> None:
        """运行所有检查"""
        print(f"{YELLOW}开始架构合规性检查...{RESET}\n")

        checks = [
            ("检查 @mcp.tool 使用位置", self.check_mcp_tool_outside_tools),
            ("检查 Context 导入位置", self.check_context_import_outside_tools),
            ("检查工具命名规范", self.check_tool_naming_convention),
            ("检查根目录 Python 文件", self.check_root_level_python_files),
            ("检查模块导入方向", self.check_import_direction),
            ("检查 Pydantic 模型位置", self.check_pydantic_model_location),
        ]

        for check_name, check_func in checks:
            print(f"  正在执行: {check_name}...")
            try:
                check_func()
            except Exception as e:
                print(f"    {RED}检查失败: {e}{RESET}")

        print()

    def report(self) -> int:
        """输出检查报告并返回退出码"""
        errors = [v for v in self.violations if v.severity == "error"]
        warnings = [v for v in self.violations if v.severity == "warning"]

        if not self.violations:
            print(f"{GREEN}✓ 所有架构检查通过！{RESET}")
            return 0

        print(f"{RED}发现 {len(errors)} 个错误, {len(warnings)} 个警告:{RESET}\n")

        for violation in self.violations:
            print(f"  {violation}")

        print()

        if errors:
            print(f"{RED}架构检查失败！请修复上述错误。{RESET}")
            return 1
        else:
            print(f"{YELLOW}架构检查通过，但存在警告。{RESET}")
            return 0


def main():
    """主函数"""
    guard = ArchitectureGuard()
    guard.run_all_checks()
    exit_code = guard.report()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
