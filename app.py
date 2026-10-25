"""Run with: python -m streamlit run app.py"""
from dataclasses import asdict, replace
import hashlib
import json
import cv2
import streamlit as st
from core.document import DocumentSession
from core.fonts import font_catalog, rank_fonts
from core.greek_recognizer import greek_available
from core.ingestion import png_bytes
from core.models import bounds
from core.ocr_engine import OCREngine
from core.pipeline import replace_region
from core.regions import manual_region
from core.renderer import RenderOptions

st.set_page_config(page_title="ScanText Lab", layout="wide")
st.title("ScanText Lab")
st.caption("Greek / English OCR · editable regions · local font matching · complete PDF export")


@st.cache_resource
def get_engine(languages, gpu):
    return OCREngine(languages, gpu)


with st.sidebar:
    st.header("OCR configuration")
    profile = st.radio("Recognition language", ["Ελληνικά + English", "English + Français", "Other EasyOCR languages"])
    if profile == "Ελληνικά + English":
        codes = "el,en"
        if not greek_available():
            st.warning("Greek OCR needs one-time setup: python scripts/setup_greek.py")
        st.caption("Greek recognition runs locally on CPU. GPU controls CRAFT detection.")
    elif profile == "English + Français":
        codes = "en,fr"
    else:
        codes = st.text_input("EasyOCR language codes, comma separated", "en,fr")
    gpu = st.checkbox("Use GPU", False)
    dpi = st.slider("DPI for newly opened or reset pages", 72, 600, 300)
    threshold = st.slider("CRAFT text threshold", 0.1, 0.95, 0.7, 0.05)
    confidence = st.slider("Minimum recognition confidence", 0.0, 1.0, 0.0, 0.05)
    canvas = st.select_slider("Detection canvas size", [2560, 3840, 5120], value=3840)
    st.caption("Changing OCR settings preserves applied edits. Run OCR to refresh detections.")

upload = st.file_uploader("Upload a scanned PDF or image", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"])
if upload is None:
    st.info("Upload a document, run OCR or choose Manual region, then replace text.")
    st.stop()

try:
    data = upload.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    if st.session_state.get("document_key") != digest:
        document = DocumentSession(data, data.startswith(b"%PDF-") or upload.name.lower().endswith(".pdf"))
        st.session_state.document = document
        st.session_state.document_key = digest
        st.session_state.pop("prepared_pdf", None)
    document = st.session_state.document
    page = int(st.number_input("Page", 1, document.count, 1, key=f"page-{digest}")) - 1
    state = document.get_page(page, dpi)
    current = state.image()
    h, w = current.shape[:2]
    st.caption(f"Page {page + 1}/{document.count} · {w} × {h} px · {state.dpi} DPI · "
               f"{sum(p.dirty for p in document.pages.values())} edited page(s)")
    if state.dpi != dpi:
        st.info(f"This page retains {state.dpi} DPI. Reset page to reload at {dpi} DPI; its edits will be removed.")

    with st.expander("Export applied edits", expanded=True):
        st.download_button("Download current page PNG", state.png, f"page-{page + 1}.png", "image/png")
        if st.button("Prepare complete PDF"):
            with st.spinner("Assembling all pages…"):
                st.session_state.prepared_pdf = (document.version, document.export_pdf())
        prepared = st.session_state.get("prepared_pdf")
        if prepared and prepared[0] == document.version:
            st.download_button("Download complete PDF", prepared[1], "edited-document.pdf", "application/pdf")
        st.caption("Complete PDF includes all pages and applied edits. Modified pages become raster images; "
                   "their old text layers and annotations are removed. Unmodified pages retain original content.")

    languages = tuple(c.strip().lower() for c in codes.split(",") if c.strip())
    if not languages:
        raise ValueError("Enter at least one OCR language.")
    if st.button("Run OCR on current page", type="primary"):
        with st.spinner("Detecting regions and recognizing text…"):
            state.regions = get_engine(languages, gpu).run(
                current, min_confidence=confidence, text_threshold=threshold, canvas_size=canvas)
    if st.button("Reset page"):
        document.reset(page, dpi)
        st.rerun()
    if state.undo and st.button("Undo last edit"):
        document.undo_edit(page)
        st.rerun()
    mode = st.radio("Region source", ["Detected text", "Manual region"], horizontal=True)
    regions = state.regions or []
    marked = current.copy()
    for r in regions:
        x0, y0, x1, y1 = r.bbox
        cv2.rectangle(marked, (x0, y0), (x1 - 1, y1 - 1), (30, 150, 80), 2)
        cv2.putText(marked, str(r.id), (x0, max(12, y0 - 3)), cv2.FONT_HERSHEY_SIMPLEX, .5, (30, 150, 80), 1)
    if mode == "Detected text" and not regions:
        st.info("Run OCR to select text, or choose Manual region to edit text the detector missed.")
        st.image(marked, caption="Current page", use_container_width=True)
        st.stop()
    source = None
    if mode == "Detected text":
        st.dataframe([{"id": r.id, "text": r.text, "confidence": round(r.confidence, 3),
                       "bbox": list(r.bbox)} for r in regions], hide_index=True)
        selected = st.selectbox("Select a detected object (IDs match the image)", range(len(regions)),
                                format_func=lambda i: f"#{i}: {regions[i].text} ({regions[i].confidence:.1%})",
                                key=f"object-{digest}-{page}-{state.revision}")
        source = regions[selected]
        default_box, original_text = source.bbox, source.text
    else:
        selected = -1
        default_box = (w // 4, h // 4, max(w // 4 + 1, 3 * w // 4), min(h, h // 4 + max(20, h // 20)))
        original_text = ""
    tag = f"{digest}-{page}-{state.revision}-{selected}-{mode}"
    with st.expander("Correct text region and transcription", expanded=True):
        st.caption("Coordinates are original-page pixels. Right/bottom are exclusive. "
                   "Use the crop preview to isolate one word, including its accents.")
        cols = st.columns(4)
        coordinates = []
        for col, label, value, limit in zip(cols, ["Left", "Top", "Right", "Bottom"], default_box, [w, h, w, h]):
            coordinates.append(col.number_input(label, 0, limit, int(value), key=f"{label}-{tag}"))
        transcription = st.text_input("Original text (correct OCR if needed)", original_text, key=f"source-{tag}")
    try:
        region = manual_region(current.shape, coordinates, transcription,
                               source.id if source else -1, source.confidence if source else 0)
        if source and tuple(coordinates) == source.bbox:
            region = replace(source, text=transcription)
    except ValueError as exc:
        st.warning(str(exc))
        st.image(marked, use_container_width=True)
        st.stop()
    x0, y0, x1, y1 = region.bbox
    cv2.rectangle(marked, (x0, y0), (x1 - 1, y1 - 1), (220, 40, 40), 2)
    st.image(current[y0:y1, x0:x1], caption="Original crop — check borders and accents",
             width=min(650, max(200, x1-x0)))
    replacement = st.text_input("Replacement (empty text erases)", transcription, key=f"replacement-{tag}")
    with st.expander("Font and placement", expanded=True):
        catalog = font_catalog()
        font_choice = st.selectbox("Font", ["Auto estimate"] + list(catalog), key=f"font-{tag}")
        try:
            if font_choice == "Auto estimate":
                match = rank_fonts(current, region)[0]
                font_path = match.path
                st.caption(f"Estimate: {match.name} · visual similarity {match.score:.2f}. "
                           "This compares local fonts; it does not identify the original font.")
            else:
                font_path = catalog[font_choice]
        except ValueError as exc:
            st.warning(str(exc))
            st.image(marked, use_container_width=True)
            st.stop()
        scale = st.slider("Font size multiplier", .25, 3.0, 1.0, .05, key=f"scale-{tag}")
        offset_x = st.slider("Horizontal adjustment (px)", -100, 100, 0, key=f"dx-{tag}")
        offset_y = st.slider("Vertical / baseline adjustment (px)", -100, 100, 0, key=f"dy-{tag}")
        angle = st.slider("Clockwise rotation (degrees)", -180, 180, 0, key=f"angle-{tag}")
    with st.expander("Removal controls", expanded=True):
        padding = st.slider("Box padding (pixels)", 0, 12, 2)
        radius = st.slider("Inpainting radius (pixels)", 1, 20, 3)
        method = st.radio("Inpainting algorithm", ["telea", "ns"], horizontal=True)
    try:
        result, erased, mask, style = replace_region(
            current, region, replacement, padding=padding, radius=radius, method=method,
            dpi=state.dpi, font_path=font_path, render_options=RenderOptions(scale, offset_x, offset_y, angle))
    except ValueError as exc:
        st.warning(str(exc))
        st.image(marked, use_container_width=True)
        st.stop()
    px0, py0, px1, py1 = bounds(region.polygon, marked.shape, padding)
    cv2.rectangle(marked, (px0, py0), (px1-1, py1-1), (240, 150, 0), 1)
    left, right = st.columns(2)
    left.image(marked, caption="Regions — red: selection; amber: removal mask", use_container_width=True)
    right.image(result.image, caption="Live replacement preview", use_container_width=True)
    st.caption(f"Font: {style.font_pixels * scale:.1f} px / {style.font_points * scale:.1f} pt; "
               f"ink RGB {style.foreground}; paper RGB {style.background}")
    with st.expander("Inspect inpainting and mask"):
        a, b = st.columns(2)
        a.image(erased, caption="Text erased", use_container_width=True)
        b.image(mask, caption="Binary removal mask", use_container_width=True)
    if style.contrast < 30:
        st.warning("Low foreground/background separation: inspect the color estimate carefully.")
    accept_overflow = False
    if result.overflow:
        st.warning("Replacement extends outside the selected box and may cover nearby content or be clipped at the page edge.")
        accept_overflow = st.checkbox("Allow replacement outside the original box", key=f"overflow-{tag}")
    if st.button("Apply edit", disabled=result.overflow and not accept_overflow):
        document.apply(page, result.image)
        st.rerun()
    st.download_button("Download preview PNG (unapplied)", png_bytes(result.image), "preview-page.png", "image/png")
    st.download_button("Download OCR JSON", json.dumps([asdict(r) for r in regions], ensure_ascii=False, indent=2),
                       f"ocr-page-{page+1}.json", "application/json")
except Exception as exc:
    st.error(f"Unable to process this page: {exc}")
    st.caption("Check upload validity, OCR setup, local fonts, and model download access.")
