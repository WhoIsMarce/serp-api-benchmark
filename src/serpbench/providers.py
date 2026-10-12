"""One small adapter per SERP API.

An adapter does exactly two things: build the HTTP request for a query, and
turn the vendor's JSON into a list of NormalizedResult. Everything else
(timing, retries policy, scoring) lives elsewhere so that every vendor goes
through the same measuring code path.

IMPORTANT: endpoint paths, parameter names and response keys below reflect the
vendors' public documentation as I understand it. They can change. Before you
publish anything, re-read each vendor's current docs and run `pytest`
(the parsing tests use saved fixtures) -- see docs/PUBLISHING_CHECKLIST.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedResult:
    position: int
    title: str
    link: str
    snippet: str


def _normalize(items: Any) -> list[NormalizedResult]:
    out: list[NormalizedResult] = []
    if not isinstance(items, list):
        return out
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue
        try:
            pos = int(it.get("position") or i)
        except (TypeError, ValueError):
            pos = i
        out.append(
            NormalizedResult(
                position=pos,
                title=str(it.get("title") or ""),
                link=str(it.get("link") or ""),
                snippet=str(it.get("snippet") or ""),
            )
        )
    return out


class Provider:
    type_name = ""
    default_base_url = ""
    path = ""

    def __init__(self, name: str, cfg: dict[str, Any]):
        self.name = name
        self.base_url = (cfg.get("base_url") or self.default_base_url).rstrip("/")
        self.api_key = self._resolve_key(cfg)
        self.extra: dict[str, Any] = dict(cfg.get("extra_params") or {})
        self.pricing: dict[str, Any] = dict(cfg.get("pricing") or {})

    @staticmethod
    def _resolve_key(cfg: dict[str, Any]) -> str | None:
        if cfg.get("api_key_literal"):
            return str(cfg["api_key_literal"])
        env = cfg.get("api_key_env")
        return os.environ.get(env) if env else None

    @property
    def url(self) -> str:
        return self.base_url + self.path

    def build(self, query: str, country: str, language: str) -> dict[str, Any]:
        raise NotImplementedError

    def extract_error(self, payload: Any) -> str | None:
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])[:200]
        return None

    def extract_results(self, payload: Any) -> list[NormalizedResult]:
        raise NotImplementedError


class SearchApi(Provider):
    type_name = "searchapi"
    default_base_url = "https://www.searchapi.io"
    path = "/api/v1/search"

    def build(self, query, country, language):
        params = {"engine": "google", "q": query, "gl": country, "hl": language,
                  "api_key": self.api_key, **self.extra}
        return {"method": "GET", "url": self.url, "params": params}

    def extract_results(self, payload):
        return _normalize(payload.get("organic_results"))


class SerpApi(Provider):
    type_name = "serpapi"
    default_base_url = "https://serpapi.com"
    path = "/search.json"

    def build(self, query, country, language):
        params = {"engine": "google", "q": query, "gl": country, "hl": language,
                  "api_key": self.api_key, **self.extra}
        return {"method": "GET", "url": self.url, "params": params}

    def extract_results(self, payload):
        return _normalize(payload.get("organic_results"))


class Serper(Provider):
    type_name = "serper"
    default_base_url = "https://google.serper.dev"
    path = "/search"

    def build(self, query, country, language):
        body = {"q": query, "gl": country, "hl": language, **self.extra}
        return {"method": "POST", "url": self.url, "json": body,
                "headers": {"X-API-KEY": self.api_key or "", "Content-Type": "application/json"}}

    def extract_results(self, payload):
        return _normalize(payload.get("organic"))


PROVIDER_TYPES: dict[str, type[Provider]] = {
    c.type_name: c for c in (SearchApi, SerpApi, Serper)
}


def load_providers(cfg: dict[str, Any], only: list[str] | None = None) -> list[Provider]:
    providers: list[Provider] = []
    for name, pcfg in (cfg.get("providers") or {}).items():
        pcfg = pcfg or {}
        if only and name not in only:
            continue
        if not only and pcfg.get("enabled") is False:
            continue
        ptype = pcfg.get("type", name)
        if ptype not in PROVIDER_TYPES:
            raise ValueError(f"Unknown provider type '{ptype}' for '{name}'. "
                            f"Known: {sorted(PROVIDER_TYPES)}")
        providers.append(PROVIDER_TYPES[ptype](name, pcfg))
    if not providers:
        raise ValueError("No providers selected.")
    return providers
