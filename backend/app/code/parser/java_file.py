"""Java 源码规则解析器：Controller 路由 + 普通 public 方法（§11.8.2）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CLASS_RE = re.compile(r"public\s+class\s+(\w+)")
_REQUEST_MAPPING_RE = re.compile(
    r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_METHOD_MAPPING_RE = re.compile(
    r"@(?:(Get|Post|Put|Delete|Patch)Mapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_PUBLIC_METHOD_RE = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s*)*"
    r"public\s+(?!class\b|interface\b|enum\b)"
    r"([\w<>,\s\[\]]+)\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_DOC_RE = re.compile(r"/\*\*([\s\S]*?)\*/")


@dataclass
class ParsedJavaMethod:
    """解析出的 Java 方法（Controller 或普通类）。"""

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
class JavaParseResult:
    """单 Java 文件解析结果。"""

    class_name: str
    file_path: str
    is_controller: bool
    methods: list[ParsedJavaMethod] = field(default_factory=list)


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


def _doc_immediately_before(content: str, pos: int) -> str | None:
    """取方法声明前最近的 Javadoc（避免误取文件头注释）。"""
    prefix = content[max(0, pos - 800) : pos]
    docs = list(_DOC_RE.finditer(prefix))
    if not docs:
        return None
    return _clean_doc(docs[-1].group(1))


def _assign_qualified_names(methods: list[ParsedJavaMethod]) -> None:
    """同名方法（重载）用行号区分，避免 uk_repo_qualified 冲突。"""
    from collections import Counter

    bases = [f"{m.class_name}.{m.method_name}" for m in methods]
    overloaded = {name for name, count in Counter(bases).items() if count > 1}
    for method, base in zip(methods, bases, strict=True):
        method.qualified_name = f"{base}#{method.start_line}" if base in overloaded else base


def _parse_controller_methods(
    content: str,
    class_name: str,
    file_path: str,
) -> list[ParsedJavaMethod]:
    """从 Spring Mapping 注解提取 Controller 路由方法。"""
    base_path = ""
    rm = _REQUEST_MAPPING_RE.search(content)
    if rm:
        base_path = rm.group(1).strip("/")

    methods: list[ParsedJavaMethod] = []
    for mm in _METHOD_MAPPING_RE.finditer(content):
        http_method = mm.group(1)
        http_method = http_method.upper() if http_method else "GET"
        sub_path = mm.group(2).strip("/")
        full_path = "/" + "/".join(p for p in (base_path, sub_path) if p)

        after = content[mm.end() : mm.end() + 800]
        jm = _PUBLIC_METHOD_RE.search(after)
        if not jm:
            continue
        method_name = jm.group(2)
        start_line = content[: mm.start()].count("\n") + 1
        end_line = start_line + after[: jm.end()].count("\n")
        snippet = content[mm.start() : mm.start() + min(len(after), 1200)]
        methods.append(
            ParsedJavaMethod(
                class_name=class_name,
                method_name=method_name,
                qualified_name="",
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                http_method=http_method,
                http_path=full_path,
                doc_comment=_doc_immediately_before(content, mm.start()),
                signature=f"{method_name}(...)",
                body_snippet=snippet,
            )
        )
    _assign_qualified_names(methods)
    return methods


def _parse_public_methods(
    content: str,
    class_name: str,
    file_path: str,
) -> list[ParsedJavaMethod]:
    """提取普通 public 方法（Service/Util 等）。"""
    methods: list[ParsedJavaMethod] = []
    for jm in _PUBLIC_METHOD_RE.finditer(content):
        return_type = jm.group(1).strip()
        method_name = jm.group(2)
        if method_name == class_name:
            continue

        start_line = content[: jm.start()].count("\n") + 1
        end_line = start_line + jm.group(0).count("\n")
        snippet = content[jm.start() : jm.start() + min(len(content) - jm.start(), 1200)]
        doc_text = _doc_immediately_before(content, jm.start())
        methods.append(
            ParsedJavaMethod(
                class_name=class_name,
                method_name=method_name,
                qualified_name="",
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                http_method=None,
                http_path=None,
                doc_comment=doc_text,
                signature=f"{return_type} {method_name}(...)",
                body_snippet=snippet,
            )
        )
    _assign_qualified_names(methods)
    return methods


def parse_java_file(content: str, file_path: str) -> JavaParseResult | None:
    """
    解析任意 .java 文件。

    优先识别 Spring Controller（Mapping 注解）；否则提取 public 方法。
    """
    class_match = _CLASS_RE.search(content)
    if not class_match:
        return None
    class_name = class_match.group(1)

    controller_methods = _parse_controller_methods(content, class_name, file_path)
    if controller_methods:
        return JavaParseResult(
            class_name=class_name,
            file_path=file_path,
            is_controller=True,
            methods=controller_methods,
        )

    public_methods = _parse_public_methods(content, class_name, file_path)
    if not public_methods:
        return None
    return JavaParseResult(
        class_name=class_name,
        file_path=file_path,
        is_controller=False,
        methods=public_methods,
    )
