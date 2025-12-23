import streamlit as st
import pdfplumber
import docx
import re
import io
import json

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

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

# Register font (place Arial.ttf in repo root)
pdfmetrics.registerFont(TTFont("Arial", "Arial.ttf"))

# =====================================================
# LOAD SMALL LOCAL LLM (NO API)
# =====================================================
@st.cache_resource
def load_llm():
    tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-base")
    model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-base")
    return tokenizer, model

tokenizer, llm_model = load_llm()

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
# LLM-BASED JD UNDERSTANDING
# =====================================================
def extract_structured_jd_llm(text):
    prompt = f"""
You are an HR assistant.

Extract the following fields from the job description.
If a field is missing, return an empty string.

Return ONLY valid JSON with these keys:
company_name
official_website
preferred_education
desired_experience
designation
stipend
stipend_part_time
internship_duration
roles_responsibilities
skills
joining_location
joining_month
openings
selection_process

Job Description:
{text}
"""

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=2048
    )

    outputs = llm_model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.0
    )

    decoded = tokenizer.decode(outputs[0], skip_special_tokens=True)

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        parsed = {v: "" for v in FIELD_KEYS.values()}

    # Ensure all keys exist
    for key in FIELD_KEYS.values():
        parsed.setdefault(key, "")

    return parsed

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
        name="LeftCol",
        fontName="Arial",
        fontSize=8,
        textColor=colors.white
    )

    style_right = ParagraphStyle(
        name="RightCol",
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
st.title("JD Generator (AI-powered)")

uploaded_file = st.file_uploader(
    "Upload Job Description (PDF, DOCX, TXT)",
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

    if st.button("Extract & Fill Template"):
        with st.spinner("Understanding job description using AI..."):
            st.session_state["jd_data"] = extract_structured_jd_llm(raw_text)

# =====================================================
# EDITABLE TEMPLATE (NO RAW TEXT SHOWN)
# =====================================================
if "jd_data" in st.session_state:
    st.subheader("Review & Edit Extracted Information")

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
        "Download Completed JD (PDF)",
        pdf_file,
        pdf_filename,
        "application/pdf"
    )
