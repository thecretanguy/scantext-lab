# Changelog

## Unreleased — Editing and document improvements

- Added per-page compressed editing state and three-step undo, preserved across
  navigation and OCR setting changes, with a 200 MiB stored-history budget.
- Added complete PDF export: untouched page content, rasterized modified pages,
  original visible page dimensions, metadata, bookmarks, and ordinary incoming
  internal links. Unmodified PDFs are returned without rewriting.
- Added editable pixel bounds and source transcription, crop inspection, and
  manual region editing without needing OCR to find the text first.
- Bundled eight DejaVu Sans/Serif style variants and added transparent visual
  font ranking, manual size/position/baseline adjustment, and text rotation.
- Added accent-sensitive corpus evaluation (CER/WER and optional word-box IoU
  precision/recall/F1), with explicit real/synthetic provenance in reports.
- Added one-command setup and GitHub Actions workflows for cross-platform unit/UI
  tests and opt-in model integration. Remote workflows have not yet been run.
- Local validation: 27 tests passed; actual Greek OCR plus evaluation passed on
  two synthetic samples. No labeled real-scan corpus has been supplied.

## Unreleased — Greek OCR

- Added a Greek/English language profile, selected by default in Streamlit.
- Kept EasyOCR/CRAFT detection; added the official Greek PP-OCRv5 recognizer.
- Added a persistent, isolated CPU worker with perspective-rectified crops,
  batched inference, bounded waits, error diagnostics, and automatic cleanup.
- Preserved recognition confidence and original page polygons; Greek output uses
  Unicode NFC normalization, retaining modern Greek accents and final sigma.
- Preserved the existing EasyOCR English/French and custom language profiles.
- Added one-command worker setup, pinned worker requirements, and a separate lock file.
- Added real Greek integration checks on clean/blurred generated pages with
  English and digits, plus Greek replacement and worker-contract unit tests.

This is a local extension of ScanText Lab. No upstream GitHub repository is
configured yet; publishing or forking requires identifying that repository.
