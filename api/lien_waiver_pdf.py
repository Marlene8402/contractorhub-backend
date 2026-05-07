"""Lien-waiver PDF generator.

Renders statutorily-correct lien waiver forms. Currently supports
Florida (Fla. Stat. §713.20). California / Texas / New York will land
in follow-ups.

Florida statute provides only TWO forms (not four like CA): one for
progress payments (§713.20(4)) and one for final payment (§713.20(5)).
There's no statutory conditional/unconditional distinction; the
'conditional on check' behavior is a one-line rider authorized by
§713.20(7) that we append below the signature when
LienWaiver.conditional_on_check is True.

Verbatim statutory language is preserved word-for-word — see
LIEN_WAIVER_RESEARCH_FL.md for the source extracts.

The output is a BytesIO of PDF bytes; callers stream it via
HttpResponse with content_type='application/pdf'.
"""
import io
from decimal import Decimal

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib import colors


def _styles():
    """Return a small style dict shared by both FL forms."""
    s = getSampleStyleSheet()
    title = ParagraphStyle(
        'Title', parent=s['Title'], fontName='Helvetica-Bold',
        fontSize=14, alignment=1, spaceAfter=18,
    )
    body = ParagraphStyle(
        'Body', parent=s['BodyText'], fontName='Helvetica',
        fontSize=11, leading=14, spaceAfter=10,
    )
    body_emph = ParagraphStyle(
        'BodyEmph', parent=body, fontName='Helvetica-Bold',
    )
    sig = ParagraphStyle(
        'Sig', parent=body, alignment=2, spaceBefore=20,
    )
    notice = ParagraphStyle(
        'Notice', parent=body, fontSize=9, leading=11,
        textColor=colors.grey, spaceBefore=18,
    )
    rider = ParagraphStyle(
        'Rider', parent=body, fontSize=10, leading=13,
        leftIndent=12, rightIndent=12, spaceBefore=10,
        textColor=colors.HexColor('#222222'),
    )
    return {'title': title, 'body': body, 'body_emph': body_emph,
            'sig': sig, 'notice': notice, 'rider': rider}


def _money(d):
    """Format Decimal/None as $X,XXX.XX. None → underscores."""
    if d is None:
        return '____________'
    return f"${Decimal(d):,.2f}"


def _date(d):
    """Format date or fallback to underscores."""
    if d is None:
        return '__________'
    return d.strftime('%B %d, %Y')


def _conditional_rider(lw, st):
    """Optional Fla. Stat. §713.20(7) check-conditional rider. Returns
    a Paragraph or None. Appended to the waiver form when
    LienWaiver.conditional_on_check is True."""
    if not lw.conditional_on_check:
        return None
    bank = (lw.check_bank or '____________').rstrip('.')
    text = (
        "<b>CONDITION:</b> This waiver and release is conditioned on "
        f"payment of check no. <b>{lw.check_number or '____'}</b> in "
        f"the amount of <b>{_money(lw.check_amount)}</b>, dated "
        f"<b>{_date(lw.check_date)}</b>, drawn on "
        f"<b>{bank}</b>. "
        "If the check is dishonored, this waiver and release shall be "
        "null and void."
    )
    return Paragraph(text, st['rider'])


def _signature_block(lw, st):
    """Standard signature block: lienor name + 'By:' line + date."""
    lienor = lw.claimant_name or '____________'
    by = lw.signed_by or '________________________'
    signed_date = _date(lw.signed_date)
    block = (
        f"<para alignment='right'>"
        f"DATED on {signed_date}.<br/><br/>"
        f"<b>{lienor}</b><br/>"
        f"By: {by}"
        f"</para>"
    )
    return Paragraph(block, st['body'])


def _property_description(lw):
    """Best property description we have for the form. Job address is
    the typical fallback when there's no formal legal description.
    Newlines in the source become <br/> in the rendered Paragraph so
    multi-line descriptions (street + legal description) wrap cleanly."""
    raw = lw.job_address or lw.job_description or '____________________'
    return raw.replace('\n', '<br/>')


def render_fl_progress(lw) -> io.BytesIO:
    """Florida Statute §713.20(4) — Waiver and Release of Lien Upon
    Progress Payment. Verbatim statutory language."""
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=1*inch, bottomMargin=1*inch,
        title=f"FL Lien Waiver (Progress) — {lw.claimant_name}",
    )
    flow = []
    flow.append(Paragraph(
        "WAIVER AND RELEASE OF LIEN UPON PROGRESS PAYMENT",
        st['title'],
    ))
    body = (
        f"The undersigned lienor, in consideration of the sum of "
        f"<b>{_money(lw.amount)}</b>, hereby waives and releases its "
        f"lien and right to claim a lien for labor, services, or "
        f"materials furnished through "
        f"<b>{_date(lw.through_date)}</b> to "
        f"<b>{lw.customer_name or '____________'}</b> on the job of "
        f"<b>{lw.owner_name or '____________'}</b> to the following "
        f"property:"
    )
    flow.append(Paragraph(body, st['body']))
    flow.append(Paragraph(
        f"<i>{_property_description(lw)}</i>", st['body'],
    ))
    flow.append(Paragraph(
        "This waiver and release does not cover any retention or "
        "labor, services, or materials furnished after the date "
        "specified.",
        st['body'],
    ))
    flow.append(_signature_block(lw, st))
    rider = _conditional_rider(lw, st)
    if rider is not None:
        flow.append(rider)
    flow.append(Paragraph(
        "Form: Fla. Stat. §713.20(4). This is the statutory form; "
        "per §713.20(6), the owner/customer cannot require a "
        "different form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


def render_fl_final(lw) -> io.BytesIO:
    """Florida Statute §713.20(5) — Waiver and Release of Lien Upon
    Final Payment. Verbatim statutory language."""
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=1*inch, bottomMargin=1*inch,
        title=f"FL Lien Waiver (Final) — {lw.claimant_name}",
    )
    flow = []
    flow.append(Paragraph(
        "WAIVER AND RELEASE OF LIEN UPON FINAL PAYMENT",
        st['title'],
    ))
    body = (
        f"The undersigned lienor, in consideration of the final "
        f"payment in the amount of <b>{_money(lw.amount)}</b>, "
        f"hereby waives and releases its lien and right to claim a "
        f"lien for labor, services, or materials furnished to "
        f"<b>{lw.customer_name or '____________'}</b> on the job of "
        f"<b>{lw.owner_name or '____________'}</b> to the following "
        f"described property:"
    )
    flow.append(Paragraph(body, st['body']))
    flow.append(Paragraph(
        f"<i>{_property_description(lw)}</i>", st['body'],
    ))
    flow.append(_signature_block(lw, st))
    rider = _conditional_rider(lw, st)
    if rider is not None:
        flow.append(rider)
    flow.append(Paragraph(
        "Form: Fla. Stat. §713.20(5). This is the statutory form; "
        "per §713.20(6), the owner/customer cannot require a "
        "different form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


# Map: (state, waiver_type) -> renderer function
_RENDERERS = {
    ('FL', 'cond_partial'):   render_fl_progress,
    ('FL', 'uncond_partial'): render_fl_progress,
    ('FL', 'cond_final'):     render_fl_final,
    ('FL', 'uncond_final'):   render_fl_final,
}


class LienWaiverRenderError(Exception):
    """Raised when no renderer matches the (state, waiver_type)."""


def render_pdf(lw) -> io.BytesIO:
    """Dispatch to the right renderer based on lw.state + lw.waiver_type.
    Raises LienWaiverRenderError if no matching renderer exists yet."""
    fn = _RENDERERS.get((lw.state, lw.waiver_type))
    if fn is None:
        raise LienWaiverRenderError(
            f"No PDF renderer for state={lw.state!r} "
            f"waiver_type={lw.waiver_type!r}. "
            f"Currently supported: FL (all 4 waiver_type values)."
        )
    return fn(lw)
