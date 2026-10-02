"""Build a 10k PC-product JSONL catalog from Amazon Reviews 2023 metadata."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download


REPO_ID = "McAuley-Lab/Amazon-Reviews-2023"
REVISION = "2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e"
SHARD_PATTERN = "raw_meta_Electronics/full-{index:05d}-of-00010.parquet"

RULES = [
    ("laptop", r"\blaptops?\b|\bnotebooks?\b|\bchromebooks?\b|\bmacbook(?:s|\s+(?:air|pro))?\b"),
    ("desktop", r"\bdesktop computers?\b|\bdesktop pcs?\b|\bgaming desktops?\b|\bgaming pcs?\b|\bmini pcs?\b|\ball-in-one computers?\b|\bworkstation computers?\b"),
    ("monitor", r"\b(?:gaming|computer|portable|desktop)?\s*monitors?\b"),
    ("keyboard", r"\b(?:computer|gaming|mechanical|wireless)?\s*keyboards?\b"),
    ("mouse", r"\bcomputer mice\b|\bgaming mouse\b|\bwireless mouse\b|\btrackball mouse\b"),
    ("motherboard", r"\bmotherboards?\b|\bmainboards?\b|\b(?:am[45]|lga\s?\d{3,4})\b"),
    ("gpu", r"\bgraphics cards?\b|\bvideo cards?\b|\bgeforce\b|\bradeon\s+rx\b|\brtx\s?\d+\b|\bgtx\s?\d+\b"),
    ("cpu", r"\bdesktop processors?\b|\bcpu processors?\b|\b(?:intel|amd)\s+(?:core|ryzen)\b"),
    ("memory", r"\bdesktop memory\b|\blaptop memory\b|\bram modules?\b|\b(?:ddr[345])\s+(?:ram|memory)\b"),
    ("ssd", r"\bsolid state drives?\b|\b(?:nvme|sata)\s+ssds?\b|\bm\.2\s+ssds?\b"),
    ("hdd", r"\binternal hard drives?\b|\bdesktop hard drives?\b|\bnas hard drives?\b|\bexternal hard drives?\b|\bportable external hard drive\b|\b\d+\s?rpm\b"),
    ("psu", r"\bpower supply units?\b|\bcomputer power suppl(?:y|ies)\b|\batx\s+power supply\b"),
    ("cooler", r"\bcpu coolers?\b|\bliquid cpu coolers?\b|\bcpu cooling fans?\b|\bthermalright\b"),
    ("case", r"\bcomputer cases?\b|\bpc cases?\b|\bgaming cases?\b|\bmid[- ]tower cases?\b"),
    ("network_card", r"\bnetwork cards?\b|\bnetwork adapters?\b|\bwifi cards?\b|\bwi-fi adapters?\b|\bethernet adapters?\b"),
]
CORE_EXCLUSIONS = {
    "laptop": re.compile(r"\b(case|sleeve|bag|backpack|charger|adapter|skin|cover|stand|table|desk|replacement|cable|dock(?:ing)?|battery|speaker|sticker|decal|bridge|hub)\b", re.I),
    "desktop": re.compile(r"\b(case|stand|replacement|cable|accessory)\b", re.I),
    "monitor": re.compile(r"\b(cable|charger|stand|riser|protector|privacy screen|arm|mount|adapter|replacement|cover|cleaner|mirror|car|dvd|security|surveillance|camera|baby|watch|bag|case|light bar|lamp)\b", re.I),
    "keyboard": re.compile(r"\b(keycaps?|switches?|cable|cover|case|charger|pcb|foam|piano|synthesizer|skins?|tray|desk|converter|cleaner|vacuum)\b", re.I),
    "mouse": re.compile(r"\b(pads?|mats?|feet|skates|case|holder)\b", re.I),
    "gpu": re.compile(r"\b(coolers?|fans?|water blocks?|holders?|supports?|brackets?|cases?|desktops?|laptops?|notebooks?|aspire|inspiron|adapters?|external|cables?|splitters?)\b", re.I),
}
CORE_REQUIRED = {
    "laptop": re.compile(r"\b(intel|amd|ryzen|celeron|pentium|snapdragon|apple\s+m[1-4]|\d+\s?gb\s+(?:ram|memory|ssd|storage))\b", re.I),
    "desktop": re.compile(r"\b(intel|amd|ryzen|celeron|pentium|windows|\d+\s?gb\s+(?:ram|memory|ssd|storage))\b", re.I),
    "monitor": re.compile(r"\b(\d{2}(?:\.\d)?[- ]?inch|\d{3,4}p|[1248]k|\d{2,3}\s?hz|lcd|led|oled|ips|crt|va panel)\b", re.I),
    "gpu": re.compile(r"\b(graphics? cards?|video cards?|(?:rtx|gtx|radeon|geforce)\s?\d{3,4})\b", re.I),
}
OTHER_RE = re.compile(
    r"\bdocking stations?\b|\busb hubs?\b|\bkvm switches?\b|\bpcie cards?\b|"
    r"\bcomputer cables?\b|\bcomputer speakers?\b|\bwebcams?\b|\bcapture cards?\b|"
    r"\bcomputer headsets?\b|\bcomputer microphones?\b|\busb flash drives?\b|"
    r"\bmemory card readers?\b|\blaptop stands?\b|\blaptop sleeves?\b|"
    r"\blaptop chargers?\b|\bmonitor arms?\b|\bcomputer desks?\b",
    re.IGNORECASE,
)


def classify(title: str, categories: list[str]) -> str | None:
    haystack = title.lower()
    for category, pattern in RULES:
        excluded = CORE_EXCLUSIONS.get(category)
        required = CORE_REQUIRED.get(category)
        if (re.search(pattern, haystack, re.IGNORECASE)
                and not (excluded and excluded.search(haystack))
                and (required is None or required.search(haystack))):
            return category
    if OTHER_RE.search(title):
        mobile_only = re.search(r"\b(ipad|iphone|tablet|smartphone|cell phone)\b", title, re.I)
        computer_term = re.search(r"\b(computer|pc|laptop|macbook|chromebook)\b", title, re.I)
        if mobile_only and not computer_term:
            return None
        return "other"
    return None


def parse_details(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def normalized_record(row: dict, category: str) -> dict:
    asin = row["parent_asin"]
    details = parse_details(row.get("details"))
    return {
        "product_id": asin,
        "category_hint": category,
        "title": row.get("title") or asin,
        "brand": details.get("Brand") or details.get("Manufacturer"),
        "description": row.get("description") or [],
        "features": row.get("features") or [],
        "details": details,
        "price": row.get("price"),
        "currency": "USD",
        "average_rating": row.get("average_rating"),
        "rating_number": row.get("rating_number"),
        "source_url": f"https://www.amazon.com/dp/{asin}",
        "dataset_source": "McAuley-Lab/Amazon-Reviews-2023 raw_meta_Electronics",
    }


def build_catalog(output: Path, source_dir: Path, limit: int) -> Counter:
    selected: dict[str, dict] = {}
    counts: Counter = Counter()
    for index in range(10):
        filename = SHARD_PATTERN.format(index=index)
        parquet_path = Path(hf_hub_download(
            repo_id=REPO_ID, repo_type="dataset", revision=REVISION,
            filename=filename, local_dir=source_dir,
        ))
        table = pq.read_table(parquet_path, columns=[
            "title", "average_rating", "rating_number", "features", "description",
            "price", "categories", "details", "parent_asin",
        ])
        for row in table.to_pylist():
            asin = row.get("parent_asin")
            title = row.get("title") or ""
            category = classify(title, row.get("categories") or [])
            if not asin or not title or category is None or asin in selected:
                continue
            selected[asin] = normalized_record(row, category)
            counts[category] += 1
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        raise RuntimeError(f"只筛选到 {len(selected)} 条电脑商品，未达到 {limit}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in selected.values():
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    metadata = {
        "dataset": "McAuley-Lab/Amazon-Reviews-2023",
        "config": "raw_meta_Electronics",
        "revision": REVISION,
        "source_url": f"https://huggingface.co/datasets/{REPO_ID}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(selected),
        "category_counts": dict(sorted(counts.items())),
        "catalog_sha256": digest,
    }
    metadata_path = output.with_name(f"{output.stem}.metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/computer_products_10000.jsonl"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/source"))
    parser.add_argument("--limit", type=int, default=10_000)
    args = parser.parse_args()
    counts = build_catalog(args.output, args.source_dir, args.limit)
    print(json.dumps({"output": str(args.output), "total": sum(counts.values()),
                      "categories": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
