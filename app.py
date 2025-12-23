import streamlit as st
import pdfplumber
import docx
import re
import io

import spacy
from transformers import pipeline

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="JD Generator", layout="wide")

nlp = spacy.blank("en")

# Register Arial font (ensure Arial.ttf is in repo root)
pdfmetrics.registerFont(TTFont("Arial", "Arial.ttf"))

# =====================================================
# LOAD HUGGINGFACE MODEL (CACHED)
# =====================================================
@st.cache_resource
def load_ner_model():
    return pipeline(
        "ner",
        model="dslim/bert-base-NER",
        aggregation_strategy="simple"
    )

ner_pipeline = load_ner_model()

# =====================================================
# TEMPLATE DEFINITION
# =====================================================
TEMPLATE_FIELDS = [
    "Company Name",
    "Official Website",
    "Preferred Education",
    "Desired Experience",
    "Designation",
    "Stipend/month (part-time)",
    "Stipend/month",
    "Internship Duration",
    "Roles & Responsibilities",
    "Skills",
    "Joining Location",
    "Joining Month",
    "No. of openings",
    "Selection Process"
]

FIELD_KEYS = {
    "Company Name": "company_name",
    "Official Website": "official_website",
    "Preferred Education": "preferred_education",
    "Desired Experience": "desired_experience",
    "Designation": "designation",
    "Stipend/month (part-time)": "stipend_part_time",
    "Stipend/month": "stipend",
    "Internship Duration": "internship_duration",
    "Roles & Responsibilities": "roles_responsibilities",
    "Skills": "skills",
    "Joining Location": "joining_location",
    "Joining Month": "joining_month",
    "No. of openings": "openings",
    "Selection Process": "selection_process"
}

# =====================================================
# FILE TEXT EXTRACTION
# =====================================================
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

# =====================================================
# IMPROVED EXTRACTION (TRANSFORMER + REGEX)
# =====================================================
def extract_structured_jd(text):
    data = {v: "" for v in FIELD_KEYS.values()}

    # -------------------------
    # Transformer NER
    # -------------------------
    ner_results = ner_pipeline(text)

    orgs, locs = [], []

    for ent in ner_results:
        if ent["entity_group"] == "ORG":
            orgs.append(ent["word"])
        elif ent["entity_group"] == "LOC":
            locs.append(ent["word"])

    if orgs:
        data["company_name"] = orgs[0]

    if locs:
        data["joining_location"] = locs[0]

    # -------------------------
    # Designation (Hybrid)
    # -------------------------
    designation_keywords = [
        "intern", "engineer", "developer", "manager", "analyst",
        "consultant", "designer", "architect", "scientist",
        "associate", "executive", "lead", "head"
    ]

    for line in text.splitlines():
        if any(k in line.lower() for k in designation_keywords):
            data["designation"] = line.strip()
            break

    # -------------------------
    # Website
    # -------------------------
    website = re.search(r"(https?://[^\s]+|www\.[^\s]+)", text)
    if website:
        data["official_website"] = website.group(0)

    # -------------------------
    # Stipend
    # -------------------------
    stipend = re.search(
        r"(₹|\$)?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?(?:-|to|–)\s?(₹|\$)?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?(?:per month|pm|monthly|/month|/mo)?",
        text,
        re.I
    )
    if stipend:
        data["stipend"] = stipend.group(0)

    # -------------------------
    # Duration
    # -------------------------
    duration = re.search(
        r"\b\d+\s?(?:months?|weeks?|days?)\b",
        text,
        re.I
    )
    if duration:
        data["internship_duration"] = duration.group(0)

    # -------------------------
    # Openings
    # -------------------------
    openings = re.search(
        r"\b(\d+)\s+(openings?|positions?|vacancies?)\b",
        text,
        re.I
    )
    if openings:
        data["openings"] = openings.group(1)

    # -------------------------
    # Education
    # -------------------------
    education = re.search(
        r"(B\.?\s?Tech|M\.?\s?Tech|Bachelor|Master|MBA|Ph\.?D|Degree|Diploma)",
        text,
        re.I
    )
    if education:
        data["preferred_education"] = education.group(0)

    # -------------------------
    # Experience
    # -------------------------
    experience = re.search(
        r"\b\d+\+?\s+years?\s+experience\b",
        text,
        re.I
    )
    if experience:
        data["desired_experience"] = experience.group(0)

    # -------------------------
    # Section Extraction
    # -------------------------
    def extract_section(headers):
        pattern = r"(?i)(?:{})\s*[:\-]?\s*(.*?)(?=\n[A-Z][^\n]{0,40}:|\Z)".format(
            "|".join(headers)
        )
        match = re.search(pattern, text, re.S)
        return match.group(1).strip() if match else ""

    data["roles_responsibilities"] = extract_section(
        ["Roles", "Responsibilities", "What you will do", "Job Description"]
    )

    data["skills"] = extract_section(
        ["Skills", "Requirements", "Qualifications", "Technical Skills", "Must Have"]
    )

    data["selection_process"] = extract_section(
        ["Selection Process", "Interview Process", "Hiring Process"]
    )

    return data

# =====================================================
# PDF GENERATION (WRAPPED TEXT)
# =====================================================
def generate_template_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    style_left = ParagraphStyle(
        name="Left",
        fontName="Arial",
        fontSize=8,
        textColor=colors.white
    )

    style_right = ParagraphStyle(
        name="Right",
        fontName="Arial",
        fontSize=8,
        textColor=colors.black
    )

    table_data = []

    for label in TEMPLATE_FIELDS:
        key = FIELD_KEYS[label]
        table_data.append([
            Paragraph(label, style_left),
            Paragraph(data.get(key, "").replace("\n", "<br/>"), style_right)
        ])

    table = Table(table_data, colWidths=[170, 330])

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#a3a3a3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2e74b5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    doc.build([table])
    buffer.seek(0)
    return buffer

# =====================================================
# STREAMLIT UI
# =====================================================
st.title("JD Generator")

uploaded_file = st.file_uploader(
    "Upload Job Description (TXT, PDF, DOCX)",
    type=["txt", "pdf", "docx"]
)

raw_text = ""

if uploaded_file:
    if uploaded_file.type == "text/plain":
        raw_text = uploaded_file.read().decode("utf-8")
    elif uploaded_file.type == "application/pdf":
        raw_text = extract_text_from_pdf(uploaded_file)
    elif uploaded_file.type.endswith("wordprocessingml.document"):
        raw_text = extract_text_from_docx(uploaded_file)

    st.subheader("Extracted Raw Text")
    st.text_area("", raw_text, height=250)

    if st.button("Extract to Template"):
        with st.spinner("Extracting using AI model..."):
            st.session_state["jd_data"] = extract_structured_jd(raw_text)

if "jd_data" in st.session_state:
    st.subheader("Editable Standard Template")

    edited_data = {}

    for label in TEMPLATE_FIELDS:
        key = FIELD_KEYS[label]
        if label in ["Roles & Responsibilities", "Skills", "Selection Process"]:
            edited_data[key] = st.text_area(
                label,
                st.session_state["jd_data"].get(key, ""),
                height=120
            )
        else:
            edited_data[key] = st.text_input(
                label,
                st.session_state["jd_data"].get(key, "")
            )

    pdf_file = generate_template_pdf(edited_data)

    company_name = edited_data.get("company_name", "Company").replace(" ", "_")
    designation = edited_data.get("designation", "Designation").replace(" ", "_")
    pdf_filename = f"{company_name}-{designation}.pdf"

    st.download_button(
        "Download Completed Template (PDF)",
        pdf_file,
        pdf_filename,
        "application/pdf"
    )
