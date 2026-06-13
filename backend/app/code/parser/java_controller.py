"""Java Controller 规则解析器（§11.8.2 · 第 10 周）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedControllerMethod:
    """解析出的 Controller 方法。"""

    class_name: str
    method_name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    http_method: str | None
    http_path: str | None
    doc_comment: str | None
    signature: str | None
    body_snippet: str


@dataclass
class ControllerParseResult:
    """单文件 Controller 解析结果。"""

    class_name: str
    file_path: str
    methods: list[ParsedControllerMethod] = field(default_factory=list)


_CLASS_RE = re.compile(r"public\s+class\s+(\w+)")
_REQUEST_MAPPING_RE = re.compile(
    r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_METHOD_MAPPING_RE = re.compile(
    r"@(?:(Get|Post|Put|Delete|Patch)Mapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_JAVA_METHOD_RE = re.compile(
    r"(?:/\*\*[\s\S]*?\*/\s*)?"
    r"(?:@\w+(?:\([^)]*\))?\s*)*"
    r"public\s+[\w<>,\s\[\]]+\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_DOC_RE = re.compile(r"/\*\*([\s\S]*?)\*/")


def _clean_doc(raw: str | None) -> str | None:
    if not raw:
        return None
    lines = []
    for line in raw.splitlines():
        line = line.strip().lstrip("*").strip()
        if line:
            lines.append(line)
    text = " ".join(lines).strip()
    return text or None


def parse_controller_file(content: str, file_path: str) -> ControllerParseResult | None:
    """
    从 Java Controller 源码提取类名、路由与方法。

    规则解析，不依赖 AST；适用于 *ReportController.java 等典型结构。
    """
    class_match = _CLASS_RE.search(content)
    if not class_match:
        return None
    class_name = class_match.group(1)
    if "Controller" not in class_name and "controller" not in file_path.lower():
        return None

    base_path = ""
    rm = _REQUEST_MAPPING_RE.search(content)
    if rm:
        base_path = rm.group(1).strip("/")

    methods: list[ParsedControllerMethod] = []
    for mm in _METHOD_MAPPING_RE.finditer(content):
        http_method = mm.group(1)
        if http_method:
            http_method = http_method.upper()
        else:
            http_method = "GET"
        sub_path = mm.group(2).strip("/")
        full_path = "/" + "/".join(p for p in (base_path, sub_path) if p)

        # 找 mapping 后第一个 public 方法
        after = content[mm.end() : mm.end() + 800]
        jm = _JAVA_METHOD_RE.search(after)
        if not jm:
            continue
        method_name = jm.group(1)
        start_line = content[: mm.start()].count("\n") + 1
        end_line = start_line + after[: jm.end()].count("\n")
        doc = _DOC_RE.search(content[max(0, mm.start() - 400) : mm.start()])
        doc_text = _clean_doc(doc.group(1) if doc else None)
        qualified = f"{class_name}.{method_name}"
        snippet = content[mm.start() : mm.start() + min(len(after), 1200)]
        methods.append(
            ParsedControllerMethod(
                class_name=class_name,
                method_name=method_name,
                qualified_name=qualified,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                http_method=http_method,
                http_path=full_path,
                doc_comment=doc_text,
                signature=f"{method_name}(...)",
                body_snippet=snippet,
            )
        )

    if not methods:
        return None
    return ControllerParseResult(class_name=class_name, file_path=file_path, methods=methods)
