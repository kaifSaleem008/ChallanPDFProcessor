# 🚚 Transport Challan PDF Filter & Reflow Tool

A Python tool (**Streamlit Web UI + Command Line Interface**) designed to filter multi-page transport challan PDFs (such as *Kirpa Cargo Carriers*) by **Consignee name**, reflow matching rows upward using the original row spacing and pagination, and recalculate a clean **ToPay totals row** for the client.

The original input PDF is **never modified**.

---

## 🌟 Key Features

1. **Pixel-Identical Template Preservation**:
   - Uses the original PDF pages as vector templates, guaranteeing that company logos, header information, typography, lines, and layout remain identical to the source.
2. **Coordinate-Based 11-Field Extraction**:
   - Uses PyMuPDF (`page.get_text("words")`) bounded by exact geometric column boundaries rather than regex on flat text.
   - Robust against variable word counts in Consignor and Consignee names.
3. **Smart Partial Filtering**:
   - Case-insensitive, partial matching on the `Consignee` column only.
   - For example, typing `azad` matches both `AZAD SAREE CENTER` and `AZAD TEXTILES`.
   - Supports multiple search terms separated by commas (e.g. `azad, rehmat`).
4. **Preserves Original Row Entries**:
   - Matched rows keep their original `SlNo`, `GR No`, quantities, and amounts. No renumbering or edits to any row entries.
5. **Upward Compaction & Reflow**:
   - Removes non-matching rows and compacts matching rows upward at the original **13.5 pt** row spacing.
   - Standard data pages hold up to **45 rows**.
   - Automatically updates `Page No.` on every page in the header.
6. **No-Gap Totals Line**:
   - Recalculates `Total GR`, `Total Nugs`, `Total Wt`, `Total ToPay`, and `Total Paid`.
   - Placed **immediately below the last entry** with no whitespace gap, between matching horizontal bounding lines.
   - Omits truck-level deductions (Less D/C, Katt) so the client sees only the clean ToPay amount due.
7. **Smart Authorised Signatory Placement**:
   - Places `"For ( KIRPA CARGO CARRIERS )"` and `"Authorised Signatory"` **directly below the totals line** on the same page whenever space allows (e.g. 1-page challans for smaller batches).
   - If no space remains on that page (e.g. multi-page lists where the final page is packed), it seamlessly moves onto a dedicated next page with an updated page number.
8. **Dual Mode (Streamlit Web UI + CLI)**:
   - Interactive Streamlit dashboard with live preview, metric badges, validation report, and instant download.
   - Headless CLI for automated scripting and batch pipelines.

---

## 📂 Project Structure

```text
Surat_challan/
├── app.py              # Unified Streamlit Web UI + CLI implementation
├── requirements.txt    # Python dependencies
├── README.md           # Documentation & Usage Guide
├── Sample.pdf          # Sample transport challan (Kirpa Cargo Carriers)
└── output/             # Output folder for generated PDFs
    └── Sample_azad.pdf # Filtered PDF generated for consignee 'azad'
```

---

## 🛠️ Installation

Ensure you have Python 3.10+ installed. Install dependencies via `pip`:

```bash
pip install -r requirements.txt
```

---

## 🚀 Usage

### 1. Streamlit Web UI

Run the Streamlit application:

```bash
streamlit run app.py
```

The web interface allows you to:
- Upload any Challan PDF (or auto-load `Sample.pdf` from the workspace).
- Filter by Consignee name with real-time matching.
- Review matched rows in an interactive table.
- Verify 11-column integrity and sum reconciliation in the **Validation Audit** tab.
- Preview rendered pages and download the generated PDF `<originalname>_<filter>.pdf`.

### 2. Command Line Interface (CLI)

Run via terminal using Python:

```bash
# Filter Sample.pdf for "azad"
python app.py --cli --input Sample.pdf --consignee azad --output output/Sample_azad.pdf

# Or use short flags
python app.py -i Sample.pdf -c "azad"
```

#### CLI Options:
- `-i`, `--input`: Path to input PDF (default: `Sample.pdf`)
- `-c`, `--consignee`: Consignee search filter (required, case-insensitive, partial matching)
- `-o`, `--output`: Output PDF file path (default: `output/<basename>_<filter>.pdf`)
- `--cli`: Explicit CLI flag

---

## 🛡️ Validation & Audit Results (`Sample.pdf`)

Running validation against the bundled `Sample.pdf` verifies:

| Metric | Original Document | Matched for "azad" |
| :--- | :--- | :--- |
| **Total Rows (GR)** | **127** | **86** |
| **Total Nugs** | **134** | **91** |
| **Total Weight (Wt)** | **77.38** | **52.74** |
| **ToPay Total** | **₹84,160.00** | **₹58,710.00** |
| **Paid Total** | **₹0.00** | **₹0.00** |
| **11-Field Parsing Errors** | **0** | **0** |
| **Pages Generated** | 4 pages | 3 pages (Page 1: 45 rows, Page 2: 41 rows + totals, Page 3: Signatory) |

- **Matched Consignees for "azad"**:
  - `AZAD SAREE CENTER` (66 rows)
  - `AZAD TEXTILES` (20 rows)
  - Total: **86 rows**
