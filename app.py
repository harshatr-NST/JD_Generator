import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

def generate_template_pdf(
    data,
    fields=None,
    field_keys=None,
    left_style=None,
    right_style=None,
    table_style=None,
    col_widths=[170, 330],
    page_size=A4,
    margins=(30, 30, 30, 30),
):
    """
    Generates a PDF template from a dictionary of data.

    Args:
        data (dict): Dictionary containing the data to be rendered in the PDF.
        fields (list, optional): List of field labels to display. Defaults to all keys in `data`.
        field_keys (dict, optional): Mapping of field labels to data keys. Defaults to identity mapping.
        left_style (ParagraphStyle, optional): Style for left column (labels).
        right_style (ParagraphStyle, optional): Style for right column (values).
        table_style (TableStyle, optional): Style for the table.
        col_widths (list, optional): Widths of the columns in the table.
        page_size (tuple, optional): Size of the PDF page. Defaults to A4.
        margins (tuple, optional): Margins of the PDF (right, left, top, bottom).

    Returns:
        io.BytesIO: Buffer containing the generated PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=margins[0],
        leftMargin=margins[1],
        topMargin=margins[2],
        bottomMargin=margins[3],
    )

    # Default styles
    if left_style is None:
        left_style = ParagraphStyle(
            name="LeftCol",
            fontName="Arial",
            fontSize=8,
            textColor=colors.white,
            leftIndent=0,
            rightIndent=0,
            spaceAfter=2,
            spaceBefore=2,
        )

    if right_style is None:
        right_style = ParagraphStyle(
            name="RightCol",
            fontName="Arial",
            fontSize=8,
            textColor=colors.black,
            leftIndent=0,
            rightIndent=0,
            spaceAfter=2,
            spaceBefore=2,
        )

    # Default fields and keys
    if fields is None:
        fields = list(data.keys())
    if field_keys is None:
        field_keys = {field: field for field in fields}

    # Prepare table data
    table_data = []
    for label in fields:
        key = field_keys[label]
        value = data.get(key, "")
        if value == "":
            print(f"Warning: Missing data for key '{key}'")
        if isinstance(value, str) and "\n" in value:
            paragraphs = [Paragraph(line, right_style) for line in value.split("\n")]
            table_data.append([Paragraph(label, left_style), paragraphs])
        else:
            table_data.append([Paragraph(label, left_style), Paragraph(str(value), right_style)])

    # Create and style the table
    table = Table(table_data, colWidths=col_widths, repeatRows=0)

    if table_style is None:
        table_style = TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#a3a3a3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2e74b5")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("FONTNAME", (0, 0), (0, -1), "Arial"),
            ("FONTSIZE", (0, 0), (0, -1), 8),
            ("BACKGROUND", (1, 0), (1, -1), colors.white),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.black),
            ("FONTNAME", (1, 0), (1, -1), "Arial"),
            ("FONTSIZE", (1, 0), (1, -1), 8),
        ])

    table.setStyle(table_style)
    doc.build([table])
    buffer.seek(0)
    return buffer

# Example usage
if __name__ == "__main__":
    # Sample data
    sample_data = {
        "name": "John Doe",
        "address": "123 Main St\nSpringfield, IL 62704",
        "phone": "555-123-4567",
        "email": "john.doe@example.com",
        "notes": "This is a sample note.\nIt spans multiple lines.",
    }

    # Generate PDF
    pdf_buffer = generate_template_pdf(sample_data)

    # Save to file
    with open("output.pdf", "wb") as f:
        f.write(pdf_buffer.read())

    print("PDF generated successfully!")
