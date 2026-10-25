# ScanText Lab

A local, educational scanned-document editor: find text with CRAFT, recognize
Greek/English or other EasyOCR languages, correct the selection, reconstruct the
paper, and render replacement text with a matching local font.

This implements a plausible public computer-vision pipeline. It does not claim
knowledge of Adobe's implementation or Acrobat-level editing fidelity.

## Install and run

Use **64-bit Python 3.11 or 3.12**:

```powershell
python scripts/setup.py --greek --dev
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux use `.venv/bin/python`. Omit `--greek` for EasyOCR-only profiles,
or `--dev` if you do not need pytest. If Python is not on PATH, invoke your
installed Python executable explicitly.

Setup creates two local environments without changing system Python:

- `.venv`: Streamlit, EasyOCR/PyTorch, headless OpenCV, Pillow, and PyMuPDF.
- `.venv-greek`: optional PaddleOCR/PaddlePaddle worker and its own OpenCV build.

Keep these environments separate: the isolation avoids conflicting native
libraries and OpenCV distributions. The worker can be installed independently:

```powershell
.\.venv\Scripts\python.exe scripts/setup_greek.py
```

First OCR use downloads official model weights to the user's EasyOCR/PaddleX
cache. Inference processes documents locally. Provision both caches for offline
use. Greek recognition uses CPU; the GPU checkbox controls CRAFT detection.
Other EasyOCR profiles can use an appropriate PyTorch GPU build following
[PyTorch's installation instructions](https://pytorch.org/get-started/locally/).

For an existing installation, reinstall `requirements.txt` and restart Streamlit.
The explicit `pyarrow==19.0.1` pin keeps tables compatible with NumPy 1.26.4.
Direct dependencies are pinned; the two lock files record validated Windows /
Python 3.12 environments. CI configuration covers Windows and Ubuntu on Python
3.11/3.12; those remote CI jobs have not been run from this workspace.

## Editing a document

1. Upload a PDF, PNG, JPEG, or TIFF. TIFF support currently reads its first frame.
2. Choose a page, language profile, and OCR settings, then run OCR.
3. Select a numbered region. Correct Left/Top/Right/Bottom and the original
   transcription if OCR joined words or missed accents. Coordinates refer to the
   full-resolution page; the crop preview shows exactly what you selected.
4. If the detector missed text entirely, choose **Manual region** and enter its
   coordinates and original text. This works without OCR/model initialization.
5. Enter replacement text, or leave it empty to erase. Choose a font manually
   or use the visual estimate. Adjust size, horizontal/vertical placement, and
   clockwise rotation while watching the preview.
6. Inspect padding, removal mask, and erased paper. Replacements outside the
   selected box require an explicit overflow override.
7. Click **Apply edit** before changing page. Switching pages or changing OCR
   settings preserves applied edits. Unapplied controls are previews, not saved
   edits. Run OCR again to select another detected word after applying.
8. Use **Prepare complete PDF**, then **Download complete PDF**, to export all
   pages and applied edits. Preview PNG is explicitly labeled as unapplied.

Undo retains the last three image edits **per page**. Reset reloads only the
current page at the selected DPI, discarding its edits. Changing DPI never
silently discards work: an already opened page keeps its raster DPI until reset.
Pages load on demand; PNG-compressed images/history are limited to 200 MiB per
session, in addition to transient processing memory. Session work is held in
memory and is lost when the server/session ends. Download before closing.

### PDF export behavior

All source PDF pages remain in order. Unmodified pages retain original page
content; modified pages are replaced with raster images at their original visible
physical size, including rotated page dimensions. Their old text layers,
annotations, outgoing links, and form widgets are removed. The original text is
not hidden under an overlay. Metadata, bookmarks, and ordinary incoming internal
page links are retained/rebuilt. An entirely unmodified PDF is returned unchanged.

Complex named destinations, attachments, signatures, tagged-PDF structure, and
interactive forms are not guaranteed to survive an edited export. Exports are
not a forensic redaction workflow. Image uploads export as a one-page PDF using
the selected physical DPI. Uploads are limited to 50 MiB; individual raster pages
to 25 megapixels; password-protected PDFs are rejected.

## Greek support and OCR architecture

The default **Ελληνικά + English** profile uses:

- **EasyOCR CRAFT** for geometry only, with its Latin recognizer disabled.
- **PP-OCRv5 Greek** (`el_PP-OCRv5_mobile_rec`) for Greek, English, and digits.

The Greek model is listed in the
[official PP-OCRv5 multilingual documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.3.2/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md).
Modern Greek output is Unicode NFC-normalized, preserving accents and final
sigma. Ancient/polytonic Greek and handwriting need separate evaluation.

English/French and compatible custom language combinations retain the original
EasyOCR CRAFT → CRNN/CTC recognition path. EasyOCR does not have a built-in Greek
recognizer; entering `el` selects our added recognizer, not a Latin fallback.

Detection and recognition are explicit separate methods in the heavily commented
`core/ocr_engine.py`. Detector boxes are converted from EasyOCR's internal
`[xmin, xmax, ymin, ymax]` order to public **half-open**
`[xmin, ymin, xmax, ymax]` coordinates. Each result retains polygon, unpadded
box, clipped padded box, recognized text, and recognition confidence. These scores
are not calibrated detector probabilities or comparable across backends.

Small detector grouping thresholds favor words. Multiword regions can be split
at measured blank columns, then each candidate is re-recognized. Ambiguous
boundaries remain phrases; manual bounds allow precise word selection. Positions
are never guessed from character counts. Original images remain uint8 RGB;
the adapters explicitly convert to BGR/grayscale where needed.

The Greek recognizer perspective-rectifies detected quadrilaterals and sends
lossless PNG crops through local process pipes. A persistent isolated worker keeps
its model loaded and batches inference. Requests have a 300-second timeout and
error diagnostics. Host preflight checks are skipped; actual model-download
failures are still reported. Set `SCANTEXT_GREEK_PYTHON` to an alternative worker
Python executable when deploying in another environment layout.

## Appearance reconstruction

Style is measured **before** erasure. Two-cluster K-means estimates foreground
and paper colors; the perimeter-dominant cluster is treated as background. This
is an approximation on multicolor text and patterned paper.

The bundled catalog contains eight DejaVu fonts: Sans/Serif, regular/bold/italic/
bold italic, all including modern Greek. Automatic matching compares thresholded
original glyphs with rendered candidates at nearby height-derived sizes, using
pixel IoU without stretching character widths. Its score is a heuristic similarity,
not recovered font identity. Incorrect source transcription, scan distortion,
rotation, or fonts outside the catalog can mislead it; manual choice stays available.

Default font pixels are calibrated from the unpadded box height against the
chosen font's glyph height; points = pixels × 72 / DPI. The user may override the
size multiplier. Pillow glyph bearings are compensated, with manual horizontal
and vertical/baseline adjustments and clockwise rotation. Placement uses the
top-left of the rotated glyph image. Baseline and angle are not automatically
recovered. Explicit overflow checks cover movement and rotation.

Telea or Navier–Stokes inpainting interpolates a padded rectangular mask from
surrounding paper. More padding catches anti-aliasing/accents but can remove
nearby strokes. Large regions, rules, illustrations, and irregular paper textures
can leave artifacts. There is no automatic deskew/dewarp, exact font retrieval,
automatic blur/noise matching, or semantic layout reflow.

## Tests and evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke_ocr.py
.\.venv\Scripts\python.exe scripts/smoke_greek.py
```

Local validation on Windows / Python 3.12: **27 tests pass**, covering UI editing,
manual selection without OCR, font ranking/placement, masks, image decoding, PDF
round-tripping, per-page history, multi-page exports, bookmarks/internal links,
and accent-sensitive evaluation metrics. Both environments pass `pip check`.

Real model inference on two **synthetic** Greek pages (clean and mildly blurred)
recognizes all eight expected words/numbers, including accented Greek; the
evaluation CLI reports CER/WER 0 on those samples. This does **not** measure
accuracy on real scans. No labeled real-scan corpus has been supplied.

Use the corpus evaluator for your own labeled documents:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ocr.py datasets/manifest.json --output outputs/real-evaluation.json
```

[Evaluation instructions](docs/EVALUATION.md) describe the manifest, full-page
transcription, optional word boxes, CER/WER, IoU matching, and reading-order limits.
Private datasets and generated outputs are gitignored.

GitHub Actions defines automatic unit/UI tests on Windows/Ubuntu and Python
3.11/3.12, plus a manually triggered real-model integration workflow. Model
downloads are excluded from ordinary unit-test runs. Remote CI still needs to be
executed after pushing the repository.

## Repository tree

```text
.
├── app.py
├── core/
│   ├── __init__.py
│   ├── models.py
│   ├── document.py             # Compressed page state, history, session budget
│   ├── ingestion.py            # Bounded decoding and complete PDF assembly
│   ├── ocr_engine.py           # CRAFT/recognition split and word refinement
│   ├── greek_recognizer.py     # Rectification and persistent worker client
│   ├── greek_worker.py         # Isolated Greek PP-OCRv5 process
│   ├── regions.py              # Validated manual/corrected bounds
│   ├── fonts.py                # Eight-font catalog and visual ranking
│   ├── style.py                # K-means colors and height-based sizing
│   ├── inpainter.py            # Telea / Navier–Stokes and binary masks
│   ├── renderer.py             # Font size, bearings, position, rotation
│   ├── pipeline.py
│   └── evaluation.py           # CER/WER, reading order, IoU matching
├── assets/fonts/               # Eight DejaVu .ttf files and LICENSE.txt
├── scripts/
│   ├── setup.py
│   ├── setup_greek.py
│   ├── smoke_ocr.py
│   ├── smoke_greek.py
│   └── evaluate_ocr.py
├── tests/
│   ├── test_app.py
│   ├── test_pipeline.py
│   ├── test_greek.py
│   ├── test_document.py
│   ├── test_editing.py
│   └── test_evaluation.py
├── docs/EVALUATION.md
├── .github/workflows/
│   ├── tests.yml
│   └── ocr-integration.yml
├── .streamlit/config.toml
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── requirements-lock.txt
├── requirements-greek.txt
├── requirements-greek-lock.txt
├── CHANGELOG.md
└── LICENSE
```

## License

Project-authored code is MIT. Bundled fonts retain the full redistribution license
in `assets/fonts/LICENSE.txt` ([upstream](https://dejavu-fonts.github.io/License.html)).
Dependencies and models retain their upstream terms. PyMuPDF is offered under
AGPL/commercial terms; consult its
[licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
when redistributing or deploying a combined application.
