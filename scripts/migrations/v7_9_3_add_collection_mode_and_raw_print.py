# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.collector_config import load_collector_config
from core.collector_raw_records import raw_records_path


def main() -> int:
    config = load_collector_config(auto_create=True)
    records = raw_records_path()
    records.parent.mkdir(parents=True, exist_ok=True)
    records.touch(exist_ok=True)
    print(f"collector_settings={config['collection_mode']} {config['updated_at']}")
    print(f"collector_raw_records={records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
