# Changelog

## V7.6.1

- Released the order editor workflow as the formal V7.6.1 project.
- Kept the lightweight data model and original category/stall/image matching workflow.
- Added the Order Recognition tab for importing 1688 order Excel files, reviewing detected category/spec/image status, editing category and keyword fields, and saving selected rows as category rules.
- Added batch rule creation from imported orders, including keyword source choices such as product short name or sales spec.

## V7.5.1-OrderEditor-20260526

- Kept the V7.5.1 lightweight data model and original category/stall/image matching workflow.
- Added an Order Recognition tab for importing 1688 order Excel files, reviewing detected category/spec/image status, editing category and keyword fields, and saving selected rows as category rules.
- Added batch rule creation from imported orders, including keyword source choices such as product short name or sales spec.

## V7.5.1-LiteData-20260525

- Reworked startup loading window into a determinate progress page with file size, decrypt/parse, and image-shard scan stages.
- Changed `system_data.enc` to a lightweight core-data file; image relations are no longer written into the encrypted main data file.
- Added category-sharded image storage under `data/image_categories/*.json` and hashed image files under `data/images/`.
- Updated backend image add/import/delete flows to operate on category shards instead of an in-memory global `image_map`.
- Web status now reports image shard counts and storage size.
- V7.5.1 starts from a clean data line and does not require old-version data compatibility.

## V7.4.8-RemarkMatch-20260525

- Added optional order remark field in import templates.
- Category detection can now match rules against remarks.
- Image matching now uses category, normalized spec, remarks, and source title text.
- Image matching supports continuous normalized text containment, so partially contained spec names can still match within the same category.
- Desktop one-click sorter now reuses the shared `order_core.py` generation logic.
- Web version and console version updated to `V7.4.8-RemarkMatch-20260525`.

## V7.4.7 Rectified Baseline

- Improved Web UI.
- Added download zip for per-stall document output.
- Added runtime config cache to avoid repeatedly rewriting large encrypted data files.
- Added safer download path checks.
