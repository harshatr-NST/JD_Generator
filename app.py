import streamlit as st
import pdfplumber
import docx
import re
import io
import spacy
from spacy.matcher import PhraseMatcher
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# =====================================================
# CONFIG & MODEL
# =====================================================
st.set_page_config(page_title="JD Pro Extractor", layout="wide")

@st.cache_resource
def load_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except:
        return spacy.blank("en")

nlp = load_nlp()

# Font handling for different environments
try:
    pdfmetrics.registerFont(TTFont("Arial", "Arial.ttf"))
    FONT_NAME = "Arial"
except:
    FONT_NAME = "Helvetica"

# =====================================================
# EXTRACTION ENGINE (REBUILT FOR ACCURACY)
# =====================================================

def get_content_block(text, keywords, next_section_keywords):
    """
    Finds a section by looking for keywords, and captures 
    until it hits a known 'next' section header.
    """
    lines = text.splitlines()
    start_idx = -1
    
    # 1. Find the starting line
    for i, line in enumerate(lines):
        if any(re.search(rf"\b{kw}\b", line, re.I) for kw in keywords):
            start_idx = i
            break
    
    if start_idx == -1: return ""

    # 2. Find the end line (look for the next major header)
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        # If line is short and contains 'next section' keywords, stop there
        if len(lines[j].strip()) < 40 and any(re.search(rf"\b{kw}\b", lines[j], re.I) for kw in next_section_keywords):
            end_idx = j
            break
            
    content = "\n".join(lines[start_idx+1 : end_idx]).strip()
    # Clean up artifacts like leading colons or dashes
    return re.sub(r'^[:\-\s•]+', '', content, flags=re.M)

def extract_structured_jd(text):
    # Dictionary of headers to help the logic know when to "stop" one section and "start" another
    headers = {
        "skills": ["Skills", "Requirements", "Qualifications", "Competencies", "Tech Stack"],
        "roles": ["Responsibilities", "Role", "What you will do", "Job Description", "Expectations"],
        "process": ["Selection Process", "Interview", "Hiring", "Hiring Workflow"],
        "edu": ["Education", "Degree", "Academic"]
    }
    
    # Flat list of all headers to use as "stop" markers
    all_headers = [item for sublist in headers.values() for item in sublist]

    doc = nlp(text)
    data = {}

    # --- Basic Fields (Regex is fine for these) ---
    web = re.search(r"(https?://[^\s,]+)", text)
    data["official_website"] = web.group(1) if web else ""
    
    stipend = re.search(r"(?:Rs\.?|INR|₹|\$)\s?\d{3,6}(?:\s?-\s?(?:Rs\.?|INR|₹|\$)?\s?\d{3,6})?", text)
    data["stipend"] = stipend.group(0) if stipend else ""

    # --- Large Block Fields (Block-Logic) ---
    data["skills"] = get_content_block(text, headers["skills"], all_headers)
    data["roles_responsibilities"] = get_content_block(text, headers["roles"], all_headers)
    data["selection_process"] = get_content_block(text, headers["process"], all_headers)
    
    # --- Heuristic Fields ---
    data["preferred_education"] = get_content_block(text, headers["edu"], all_headers)[:200] # Cap length
    
    # Extract Location via NER
    locs = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    data["joining_location"] = locs[0] if locs else ""

    # Designation: Usually in the first 5 lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    data["designation"] = lines[0] if lines else ""

    return data

# =====================================================
# PDF GENERATION
# =====================================================
def generate_template_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    
    style_label = ParagraphStyle('Label', fontName=FONT_NAME, fontSize=10, textColor=colors.white, leading=14)
    style_val = ParagraphStyle('Value', fontName=FONT_NAME, fontSize=10, textColor=colors.black, leading=14)

    # Mapping internal keys back to Display Labels
    display_map = [
        ("Designation", "designation"),
        ("Official Website", "official_website"),
        ("Preferred Education", "preferred_education"),
        ("Stipend", "stipend"),
        ("Skills", "skills"),
        ("Roles & Responsibilities", "roles_responsibilities"),
        ("Joining Location", "joining_location"),
        ("Selection Process", "selection_process")
    ]

    table_data = []
    for label, key in display_map:
        val = data.get(key, "N/A")
        if not val: val = "N/A"
        table_data.append([Paragraph(label, style_label), Paragraph(val.replace("\n", "<br/>"), style_val)])

    table = Table(table_data, colWidths=[140, 380])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#2e74b5")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))

    doc.build([table])
    buffer.seek(0)
    return buffer

# =====================================================
# UI
# =====================================================
st.title("🚀 Precision JD Extractor")

uploaded_file = st.file_uploader("Upload JD", type=["pdf", "docx", "txt"])

if uploaded_file:
    # Text Extraction
    if uploaded_file.type == "application/pdf":
        with pdfplumber.open(uploaded_file) as pdf:
            raw_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
    elif uploaded_file.type.endswith("wordprocessingml.document"):
        raw_text = "\n".join([p.text for p in docx.Document(uploaded_file).paragraphs])
    else:
        raw_text = uploaded_file.read().decode("utf-8")

    if st.button("Extract Content"):
        with st.spinner("Analyzing document structure..."):
            st.session_state["extracted"] = extract_structured_jd(raw_text)

if "extracted" in st.session_state:
    st.subheader("Verify & Edit Extracted Data")
    
    updated_data = {}
    col1, col2 = st.columns(2)
    
    # Split fields for UI
    fields = list(st.session_state["extracted"].keys())
    for i, key in enumerate(fields):
        with (col1 if i % 2 == 0 else col2):
            val = st.session_state["extracted"][key]
            if len(val) > 100:
                updated_data[key] = st.text_area(key.replace("_", " ").title(), val, height=200)
            else:
                updated_data[key] = st.text_input(key.replace("_", " ").title(), val)

    pdf_file = generate_template_pdf(updated_data)
    st.download_button("Download Standardized PDF", pdf_file, "Processed_JD.pdf", "application/pdf")
