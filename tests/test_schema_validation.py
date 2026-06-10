from canon_tcm_hermes.annotators.base import annotate_segment
from canon_tcm_hermes.validators.schema_validator import schema_errors, validate_schema_file


def make_row(content: str) -> dict:
    return {
        "source_id": "SHL::T::C::ROW000001",
        "row_id": 1,
        "book": "伤寒论",
        "volume": "辨太阳病脉证并治",
        "chapter": "太阳病",
        "version": "宋本",
        "content": content,
        "content_hash": "sha1_x",
    }


def make_segment(row: dict, genre: str) -> dict:
    return {
        "segment_id": f"{row['source_id']}::SEG00",
        "span": [0, len(row["content"])],
        "genre": genre,
    }


def test_clause_annotation_schema_validates():
    row = make_row("太阳病，无汗而喘者，麻黄汤主之。")
    ann = annotate_segment(row, make_segment(row, "canonical_clause"))
    validate_schema_file(ann, "clause_template.schema.json")
    assert ann["clause_subtype"] == "prescriptive"
    assert ann["conclusion"]["formula"] == "麻黄汤"
    assert ann["evidence"]["source"]["source_id"] == row["source_id"]


def test_all_genres_validate_against_authoritative_schemas():
    samples = {
        "canonical_clause": ("太阳病，无汗而喘者，麻黄汤主之。", "clause_template.schema.json"),
        "treatise": ("诸风掉眩，皆属于肝。", "treatise_claim.schema.json"),
        "formula_entry": ("麻黄三两桂枝二两，右二味，以水九升，煮取二升，温服。", "formula_template.schema.json"),
        "materia_medica": ("麻黄，味苦温，主中风伤寒头痛，无毒。", "herb_template.schema.json"),
        "pulse_text": ("浮脉，举之有余，按之不足，浮为风。", "pulse_template.schema.json"),
        "case_record": ("王姓妇，年三十，初诊发热恶寒无汗，投麻黄汤一剂，翌日而愈。", "case_template.schema.json"),
        "commentary": ("注曰：此表实无汗，故以麻黄发之。", "commentary_template.schema.json"),
        "mnemonic_misc": ("麻黄汤中用桂枝，杏仁甘草四般施。", "mnemonic_template.schema.json"),
    }
    for genre, (content, schema_name) in samples.items():
        row = make_row(content)
        ann = annotate_segment(row, make_segment(row, genre))
        errors = schema_errors(ann, schema_name)
        assert not errors, f"{genre}: {errors}"


def test_contraindication_clause_is_t3():
    row = make_row("脉微弱，汗出恶风者，不可服之。")
    ann = annotate_segment(row, make_segment(row, "canonical_clause"))
    assert ann["clause_subtype"] == "contraindication"
    assert ann["risk_tier"] == "T3"
