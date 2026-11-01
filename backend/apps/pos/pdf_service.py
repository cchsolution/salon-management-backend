import io
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_invoice_pdf(invoice):
    """
    Generates a professional, branded PDF invoice using ReportLab.
    Formatted cleanly for standard print & download in INR.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'InvoiceSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#475569'),
        spaceAfter=2
    )
    bold_style = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0F172A')
    )
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#334155')
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )
    right_align_style = ParagraphStyle(
        'RightAlign',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        alignment=2,
        textColor=colors.HexColor('#0F172A')
    )

    story = []
    salon = invoice.salon
    branch = invoice.branch
    customer = invoice.customer

    # Header: Salon info & Invoice Metadata
    header_data = [
        [
            Paragraph(f"<b>{salon.name}</b>", title_style),
            Paragraph(f"<b>TAX INVOICE</b>", ParagraphStyle('RTitle', parent=title_style, alignment=2, textColor=colors.HexColor('#6D28D9')))
        ],
        [
            Paragraph(f"{branch.address if branch else salon.address}<br/>Phone: {branch.phone if branch else salon.phone}<br/>Email: {salon.email}", subtitle_style),
            Paragraph(f"<b>Invoice #:</b> {invoice.invoice_number}<br/><b>Date:</b> {invoice.created_at.strftime('%d-%b-%Y %I:%M %p')}<br/><b>Status:</b> {invoice.get_status_display()}", ParagraphStyle('RSub', parent=subtitle_style, alignment=2))
        ]
    ]
    header_table = Table(header_data, colWidths=[4.0 * inch, 3.5 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    # Bill To section
    cust_name = customer.full_name if customer else 'Retail Walk-in Customer'
    cust_phone = customer.phone if customer else 'N/A'
    cust_email = customer.email if (customer and customer.email) else 'N/A'

    bill_to_data = [
        [
            Paragraph("<b>BILLED TO:</b>", ParagraphStyle('BillToH', parent=bold_style, textColor=colors.HexColor('#6D28D9'))),
            Paragraph("<b>PAYMENT SUMMARY:</b>", ParagraphStyle('PayH', parent=bold_style, textColor=colors.HexColor('#6D28D9')))
        ],
        [
            Paragraph(f"<b>Name:</b> {cust_name}<br/><b>Phone:</b> {cust_phone}<br/><b>Email:</b> {cust_email}", normal_style),
            Paragraph(f"<b>Currency:</b> INR (₹)<br/><b>GST Tax Rate:</b> {salon.tax_rate}%<br/><b>Payment Status:</b> {invoice.get_status_display()}", normal_style)
        ]
    ]
    bill_table = Table(bill_to_data, colWidths=[4.0 * inch, 3.5 * inch])
    bill_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 16))

    # Line Items Table
    item_rows = [
        [
            Paragraph("Item & Description", table_header_style),
            Paragraph("Type", table_header_style),
            Paragraph("Qty", table_header_style),
            Paragraph("Unit Price (₹)", table_header_style),
            Paragraph("Discount (₹)", table_header_style),
            Paragraph("Total (₹)", table_header_style),
        ]
    ]

    for item in invoice.items.all():
        desc = item.item_name
        if item.product and item.product.sku:
            desc += f"<br/><font size=7 color='#64748B'>SKU: {item.product.sku}</font>"
        item_rows.append([
            Paragraph(desc, normal_style),
            Paragraph(item.get_item_type_display(), normal_style),
            Paragraph(str(item.quantity), normal_style),
            Paragraph(f"{item.unit_price:.2f}", normal_style),
            Paragraph(f"{item.discount_amount:.2f}", normal_style),
            Paragraph(f"{item.total_price:.2f}", normal_style),
        ])

    items_table = Table(item_rows, colWidths=[2.7 * inch, 1.0 * inch, 0.6 * inch, 1.1 * inch, 1.0 * inch, 1.1 * inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6D28D9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # Financial Summary Table (Right aligned)
    summary_data = [
        [Paragraph("Subtotal:", normal_style), Paragraph(f"₹ {invoice.subtotal:.2f}", right_align_style)],
        [Paragraph(f"Discount ({invoice.get_discount_type_display()}):", normal_style), Paragraph(f"- ₹ {invoice.discount_amount:.2f}", right_align_style)],
        [Paragraph(f"Tax (GST {salon.tax_rate}%):", normal_style), Paragraph(f"₹ {invoice.tax_amount:.2f}", right_align_style)],
        [Paragraph("<b>FINAL TOTAL:</b>", bold_style), Paragraph(f"<b>₹ {invoice.total_amount:.2f}</b>", ParagraphStyle('TotVal', parent=right_align_style, fontSize=12, textColor=colors.HexColor('#6D28D9')))],
        [Paragraph("Paid Amount:", normal_style), Paragraph(f"₹ {invoice.paid_amount:.2f}", right_align_style)],
        [Paragraph("<b>Balance Due:</b>", bold_style), Paragraph(f"<b>₹ {invoice.balance_due:.2f}</b>", right_align_style)],
    ]
    summary_table = Table(summary_data, colWidths=[5.5 * inch, 2.0 * inch])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 3), (-1, 3), 1, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0, 3), (-1, 3), 1, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Footer Notes
    notes_text = invoice.notes or "Thank you for shopping with us! Please retain this invoice for your records."
    story.append(Paragraph(f"<b>Notes:</b> {notes_text}", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0'), spaceAfter=8))
    story.append(Paragraph(f"This is a computer-generated invoice from {salon.name}. All prices are in Indian Rupees (INR).", ParagraphStyle('Foot', parent=subtitle_style, alignment=1, fontSize=8)))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

