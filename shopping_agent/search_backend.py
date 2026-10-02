"""Local JSONL product database and the replaceable search boundary."""

from collections import Counter
import json
from pathlib import Path
import re
from typing import Protocol

from pydantic import Field

from .models import StrictModel
from .schemas.autonomous import SearchPlan


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "computer_products_10000.jsonl"


class RawProductRecord(StrictModel):
    source_id: str = Field(min_length=1)
    source_url: str | None = None
    raw_text: str = Field(min_length=1)


class ProductSearchBackend(Protocol):
    def search(self, plan: SearchPlan) -> list[RawProductRecord]: ...


class SearchBackendNotConfigured(RuntimeError):
    pass


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9.+-]*|[\u4e00-\u9fff]+", text.lower())


class JsonlProductSearchBackend:
    """Small in-memory lexical index for the local 10k product database."""

    def __init__(self, catalog_path: str | Path = DEFAULT_CATALOG_PATH):
        self.catalog_path = Path(catalog_path)
        self._records: list[dict] | None = None

    def _load(self) -> list[dict]:
        if self._records is not None:
            return self._records
        if not self.catalog_path.is_file():
            raise SearchBackendNotConfigured(f"本地商品数据库不存在：{self.catalog_path}")
        records = []
        with self.catalog_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"数据库第 {line_number} 行不是合法 JSON") from error
                if item.get("product_id") and item.get("title"):
                    records.append(item)
        self._records = records
        return records

    def search(self, plan: SearchPlan) -> list[RawProductRecord]:
        query_counts = Counter(_tokens(" ".join([
            plan.query, *plan.required_terms,
        ])))
        excluded = [term.lower() for term in plan.excluded_terms]
        ranked: list[tuple[float, dict]] = []
        for item in self._load():
            title = str(item.get("title") or "")
            features = " ".join(map(str, item.get("features") or []))
            description = " ".join(map(str, item.get("description") or []))
            details = json.dumps(item.get("details") or {}, ensure_ascii=False)
            full_text = f"{title} {features} {description} {details}".lower()
            if any(term in full_text for term in excluded):
                continue
            title_tokens = Counter(_tokens(title))
            body_tokens = Counter(_tokens(f"{features} {description} {details}"))
            score = sum(
                count * (5 * min(title_tokens[token], 1) + min(body_tokens[token], 2))
                for token, count in query_counts.items()
            )
            if item.get("category_hint") == plan.category:
                score += 12
            if score > 0:
                score += min(float(item.get("average_rating") or 0), 5) * 0.1
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1]["product_id"])))
        return [
            RawProductRecord(
                source_id=item["product_id"],
                source_url=item.get("source_url"),
                raw_text=json.dumps(item, ensure_ascii=False),
            )
            for _, item in ranked[:plan.limit]
        ]


class UnconfiguredSearchBackend:
    """Explicit placeholder for deployments that opt out of the local database."""

    def search(self, plan: SearchPlan) -> list[RawProductRecord]:
        raise SearchBackendNotConfigured("商品搜索数据库尚未接入")
