import json
from pathlib import Path

import pytest

from serpbench.providers import SearchApi, Serper, load_providers

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_searchapi_parse_and_request():
    p = SearchApi("searchapi", {"api_key_literal": "k"})
    res = p.extract_results(load("searchapi_like.json"))
    assert [r.link for r in res] == ["https://a.example/x", "https://b.example/y"]
    req = p.build("hello", "us", "en")
    assert req["method"] == "GET" and req["params"]["q"] == "hello"


def test_serper_parse_and_request():
    p = Serper("serper", {"api_key_literal": "k"})
    assert len(p.extract_results(load("serper_like.json"))) == 2
    req = p.build("hello", "us", "en")
    assert req["method"] == "POST" and req["headers"]["X-API-KEY"] == "k"


def test_error_payload_detected():
    p = SearchApi("searchapi", {"api_key_literal": "k"})
    assert p.extract_error(load("error_like.json")) == "Invalid API key."


def test_unknown_provider_type_rejected():
    with pytest.raises(ValueError):
        load_providers({"providers": {"x": {"type": "nope"}}})
