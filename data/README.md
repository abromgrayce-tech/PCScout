# Local product catalog

The generated catalog and downloaded source shards are deliberately excluded from Git.
The upstream Amazon Reviews 2023 dataset does not publish a redistribution license for
these records, so this repository contains only the reproducible builder and generation
metadata.

Build a local 10,000-product catalog from the project root:

```powershell
python -m pip install -r requirements-data.txt
python scripts\build_computer_catalog.py
```

This creates `data/computer_products_10000.jsonl` and refreshes its metadata file. Review
the upstream dataset terms before downloading or using the data.

