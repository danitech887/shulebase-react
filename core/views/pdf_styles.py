"""
pdf_styles.py
=============
Drop-in replacement for every PDF helper in views.py.
Import these instead of the originals:

    from .pdf_styles import (
        StyledPDF, PdfReciept, PdfReportForm,
        pdf_header, pdf_footer,
        draw_section_title, draw_styled_table_header, draw_styled_row,
        CBC_LEVEL_MAP, get_cbc_level_and_remark,
    )

Design language
---------------
• Deep navy (#0D1B2A) primary  + gold (#C9A84C) accent
• Soft sky (#EAF4FB) alternating row tint
• Crimson (#B5271A) for deficit / balance figures
• Rounded column blocks via fill rectangles (FPDF draws fills before text)
• All fonts: built-in Arial family (safe for fpdf1)
"""

from fpdf import FPDF
from core.models import MasterSchool

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY    = (13,  27,  42)    # primary dark
GOLD    = (201, 168, 76)    # accent / highlight
SKY     = (234, 244, 251)   # alternating row tint
WHITE   = (255, 255, 255)
GREY    = (240, 240, 240)   # light rule / divider
MID     = (100, 116, 139)   # muted text / labels
GREEN   = (22,  101,  52)   # positive / pass
CRIMSON = (181,  39,  26)   # deficit / balance
BLACK   = (0,    0,   0)

# ── CBC level map ─────────────────────────────────────────────────────────────
CBC_LEVEL_MAP = {
    'EE': {'min_avg': 3.50, 'label': 'Exceeding Expectations',  'remark': 'Excellent Mastery'},
    'ME': {'min_avg': 2.50, 'label': 'Meeting Expectations',    'remark': 'Good Progress'},
    'AE': {'min_avg': 1.50, 'label': 'Approaching Expectations','remark': 'Needs Improvement'},
    'BE': {'min_avg': 0.00, 'label': 'Below Expectations',      'remark': 'Critical Intervention'},
}

core_competencies = [
    'Communication Skills','Critical Thinking','Creativity','Collaboration',
    'Digital Literacy','Learning to Learn','Citizenship','Self-Efficacy',
]


def get_cbc_level_and_remark(avg_level):
    if avg_level is None or avg_level <= 0:
        return {'level': '-', 'remark': '-'}
    capped = min(avg_level, 4.0)
    for code, data in sorted(CBC_LEVEL_MAP.items(), key=lambda i: i[1]['min_avg'], reverse=True):
        if capped >= data['min_avg']:
            return {'level': code, 'remark': data['remark']}
    return {'level': 'BE', 'remark': CBC_LEVEL_MAP['BE']['remark']}


# ── Colour helpers ────────────────────────────────────────────────────────────
def _set_fill(pdf, rgb):   pdf.set_fill_color(*rgb)
def _set_text(pdf, rgb):   pdf.set_text_color(*rgb)
def _set_draw(pdf, rgb):   pdf.set_draw_color(*rgb)


# ── Shared header ─────────────────────────────────────────────────────────────
def pdf_header(request, pdf, _x=30):
    """
    Replaces the original pdf_header.
    Draws:
      • full-width navy banner with school name centred in gold
      • contact line in white below name
      • a gold rule underneath
    """
    school = _get_school(request)

    logo, name, address, contact, email, motto = _school_attrs(school)

    page_w = pdf.w
    banner_h = 28

    # ── navy banner ──
    _set_fill(pdf, NAVY)
    _set_draw(pdf, NAVY)
    pdf.rect(0, 0, page_w, banner_h, style='F')

    # ── logo (if available) ──
    if logo:
        try:
            pdf.image(str(logo), x=6, y=3, h=22)
        except Exception:
            try:
                pdf.image("static/images/logo.png", x=6, y=3, h=22)
            except Exception:
                pass

    # ── school name ──
    _set_text(pdf, GOLD)
    pdf.set_font("Arial", "B", 15)
    pdf.set_xy(0, 5)
    pdf.cell(page_w, 8, name.upper(), align="C")

    # ── address / contacts ──
    _set_text(pdf, WHITE)
    pdf.set_font("Arial", "", 8)
    pdf.set_xy(0, 14)
    pdf.cell(page_w, 5, f"  {address}   |   Tel: {contact}   |   {email}", align="C")

    # ── motto ──
    if motto:
        pdf.set_xy(0, 20)
        pdf.set_font("Arial", "I", 7)
        _set_text(pdf, (220, 200, 140))
        pdf.cell(page_w, 5, f'"{motto}"', align="C")

    # ── gold rule below banner ──
    _set_draw(pdf, GOLD)
    pdf.set_line_width(0.8)
    pdf.line(0, banner_h, page_w, banner_h)
    pdf.set_line_width(0.2)

    pdf.set_y(banner_h + 4)
    _set_text(pdf, BLACK)
    _set_draw(pdf, BLACK)


def pdf_footer(pdf, vision=""):
    """Styled footer: page number + optional vision text."""
    pdf.set_y(-12)
    _set_fill(pdf, NAVY)
    pdf.rect(0, pdf.h - 10, pdf.w, 10, style='F')
    _set_text(pdf, GOLD)
    pdf.set_font("Arial", "I", 7)
    pdf.set_y(pdf.h - 9)
    page_label = f"Page {pdf.page_no()}"
    pdf.cell(0, 6, page_label, align="C")
    _set_text(pdf, BLACK)


# ── Section title helper ──────────────────────────────────────────────────────
def draw_section_title(pdf, text, w=None):
    """Gold-accent section divider."""
    w = w or (pdf.w - pdf.l_margin - pdf.r_margin)
    x0 = pdf.get_x()
    y0 = pdf.get_y()
    # left gold bar
    _set_fill(pdf, GOLD)
    pdf.rect(x0, y0, 3, 7, style='F')
    _set_fill(pdf, GREY)
    pdf.rect(x0 + 3, y0, w - 3, 7, style='F')
    _set_text(pdf, NAVY)
    pdf.set_font("Arial", "B", 9)
    pdf.set_xy(x0 + 6, y0)
    pdf.cell(w - 6, 7, text.upper())
    pdf.ln(9)
    _set_text(pdf, BLACK)


# ── Table helpers ─────────────────────────────────────────────────────────────
def draw_styled_table_header(pdf, columns):
    """
    columns: list of (label, width) tuples
    Draws a navy header row with white bold text.
    """
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    _set_draw(pdf, NAVY)
    pdf.set_font("Arial", "B", 7)
    for label, w in columns:
        pdf.cell(w, 7, label, border=0, align='C', fill=True)
    pdf.ln()
    # thin gold underline
    y = pdf.get_y()
    _set_draw(pdf, GOLD)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_line_width(0.2)
    _set_draw(pdf, (200, 200, 200))
    _set_text(pdf, BLACK)


def draw_styled_row(pdf, values, widths, row_index=0, aligns=None, h=6):
    """
    Draws a single alternating-colour data row.
    values  : list of strings
    widths  : list of floats (mm)
    aligns  : list of 'L'|'C'|'R'  (defaults to 'C')
    """
    fill_color = SKY if row_index % 2 == 0 else WHITE
    _set_fill(pdf, fill_color)
    _set_draw(pdf, (210, 220, 230))
    _set_text(pdf, BLACK)
    pdf.set_font("Arial", "", 6)
    aligns = aligns or ['C'] * len(values)
    for val, w, a in zip(values, widths, aligns):
        pdf.cell(w, h, str(val), border=1, align=a, fill=True)
    pdf.ln()
    _set_fill(pdf, WHITE)
    _set_draw(pdf, BLACK)


# ── Receipt PDF class ─────────────────────────────────────────────────────────
class PdfReciept(FPDF):
    """Styled receipt / small-format PDF (110×150 mm)."""

    def __init__(self, orientation='P', unit='mm', format=(110, 150)):
        super().__init__(orientation, unit, format)
        self.set_auto_page_break(auto=True, margin=12)

    # ── background ──
    def add_background_color(self, r=234, g=244, b=251):
        _set_fill(self, (r, g, b))
        self.rect(0, 0, self.w, self.h, style='F')

    # ── diagonal watermark ──
    def add_watermark(self, text):
        self.set_font('Arial', 'B', 40)
        _set_text(self, (210, 225, 240))
        w = self.get_string_width(text)
        x = (self.w - w) / 2
        y = self.h / 2
        self.text(x, y, text)
        self.rotate(35, x=x, y=y)
        self.rotate(0)
        _set_text(self, BLACK)

    # ── header ──
    def add_header(self, request):
        school = _get_school(request)
        logo, name, address, contact, email, motto = _school_attrs(school)

        # navy strip
        _set_fill(self, NAVY)
        self.rect(0, 0, self.w, 24, style='F')

        if logo:
            try:
                self.image(str(logo), x=3, y=2, h=18)
            except Exception:
                pass

        _set_text(self, GOLD)
        self.set_font("Arial", "B", 11)
        self.set_xy(0, 4)
        self.cell(self.w, 6, name.upper(), align='C')

        _set_text(self, WHITE)
        self.set_font("Arial", "", 6)
        self.set_xy(0, 11)
        self.cell(self.w, 4, f"Tel: {contact}  |  {email}", align='C')
        self.set_xy(0, 16)
        self.cell(self.w, 4, address, align='C')

        # gold rule
        _set_draw(self, GOLD)
        self.set_line_width(0.6)
        self.line(0, 24, self.w, 24)
        self.set_line_width(0.2)
        self.set_y(27)
        _set_text(self, BLACK)
        _set_draw(self, BLACK)

    # ── compact info pair ──
    def info_pair(self, label, value, w_label=35, w_value=55):
        _set_text(self, MID)
        self.set_font("Arial", "B", 6)
        self.cell(w_label, 5, label)
        _set_text(self, BLACK)
        self.set_font("Arial", "", 6)
        self.cell(w_value, 5, str(value), ln=True)

    # ── summary table for fees ──
    def fee_summary_table(self, expected, this_payment, total_paid, balance):
        cols = [("Expected Fee", 22), ("This Payment", 22), ("Total Paid", 22), ("Balance", 22)]
        draw_styled_table_header(self, cols)
        _set_text(self, BLACK)
        self.set_font("Arial", "", 7)
        vals   = [expected, this_payment, total_paid, balance]
        colors = [BLACK, BLACK, GREEN, CRIMSON if balance > 0 else GREEN]
        for (_, w), val, clr in zip(cols, vals, colors):
            _set_text(self, clr)
            self.cell(w, 6, str(val), border=1, align='C')
        self.ln()
        _set_text(self, BLACK)


# ── Full-page report PDF class ────────────────────────────────────────────────
class PdfReportForm(FPDF):
    """Styled A4 report / result form PDF."""

    def add_watermark(self, text):
        self.set_font('Arial', 'B', 80)
        _set_text(self, (220, 230, 240))
        w = self.get_string_width(text)
        x = (self.w - w) / 2
        y = self.h / 2
        self.text(x, y, text)
        self.rotate(40, x=x, y=y)
        self.rotate(0)
        _set_text(self, BLACK)

    def add_background_color(self, r=245, g=249, b=255):
        _set_fill(self, (r, g, b))
        self.rect(0, 0, self.w, self.h, style='F')

    # ── Student info banner ──
    def student_info_banner(self, reg_no, full_name, grade, stream, term):
        _set_fill(self, SKY)
        _set_draw(self, (190, 215, 235))
        x0 = self.l_margin
        y0 = self.get_y()
        bw = self.w - self.l_margin - self.r_margin
        self.rect(x0, y0, bw, 20, style='FD')

        _set_text(self, NAVY)
        self.set_font("Arial", "B", 9)
        self.set_xy(x0 + 2, y0 + 2)
        self.cell(bw / 2, 5, f"Reg No: {reg_no}")
        self.set_xy(x0 + bw / 2, y0 + 2)
        self.cell(bw / 2, 5, f"Name: {full_name}", align='R')

        _set_text(self, MID)
        self.set_font("Arial", "", 8)
        self.set_xy(x0 + 2, y0 + 9)
        self.cell(bw / 2, 5, f"Grade: {grade}   Stream: {stream}")
        self.set_xy(x0 + bw / 2, y0 + 9)
        self.cell(bw / 2, 5, f"Term: {term}", align='R')

        self.set_y(y0 + 23)
        _set_text(self, BLACK)
        _set_draw(self, BLACK)


# ── Internal helpers ──────────────────────────────────────────────────────────
def _get_school(request):
    try:
        school_id = getattr(request.user, 'school_id', None)
        if school_id:
            return MasterSchool.objects.filter(id=school_id).first()
    except Exception:
        pass
    return None


def _school_attrs(school):
    logo = address = contact = email = motto = ''
    name = 'SCHOOL NAME'
    if school:
        try:
            logo = school.logo_path.path if getattr(school, 'logo_path') else None
        except Exception:
            logo = getattr(school, 'logo_path', None)
        name    = getattr(school, 'school_name',   'SCHOOL NAME') or 'SCHOOL NAME'
        address = getattr(school, 'address',       '') or ''
        contact = getattr(school, 'contact',       '') or ''
        email   = getattr(school, 'email_address', '') or ''
        motto   = getattr(school, 'motto',         '') or ''
    return logo, name, address, contact, email, motto