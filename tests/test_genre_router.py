from canon_tcm_hermes.router.genre_router import classify_text, segment_row


def row(content):
    return {"row_id":1,"source_id":"SHL::T::C::ROW000001","content":content,"book":"伤寒论","chapter":"太阳病","content_hash":"x"}


def test_eight_genre_classification():
    samples = {
        "canonical_clause": "太阳病，头痛发热，无汗而喘者，麻黄汤主之。",
        "treatise": "夫邪之所凑，其气必虚，所以然者，阳气不足也。",
        "formula_entry": "麻黄三两桂枝二两杏仁七十枚甘草一两，右四味，以水九升，煮取二升半。",
        "materia_medica": "麻黄，味苦温，主中风伤寒头痛，无毒。",
        "pulse_text": "浮脉，举之有余，按之不足。",
        "case_record": "王姓妇，年三十，初诊发热，予投麻黄汤一剂，翌日热退而愈。",
        "commentary": "太阳病，头痛发热，无汗而喘者，麻黄汤主之。注曰：表实也。",
        "mnemonic_misc": "麻黄汤中用桂枝，杏仁甘草四般施。",
    }
    for genre, text in samples.items():
        assert classify_text(text, "脉经" if genre == "pulse_text" else "", "")[0] == genre


def test_mixed_clause_formula_segmentation():
    r = segment_row(row("太阳病，无汗而喘者，麻黄汤主之。麻黄三两桂枝二两，右二味，以水九升，煮取。"))
    assert r["is_mixed"] is True
    assert [s["genre"] for s in r["genre_segmentation"]] == ["canonical_clause", "formula_entry"]
    assert r["cross_links"][0]["relation"] == "prescribes"


def test_short_even_phrase_clause_is_not_verse():
    # regression: 3+5+5 char phrases look metrically even, but 主之 marks a clause
    assert classify_text("太阳病，无汗而喘者，麻黄汤主之。")[0] == "canonical_clause"


def test_commentary_quote_split_marks_dedup_target():
    r = segment_row(row("太阳病，头痛发热，无汗而喘者，麻黄汤主之。注曰：此表实无汗，故以麻黄发之。"))
    assert r["is_mixed"] is True
    genres = [s["genre"] for s in r["genre_segmentation"]]
    assert genres == ["canonical_clause", "commentary"]
    assert r["genre_segmentation"][0]["quoted"] is True
    assert r["cross_links"][0]["relation"] == "comments_on"


def test_route_output_matches_authoritative_schema():
    from canon_tcm_hermes.validators.schema_validator import schema_errors

    r = segment_row(row("太阳病，头痛发热，身疼腰痛，恶风，无汗而喘者，麻黄汤主之。"))
    assert schema_errors(r, "genre_segmentation.schema.json") == []
    assert r["annotation_meta"]["annotator_type"] in {"heuristic", "llm"}
