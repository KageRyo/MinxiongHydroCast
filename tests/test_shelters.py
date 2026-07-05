from floodcasttw.ingestion.shelters import parse_shelter_line


def test_parse_shelter_line_keeps_address_tokens_together():
    record = parse_shelter_line(
        "民雄鄉 民雄國中活動中心 民雄鄉中庄村 147號 何智豪 200",
        source="sample.docx",
        extracted_at="2026-07-05T00:00:00",
    )

    assert record is not None
    assert record["鄉鎮市"] == "民雄鄉"
    assert record["避難所名稱"] == "民雄國中活動中心"
    assert record["避難所地址"] == "民雄鄉中庄村 147號"
    assert record["避難所聯絡人"] == "何智豪"
    assert record["收容人數"] == "200"


def test_parse_shelter_line_skips_heading():
    assert (
        parse_shelter_line("嘉義縣避難收容處所清冊（測試用）", "sample.docx")
        is None
    )
