import streamlit as st
import pdfplumber
import docx
import re
import io

import spacy
from spacy.matcher import Matcher, PhraseMatcher

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="JD Auto Extractor (spaCy)", layout="wide")

nlp = spacy.blank("en")

# Register Arial font (ensure arial.ttf is available in your system)
pdfmetrics.registerFont(TTFont("Arial", "arial.ttf"))

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
# RULE-BASED NLP EXTRACTION
# =====================================================
def extract_structured_jd(text):
    data = {v: "" for v in FIELD_KEYS.values()}
    doc = nlp(text)

    # -------------------------
    # WEBSITE
    # -------------------------
    website = re.search(r"(https?://\S+)", text)
    if website:
        data["official_website"] = website.group(1)

    # -------------------------
    # STIPEND / SALARY
    # -------------------------
    stipend = re.search(r"(₹|\$)?\s?\d{3,6}\s?[-to]+\s?(₹|\$)?\s?\d{3,6}", text)
    if stipend:
        data["stipend"] = stipend.group(0)

    # -------------------------
    # DURATION
    # -------------------------
    duration = re.search(r"\d+\s?(months|month|weeks|week)", text, re.I)
    if duration:
        data["internship_duration"] = duration.group(0)

    # -------------------------
    # OPENINGS
    # -------------------------
    openings = re.search(r"(\d+)\s+(openings|positions|vacancies)", text, re.I)
    if openings:
        data["openings"] = openings.group(1)

    # -------------------------
    # LOCATION (spaCy NER)
    # -------------------------
    locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    if locations:
        data["joining_location"] = locations[0]

    # -------------------------
    # DESIGNATION (Heuristic)
    # -------------------------
    for line in text.splitlines():
        match = re.search(r"(intern|engineer|developer|manager|analyst|consultant)", line, re.I)
        if match:
            designation = re.sub(r"(?i)Designation\s*[:\-]?\s*", "", line).strip()
            data["designation"] = designation
            break

    # -------------------------
    # EDUCATION / EXPERIENCE
    # -------------------------
    education = re.search(r"(B\.?Tech|M\.?Tech|Bachelor|Master|Degree)", text, re.I)
    if education:
        data["preferred_education"] = education.group(0)

    experience = re.search(r"\d+\+?\s+years?\s+experience", text, re.I)
    if experience:
        data["desired_experience"] = experience.group(0)

    # -------------------------
    # SECTION EXTRACTION
    # -------------------------
    def extract_section(header_keywords):
        pattern = r"(?i)(" + "|".join(header_keywords) + r")\s*[:\-]?\s*(.*?)(?=\n[A-Z][^\n]{0,40}:|\Z)"
        match = re.search(pattern, text, re.S)
        return match.group(2).strip() if match else ""

    data["roles_responsibilities"] = extract_section(
        ["Roles", "Responsibilities", "What you will do"]
    )

    data["skills"] = extract_section(
        ["Skills", "Requirements", "Qualifications"]
    )

    data["selection_process"] = extract_section(
        ["Selection Process", "Interview Process", "Hiring Process"]
    )

    return data

# =====================================================
# PDF GENERATION WITH WRAPPING
# =====================================================
def generate_template_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=30)

    # Paragraph style with Arial, size 8
    style_left = ParagraphStyle(
        name='LeftCol',
        fontName='Arial',
        fontSize=8,
        textColor=colors.white,
        backColor=colors.HexColor("#2e74b5"),
        leftIndent=0,
        rightIndent=0,
        spaceAfter=2,
        spaceBefore=2
    )

    style_right = ParagraphStyle(
        name='RightCol',
        fontName='Arial',
        fontSize=8,
        textColor=colors.black,
        backColor=colors.white,
        leftIndent=0,
        rightIndent=0,
        spaceAfter=2,
        spaceBefore=2
    )

    table_data = []

    for label in TEMPLATE_FIELDS:
        key = FIELD_KEYS[label]
        table_data.append([
            Paragraph(label, style_left),
            Paragraph(data.get(key, "").replace("\n", "<br/>"), style_right)
        ])

    table = Table(table_data, colWidths=[170, 330], repeatRows=0)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#a3a3a3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
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
st.title("JD Auto-Extraction Tool (spaCy – Open Source)")

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
        with st.spinner("Extracting using NLP rules..."):
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

    st.download_button(
        "Download Completed Template (PDF)",
        pdf_file,
        "Standard_JD_Template.pdf",
        "application/pdf"
    )
