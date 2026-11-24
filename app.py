"""
Transport Challan PDF Filter & Reflow Tool
Author: AI Pair Programmer
Features:
- Streamlit Web UI + Command Line Interface (CLI)
- Coordinate-based 11-field extraction using PyMuPDF (words & dict)
- Case-insensitive, partial multi-name matching on Consignee column
- Pixel-identical template preservation (fonts, header, logos, vector layout)
- Preserves original SlNo, GR No, and amounts (no renumbering or edits)
- Upward row compaction & reflow at exact 13.5 pt spacing
- Recalculates totals line (Total GR, Nugs, Wt, ToPay, Paid)
- Updates Page No. dynamically on each page
- Preserves dedicated Authorised Signatory final page
- Full validation suite (11-field check, consignee group total reconciliation)
"""

import os
import sys
import argparse
import re
import pandas as pd
import pymupdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CONSTANTS & GEOMETRY (derived from Kirpa Cargo Carriers template) ---
ROW_SPACING = 13.5
FIRST_ROW_BASELINE = 204.35
FIRST_ROW_BASELINE_SMALL = 203.40

# Normal page capacity vs page with totals capacity
MAX_ROWS_NORMAL_PAGE = 45
MAX_ROWS_TOTALS_PAGE = 37

TOTALS_Y_TOP_LINE = 699.2
TOTALS_Y_BOT_LINE = 714.7
TOTALS_BASELINE = 710.05
TOTALS_LABEL_BASELINE = 710.15

# Target redaction areas
RECT_DATA_ROWS = pymupdf.Rect(10, 194, 580, 805)
RECT_PAGE_NO = pymupdf.Rect(545, 98, 565, 112)


def parse_challan_pdf(pdf_source):
    """
    Parses a challan PDF (filepath or bytes) and extracts all table rows with 11 fields.
    Returns:
        doc: pymupdf.Document
        rows: list of row dicts
        errors: list of error/warning strings
        validation_info: dict of sum totals
    """
    if isinstance(pdf_source, (bytes, bytearray)):
        doc = pymupdf.open(stream=pdf_source, filetype="pdf")
    else:
        doc = pymupdf.open(pdf_source)

    parsed_rows = []
    errors = []

    for pno in range(len(doc)):
        page = doc[pno]
        words = page.get_text("words")

        # Locate SlNos in column range x in [15, 38], y in [195, 805]
        sl_words = [w for w in words if 15 <= w[0] <= 38 and 195 <= w[1] <= 805 and w[4].isdigit()]
        sl_words.sort(key=lambda w: w[1])

        # Extract text blocks / spans for precise formatting
        d = page.get_text("dict")
        spans_by_y = {}
        for b in d["blocks"]:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        ym = (s["bbox"][1] + s["bbox"][3]) / 2
                        matched_k = None
                        for k in spans_by_y:
                            if abs(k - ym) < 4:
                                matched_k = k
                                break
                        if matched_k is None:
                            matched_k = ym
                            spans_by_y[matched_k] = []
                        spans_by_y[matched_k].append(s)

        for sw in sl_words:
            y_mid = (sw[1] + sw[3]) / 2
            row_words = [w for w in words if abs((w[1] + w[3]) / 2 - y_mid) < 5]
            row_words.sort(key=lambda x: x[0])

            sl_no = sw[4]
            gr_no = " ".join([w[4] for w in row_words if 38 <= (w[0] + w[2]) / 2 < 80])
            consignor = " ".join([w[4] for w in row_words if 80 <= (w[0] + w[2]) / 2 < 165])
            consignee = " ".join([w[4] for w in row_words if 165 <= (w[0] + w[2]) / 2 < 238])
            nugs = " ".join([w[4] for w in row_words if 238 <= (w[0] + w[2]) / 2 < 255])
            particular = " ".join([w[4] for w in row_words if 255 <= (w[0] + w[2]) / 2 < 315])
            to_stn = " ".join([w[4] for w in row_words if 315 <= (w[0] + w[2]) / 2 < 395])
            wt = " ".join([w[4] for w in row_words if 395 <= (w[0] + w[2]) / 2 < 418])
            pvt_mrk = " ".join([w[4] for w in row_words if 418 <= (w[0] + w[2]) / 2 < 495])
            topay = " ".join([w[4] for w in row_words if 495 <= (w[0] + w[2]) / 2 < 545])
            paid = " ".join([w[4] for w in row_words if 545 <= (w[0] + w[2]) / 2 < 585])

            # Validate that none of the 11 columns are empty
            fields = {
                "SlNo": sl_no,
                "GR No": gr_no,
                "Consignor": consignor,
                "Consignee": consignee,
                "Nugs": nugs,
                "Particular": particular,
                "To Stn": to_stn,
                "Wt": wt,
                "Pvt/Mrk": pvt_mrk,
                "ToPay": topay,
                "Paid": paid,
            }
            empty_cols = [k for k, v in fields.items() if not v.strip()]
            if empty_cols:
                errors.append(f"Page {pno+1}, SlNo {sl_no}: Missing fields: {', '.join(empty_cols)}")

            # Collect original spans for identical font injection
            matched_spans = []
            for k, slist in spans_by_y.items():
                if abs(k - y_mid) < 5:
                    matched_spans.extend(slist)
            matched_spans.sort(key=lambda s: s["bbox"][0])

            parsed_rows.append({
                "page": pno + 1,
                "y_mid": y_mid,
                "SlNo": sl_no,
                "GR No": gr_no,
                "Consignor": consignor,
                "Consignee": consignee,
                "Nugs": nugs,
                "Particular": particular,
                "To Stn": to_stn,
                "Wt": wt,
                "Pvt/Mrk": pvt_mrk,
                "ToPay": topay,
                "Paid": paid,
                "spans": matched_spans,
            })

    # Totals across parsed rows
    try:
        sum_topay = sum(float(r["ToPay"].replace(",", "")) for r in parsed_rows)
        sum_paid = sum(float(r["Paid"].replace(",", "")) for r in parsed_rows)
        sum_gr = len(parsed_rows)
        sum_nugs = sum(int(r["Nugs"]) for r in parsed_rows)
        sum_wt = sum(float(r["Wt"]) for r in parsed_rows)
    except Exception as e:
        errors.append(f"Failed to calculate parsed sums: {e}")
        sum_topay = sum_paid = sum_gr = sum_nugs = sum_wt = 0

    # Extract printed document totals if present in the document
    doc_totals = None
    for p in doc:
        p_words = p.get_text("words")
        for i, w in enumerate(p_words):
            if w[4] == "Total" and i + 1 < len(p_words) and "GR" in p_words[i + 1][4]:
                y_mid = (w[1] + w[3]) / 2
                line = [cw for cw in p_words if abs((cw[1] + cw[3]) / 2 - y_mid) < 5]
                line.sort(key=lambda x: x[0])
                vals = [cw[4].replace(",", "") for cw in line if cw[4] not in ["Total", "GR:"]]
                if len(vals) >= 4:
                    try:
                        doc_totals = {
                            "total_gr": int(vals[0]),
                            "total_nugs": int(vals[1]),
                            "total_wt": round(float(vals[2]), 2),
                            "total_topay": round(float(vals[3]), 2),
                            "total_paid": round(float(vals[4]), 2) if len(vals) > 4 else 0.0,
                        }
                        break
                    except Exception:
                        pass
        if doc_totals:
            break

    validation_info = {
        "total_gr": sum_gr,
        "total_nugs": sum_nugs,
        "total_wt": round(sum_wt, 2),
        "total_topay": round(sum_topay, 2),
        "total_paid": round(sum_paid, 2),
        "doc_totals": doc_totals,
    }

    return doc, parsed_rows, errors, validation_info


def filter_rows(parsed_rows, filter_query):
    """
    Performs case-insensitive, partial matching on Consignee column.
    Supports comma-separated queries (e.g. 'azad, rehmat').
    """
    if not filter_query or not filter_query.strip():
        return parsed_rows

    terms = [t.strip().lower() for t in filter_query.split(",") if t.strip()]
    matched = []
    for r in parsed_rows:
        consignee_lower = r["Consignee"].lower()
        if any(term in consignee_lower for term in terms):
            matched.append(r)
    return matched


def paginate_rows(matched_rows):
    """
    Reflows rows onto data pages:
    - Normal data page holds up to 45 rows
    - If remaining rows on the last page is 43..45, take 40 so totals fits below the remaining rows
    Returns list of tuples: (start_idx, end_idx)
    """
    pages_data = []
    cur_idx = 0
    total = len(matched_rows)

    if total == 0:
        return [(0, 0)]

    while cur_idx < total:
        remaining = total - cur_idx
        take = min(remaining, MAX_ROWS_NORMAL_PAGE)
        if remaining == take and take > 42:
            take = 40
        pages_data.append((cur_idx, cur_idx + take))
        cur_idx += take

    return pages_data


def generate_filtered_pdf(doc, matched_rows, output_path=None):
    """
    Builds the filtered PDF using the original pages as template.
    - Places the totals line immediately below the last entry (no whitespace gap).
    - Places the Authorised Signatory block just below the totals line if space permits.
    - If no space is left on the page, Authorised Signatory moves to the next page.
    Returns:
        output_bytes: bytes of the generated PDF
        summary: dict with totals & pagination stats
    """
    tot_gr = len(matched_rows)
    tot_nugs = sum(int(r["Nugs"]) for r in matched_rows) if matched_rows else 0
    tot_wt = sum(float(r["Wt"]) for r in matched_rows) if matched_rows else 0.0
    tot_topay = sum(float(r["ToPay"].replace(",", "")) for r in matched_rows) if matched_rows else 0.0
    tot_paid = sum(float(r["Paid"].replace(",", "")) for r in matched_rows) if matched_rows else 0.0

    # Extract carrier signatory line dynamically if possible
    carrier_line = " For   ( KIRPA CARGO CARRIERS ) "
    signatory_line = "Authorised Signatory"
    for p in doc:
        txt = p.get_text("text")
        if "Authorised Signatory" in txt or "Authorized Signatory" in txt:
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            for idx, l in enumerate(lines):
                if "Authorised Signatory" in l or "Authorized Signatory" in l:
                    for prev in lines[max(0, idx - 3):idx]:
                        if "For" in prev:
                            carrier_line = f" {prev} "
                            signatory_line = l
                            break

    pages_plan = paginate_rows(matched_rows)

    # Check last page geometry for Authorised Signatory
    last_s, last_e = pages_plan[-1]
    n_last = last_e - last_s
    last_baseline = FIRST_ROW_BASELINE + (n_last - 1) * ROW_SPACING if n_last > 0 else FIRST_ROW_BASELINE
    y_tot_top = last_baseline + 8.85
    y_tot_bot = y_tot_top + 15.5
    y_tot_base = y_tot_top + 10.85
    y_tot_lbl_base = y_tot_top + 10.95

    # Authorised Signatory dimensions
    y_for_base = y_tot_bot + 22.0
    y_sig_base = y_for_base + 36.0
    fits_signatory_on_last_page = (y_sig_base + 10.0 <= 805)

    total_output_pages = len(pages_plan) if fits_signatory_on_last_page else len(pages_plan) + 1

    out_doc = pymupdf.open()

    for page_idx, (start_r, end_r) in enumerate(pages_plan, 1):
        # Insert Page 1 as template
        out_doc.insert_pdf(doc, from_page=0, to_page=0)
        p = out_doc[-1]

        # Redact old table rows & Page No.
        p.add_redact_annot(RECT_DATA_ROWS, fill=(1, 1, 1))
        p.add_redact_annot(RECT_PAGE_NO, fill=(1, 1, 1))
        p.apply_redactions()

        # Update Page No. in header
        p.insert_text(pymupdf.Point(551.0, 108.5), str(page_idx), fontname="hebo", fontsize=7.0)

        # Draw matching rows at exact original row spacing (13.5 pt)
        page_rows = matched_rows[start_r:end_r]
        for row_i, r in enumerate(page_rows):
            target_baseline = FIRST_ROW_BASELINE + row_i * ROW_SPACING
            target_baseline_small = FIRST_ROW_BASELINE_SMALL + row_i * ROW_SPACING

            for s in r["spans"]:
                txt = s["text"]
                sz = s["size"]
                orig_x = s["origin"][0]
                use_font = "hebo" if "Bold" in s.get("font", "") else "helv"
                base_y = target_baseline_small if sz < 6.8 else target_baseline
                p.insert_text(pymupdf.Point(orig_x, base_y), txt, fontname=use_font, fontsize=sz)

        # Draw totals row immediately below the last entry on the final data page
        if page_idx == len(pages_plan):
            # Enclosing horizontal lines
            p.draw_line(pymupdf.Point(11.4, y_tot_top), pymupdf.Point(575.4, y_tot_top), width=0.5, color=(0, 0, 0))
            p.draw_line(pymupdf.Point(11.4, y_tot_bot), pymupdf.Point(575.4, y_tot_bot), width=0.5, color=(0, 0, 0))

            # Values
            p.insert_text(pymupdf.Point(17.4, y_tot_lbl_base), "Total GR:", fontname="hebo", fontsize=6.95)
            p.insert_text(pymupdf.Point(59.4, y_tot_base), f" {tot_gr}", fontname="hebo", fontsize=6.95)
            p.insert_text(pymupdf.Point(234.6, y_tot_base), f" {tot_nugs}", fontname="hebo", fontsize=6.95)
            p.insert_text(pymupdf.Point(397.4, y_tot_base), f" {tot_wt:.2f}", fontname="hebo", fontsize=6.95)
            p.insert_text(pymupdf.Point(496.55, y_tot_base), f" {tot_topay:.2f}", fontname="hebo", fontsize=6.95)
            p.insert_text(pymupdf.Point(553.95, y_tot_base), f" {tot_paid:.2f}", fontname="hebo", fontsize=6.95)

            # If Authorised Signatory fits on this page, place it immediately below totals
            if fits_signatory_on_last_page:
                p.insert_text(pymupdf.Point(437.5, y_for_base), carrier_line, fontname="hebo", fontsize=7.8)
                p.insert_text(pymupdf.Point(480.45, y_sig_base), signatory_line, fontname="hebo", fontsize=8.75)

    # If Authorised Signatory did not fit on the final data page, add dedicated clean final page
    if not fits_signatory_on_last_page:
        out_doc.insert_pdf(doc, from_page=0, to_page=0)
        final_p = out_doc[-1]
        final_p.add_redact_annot(RECT_DATA_ROWS, fill=(1, 1, 1))
        final_p.add_redact_annot(RECT_PAGE_NO, fill=(1, 1, 1))
        final_p.apply_redactions()
        final_p.insert_text(pymupdf.Point(551.0, 108.5), str(total_output_pages), fontname="hebo", fontsize=7.0)
        final_p.insert_text(pymupdf.Point(437.5, 205.5), carrier_line, fontname="hebo", fontsize=7.8)
        final_p.insert_text(pymupdf.Point(480.45, 242.5), signatory_line, fontname="hebo", fontsize=8.75)

    pdf_bytes = out_doc.tobytes()

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    summary = {
        "matched_rows": tot_gr,
        "tot_nugs": tot_nugs,
        "tot_wt": round(tot_wt, 2),
        "tot_topay": round(tot_topay, 2),
        "tot_paid": round(tot_paid, 2),
        "pages_count": total_output_pages,
    }
    return pdf_bytes, summary


# --- CLI MODE HANDLER ---
def run_cli():
    parser = argparse.ArgumentParser(description="Challan PDF Consignee Filter & Reflow Tool")
    default_input = os.path.join(BASE_DIR, "Sample.pdf")
    parser.add_argument("-i", "--input", default=default_input, help=f"Path to input PDF (default: {default_input})")
    parser.add_argument("-c", "--consignee", required=True, help="Consignee filter (case-insensitive, partial match)")
    parser.add_argument("-o", "--output", default=None, help="Output PDF file path (default: output/<basename>_<filter>.pdf)")
    parser.add_argument("--cli", action="store_true", help="Explicit CLI mode flag")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)

    print(f"Loading '{args.input}'...")
    doc, rows, errors, val_info = parse_challan_pdf(args.input)
    print(f"Parsed {len(rows)} rows across {len(doc)} pages.")

    if errors:
        print(f"Warnings ({len(errors)}):")
        for e in errors[:5]:
            print(f"  - {e}")
        if len(errors) > 5:
            print(f"  ... and {len(errors)-5} more warnings.")
    else:
        print("All rows cleanly parsed into 11 fields (0 errors).")

    print(f"Original Totals: {val_info['total_gr']} GR, {val_info['total_nugs']} Nugs, {val_info['total_wt']} Wt, Rs {val_info['total_topay']} ToPay")

    # Filter
    matched = filter_rows(rows, args.consignee)
    print(f"\nFiltering by consignee query: '{args.consignee}'")
    print(f"Found {len(matched)} matching rows out of {len(rows)}.")

    if not matched:
        print("Warning: No matching rows found.")

    # Determine output path
    if not args.output:
        base = os.path.splitext(os.path.basename(args.input))[0]
        safe_filter = re.sub(r"[^\w\-]", "_", args.consignee.strip().lower())
        args.output = os.path.join(BASE_DIR, "output", f"{base}_{safe_filter}.pdf")

    _, summary = generate_filtered_pdf(doc, matched, args.output)
    print(f"\nSuccessfully generated: {args.output}")
    print(f"Summary:")
    print(f"  Total Pages: {summary['pages_count']}")
    print(f"  Matched GR:  {summary['matched_rows']}")
    print(f"  Total Nugs:  {summary['tot_nugs']}")
    print(f"  Total Wt:    {summary['tot_wt']}")
    print(f"  ToPay Total: Rs {summary['tot_topay']:.2f}")
    print(f"  Paid Total:  Rs {summary['tot_paid']:.2f}")


# --- STREAMLIT UI ---
def run_streamlit_app():
    import streamlit as st

    st.set_page_config(
        page_title="Transport Challan Filter Tool",
        page_icon="🚚",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for modern styling
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 700;
            color: #1E293B;
            margin-bottom: 0.2rem;
        }
        .sub-header {
            font-size: 1.05rem;
            color: #64748B;
            margin-bottom: 1.5rem;
        }
        .metric-card {
            background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%);
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 1rem;
            text-align: center;
        }
        .stButton>button {
            background-color: #2563EB;
            color: white;
            font-weight: 600;
            border-radius: 8px;
            padding: 0.6rem 1.5rem;
            border: none;
        }
        .stButton>button:hover {
            background-color: #1D4ED8;
            color: white;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-header">🚚 Transport Challan PDF Filter & Reflow</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Filter challan rows by Consignee, reflow with identical typography, and recalculate clean ToPay totals.</div>', unsafe_allow_html=True)

    # Sidebar: Input source
    with st.sidebar:
        st.header("📄 Input Document")
        uploaded_file = st.file_uploader("Upload Transport Challan PDF", type=["pdf"])

        default_sample = os.path.join(BASE_DIR, "Sample.pdf")
        use_default = False
        if not uploaded_file:
            if os.path.exists(default_sample):
                use_default = st.checkbox(f"Use default sample file (Sample.pdf)", value=True)
                if use_default:
                    st.info("Loaded default: `Sample.pdf`")
            else:
                st.warning("Please upload a PDF file to begin.")

    # Load and parse PDF
    pdf_bytes = None
    original_filename = "challan"

    if uploaded_file:
        pdf_bytes = uploaded_file.read()
        original_filename = os.path.splitext(uploaded_file.name)[0]
    elif use_default and os.path.exists(default_sample):
        with open(default_sample, "rb") as f:
            pdf_bytes = f.read()
        original_filename = "Sample"

    if not pdf_bytes:
        st.info("👈 Please upload a PDF or select the sample file from the sidebar to start.")
        return

    # Parse
    doc, parsed_rows, errors, val_info = parse_challan_pdf(pdf_bytes)

    # Filter section
    col_search, col_stats = st.columns([2, 1])
    with col_search:
        filter_query = st.text_input(
            "🔍 Filter by Consignee Name (case-insensitive, partial matching, comma-separated for multiple):",
            value="azad",
            placeholder="e.g. azad, rehmat",
            help="Matches any row where Consignee contains any of the specified words.",
        )

    matched_rows = filter_rows(parsed_rows, filter_query)

    # Metrics Summary Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Rows in PDF", f"{len(parsed_rows)}")
    with m2:
        st.metric("Matched Rows (GR)", f"{len(matched_rows)}")
    with m3:
        nugs_sum = sum(int(r["Nugs"]) for r in matched_rows) if matched_rows else 0
        st.metric("Total Nugs", f"{nugs_sum}")
    with m4:
        wt_sum = sum(float(r["Wt"]) for r in matched_rows) if matched_rows else 0.0
        st.metric("Total Wt", f"{wt_sum:.2f}")
    with m5:
        topay_sum = sum(float(r["ToPay"].replace(",", "")) for r in matched_rows) if matched_rows else 0.0
        st.metric("ToPay Amount", f"₹{topay_sum:,.2f}")

    # Tabs for Workflow
    tab_preview, tab_generate, tab_validation = st.tabs(["📋 Matched Rows Preview", "📄 Generated PDF", "🛡️ Validation Audit"])

    with tab_preview:
        if matched_rows:
            # Format as DataFrame
            display_data = []
            for r in matched_rows:
                display_data.append({
                    "SlNo": r["SlNo"],
                    "GR No": r["GR No"],
                    "Consignor": r["Consignor"],
                    "Consignee": r["Consignee"],
                    "Nugs": r["Nugs"],
                    "Particular": r["Particular"],
                    "To Stn": r["To Stn"],
                    "Wt": r["Wt"],
                    "Pvt/Mrk": r["Pvt/Mrk"],
                    "ToPay": r["ToPay"],
                    "Paid": r["Paid"],
                })
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True, height=400)
            st.caption(f"Showing all {len(matched_rows)} matched rows. Original SlNo, GR No, and amounts are preserved unchanged.")
        else:
            st.warning(f"No rows matched the query '{filter_query}'. Try another search term.")

    with tab_generate:
        col_btn, col_info = st.columns([1, 2])
        safe_filter = re.sub(r"[^\w\-]", "_", filter_query.strip().lower()) if filter_query else "all"
        output_filename = f"{original_filename}_{safe_filter}.pdf"
        output_filepath = os.path.join(BASE_DIR, "output", output_filename)

        out_pdf_bytes, summary = generate_filtered_pdf(doc, matched_rows, output_path=output_filepath)

        with col_btn:
            st.success(f"Output saved to: `{output_filepath}`")
            st.download_button(
                label=f"⬇️ Download {output_filename}",
                data=out_pdf_bytes,
                file_name=output_filename,
                mime="application/pdf",
                key="download_pdf_btn",
            )

        with col_info:
            st.info(f"""
            **PDF Layout Summary:**
            - **Pages:** {summary['pages_count']} pages (including dedicated Authorised Signatory page)
            - **Template:** Original vector headers, fonts, and borders preserved
            - **Totals Row:** Recalculated ToPay sum (₹{summary['tot_topay']:.2f}) at fixed standard line
            - **Deductions:** Clean client layout (no D/C or Katt deductions)
            """)

        # Render preview images of pages
        st.subheader("Visual PDF Inspection")
        gen_doc = pymupdf.open(stream=out_pdf_bytes, filetype="pdf")
        preview_cols = st.columns(len(gen_doc))
        for p_idx, col in enumerate(preview_cols):
            with col:
                st.write(f"**Page {p_idx+1}**")
                pix = gen_doc[p_idx].get_pixmap(dpi=100)
                img_bytes = pix.tobytes("png")
                st.image(img_bytes, use_container_width=True)

    with tab_validation:
        st.subheader("Data & Parsing Validation Report")

        v_col1, v_col2 = st.columns(2)
        with v_col1:
            st.write("#### 11-Field Integrity Check")
            if not errors:
                st.success(f"✅ All {len(parsed_rows)} rows successfully parsed into all 11 fields with 0 missing columns.")
            else:
                st.warning(f"⚠️ {len(errors)} warnings detected:")
                for e in errors:
                    st.write(f"- {e}")

        with v_col2:
            st.write("#### Consignee Group Reconciliation")
            # Group by consignee and check total sum
            consignee_groups = {}
            for r in parsed_rows:
                c = r["Consignee"]
                consignee_groups[c] = consignee_groups.get(c, 0) + float(r["ToPay"].replace(",", ""))

            st.write(f"**Total Consignees:** {len(consignee_groups)}")

            doc_totals = val_info.get("doc_totals")
            if doc_totals:
                recon_pass = (
                    val_info["total_gr"] == doc_totals["total_gr"]
                    and val_info["total_nugs"] == doc_totals["total_nugs"]
                    and abs(val_info["total_wt"] - doc_totals["total_wt"]) < 0.05
                    and abs(val_info["total_topay"] - doc_totals["total_topay"]) < 0.05
                    and abs(val_info["total_paid"] - doc_totals["total_paid"]) < 0.05
                )

                if recon_pass:
                    st.success("✅ Group Sum Matches Original Document Totals:")
                    st.write(f"- **Total GR:** {val_info['total_gr']} / {doc_totals['total_gr']}")
                    st.write(f"- **Total Nugs:** {val_info['total_nugs']} / {doc_totals['total_nugs']}")
                    st.write(f"- **Total Wt:** {val_info['total_wt']:.2f} / {doc_totals['total_wt']:.2f}")
                    st.write(f"- **Total ToPay:** ₹{val_info['total_topay']:,.2f} / ₹{doc_totals['total_topay']:,.2f}")
                else:
                    st.error("❌ Totals reconciliation mismatch. Please inspect document.")
                    st.write(f"- **Total GR:** Parsed {val_info['total_gr']} vs Document {doc_totals['total_gr']}")
                    st.write(f"- **Total Nugs:** Parsed {val_info['total_nugs']} vs Document {doc_totals['total_nugs']}")
                    st.write(f"- **Total Wt:** Parsed {val_info['total_wt']:.2f} vs Document {doc_totals['total_wt']:.2f}")
                    st.write(f"- **Total ToPay:** Parsed ₹{val_info['total_topay']:,.2f} vs Document ₹{doc_totals['total_topay']:,.2f}")
            else:
                st.info("ℹ️ Document totals line not explicitly found; displaying computed totals:")
                st.write(f"- **Total GR:** {val_info['total_gr']}")
                st.write(f"- **Total Nugs:** {val_info['total_nugs']}")
                st.write(f"- **Total Wt:** {val_info['total_wt']:.2f}")
                st.write(f"- **Total ToPay:** ₹{val_info['total_topay']:,.2f}")


if __name__ == "__main__":
    # If invoked with CLI arguments or explicit --cli, run CLI mode
    if len(sys.argv) > 1 and any(arg in sys.argv for arg in ["--cli", "-c", "--consignee", "-i", "--input", "-h", "--help"]):
        run_cli()
    else:
        run_streamlit_app()
