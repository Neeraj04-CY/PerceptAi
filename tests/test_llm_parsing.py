from perceptai.llm import parse_json_reply


def test_parses_plain_json():
    assert parse_json_reply('{"a": 1}') == {"a": 1}


def test_strips_markdown_fences():
    assert parse_json_reply('```json\n[{"x": 2}]\n```') == [{"x": 2}]


def test_malformed_returns_none():
    assert parse_json_reply("here are your steps: 1. open app") is None


def test_empty_returns_none():
    assert parse_json_reply("") is None
