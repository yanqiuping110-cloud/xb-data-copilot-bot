"""glossary_service 单测。"""

from app.meta.glossary_repository import GlossaryTermRow
from app.meta.glossary_service import format_glossary_prompt_lines, match_glossary_terms, suggest_terms_from_question


def _term(term: str, canonical: str) -> GlossaryTermRow:
    return GlossaryTermRow(
        id=1,
        term=term,
        canonical_name=canonical,
        definition=None,
        ref_type="concept",
        ref_id=None,
        scope_role=None,
        status=1,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def test_match_glossary_terms():
    terms = [_term("参与人数", "stat_participant_cnt"), _term("打卡", "checkin")]
    matched = match_glossary_terms("本月参与人数趋势", terms, top_k=5)
    assert len(matched) == 1
    assert matched[0].term == "参与人数"


def test_format_glossary_prompt_lines():
    lines = format_glossary_prompt_lines([_term("参与人数", "stat_participant_cnt")], sanitize=False)
    assert any("术语对齐" in line for line in lines)
    assert any("参与人数" in line for line in lines)


def test_suggest_terms_from_question():
    items = suggest_terms_from_question("全平台游泳参与人数本月趋势")
    assert len(items) >= 1
    assert all("term" in i for i in items)
