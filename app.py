import streamlit as st
import pdfplumber
import docx
import re
import io

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

# Font (safe fallback)
try:
    pdfmetrics.registerFont(TTFont("Arial", "Arial.ttf"))
    FONT = "Arial"
except:
    FONT = "Helvetica"

# =====================================================
# LOAD LOCAL LLM (SECTION EXTRACTION ONLY)
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
# RULE-BASED EXTRACTION (DETERMINISTIC)
# =====================================================
def extract_with_rules(text):
    data = {v: "" for v in FIELD_KEYS.values()}

    # Website
    m = re.search(r"https?://\S+", text)
    if m:
        data["official_website"] = m.group(0)

    # Designation
    for line in text.splitlines():
        if re.search(r"(intern|engineer|developer|manager|analyst)", line, re.I):
            data["designation"] = line.strip()
            break

    # Internship duration
    m = re.search(r"\d+\s*(months?|weeks?)", text, re.I)
    if m:
        data["internship_duration"] = m.group(0)

    # Openings
    m = re.search(r"(\d+)\s+(openings|positions|vacancies)", text, re.I)
    if m:
        data["openings"] = m.group(1)

    # Stipend / salary
    m = re.search(r"(₹|\$)\s?\d+[,\d]*", text)
    if m:
        data["stipend"] = m.group(0)

    # Education
    m = re.search(r"(B\.?Tech|M\.?Tech|Bachelor|Master|Degree)", text, re.I)
    if m:
        data["preferred_education"] = m.group(0)

    # Experience
    m = re.search(r"\d+\+?\s+years?\s+experience", text, re.I)
    if m:
        data["desired_experience"] = m.group(0)

    # Location (simple heuristic)
    for line in text.splitlines():
        if "location" in line.lower():
            data["joining_location"] = line.split(":")[-1].strip()
            break

    return data


# =====================================================
# LLM SECTION EXTRACTION (NO JSON)
# =====================================================
def extract_section_llm(text, section_name):
    prompt = f"""
Extract ONLY the {section_name} from the job description.
Return plain text only. No explanation.

Job Description:
{text}
"""
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
    outputs = llm_model.generate(**inputs, max_new_tokens=256)
    return tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


def extract_sections_with_llm(text):
    return {
        "roles_responsibilities": extract_section_llm(text, "Roles & Responsibilities"),
        "skills": extract_section_llm(text, "Skills / Requirements"),
        "selection_process": extract_section_llm(text, "Selection Process"),
    }


# =====================================================
# HYBRID EXTRACTION (FINAL)
# =====================================================
def extract_structured_jd(text):
    data = extract_with_rules(text)
    llm_sections = extract_sections_with_llm(text)
    data.update(llm_sections)
    return data


# =====================================================
# PDF GENERATION
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
        fontName=FONT,
        fontSize=8,
        textColor=colors.white
    )

    style_right = ParagraphStyle(
        name="Right",
        fontName=FONT,
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
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2e74b5")),
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
st.title("JD Generator (Hybrid AI + Rules)")

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
        with st.spinner("Extracting job information..."):
            st.session_state["jd_data"] = extract_structured_jd(raw_text)


# =====================================================
# EDITABLE TEMPLATE
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

    company = edited_data.get("company_name", "Company").replace(" ", "_")
    role = edited_data.get("designation", "Role").replace(" ", "_")

    st.download_button(
        "Download Completed JD (PDF)",
        pdf_file,
        f"{company}-{role}.pdf",
        "application/pdf"
    )
