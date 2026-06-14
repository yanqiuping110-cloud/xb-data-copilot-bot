"""Java Controller 规则解析器（兼容旧接口，内部委托 java_file）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.code.parser.java_file import ParsedJavaMethod, parse_java_file

ParsedControllerMethod = ParsedJavaMethod


@dataclass
class ControllerParseResult:
    """单文件 Controller 解析结果。"""

    class_name: str
    file_path: str
    methods: list[ParsedControllerMethod] = field(default_factory=list)


def parse_controller_file(content: str, file_path: str) -> ControllerParseResult | None:
    """从 Java Controller 源码提取类名、路由与方法。"""
    parsed = parse_java_file(content, file_path)
    if parsed is None or not parsed.is_controller:
        return None
    return ControllerParseResult(
        class_name=parsed.class_name,
        file_path=parsed.file_path,
        methods=parsed.methods,
    )
