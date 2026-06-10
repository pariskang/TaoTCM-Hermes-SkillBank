from canon_tcm_hermes.annotators.base import annotate_segment
from canon_tcm_hermes.validators.schema_validator import validate_schema_file


def test_clause_annotation_schema_validates():
    row={"source_id":"SHL::T::C::ROW000001","content":"太阳病，无汗而喘者，麻黄汤主之。","content_hash":"sha1_x"}
    seg={"segment_id":"SHL::T::C::ROW000001::SEG00","span":[0,len(row["content"])],"genre":"canonical_clause"}
    ann=annotate_segment(row, seg)
    validate_schema_file(ann, "clause_template.schema.json")
