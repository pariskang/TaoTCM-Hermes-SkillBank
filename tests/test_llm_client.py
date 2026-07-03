import pytest

from canon_tcm_hermes.llm import litellm_client
from canon_tcm_hermes.llm.litellm_client import LLMError, LLMSettings, complete_json


def test_complete_json_retries_on_parse_error(monkeypatch):
    replies = iter(["not json at all", '{"segments": []}'])
    monkeypatch.setattr(litellm_client, "_completion_text", lambda settings, messages: next(replies))
    data = complete_json("sys", "user", settings=LLMSettings(model="azure/test", max_retries=3))
    assert data == {"segments": []}


def test_complete_json_retries_on_schema_error(monkeypatch):
    replies = iter([
        '{"is_mixed": true}',  # misses required fields
        '{"segmentation_id": "GSEG::X", "row_source": {"book": "b", "row_id": 1, "row_text_hash": "h", "row_char_length": 3}, "is_mixed": false, "genre_segmentation": [{"span_index": 0, "span": [0, 3], "genre": "treatise", "routed_template": "treatise_claim", "genre_confidence": "high"}], "genre_uncertain": false, "annotation_meta": {"annotator_type": "llm", "confidence": "high", "guideline_version": "v1.0"}}',
    ])
    monkeypatch.setattr(litellm_client, "_completion_text", lambda settings, messages: next(replies))
    data = complete_json("sys", "user", schema_name="genre_segmentation.schema.json", settings=LLMSettings(model="azure/test", max_retries=3))
    assert data["is_mixed"] is False


def test_complete_json_raises_after_budget(monkeypatch):
    monkeypatch.setattr(litellm_client, "_completion_text", lambda settings, messages: "still not json")
    with pytest.raises(LLMError):
        complete_json("sys", "user", settings=LLMSettings(model="azure/test", max_retries=2))


def test_complete_json_survives_base_exception(monkeypatch):
    class NativePanic(BaseException):
        pass

    def boom(settings, messages):
        raise NativePanic("pyo3 panic")

    monkeypatch.setattr(litellm_client, "_completion_text", boom)
    with pytest.raises(LLMError):
        complete_json("sys", "user", settings=LLMSettings(model="azure/test", max_retries=2))


def test_complete_json_retries_with_custom_validator(monkeypatch):
    replies = iter(['{"n": 1}', '{"n": 2}'])
    monkeypatch.setattr(litellm_client, "_completion_text", lambda settings, messages: next(replies))
    seen = []

    def validate(data):
        seen.append(data)
        return [] if data.get("n") == 2 else ["n must be 2"]

    data = complete_json("sys", "user", settings=LLMSettings(model="azure/test", max_retries=3), validate=validate)
    assert data == {"n": 2}
    assert seen == [{"n": 1}, {"n": 2}]


def test_llm_annotation_retries_with_assembled_schema_diff(monkeypatch):
    """The production annotator path must feed schema diffs back to the LLM."""
    from canon_tcm_hermes.annotators import base

    replies = iter([
        '{"clause_subtype": "prescriptive"}',  # valid after assemble()
    ])
    monkeypatch.setattr(litellm_client, "_completion_text", lambda settings, messages: next(replies))
    monkeypatch.setenv("LITELLM_MODEL", "azure/test")
    row = {"source_id": "SHL::T::C::ROW000001", "row_id": 1, "book": "伤寒论", "volume": "v", "chapter": "c", "version": "", "content": "太阳病，无汗而喘者，麻黄汤主之。", "content_hash": "sha1_x"}
    seg = {"segment_id": f"{row['source_id']}::SEG00", "span": [0, len(row["content"])], "genre": "canonical_clause"}
    content = base.llm_content("canonical_clause", row, seg, row["content"])
    assert content == {"clause_subtype": "prescriptive"}


def test_prompt_version_fingerprint_tracks_prompt_content(monkeypatch, tmp_path):
    from canon_tcm_hermes.annotators import base

    (tmp_path / "annotate_clause.md").write_text("v_a", encoding="utf-8")
    (tmp_path / "_annotate_common.md").write_text("common", encoding="utf-8")
    monkeypatch.setattr(base, "prompts_dir", lambda: tmp_path)
    base.prompt_version.cache_clear()
    first = base.prompt_version("canonical_clause")
    (tmp_path / "annotate_clause.md").write_text("v_b", encoding="utf-8")
    base.prompt_version.cache_clear()
    second = base.prompt_version("canonical_clause")
    base.prompt_version.cache_clear()
    assert first != second


def test_annotate_segment_falls_back_to_heuristic(monkeypatch):
    from canon_tcm_hermes.annotators import base

    def fail(*args, **kwargs):
        raise LLMError("provider down")

    monkeypatch.setattr(base, "llm_content", fail)
    row = {"source_id": "SHL::T::C::ROW000001", "row_id": 1, "book": "伤寒论", "volume": "v", "chapter": "c", "version": "", "content": "太阳病，无汗而喘者，麻黄汤主之。", "content_hash": "sha1_x"}
    seg = {"segment_id": f"{row['source_id']}::SEG00", "span": [0, len(row["content"])], "genre": "canonical_clause"}
    ann = base.annotate_segment(row, seg, use_llm=True)
    assert ann["annotation_meta"]["annotator_type"] == "heuristic"
    assert any(flag.startswith("llm_annotation_failed_fallback_heuristic") for flag in ann["annotation_meta"]["annotation_flags"])
    assert ann["conclusion"]["formula"] == "麻黄汤"
