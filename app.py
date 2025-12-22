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
# CONFIG & MODEL LOADING
# =====================================================
st.set_page_config(page_title="JD Auto Extractor Pro", layout="wide")

@st.cache_resource
def load_nlp():
    try:
        # Try to load the small English model for better NER
        return spacy.load("en_core_web_sm")
    except:
        # Fallback to blank if not installed
        return spacy.blank("en")

nlp = load_nlp()

# Register Font - Fallback to Helvetica if Arial is missing
try:
    pdfmetrics.registerFont(TTFont("Arial", "Arial.ttf"))
    FONT_NAME = "Arial"
except:
    FONT_NAME = "Helvetica"

# =====================================================
# CONSTANTS
# =====================================================
TEMPLATE_FIELDS = [
    "Company Name", "Official Website", "Preferred Education",
    "Desired Experience", "Designation", "Stipend/month",
    "Internship Duration", "Roles & Responsibilities", "Skills",
    "Joining Location", "No. of openings", "Selection Process"
]

FIELD_KEYS = {label: label.lower().replace(" ", "_").replace("/", "_").replace("&_", "") for label in TEMPLATE_FIELDS}

# Common skills for the PhraseMatcher to "catch" specifically
SKILL_DB = [
    "Python", "Java", "C++", "JavaScript", "React", "Angular", "Node.js", 
    "SQL", "NoSQL", "AWS", "Azure", "Docker", "Kubernetes", "Machine Learning",
    "Data Analysis", "Project Management", "Agile", "Excel", "Communication"
]

# =====================================================
# EXTRACTION LOGIC
# =====================================================

def clean_text(text):
    """Fixes spacing and removes redundant newlines."""
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def extract_skills(doc, text):
    """Hybrid approach: Regex sections + Phrase Matching + NER."""
    # 1. Regex Section Extraction
    skill_patterns = [
        r"(?i)(?:Skills|Requirements|Key Skills|What you need|Technical Stack)[:\-\n]+(.*?)(?=\n\n|\n[A-Z]{3,}|\Z)",
    ]
    extracted_text = ""
    for p in skill_patterns:
        match = re.search(p, text, re.S)
        if match:
            extracted_text = match.group(1).strip()
            break

    # 2. Phrase Matching (catching specific keywords)
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(text) for text in SKILL_DB]
    matcher.add("SKILL_LIST", patterns)
    
    matches = matcher(doc)
    found_entities = set([doc[start:end].text for _, start, end in matches])
    
    # 3. Add Entities (catching things like 'Oracle' or 'Google Cloud' via NER)
    for ent in doc.ents:
        if ent.label_ in ["ORG", "PRODUCT"] and len(ent.text) < 20:
            found_entities.add(ent.text)

    # Combine
    if extracted_text:
        return extracted_text
    return ", ".join(list(found_entities)) if found_entities else "Not found"

def extract_structured_jd(text):
    text = clean_text(text)
    doc = nlp(text)
    data = {v: "" for v in FIELD_KEYS.values()}

    # Website
    web = re.search(r"(https?://[^\s,]+)", text)
    data["official_website"] = web.group(1) if web else ""

    # Stipend
    stipend = re.search(r"(?:Rs\.?|INR|₹|\$)\s?\d{3,6}(?:\s?-\s?(?:Rs\.?|INR|₹|\$)?\s?\d{3,6})?", text)
    data["stipend_month"] = stipend.group(0) if stipend else ""

    # Duration
    dur = re.search(r"\d+\s?(?:months|month|weeks|week)", text, re.I)
    data["internship_duration"] = dur.group(0) if dur else ""

    # Designation
    for line in text.splitlines()[:10]: # Check first 10 lines
        if any(kw in line.lower() for kw in ["intern", "engineer", "developer", "manager", "analyst"]):
            data["designation"] = line.strip()
            break

    # Location
    locs = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    data["joining_location"] = locs[0] if locs else ""

    # Skills (The Improved Function)
    data["skills"] = extract_skills(doc, text)

    # Roles & Responsibilities
    roles = re.search(r"(?i)(?:Responsibilities|Roles|What you will do)[:\-\n]+(.*?)(?=\n\n|\n[A-Z]{3,}|\Z)", text, re.S)
    data["roles_responsibilities"] = roles.group(1).strip() if roles else ""

    return data

# =====================================================
# PDF GENERATION
# =====================================================
def generate_template_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    style_left = ParagraphStyle('Left', fontName=FONT_NAME, fontSize=9, textColor=colors.white)
    style_right = ParagraphStyle('Right', fontName=FONT_NAME, fontSize=9, textColor=colors.black, leading=12)

    table_data = []
    for label in TEMPLATE_FIELDS:
        key = FIELD_KEYS[label]
        val = str(data.get(key, "")).replace("\n", "<br/>")
        table_data.append([Paragraph(label, style_left), Paragraph(val, style_right)])

    table = Table(table_data, colWidths=[150, 350])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#2e74b5")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))

    doc.build([table])
    buffer.seek(0)
    return buffer

# =====================================================
# MAIN APP
# =====================================================
def main():
    st.title("📄 JD Template Auto-Extractor")
    st.markdown("Upload a Job Description and this tool will attempt to format it into your standard template.")

    uploaded_file = st.file_uploader("Upload JD (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
    
    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            with pdfplumber.open(uploaded_file) as pdf:
                raw_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif uploaded_file.type.endswith("wordprocessingml.document"):
            raw_text = "\n".join([p.text for p in docx.Document(uploaded_file).paragraphs])
        else:
            raw_text = uploaded_file.read().decode("utf-8")

        if st.button("✨ Extract Data"):
            st.session_state["jd_data"] = extract_structured_jd(raw_text)

    if "jd_data" in st.session_state:
        st.divider()
        col1, col2 = st.columns([1, 1])
        
        edited_data = {}
        with col1:
            st.subheader("Edit Extracted Information")
            for label in TEMPLATE_FIELDS:
                key = FIELD_KEYS[label]
                if len(st.session_state["jd_data"].get(key, "")) > 50:
                    edited_data[key] = st.text_area(label, st.session_state["jd_data"].get(key, ""), height=150)
                else:
                    edited_data[key] = st.text_input(label, st.session_state["jd_data"].get(key, ""))

        with col2:
            st.subheader("Preview & Export")
            pdf_out = generate_template_pdf(edited_data)
            st.download_button("📥 Download PDF Template", pdf_out, "JD_Standard.pdf", "application/pdf")
            st.info("Review the fields on the left before downloading. Some complex JDs may require manual cleanup.")

if __name__ == "__main__":
    main()
