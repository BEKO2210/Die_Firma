"""OllamaClient JSON/reasoning robustness + thin HTTP wrappers (via fakes)."""

from __future__ import annotations

import pytest

from die_firma.ollama_client import OllamaClient, encode_image, extract_json, strip_reasoning


def test_strip_reasoning_removes_think_blocks():
    assert strip_reasoning("<think>plan plan</think>\nHello") == "Hello"
    assert strip_reasoning("no think here") == "no think here"


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_fenced_and_prose():
    text = 'Sure!\n```json\n{"score": 80, "pass": true}\n```\nDone.'
    assert extract_json(text) == {"score": 80, "pass": True}


def test_extract_json_after_reasoning():
    text = '<think>let me grade</think> here: {"score": 50}'
    assert extract_json(text) == {"score": 50}


def test_extract_json_nested_balanced():
    text = 'noise {"a": {"b": 2}, "c": [1,2]} trailing'
    assert extract_json(text) == {"a": {"b": 2}, "c": [1, 2]}


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        extract_json("no object at all")


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, json):  # noqa: A002 - mirror httpx signature
        self.calls.append((url, json))
        return _FakeResp(self.payload)

    def get(self, url):
        return _FakeResp(self.payload)


def test_generate_text_returns_tokens():
    http = _FakeHTTP({"response": "hi", "prompt_eval_count": 7, "eval_count": 3})
    c = OllamaClient(client=http)
    text, tin, tout = c.generate_text("m", "p", system="s", options={"temperature": 0.1})
    assert (text, tin, tout) == ("hi", 7, 3)
    assert http.calls[0][1]["system"] == "s"
    assert http.calls[0][1]["options"] == {"temperature": 0.1}


def test_generate_json_parses_and_defends():
    http = _FakeHTTP({"response": 'ok {"score": 90}', "prompt_eval_count": 1, "eval_count": 2})
    c = OllamaClient(client=http)
    obj, tin, tout = c.generate_json("m", "p")
    assert obj == {"score": 90} and (tin, tout) == (1, 2)


def test_has_model_matches_with_or_without_tag():
    http = _FakeHTTP({"models": [{"name": "llava:7b"}, {"name": "qwen2.5:14b"}]})
    c = OllamaClient(client=http)
    assert c.has_model("llava:7b")
    assert c.has_model("llava")  # bare name matches
    assert not c.has_model("phi4:14b")


def test_encode_image_roundtrips(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x89PNG\r\n")
    assert encode_image(p) == "iVBORw0K"  # base64 of b"\x89PNG\r\n"
