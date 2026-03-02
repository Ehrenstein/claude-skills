#!/usr/bin/env python3
"""
Payne & Amber — Markdown → CI-konformes PDF

Konvertiert Markdown-Dateien in professionelle PDFs im Payne & Amber Design System.
Unterstützt: Deckblatt, Header-Bar, Footer mit Seitenzahlen, Blockquotes mit
Amber-Linie, Aufzählungen, Code-Blöcke, Überschriften H1–H4.

Nutzung:
    python md2pdf.py input.md [output.pdf] [--author "Name"] [--date "Datum"]
                     [--type recherche|konzept|shownotes]
                     [--variant classic|editorial] [--sides single|double]

Tokens: Farben und Typo aus dem Payne & Amber Design System.
Fonts:  Nunito Sans (Headings) → Fallback: Lato
        Lora (Body)
        JetBrains Mono (Code) → Fallback: Noto Sans Mono

Variants:
    classic   — Payne-Deep header bar, standard sizes
    editorial — Light header (like footer), finer type, H2 in Versalien

Sides:
    double — Druckbogen: alternating binding/outside margins (for duplex printing)
    single — Binding always left, outside always right (for simplex printing)
"""

import sys
import os
import re
import argparse
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    PageBreak, Table, TableStyle, KeepTogether, Flowable,
    NextPageTemplate
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ═══════════════════════════════════════════════════════════════════════
# DESIGN TOKENS — Payne & Amber
# ═══════════════════════════════════════════════════════════════════════

COLORS = {
    # Primitives
    'payne-deep':      HexColor('#2C3E50'),
    'payne-classic':   HexColor('#4A6274'),
    'payne-mid':       HexColor('#6B8299'),
    'payne-light':     HexColor('#A8B8C8'),
    'payne-wash':      HexColor('#D6DEE6'),
    'amber':           HexColor('#C17A2A'),
    'amber-dark':      HexColor('#A66B3A'),
    'terracotta':      HexColor('#B85C3A'),
    'gold':            HexColor('#D4A855'),
    'sand':            HexColor('#E8D5B5'),
    'ink':             HexColor('#1C2833'),
    'paper':           HexColor('#F6F2EC'),
    'paper-accent':    HexColor('#EDE4D5'),
    'white':           HexColor('#FFFFFF'),
}

# Semantic roles — Print context (no colored backgrounds, ink-efficient)
SEMANTIC_PRINT = {
    'accent':       COLORS['amber-dark'],
    'accent-hover': COLORS['amber-dark'],
    'accent-alt':   COLORS['terracotta'],
    'text-heading': COLORS['ink'],
    'text-body':    COLORS['payne-deep'],
    'text-secondary': COLORS['payne-classic'],
    'text-disabled':  COLORS['payne-light'],
    'bg-page':      COLORS['white'],
    'bg-surface':   COLORS['white'],
    'bg-card':      COLORS['paper-accent'],
    'border':       COLORS['payne-light'],
    'border-subtle': COLORS['payne-wash'],
}

# Semantic roles — Light mode (warmer Paper backgrounds)
SEMANTIC_LIGHT = {
    'accent':       COLORS['amber-dark'],
    'accent-hover': COLORS['terracotta'],
    'accent-alt':   COLORS['gold'],
    'text-heading': COLORS['ink'],
    'text-body':    COLORS['payne-deep'],
    'text-secondary': COLORS['payne-classic'],
    'text-disabled':  COLORS['payne-light'],
    'bg-page':      COLORS['white'],
    'bg-surface':   COLORS['paper'],
    'bg-card':      COLORS['paper-accent'],
    'border':       COLORS['payne-light'],
    'border-subtle': COLORS['payne-wash'],
}

# Typography scale — Major Third (1.25)
SIZES = {
    'xs':   9.6,     # 12.8px * 0.75 (pt conversion)
    'sm':   10.5,    # 14px
    'base': 11,      # ~16px → 11pt is standard for print body
    'md':   12.5,    # 18px
    'lg':   14,      # 20px
    'xl':   17,      # 25px
    'xxl':  21,      # 31.25px
    'xxxl': 27,      # 39px
    'xxxxl': 33,     # 48.8px
}

LINE_HEIGHTS = {
    'tight':    1.1,
    'snug':     1.2,
    'heading':  1.3,
    'moderate': 1.4,
    'relaxed':  1.5,
    'body':     1.55,
}

# ═══════════════════════════════════════════════════════════════════════
# PAGE LAYOUT — Druckbogen (facing pages with binding margin)
# ═══════════════════════════════════════════════════════════════════════

PAGE_W, PAGE_H = A4  # 595.27 × 841.89 points

# Bund/Binding margins
MARGIN_BINDING = 28 * mm     # Inner side (binding/Bund) — room for hole-punch
MARGIN_OUTSIDE = 42 * mm     # Outer side — generous space for margin notes
MARGIN_OUTSIDE_EDITORIAL = 48 * mm  # Editorial: significantly wider outside for airy layout
MARGIN_TOP = 25 * mm
MARGIN_BOTTOM = 22 * mm
HEADER_BAR_H = 12 * mm
HEADER_SPACING = 4 * mm    # Compact gap between header bar/line and content

# Footer positioning
FOOTER_LINE_Y = MARGIN_BOTTOM + 3 * mm     # Amber line, close to bottom
FOOTER_TEXT_Y = 12 * mm                      # Text ~12mm from paper edge


def margin_left(page_num, duplex=True, m_outside=None):
    """Left margin for a given page (1-based).
    duplex=True:  Odd = binding left, Even = outside left (Druckbogen)
    duplex=False: Always binding left (simplex)
    m_outside: override for outside margin (e.g. editorial variant)."""
    _outside = m_outside or MARGIN_OUTSIDE
    if not duplex:
        return MARGIN_BINDING  # Always binding on left
    if page_num % 2 == 1:  # Odd (recto): binding on left
        return MARGIN_BINDING
    else:                   # Even (verso): binding on right → outside on left
        return _outside


def margin_right(page_num, duplex=True, m_outside=None):
    """Right margin for a given page (1-based).
    duplex=True:  Odd = outside right, Even = binding right (Druckbogen)
    duplex=False: Always outside right (simplex)
    m_outside: override for outside margin (e.g. editorial variant)."""
    _outside = m_outside or MARGIN_OUTSIDE
    if not duplex:
        return _outside  # Always outside on right
    if page_num % 2 == 1:  # Odd (recto): outside on right
        return _outside
    else:                   # Even (verso): outside on left → binding on right
        return MARGIN_BINDING


def line_start_x(page_num, duplex=True):
    """X where lines START (binding side — stops at binding margin)."""
    return margin_left(page_num, duplex)


def line_end_x(page_num, duplex=True):
    """X where lines END (outside — extends into bleed, 15mm past margin)."""
    if not duplex or page_num % 2 == 1:  # Simplex or odd: outside is right
        return PAGE_W - margin_right(page_num, duplex) + 15 * mm
    else:                   # Duplex even: outside is left
        return PAGE_W - margin_right(page_num, duplex) + 15 * mm


def line_start_x_asym(page_num, duplex=True):
    """Left x-coordinate of asymmetric line.
    Line runs from binding margin to outside bleed (5mm past page edge).
    Simplex: binding=left → start at MARGIN_BINDING.
    Duplex odd (recto): binding=left → start at MARGIN_BINDING.
    Duplex even (verso): outside=left → start at -5mm (left bleed)."""
    if not duplex:
        return MARGIN_BINDING
    if page_num % 2 == 1:  # Odd (recto): binding=left
        return MARGIN_BINDING
    else:                   # Even (verso): outside=left → extend into left bleed
        return -5 * mm


def line_end_x_asym(page_num, duplex=True):
    """Right x-coordinate of asymmetric line.
    Line runs from binding margin to outside bleed (5mm past page edge).
    Simplex: outside=right → end at PAGE_W + 5mm (right bleed).
    Duplex odd (recto): outside=right → end at PAGE_W + 5mm (right bleed).
    Duplex even (verso): binding=right → end at PAGE_W - MARGIN_BINDING."""
    if not duplex:
        return PAGE_W + 5 * mm
    if page_num % 2 == 1:  # Odd (recto): outside=right → right bleed
        return PAGE_W + 5 * mm
    else:                   # Even (verso): binding=right → stop at binding margin
        return PAGE_W - MARGIN_BINDING


# ═══════════════════════════════════════════════════════════════════════
# FONT REGISTRATION
# ═══════════════════════════════════════════════════════════════════════

def register_fonts():
    """Register Payne & Amber fonts with fallbacks."""
    assets_dir = Path(__file__).parent.parent / 'assets' / 'fonts'

    font_map = {
        # Heading: Nunito Sans (assets/) → Lato (system) → Helvetica (built-in)
        'Heading':              find_font('NunitoSans', 'Regular', assets_dir, fallback_system='Lato-Regular'),
        'Heading-ExtraLight':   find_font('NunitoSans', 'ExtraLight', assets_dir, fallback_system='Lato-Regular'),
        'Heading-Light':        find_font('NunitoSans', 'Light', assets_dir, fallback_system='Lato-Regular'),
        'Heading-Bold':         find_font('NunitoSans', 'Bold', assets_dir, fallback_system='Lato-Bold'),
        'Heading-SemiBold':     find_font('NunitoSans', 'SemiBold', assets_dir, fallback_system='Lato-Semibold'),
        'Heading-Medium':       find_font('NunitoSans', 'Medium', assets_dir, fallback_system='Lato-Medium'),
        'Heading-Italic':       find_font('NunitoSans', 'Italic', assets_dir, fallback_system='Lato-Italic'),
        'Heading-ExtraLightItalic': find_font('NunitoSans', 'ExtraLightItalic', assets_dir, fallback_system='Lato-Italic'),
        # Body: Lora variable (system) → Times-Roman (built-in)
        'Body':             find_font('Lora', 'Variable', assets_dir, fallback_system=None),
        'Body-Italic':      find_font('Lora', 'Italic-Variable', assets_dir, fallback_system=None),
        # Mono: JetBrains Mono (assets/) → Noto Sans Mono (system) → Courier (built-in)
        'Mono':             find_font('JetBrainsMono', 'Regular', assets_dir, fallback_system='NotoSansMono-Regular'),
        'Mono-Bold':        find_font('JetBrainsMono', 'Bold', assets_dir, fallback_system='NotoSansMono-Bold'),
    }

    # Ornamental bullet font: DejaVu Sans has ◆ ✦ ◉ etc.
    dejavu_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if os.path.exists(dejavu_path):
        font_map['Bullet-Ornament'] = dejavu_path

    for name, path in font_map.items():
        if path:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception as e:
                print(f"  Warning: Could not register {name} from {path}: {e}")
                _register_fallback(name)
        else:
            _register_fallback(name)

    # Register font families for bold/italic auto-switching in Paragraphs
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily('Heading',
        normal='Heading', bold='Heading-Bold',
        italic='Heading-Italic', boldItalic='Heading-Bold')
    registerFontFamily('Body',
        normal='Body', bold='Body',  # Lora variable handles weight
        italic='Body-Italic', boldItalic='Body-Italic')
    registerFontFamily('Mono',
        normal='Mono', bold='Mono-Bold',
        italic='Mono', boldItalic='Mono-Bold')


def find_font(family, variant, assets_dir, fallback_system=None):
    """Find font file: assets dir first, then system paths."""
    candidates = [
        assets_dir / family / f"{family}-{variant}.ttf",
        assets_dir / family / f"{family}-{variant.replace('-', '')}.ttf",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    system_dirs = [
        Path('/usr/share/fonts/truetype/google-fonts'),
        Path('/usr/share/fonts/truetype/lato'),
        Path('/usr/share/fonts/truetype/noto'),
        Path('/usr/share/fonts/truetype/dejavu'),
        Path('/usr/share/fonts/truetype/liberation'),
    ]

    if family == 'Lora':
        lora_path = Path('/usr/share/fonts/truetype/google-fonts') / f"Lora-{variant}.ttf"
        if lora_path.exists():
            return str(lora_path)

    if fallback_system:
        for sd in system_dirs:
            fp = sd / f"{fallback_system}.ttf"
            if fp.exists():
                return str(fp)

    return None


def _register_fallback(name):
    """Register Helvetica/Times/Courier as ultimate fallback."""
    fallbacks = {
        'Heading': 'Helvetica', 'Heading-ExtraLight': 'Helvetica',
        'Heading-Light': 'Helvetica',
        'Heading-Bold': 'Helvetica-Bold',
        'Heading-SemiBold': 'Helvetica-Bold', 'Heading-Medium': 'Helvetica',
        'Heading-Italic': 'Helvetica-Oblique',
        'Heading-ExtraLightItalic': 'Helvetica-Oblique',
        'Body': 'Times-Roman', 'Body-Italic': 'Times-Italic',
        'Mono': 'Courier', 'Mono-Bold': 'Courier-Bold',
    }
    fb = fallbacks.get(name, 'Helvetica')
    try:
        pdfmetrics.registerFont(TTFont(name, fb))
    except:
        pass


# ═══════════════════════════════════════════════════════════════════════
# CUSTOM FLOWABLES
# ═══════════════════════════════════════════════════════════════════════

class AmberBlockquote(Flowable):
    """Blockquote with amber left border on paper-accent background."""

    def __init__(self, text, sem, width=None, variant='classic'):
        super().__init__()
        self.text = text
        self.sem = sem
        self.variant = variant
        self._width = width or 400
        # Slightly larger than body text for emphasis (body=11pt, quote=12pt)
        _quote_size = SIZES['base'] + 1
        # Pullquote inset: narrower than text frame on both sides
        self._inset = 6 * mm           # Inset from text frame edges
        self._line_w = 1.5 * mm        # Amber accent line width
        self.style = ParagraphStyle(
            'Blockquote',
            fontName='Body-Italic',
            fontSize=_quote_size,
            leading=_quote_size * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-body'],
            leftIndent=self._line_w + 4 * mm,   # line + gap
            rightIndent=4 * mm,
            spaceBefore=0,
            spaceAfter=0,
        )
        self._para = Paragraph(self.text, self.style)
        w, h = self._para.wrap(self._width - 2 * self._inset, PAGE_H)
        self._height = h + 10 * mm

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        inner_w = availWidth - 2 * self._inset
        w, h = self._para.wrap(inner_w, availHeight)
        self._height = h + 10 * mm
        return availWidth, self._height

    def draw(self):
        c = self.canv
        inset = self._inset
        draw_w = self._width - 2 * inset
        # Background rect — inset from both sides
        c.setFillColor(self.sem['bg-card'])
        c.roundRect(inset, 0, draw_w, self._height, 2, fill=1, stroke=0)
        # Amber accent line at left edge of the inset box
        c.setFillColor(self.sem['accent'])
        c.rect(inset, 0, self._line_w, self._height, fill=1, stroke=0)
        self._para.drawOn(c, inset, 5 * mm)


class DuplexAwareH2(Flowable):
    """H2 heading that aligns to the outside edge in duplex mode.
    Duplex: odd pages → right-aligned, even pages → left-aligned (with negative indent into margin)
    Simplex: always left-aligned (with negative indent into margin)"""

    def __init__(self, text, style, sem, variant='classic', duplex=True):
        super().__init__()
        self.text = text
        self.base_style = style
        self.sem = sem
        self.variant = variant
        self.duplex = duplex
        # Golden ratio: H2 begins at 0.618× of outside margin from page edge
        # → extension into margin = margin × (1 − 0.618) = margin × 0.382
        self._margin_extension = (MARGIN_OUTSIDE_EDITORIAL * 0.382) if variant == 'editorial' else 0
        # Create two versions: left-aligned and right-aligned
        self._para_left = Paragraph(text, ParagraphStyle(
            'H2Left', parent=style,
            leftIndent=-self._margin_extension,
            alignment=TA_LEFT,
        ))
        self._para_right = Paragraph(text, ParagraphStyle(
            'H2Right', parent=style,
            rightIndent=-self._margin_extension,
            alignment=TA_RIGHT,
        ))
        self._para = self._para_left  # default
        self._width = 400
        self._height = 20

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        # Wrap both variants at frame width — the negative indent in each
        # ParagraphStyle alone provides the margin extension.  Do NOT add
        # extension here; that caused a double-shift on odd (right) pages.
        w1, h1 = self._para_left.wrap(availWidth, availHeight)
        w2, h2 = self._para_right.wrap(availWidth, availHeight)
        self._height = max(h1, h2)
        return availWidth, self._height

    def draw(self):
        c = self.canv
        # Get current page number from canvas
        pn = getattr(c, '_pageNumber', 1)

        if not self.duplex:
            # Simplex: outside = right → right-aligned, extend into right margin
            # (leftIndent already in style via _para_right's rightIndent)
            self._para_right.drawOn(c, 0, 0)
        elif pn % 2 == 1:
            # Odd (recto): outside = right → right-aligned, extend into right margin
            self._para_right.drawOn(c, 0, 0)
        else:
            # Even (verso): outside = left → left-aligned, extend into left margin
            # (leftIndent=-extension already in _para_left style, no additional offset!)
            self._para_left.drawOn(c, 0, 0)


class DuplexAwareH2Line(Flowable):
    """Amber underline for H2 — same extent as header/footer lines:
    from binding margin to outside bleed (5mm past page edge).
    Drawn in absolute page coordinates, just thicker than footer."""

    def __init__(self, sem, variant='classic', duplex=True):
        super().__init__()
        self.sem = sem
        self.variant = variant
        self.duplex = duplex
        self._m_outside = MARGIN_OUTSIDE_EDITORIAL if variant == 'editorial' else MARGIN_OUTSIDE

    def wrap(self, availWidth, availHeight):
        return availWidth, 1.5 * mm  # Small vertical space for the line

    def draw(self):
        c = self.canv
        pn = getattr(c, '_pageNumber', 1)

        # Same asymmetric line as header/footer: binding margin → outside bleed
        lx_start = line_start_x_asym(pn, self.duplex)
        lx_end = line_end_x_asym(pn, self.duplex)

        # Convert to frame-relative coordinates:
        # The canvas origin for flowable drawing is at the frame's (x, y).
        # We need to offset to draw in absolute page coordinates.
        frame_x = margin_left(pn, self.duplex, self._m_outside)
        abs_start = lx_start - frame_x
        abs_end = lx_end - frame_x

        c.setStrokeColor(self.sem['accent'])
        c.setLineWidth(1.0)  # Thicker than footer (0.75)
        c.line(abs_start, 0, abs_end, 0)


class HorizontalRule(Flowable):
    """Thin horizontal line in border-subtle color."""

    def __init__(self, sem, width=None):
        super().__init__()
        self.sem = sem
        self._width = width or 400

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return availWidth, 6 * mm

    def draw(self):
        self.canv.setStrokeColor(self.sem['border-subtle'])
        self.canv.setLineWidth(0.5)
        self.canv.line(0, 3 * mm, self._width, 3 * mm)


class ParagraphWithMarginNote(Flowable):
    """Paragraph that carries a margin note aligned to its first text line.

    The note is drawn in the outside margin, vertically aligned to the
    paragraph's top.  This composite approach guarantees alignment because
    both elements share the same draw() call — no fragile y-offset hacks.

    In the Markdown source the note ``{>> text <<}`` appears AFTER its
    reference paragraph, so the parser retroactively wraps the already-
    emitted Paragraph with this class.
    """

    def __init__(self, paragraph, note_text, sem, variant='classic', duplex=True):
        super().__init__()
        self._para = paragraph
        self.sem = sem
        self.variant = variant
        self.duplex = duplex
        self._m_outside = (MARGIN_OUTSIDE_EDITORIAL
                           if variant == 'editorial' else MARGIN_OUTSIDE)
        _ns = SIZES['xs']
        _base_style = dict(
            fontName='Heading', fontSize=_ns,
            leading=_ns * LINE_HEIGHTS['snug'],
            textColor=sem['accent'],
        )
        self._nstyle_l = ParagraphStyle('MNoteL', alignment=TA_LEFT, **_base_style)
        self._nstyle_r = ParagraphStyle('MNoteR', alignment=TA_RIGHT, **_base_style)
        self._note_l = Paragraph(note_text, self._nstyle_l)
        self._note_r = Paragraph(note_text, self._nstyle_r)
        self._note_h = 0

    # ------------------------------------------------------------------
    def wrap(self, availWidth, availHeight):
        w, h = self._para.wrap(availWidth, availHeight)
        note_w = self._m_outside - 8 * mm
        _, h1 = self._note_l.wrap(note_w, availHeight)
        _, h2 = self._note_r.wrap(note_w, availHeight)
        self._note_h = max(h1, h2)
        self._width = availWidth
        self._height = h
        return availWidth, h          # same footprint as the paragraph

    # ------------------------------------------------------------------
    def draw(self):
        c = self.canv

        # ---- draw the paragraph in its normal position ---------------
        self._para.drawOn(c, 0, 0)

        # ---- draw the margin note ------------------------------------
        pn = getattr(c, '_pageNumber', 1)
        note_w = self._m_outside - 8 * mm
        gap = SIZES['base'] * 1.2           # ≥ 1 em
        _fpad = 12                          # ReportLab default 6pt × 2

        # Vertical: note top aligns with paragraph top
        note_y = self._height - self._note_h

        c.setStrokeColor(self.sem['accent'])
        c.setLineWidth(0.5)

        if not self.duplex or pn % 2 == 1:
            # Outside = right → left-aligned, amber line on text-facing side
            content_w = PAGE_W - MARGIN_BINDING - self._m_outside
            note_x = content_w + gap
            line_x = note_x - 2 * mm
            c.line(line_x, note_y, line_x, note_y + self._note_h)
            self._note_l.drawOn(c, note_x, note_y)
        else:
            # Outside = left → right-aligned, amber line on text-facing side
            note_x_re = -(gap + _fpad)
            note_x = note_x_re - note_w
            line_x = note_x_re + 2 * mm
            c.line(line_x, note_y, line_x, note_y + self._note_h)
            self._note_r.drawOn(c, note_x, note_y)

    # Delegate style/spaceAfter so the flow engine spaces us like a paragraph
    @property
    def style(self):
        return self._para.style


class ImagePlaceholder(Flowable):
    """Placeholder for an image with caption and source attribution.
    Renders as a tinted rectangle with an icon-like label."""

    def __init__(self, caption, source, sem, width=None, height=None):
        super().__init__()
        self.caption = caption
        self.source = source
        self.sem = sem
        self._width = width or 120 * mm
        self._img_h = height or 60 * mm
        self._cap_style = ParagraphStyle(
            'ImageCaption', fontName='Body-Italic', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-secondary'], spaceBefore=2 * mm,
        )
        self._src_style = ParagraphStyle(
            'ImageSource', fontName='Body', fontSize=SIZES['xs'],
            leading=SIZES['xs'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-disabled'],
        )

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        cap_para = Paragraph(self.caption, self._cap_style)
        _, cap_h = cap_para.wrap(availWidth, 100)
        src_para = Paragraph(self.source, self._src_style)
        _, src_h = src_para.wrap(availWidth, 100)
        self._total_h = self._img_h + cap_h + src_h + 4 * mm
        return availWidth, self._total_h

    def draw(self):
        c = self.canv
        # Tinted placeholder rectangle
        c.setFillColor(self.sem['bg-card'])
        c.setStrokeColor(self.sem['border-subtle'])
        c.setLineWidth(0.5)
        c.roundRect(0, self._total_h - self._img_h, self._width, self._img_h,
                     3, fill=1, stroke=1)
        # Center label
        c.setFont('Heading', SIZES['md'])
        c.setFillColor(self.sem['text-disabled'])
        c.drawCentredString(self._width / 2,
                            self._total_h - self._img_h / 2 - SIZES['md'] / 2,
                            '[ Abbildung ]')
        # Caption + source
        cap_para = Paragraph(self.caption, self._cap_style)
        cap_w, cap_h = cap_para.wrap(self._width, 100)
        cap_para.drawOn(c, 0, self._total_h - self._img_h - cap_h - 2 * mm)
        src_para = Paragraph(self.source, self._src_style)
        src_w, src_h = src_para.wrap(self._width, 100)
        src_para.drawOn(c, 0, 0)


# ═══════════════════════════════════════════════════════════════════════
# PAGE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════

class PaineAmberDocTemplate(BaseDocTemplate):
    """Document template with Payne & Amber CI styling + Druckbogen."""

    def __init__(self, filename, meta, sem, variant='classic', duplex=True, **kwargs):
        # Determine effective outside margin based on variant
        m_outside = MARGIN_OUTSIDE_EDITORIAL if variant == 'editorial' else MARGIN_OUTSIDE

        super().__init__(filename, pagesize=A4,
                         leftMargin=m_outside if duplex else MARGIN_BINDING,
                         rightMargin=MARGIN_BINDING if duplex else m_outside,
                         topMargin=MARGIN_TOP + HEADER_BAR_H + HEADER_SPACING,
                         bottomMargin=MARGIN_BOTTOM + 12 * mm,
                         **kwargs)

        # Set attributes AFTER super().__init__ to avoid ReportLab overwriting them
        self.meta = meta
        self.sem = sem
        self.variant = variant  # 'classic' or 'editorial'
        self._duplex = duplex   # True = double-sided (Druckbogen), False = single-sided
        self._m_outside = m_outside

        content_w = PAGE_W - MARGIN_BINDING - m_outside
        content_h = PAGE_H - MARGIN_TOP - HEADER_BAR_H - HEADER_SPACING - MARGIN_BOTTOM - 12 * mm
        content_y = MARGIN_BOTTOM + 12 * mm

        if duplex:
            # Content frame for even pages (first content page = page 2)
            # Even: outside-left, binding-right
            content_frame_even = Frame(
                m_outside, content_y, content_w, content_h,
                id='content_even',
            )
            # Content frame for odd pages (page 3, 5, 7…)
            # Odd: binding-left, outside-right
            content_frame_odd = Frame(
                MARGIN_BINDING, content_y, content_w, content_h,
                id='content_odd',
            )
        else:
            # Single-sided: always binding-left, outside-right
            content_frame_single = Frame(
                MARGIN_BINDING, content_y, content_w, content_h,
                id='content_single',
            )

        # Cover page frame (always binding-left for page 1, full-width for cover)
        cover_w = PAGE_W - MARGIN_BINDING - MARGIN_OUTSIDE  # Cover always uses standard margins
        cover_frame = Frame(
            MARGIN_BINDING,
            MARGIN_BOTTOM,
            cover_w,
            PAGE_H - MARGIN_TOP - MARGIN_BOTTOM,
            id='cover',
        )

        if duplex:
            self.addPageTemplates([
                PageTemplate(id='cover', frames=[cover_frame],
                             onPage=self._draw_cover_page),
                PageTemplate(id='content_even', frames=[content_frame_even],
                             onPage=self._draw_content_page),
                PageTemplate(id='content_odd', frames=[content_frame_odd],
                             onPage=self._draw_content_page),
            ])
        else:
            self.addPageTemplates([
                PageTemplate(id='cover', frames=[cover_frame],
                             onPage=self._draw_cover_page),
                PageTemplate(id='content_single', frames=[content_frame_single],
                             onPage=self._draw_content_page),
            ])

    def afterPage(self):
        """Switch between even/odd templates for facing pages (duplex only)."""
        if self._duplex:
            # After cover (page 1), go to even (page 2)
            # After page 2 (even), go to odd (page 3), etc.
            next_page = self.page + 1
            if next_page % 2 == 0:
                self._nextPageTemplateIndex = 1  # content_even
            else:
                self._nextPageTemplateIndex = 2  # content_odd
        else:
            # Single-sided: always use the same template
            self._nextPageTemplateIndex = 1  # content_single

    def _draw_cover_page(self, canvas, doc):
        """Draw cover page with large header bar and all cover text.
        Uses golden ratio (φ ≈ 0.618): dark bar takes the larger portion."""
        canvas.saveState()
        w, h = PAGE_W, PAGE_H

        # Golden ratio: dark bar = 61.8% of page height
        bar_h = h * 0.618
        canvas.setFillColor(COLORS['payne-deep'])
        canvas.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)

        # Prominent amber accent strip at bottom of bar (2.5mm high)
        accent_strip_h = 2.5 * mm
        canvas.setFillColor(self.sem['accent'])
        canvas.rect(0, h - bar_h - accent_strip_h, w, accent_strip_h, fill=1, stroke=0)

        # Draw title directly on canvas (inside the bar, vertically centered)
        text_x = MARGIN_BINDING
        text_w = w - MARGIN_BINDING - MARGIN_OUTSIDE
        # Position title in upper third of the dark bar
        y_cursor = h - bar_h * 0.30

        from reportlab.platypus import Paragraph as P

        # Editorial cover: ExtraLight, uppercase, 1.5× H2 size
        if self.variant == 'editorial':
            cover_title_size = (SIZES['xxxxl'] + 2) * 1.5  # ~52pt
            title_style = ParagraphStyle(
                'CoverTitle', fontName='Heading-ExtraLight',
                fontSize=cover_title_size,
                leading=cover_title_size * LINE_HEIGHTS['tight'],
                textColor=COLORS['white'],
            )
            title_text = self.meta.get('title', 'Dokument').upper()
        else:
            title_style = ParagraphStyle(
                'CoverTitle', fontName='Heading-Bold', fontSize=SIZES['xxxxl'],
                leading=SIZES['xxxxl'] * LINE_HEIGHTS['tight'],
                textColor=COLORS['white'],
            )
            title_text = self.meta.get('title', 'Dokument')
        title_para = P(title_text, title_style)
        tw, th = title_para.wrap(text_w, 200)
        title_para.drawOn(canvas, text_x, y_cursor - th)
        y_cursor -= th + 6 * mm

        if self.meta.get('subtitle'):
            sub_style = ParagraphStyle(
                'CoverSub', fontName='Heading', fontSize=SIZES['xl'],
                leading=SIZES['xl'] * LINE_HEIGHTS['heading'],
                textColor=COLORS['payne-light'],
            )
            sub_para = P(self.meta['subtitle'], sub_style)
            sw, sh = sub_para.wrap(text_w, 100)
            sub_para.drawOn(canvas, text_x, y_cursor - sh)
            y_cursor -= sh + 4 * mm

        meta_parts = []
        if self.meta.get('doc_type'):
            meta_parts.append(self.meta['doc_type'])
        if self.meta.get('date'):
            meta_parts.append(self.meta['date'])
        if self.meta.get('author'):
            meta_parts.append(self.meta['author'])
        if meta_parts:
            meta_style = ParagraphStyle(
                'CoverMeta', fontName='Body-Italic', fontSize=SIZES['base'],
                leading=SIZES['base'] * LINE_HEIGHTS['relaxed'],
                textColor=COLORS['amber'],
            )
            meta_para = P(' · '.join(meta_parts), meta_style)
            mw, mh = meta_para.wrap(text_w, 60)
            meta_para.drawOn(canvas, text_x, y_cursor - mh)

        canvas.restoreState()

    def _draw_content_page(self, canvas, doc):
        """Draw header + footer on content pages (variant-aware + duplex-aware)."""
        canvas.saveState()
        w, h = PAGE_W, PAGE_H
        pn = doc.page  # current page number (1-based)
        dx = self._duplex
        mo = self._m_outside

        ml = margin_left(pn, dx, mo)
        mr = margin_right(pn, dx, mo)

        if self.variant == 'classic':
            self._draw_header_classic(canvas, w, h, ml, mr, pn)
        else:
            self._draw_header_editorial(canvas, w, h, ml, mr, pn, dx)

        self._draw_footer(canvas, w, h, ml, mr, pn, dx)
        canvas.restoreState()

    def _draw_header_classic(self, canvas, w, h, ml, mr, pn):
        """Classic: Payne-Deep header bar with text."""
        canvas.setFillColor(COLORS['payne-deep'])
        canvas.rect(0, h - HEADER_BAR_H, w, HEADER_BAR_H, fill=1, stroke=0)

        header_text = self.meta.get('header_text', '')
        if header_text:
            canvas.setFont('Heading', SIZES['base'])
            canvas.setFillColor(COLORS['payne-light'])
            text_y = h - HEADER_BAR_H + (HEADER_BAR_H - SIZES['base']) / 2
            canvas.drawString(ml, text_y, header_text)

    def _draw_header_editorial(self, canvas, w, h, ml, mr, pn, duplex=True):
        """Editorial: Light header — amber line + text, no dark bar.
        Line sits lower to give header text more breathing room."""
        # Line sits 4mm lower than bar bottom → more air between text and line
        header_line_y = h - HEADER_BAR_H - 4 * mm

        # Asymmetric amber line (binding → outside+bleed)
        lx_start = line_start_x_asym(pn, duplex)
        lx_end = line_end_x_asym(pn, duplex)
        canvas.setStrokeColor(self.sem['accent'])
        canvas.setLineWidth(0.5)
        canvas.line(lx_start, header_line_y, lx_end, header_line_y)

        # Header text above line — larger font, more space above line
        # Duplex odd: right-aligned (outside=right); even/simplex: left-aligned
        header_text = self.meta.get('header_text', '')
        if header_text:
            canvas.setFont('Heading', SIZES['base'])
            canvas.setFillColor(self.sem['text-secondary'])
            text_y = header_line_y + 3 * mm
            if duplex and pn % 2 == 1:
                canvas.drawRightString(w - mr, text_y, header_text)
            else:
                canvas.drawString(ml, text_y, header_text)

    def _draw_footer(self, canvas, w, h, ml, mr, pn, duplex=True):
        """Footer with asymmetric amber line + author/date + page number."""
        # Asymmetric amber line: from binding margin to outside bleed
        lx_start = line_start_x_asym(pn, duplex)
        lx_end = line_end_x_asym(pn, duplex)

        canvas.setStrokeColor(self.sem['accent'])
        canvas.setLineWidth(0.75)
        canvas.line(lx_start, FOOTER_LINE_Y, lx_end, FOOTER_LINE_Y)

        # Footer text at ~12mm from paper bottom edge
        canvas.setFont('Body', SIZES['xs'])
        canvas.setFillColor(self.sem['text-secondary'])
        footer_text = self.meta.get('footer_text', '')

        if not duplex:
            # Single-sided: footer text always left (binding side), page num always right
            canvas.drawString(ml, FOOTER_TEXT_Y, footer_text)
        elif pn % 2 == 1:  # Duplex odd: outside = right → footer text left, page num right
            canvas.drawString(ml, FOOTER_TEXT_Y, footer_text)
        else:              # Duplex even: outside = left → footer text right, page num left
            canvas.drawRightString(w - mr, FOOTER_TEXT_Y, footer_text)


# ═══════════════════════════════════════════════════════════════════════
# MARKDOWN PARSER → FLOWABLES
# ═══════════════════════════════════════════════════════════════════════

def build_styles(sem, variant='classic'):
    """Create all paragraph styles from design tokens."""
    # Editorial variant: large airy H2, finer type
    if variant == 'editorial':
        h2_font = 'Heading-ExtraLight'  # Weight 200 — very light, editorial statement
        h2_size = SIZES['xxxxl'] + 2  # ~35pt — very large, editorial statement
        h3_font = 'Heading-Medium'
        h3_size = SIZES['lg']
    else:
        h2_font = 'Heading-SemiBold'
        h2_size = SIZES['xxl']
        h3_font = 'Heading-SemiBold'
        h3_size = SIZES['xl']

    return {
        'title': ParagraphStyle(
            'Title', fontName='Heading-Bold', fontSize=SIZES['xxxxl'],
            leading=SIZES['xxxxl'] * LINE_HEIGHTS['tight'],
            textColor=COLORS['white'], spaceAfter=4 * mm,
        ),
        'subtitle': ParagraphStyle(
            'Subtitle', fontName='Heading', fontSize=SIZES['xl'],
            leading=SIZES['xl'] * LINE_HEIGHTS['heading'],
            textColor=COLORS['payne-light'], spaceAfter=3 * mm,
        ),
        'cover-meta': ParagraphStyle(
            'CoverMeta', fontName='Body-Italic', fontSize=SIZES['base'],
            leading=SIZES['base'] * LINE_HEIGHTS['relaxed'],
            textColor=COLORS['amber'], spaceAfter=2 * mm,
        ),
        'h1': ParagraphStyle(
            'H1', fontName='Heading-Bold', fontSize=SIZES['xxxl'],
            leading=SIZES['xxxl'] * LINE_HEIGHTS['snug'],
            textColor=sem['text-heading'], spaceBefore=10 * mm, spaceAfter=4 * mm,
        ),
        'h2': ParagraphStyle(
            'H2', fontName=h2_font, fontSize=h2_size,
            leading=h2_size * (LINE_HEIGHTS['relaxed'] if variant == 'editorial' else LINE_HEIGHTS['snug']),
            textColor=sem['text-heading'],
            spaceBefore=0,  # spaceBefore handled by explicit Spacer before KeepTogether
            spaceAfter=4 * mm if variant == 'editorial' else 3 * mm,
            borderWidth=0, borderPadding=0,
            keepWithNext=1,
        ),
        'h3': ParagraphStyle(
            'H3', fontName=h3_font, fontSize=h3_size,
            leading=h3_size * LINE_HEIGHTS['heading'],
            textColor=sem['text-heading'], spaceBefore=6 * mm, spaceAfter=3 * mm,
            keepWithNext=1,
        ),
        'h4': ParagraphStyle(
            'H4', fontName='Heading-Medium', fontSize=SIZES['lg'],
            leading=SIZES['lg'] * LINE_HEIGHTS['moderate'],
            textColor=sem['text-heading'], spaceBefore=4 * mm, spaceAfter=3 * mm,
            keepWithNext=1,
        ),
        'body': ParagraphStyle(
            'Body', fontName='Body', fontSize=SIZES['base'],
            leading=SIZES['base'] * LINE_HEIGHTS['body'],
            textColor=sem['text-body'], spaceAfter=3 * mm,
            alignment=TA_JUSTIFY,
            allowWidows=0, allowOrphans=0,
        ),
        'lead': ParagraphStyle(
            'Lead', fontName='Body', fontSize=SIZES['md'],
            leading=SIZES['md'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-body'], spaceAfter=4 * mm,
        ),
        'bullet': ParagraphStyle(
            'Bullet', fontName='Body', fontSize=SIZES['base'],
            leading=SIZES['base'] * LINE_HEIGHTS['body'],
            textColor=sem['text-body'], spaceAfter=1.5 * mm,
            leftIndent=8 * mm, bulletIndent=2 * mm,
            bulletFontName='Heading', bulletFontSize=SIZES['base'],
            bulletColor=sem['accent'],
        ),
        'code': ParagraphStyle(
            'Code', fontName='Mono', fontSize=SIZES['xs'],
            leading=SIZES['xs'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-body'], spaceAfter=3 * mm,
            leftIndent=6 * mm, rightIndent=6 * mm,
            backColor=sem['bg-card'],
            borderPadding=(6, 8, 6, 8),  # top, right, bottom, left (pt)
            borderWidth=0,
            borderRadius=2,
        ),
        'link': ParagraphStyle(
            'Link', fontName='Body', fontSize=SIZES['base'],
            leading=SIZES['base'] * LINE_HEIGHTS['body'],
            textColor=sem['accent'], spaceAfter=2 * mm,
            leftIndent=4 * mm,
        ),
        'caption': ParagraphStyle(
            'Caption', fontName='Body', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-secondary'], spaceAfter=2 * mm,
        ),
        'table-caption': ParagraphStyle(
            'TableCaption', fontName='Body-Italic', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-secondary'], spaceBefore=2 * mm, spaceAfter=4 * mm,
        ),
        'table-header': ParagraphStyle(
            'TableHeader', fontName='Heading-SemiBold', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['snug'],
            textColor=sem['text-heading'],
        ),
        'table-cell': ParagraphStyle(
            'TableCell', fontName='Body', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['moderate'],
            textColor=sem['text-body'],
        ),
        'footnote': ParagraphStyle(
            'Footnote', fontName='Body', fontSize=SIZES['xs'],
            leading=SIZES['xs'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-secondary'], spaceAfter=1.5 * mm,
            leftIndent=6 * mm, firstLineIndent=-6 * mm,
        ),
        'toc-h2': ParagraphStyle(
            'TOCH2', fontName='Heading-SemiBold' if variant == 'classic' else 'Heading',
            fontSize=SIZES['base'],
            leading=SIZES['base'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-heading'], spaceAfter=1.5 * mm,
            leftIndent=0,
        ),
        'toc-h3': ParagraphStyle(
            'TOCH3', fontName='Body', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-body'], spaceAfter=1 * mm,
            leftIndent=8 * mm,
        ),
        'appendix-heading': ParagraphStyle(
            'AppendixHeading', fontName='Heading-SemiBold', fontSize=SIZES['lg'],
            leading=SIZES['lg'] * LINE_HEIGHTS['heading'],
            textColor=sem['text-heading'], spaceBefore=8 * mm, spaceAfter=3 * mm,
        ),
        'bib-entry': ParagraphStyle(
            'BibEntry', fontName='Body', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['relaxed'],
            textColor=sem['text-body'], spaceAfter=2 * mm,
            leftIndent=8 * mm, firstLineIndent=-8 * mm,
        ),
        'index-entry': ParagraphStyle(
            'IndexEntry', fontName='Body', fontSize=SIZES['sm'],
            leading=SIZES['sm'] * LINE_HEIGHTS['moderate'],
            textColor=sem['text-body'], spaceAfter=0.5 * mm,
        ),
    }


def inline_format(text, sem):
    """Convert inline Markdown to ReportLab XML markup."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    accent_hex = sem['accent'].hexval() if hasattr(sem['accent'], 'hexval') else '#A66B3A'
    text = re.sub(r'`([^`]+)`',
                  rf'<font name="Mono" size="{SIZES["sm"]}">\1</font>', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)',
                  rf'<font name="Heading" color="{accent_hex}">→&nbsp;</font><font color="{accent_hex}">\1</font>', text)
    # Footnote references [^n] → amber superscript number
    text = re.sub(r'\[\^(\d+)\]',
                  rf'<super><font color="{accent_hex}">\1</font></super>', text)
    text = text.replace(' -- ', ' — ')
    text = text.replace('--', '—')
    return text


def parse_markdown(md_text, sem, styles, meta, variant='classic', duplex=True):
    """Parse Markdown text into ReportLab flowables.
    Supports: headings, blockquotes, code, bullets, numbered lists, tables,
    margin notes {>> text <<}, images ![cap](src), footnotes [^n], TOC [TOC]."""
    lines = md_text.split('\n')
    flowables = []
    toc_entries = []  # (level, text) for TOC
    footnotes = {}    # {number: text}
    i = 0
    in_code_block = False
    code_lines = []

    # Pre-scan for footnote definitions [^n]: text
    for line in lines:
        fn_def = re.match(r'^\[\^(\d+)\]:\s+(.+)$', line)
        if fn_def:
            footnotes[fn_def.group(1)] = fn_def.group(2)

    # Build cover page
    flowables.extend(_build_cover(meta, styles, sem))
    if duplex:
        flowables.append(NextPageTemplate('content_even'))
    else:
        flowables.append(NextPageTemplate('content_single'))
    flowables.append(PageBreak())

    while i < len(lines):
        line = lines[i]

        # Skip footnote definition lines (already collected)
        if re.match(r'^\[\^(\d+)\]:\s+', line):
            i += 1
            continue

        # Code blocks
        if line.strip().startswith('```'):
            if in_code_block:
                code_text = '<br/>'.join(
                    l.replace(' ', '&nbsp;').replace('<', '&lt;').replace('>', '&gt;')
                    for l in code_lines
                )
                flowables.append(Paragraph(code_text, styles['code']))
                flowables.append(Spacer(1, 2 * mm))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # TOC placeholder
        if line.strip() == '[TOC]':
            flowables.append(_TOC_PLACEHOLDER)  # Replaced after parsing
            i += 1
            continue

        # Margin notes: {>> text <<}
        # Attach to the PREVIOUS paragraph by retroactively wrapping it
        # in ParagraphWithMarginNote.  This guarantees the note aligns
        # with the paragraph it annotates (which precedes it in the MD).
        margin_match = re.match(r'^\{>>\s*(.+?)\s*<<\}$', line.strip())
        if margin_match:
            note_text = margin_match.group(1)
            # Walk backwards past any Spacers to find the actual content
            attach_idx = len(flowables) - 1
            while attach_idx >= 0 and isinstance(flowables[attach_idx], Spacer):
                attach_idx -= 1
            if attach_idx >= 0 and isinstance(flowables[attach_idx], Paragraph):
                prev = flowables[attach_idx]
                flowables[attach_idx] = ParagraphWithMarginNote(
                    prev, note_text, sem, variant=variant, duplex=duplex)
            elif attach_idx >= 0 and isinstance(flowables[attach_idx], KeepTogether):
                # H2 or similar group — wrap the whole group
                prev_kt = flowables[attach_idx]
                # Find last Paragraph inside the KeepTogether
                for ci in range(len(prev_kt._content) - 1, -1, -1):
                    if isinstance(prev_kt._content[ci], Paragraph):
                        prev_kt._content[ci] = ParagraphWithMarginNote(
                            prev_kt._content[ci], note_text, sem,
                            variant=variant, duplex=duplex)
                        break
            # else: note can't be attached — silently skip (edge case)
            i += 1
            continue

        # Image placeholder: ![caption](source "attribution")
        img_match = re.match(r'^!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)$', line.strip())
        if img_match:
            caption = img_match.group(1) or 'Abbildung'
            source = img_match.group(2) or ''
            attrib = img_match.group(3) or source
            flowables.append(Spacer(1, 3 * mm))
            flowables.append(ImagePlaceholder(
                f'<i>{caption}</i>', f'Quelle: {attrib}', sem))
            flowables.append(Spacer(1, 3 * mm))
            i += 1
            continue

        # Table: lines starting with |
        if line.strip().startswith('|') and '|' in line.strip()[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            # Check for table caption: next non-empty line starting with ^
            caption = None
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith('^'):
                caption = lines[i].strip().lstrip('^').strip()
                i += 1
            flowables.extend(_build_table(table_lines, caption, sem, styles))
            continue

        # Headings
        heading_match = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            raw_text = heading_match.group(2)
            text = inline_format(raw_text, sem)
            style_key = f'h{level}'

            # Collect for TOC
            if level in (2, 3):
                toc_entries.append((level, raw_text))

            # Editorial variant: H2 in Versalien (uppercase)
            if level == 2 and variant == 'editorial':
                text = text.upper()

            # H2 gets an amber underline + duplex-aware alignment
            # Wrapped in KeepTogether with a spacer to prevent lonely headings
            # Explicit spaceBefore OUTSIDE KeepTogether (KT can swallow it)
            if level == 2:
                h2_space_before = 12 * mm if variant == 'editorial' else 8 * mm
                flowables.append(Spacer(1, h2_space_before))
                h2_group = [
                    DuplexAwareH2(
                        text, styles[style_key], sem,
                        variant=variant, duplex=duplex,
                    ),
                    DuplexAwareH2Line(
                        sem, variant=variant, duplex=duplex,
                    ),
                    Spacer(1, 4 * mm),
                ]
                flowables.append(KeepTogether(h2_group))
            else:
                flowables.append(Paragraph(text, styles[style_key]))
            i += 1
            continue

        # Blockquotes
        if line.strip().startswith('>'):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                quote_lines.append(lines[i].strip().lstrip('>').strip())
                i += 1
            quote_text = '<br/>'.join(
                inline_format(ql, sem) for ql in quote_lines
            )
            flowables.append(Spacer(1, 2 * mm))
            flowables.append(AmberBlockquote(f'<i>{quote_text}</i>', sem, variant=variant))
            flowables.append(Spacer(1, 2 * mm))
            continue

        # Horizontal rule
        if re.match(r'^---+$', line.strip()) or re.match(r'^\*\*\*+$', line.strip()):
            flowables.append(HorizontalRule(sem))
            i += 1
            continue

        # Bullet points
        bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if bullet_match:
            indent = len(bullet_match.group(1)) // 2
            text = inline_format(bullet_match.group(2), sem)
            accent_hex = sem['accent'].hexval() if hasattr(sem['accent'], 'hexval') else '#A66B3A'
            if variant == 'editorial':
                bullet_char = '\u25C6'
                bullet_size = SIZES['sm'] - 1
                bullet_font_attr = ' name="Bullet-Ornament"'
            else:
                bullet_char = '\u2022'
                bullet_size = SIZES['base']
                bullet_font_attr = ''
            flowables.append(Paragraph(
                f'<bullet><font color="{accent_hex}" size="{bullet_size}"{bullet_font_attr}>{bullet_char}</font></bullet>{text}',
                ParagraphStyle(
                    'BulletItem',
                    parent=styles['bullet'],
                    leftIndent=8 * mm + indent * 6 * mm,
                    bulletIndent=2 * mm + indent * 6 * mm,
                )
            ))
            i += 1
            continue

        # Numbered list
        num_match = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if num_match:
            indent = len(num_match.group(1)) // 2
            num = num_match.group(2)
            text = inline_format(num_match.group(3), sem)
            accent_hex = sem['accent'].hexval() if hasattr(sem['accent'], 'hexval') else '#A66B3A'
            base_indent = 10 * mm + indent * 6 * mm
            num_size = SIZES['md'] if variant == 'editorial' else SIZES['base']
            flowables.append(Paragraph(
                f'<bullet><font color="{accent_hex}" size="{num_size}"><b>{num}.</b></font></bullet>{text}',
                ParagraphStyle(
                    'NumItem',
                    parent=styles['body'],
                    leftIndent=base_indent,
                    bulletIndent=base_indent - 8 * mm,
                    spaceAfter=1.5 * mm,
                )
            ))
            i += 1
            continue

        # Regular paragraph
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#') \
                and not lines[i].strip().startswith('>') and not lines[i].strip().startswith('```') \
                and not re.match(r'^[-*+]\s+', lines[i].strip()) \
                and not re.match(r'^\d+\.\s+', lines[i].strip()) \
                and not re.match(r'^---+$', lines[i].strip()) \
                and not lines[i].strip().startswith('|') \
                and not re.match(r'^\{>>', lines[i].strip()) \
                and not re.match(r'^!\[', lines[i].strip()) \
                and not re.match(r'^\[\^(\d+)\]:', lines[i].strip()):
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            text = inline_format(' '.join(para_lines), sem)
            flowables.append(Paragraph(text, styles['body']))

    # Replace TOC placeholder with actual TOC
    if toc_entries:
        toc_flowables = _build_toc(toc_entries, sem, styles, variant)
        if duplex:
            # Duplex: TOC on page 2 (even), then PageBreak so text
            # starts on page 3 (odd).  Switch to odd template after.
            toc_flowables.append(NextPageTemplate('content_odd'))
            toc_flowables.append(PageBreak())
        # else simplex: TOC flows directly into text (no extra break)
        for idx, f in enumerate(flowables):
            if f is _TOC_PLACEHOLDER:
                flowables[idx:idx+1] = toc_flowables
                break

    # Append endnotes if any footnotes exist
    if footnotes:
        flowables.append(Spacer(1, 6 * mm))
        flowables.append(HorizontalRule(sem))
        accent_hex = sem['accent'].hexval() if hasattr(sem['accent'], 'hexval') else '#A66B3A'
        for num in sorted(footnotes.keys(), key=int):
            fn_text = inline_format(footnotes[num], sem)
            flowables.append(Paragraph(
                f'<super><font color="{accent_hex}">{num}</font></super>&nbsp;&nbsp;{fn_text}',
                styles['footnote']
            ))

    return flowables


# Sentinel for TOC placeholder
_TOC_PLACEHOLDER = Spacer(1, 1)


def _build_toc(entries, sem, styles, variant):
    """Build Table of Contents flowables from collected heading entries."""
    toc = []
    accent_hex = sem['accent'].hexval() if hasattr(sem['accent'], 'hexval') else '#A66B3A'

    toc_title = 'INHALT' if variant == 'editorial' else 'Inhalt'
    toc.append(Paragraph(toc_title, ParagraphStyle(
        'TOCTitle', fontName='Heading-SemiBold', fontSize=SIZES['xl'],
        leading=SIZES['xl'] * LINE_HEIGHTS['heading'],
        textColor=sem['text-heading'], spaceAfter=4 * mm,
    )))

    for level, text in entries:
        style_key = 'toc-h2' if level == 2 else 'toc-h3'
        display = text.upper() if level == 2 and variant == 'editorial' else text
        toc.append(Paragraph(display, styles[style_key]))

    toc.append(Spacer(1, 6 * mm))
    toc.append(HorizontalRule(sem))
    toc.append(Spacer(1, 4 * mm))
    return toc


def _build_table(table_lines, caption, sem, styles):
    """Parse Markdown table lines into ReportLab Table + optional caption."""
    flowables = []
    rows = []
    is_header_next = True

    for line in table_lines:
        cells = [c.strip() for c in line.strip('|').split('|')]
        # Skip separator line (---+)
        if all(re.match(r'^[-:]+$', c) for c in cells):
            is_header_next = False
            continue
        rows.append((cells, is_header_next))
        if is_header_next:
            is_header_next = False  # Only first row is header

    if not rows:
        return flowables

    # Build table data with styled Paragraphs
    table_data = []
    for cells, is_header in rows:
        style = styles['table-header'] if is_header else styles['table-cell']
        row = [Paragraph(c, style) for c in cells]
        table_data.append(row)

    # Create table
    num_cols = max(len(r) for r, _ in rows)
    col_widths = None  # Auto-calculate

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), sem['bg-card']),
        ('TEXTCOLOR', (0, 0), (-1, 0), sem['text-heading']),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, 0), 0.75, sem['accent']),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, sem['border-subtle']),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, sem['border']),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    flowables.append(Spacer(1, 3 * mm))
    flowables.append(t)
    if caption:
        flowables.append(Paragraph(f'<i>{caption}</i>', styles['table-caption']))
    flowables.append(Spacer(1, 3 * mm))
    return flowables


def _build_cover(meta, styles, sem):
    """Build cover page flowables (spacer only — text drawn on canvas)."""
    return [Spacer(1, 1)]


# ═══════════════════════════════════════════════════════════════════════
# METADATA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

def extract_meta(md_text, args):
    """Extract metadata from YAML frontmatter or first heading."""
    meta = {
        'title': args.title or 'Dokument',
        'subtitle': args.subtitle or '',
        'author': args.author or 'Constantin Ehrenstein',
        'date': args.date or datetime.now().strftime('%B %Y'),
        'doc_type': args.type or '',
    }

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', md_text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for key in ['title', 'subtitle', 'author', 'date', 'type']:
            m = re.search(rf'^{key}:\s*(.+)$', fm, re.MULTILINE)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
                if key == 'type':
                    meta['doc_type'] = val
                else:
                    meta[key] = val

    if meta['title'] == 'Dokument':
        h1_match = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
        if h1_match:
            meta['title'] = h1_match.group(1)

    # Header text — doc type + short title
    header_parts = []
    if meta['doc_type']:
        header_parts.append(meta['doc_type'])
    title_short = meta['title'][:40] + '…' if len(meta['title']) > 40 else meta['title']
    header_parts.append(title_short)
    meta['header_text'] = ' · '.join(header_parts)

    # Footer text — author + date
    footer_parts = []
    if meta['author']:
        footer_parts.append(meta['author'])
    if meta['date']:
        footer_parts.append(meta['date'])
    meta['footer_text'] = ' · '.join(footer_parts)

    return meta


def strip_frontmatter(md_text):
    """Remove YAML frontmatter from markdown."""
    return re.sub(r'^---\s*\n.*?\n---\s*\n', '', md_text, count=1, flags=re.DOTALL)


# ═══════════════════════════════════════════════════════════════════════
# NUMBERED CANVAS — "Seite X von Y" without post-processing
# ═══════════════════════════════════════════════════════════════════════

class NumberedCanvas(canvas.Canvas):
    """Canvas subclass that supports 'Page X of Y' by deferring page output.
    After all pages are rendered, it goes back and writes the total count.
    Page numbers are placed on the outside edge (duplex-aware)."""

    # Class-level flags, set before build() via make_numbered_canvas()
    duplex = True
    m_outside = None  # Override for editorial outside margin

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        """Draw 'Seite X von Y' on content pages (skips cover).
        Page number on outside edge (duplex) or always right (simplex)."""
        pn = self._pageNumber
        dx = self.__class__.duplex
        mo = self.__class__.m_outside
        if pn > 1:  # Skip cover page
            page_text = f"Seite {pn} von {page_count}"
            self.setFont('Body', SIZES['xs'])
            self.setFillColor(COLORS['payne-classic'])

            if not dx:
                # Single-sided: page number always on right (outside)
                self.drawRightString(PAGE_W - margin_right(pn, dx, mo), FOOTER_TEXT_Y, page_text)
            elif pn % 2 == 1:  # Duplex odd: outside = right → page num right
                self.drawRightString(PAGE_W - margin_right(pn, dx, mo), FOOTER_TEXT_Y, page_text)
            else:              # Duplex even: outside = left → page num left
                self.drawString(margin_left(pn, dx, mo), FOOTER_TEXT_Y, page_text)


def make_numbered_canvas(duplex=True, m_outside=None):
    """Factory: create a NumberedCanvas subclass with the correct settings."""
    class ConfiguredCanvas(NumberedCanvas):
        pass
    ConfiguredCanvas.duplex = duplex
    ConfiguredCanvas.m_outside = m_outside
    return ConfiguredCanvas


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Payne & Amber — Markdown → CI-konformes PDF'
    )
    parser.add_argument('input', help='Markdown input file')
    parser.add_argument('output', nargs='?', help='PDF output file (default: input with .pdf)')
    parser.add_argument('--author', default=None, help='Author name')
    parser.add_argument('--date', default=None, help='Date string')
    parser.add_argument('--title', default=None, help='Document title (overrides frontmatter/H1)')
    parser.add_argument('--subtitle', default=None, help='Subtitle')
    parser.add_argument('--type', default=None,
                        help='Document type (Recherche, Konzept, Show Notes, etc.)')
    parser.add_argument('--variant', choices=['classic', 'editorial'], default='classic',
                        help='Layout variant (default: classic)')
    parser.add_argument('--sides', choices=['single', 'double'], default='double',
                        help='Printing sides: single (binding always left) or double (Druckbogen, default)')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found.")
        sys.exit(1)

    md_text = input_path.read_text(encoding='utf-8')

    # If no output specified, generate both variants
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix('.pdf')

    sem = SEMANTIC_PRINT
    duplex = (args.sides == 'double')
    meta = extract_meta(md_text, args)
    content = strip_frontmatter(md_text)
    content = re.sub(r'^#\s+' + re.escape(meta['title']) + r'\s*\n', '', content, count=1)

    print(f"Payne & Amber PDF Generator")
    print(f"  Input:    {input_path}")
    print(f"  Output:   {output_path}")
    print(f"  Title:    {meta['title']}")
    print(f"  Variant:  {args.variant}")
    print(f"  Sides:    {args.sides} ({'Druckbogen' if duplex else 'Simplex'})")

    register_fonts()
    m_outside = MARGIN_OUTSIDE_EDITORIAL if args.variant == 'editorial' else MARGIN_OUTSIDE
    styles = build_styles(sem, variant=args.variant)
    flowables = parse_markdown(content, sem, styles, meta, variant=args.variant, duplex=duplex)

    canvas_cls = make_numbered_canvas(duplex=duplex, m_outside=m_outside)
    doc = PaineAmberDocTemplate(str(output_path), meta, sem, variant=args.variant, duplex=duplex)
    doc.build(flowables, canvasmaker=canvas_cls)

    print(f"  ✓ PDF generated: {output_path}")
    return str(output_path)


if __name__ == '__main__':
    main()
