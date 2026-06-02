# -*- coding: utf-8 -*-
from __future__ import annotations

# Compatibility facade. New code should import either:
# - waybill_files for server-side file naming/export helpers.
# - waybill_collector_reader for business-machine print database reading.

from waybill_collector_reader import (  # noqa: F401
    DEFAULT_DBS,
    choose_product_text,
    collect_records,
    component_name,
    component_status,
    copy_db,
    db_paths,
    extract_and_export_once,
    extract_records,
    get_component_copy_dir,
    get_waybill_data_dir,
    iter_text_nodes,
    normalize_print_text,
)
from waybill_files import (  # noqa: F401
    FIELDS,
    MACHINE_NAME,
    RAW_WAYBILL_HEADERS,
    build_raw_waybill_rows,
    export_records,
    get_waybill_output_dir,
    merge_records,
    output_paths,
    processed_waybill_path,
    raw_record_text,
    raw_waybill_path,
    read_exported_records,
    read_jsonl,
    record_key,
    safe_batch_tag,
    safe_filename,
    unique_path,
    write_jsonl,
    write_raw_waybill_xlsx,
    write_xlsx,
)
