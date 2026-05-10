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
    """Return a small style dict shared by all renderers."""
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
    # CA NOTICE preamble — statute requires "at least as large type as
    # the largest type otherwise in the form." We size it equal to the
    # title (14pt bold), boxed to make it visually unmissable.
    ca_notice = ParagraphStyle(
        'CANotice', parent=body, fontName='Helvetica-Bold',
        fontSize=12, leading=15, alignment=1,
        spaceBefore=4, spaceAfter=14,
        borderColor=colors.black, borderWidth=1.5,
        borderPadding=10, backColor=colors.HexColor('#FFF4D6'),
    )
    section_label = ParagraphStyle(
        'SectionLabel', parent=body, fontName='Helvetica-Bold',
        fontSize=11, spaceBefore=10, spaceAfter=4,
    )
    field_line = ParagraphStyle(
        'FieldLine', parent=body, fontSize=10, leading=14,
        spaceAfter=2, leftIndent=8,
    )
    return {'title': title, 'body': body, 'body_emph': body_emph,
            'sig': sig, 'notice': notice, 'rider': rider,
            'ca_notice': ca_notice, 'section_label': section_label,
            'field_line': field_line}


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


# =============================================================================
# California — Cal. Civ. Code §§8132, 8134, 8136, 8138
# =============================================================================
#
# CA's statutory regime has FOUR forms (vs FL's two): conditional vs
# unconditional × progress vs final. The forms are MANDATORY when the
# claimant is required to execute a waiver — not merely safe-harbor.
# Per §8132(a): "shall be null, void, and unenforceable unless it is
# in substantially the form."
#
# Two NOTICE preambles:
#   - Conditional forms (§§8132, 8136): single sentence, on-receipt-of-payment
#   - Unconditional forms (§§8134, 8138): three sentences, paid-in-full warning
#
# Statutory requirement: the notice "shall appear in at least as large
# a type as the largest type otherwise in the form." We render it
# 12pt bold inside a boxed yellow background to satisfy this.

_CA_NOTICE_CONDITIONAL = (
    "NOTICE: THIS DOCUMENT WAIVES THE CLAIMANT'S LIEN, STOP PAYMENT "
    "NOTICE, AND PAYMENT BOND RIGHTS EFFECTIVE ON RECEIPT OF PAYMENT. "
    "A PERSON SHOULD NOT RELY ON THIS DOCUMENT UNLESS SATISFIED THAT "
    "THE CLAIMANT HAS RECEIVED PAYMENT."
)
_CA_NOTICE_UNCONDITIONAL = (
    "NOTICE TO CLAIMANT: THIS DOCUMENT WAIVES AND RELEASES LIEN, "
    "STOP PAYMENT NOTICE, AND PAYMENT BOND RIGHTS UNCONDITIONALLY "
    "AND STATES THAT YOU HAVE BEEN PAID FOR GIVING UP THOSE RIGHTS. "
    "THIS DOCUMENT IS ENFORCEABLE AGAINST YOU IF YOU SIGN IT, EVEN "
    "IF YOU HAVE NOT BEEN PAID. IF YOU HAVE NOT BEEN PAID, USE A "
    "CONDITIONAL WAIVER AND RELEASE FORM."
)


def _ca_id_block(lw, st, include_through_date: bool):
    """California §§8132/8134/8136/8138 'Identifying Information'
    section. Progress forms include Through Date; final forms do not."""
    flow = [Paragraph("<b>Identifying Information</b>", st['section_label'])]
    fields = [
        ('Name of Claimant',  lw.claimant_name or '____________________'),
        ('Name of Customer',  lw.customer_name or '____________________'),
        ('Job Location',      lw.job_address or '____________________'),
        ('Owner',             lw.owner_name or '____________________'),
    ]
    if include_through_date:
        fields.append(('Through Date', _date(lw.through_date)))
    for label, value in fields:
        flow.append(Paragraph(
            f"{label}: <b>{value}</b>", st['field_line'],
        ))
    return flow


def _ca_check_block(lw, st):
    """§§8132/8136 — check info on conditional forms only."""
    flow = [Paragraph(
        "This document is effective only on the claimant's receipt "
        "of payment from the financial institution on which the "
        "following check is drawn:",
        st['body'],
    )]
    fields = [
        ('Maker of Check',  lw.check_bank or '____________________'),
        ('Amount of Check', _money(lw.check_amount)),
        ('Check Payable to', lw.claimant_name or '____________________'),
    ]
    for label, value in fields:
        flow.append(Paragraph(
            f"{label}: <b>{value}</b>", st['field_line'],
        ))
    return flow


def _ca_signature(lw, st):
    """§§8132/8134/8136/8138 signature block — same across all four."""
    return [
        Paragraph("<b>Signature</b>", st['section_label']),
        Paragraph(
            f"Claimant's Signature: <b>{lw.signed_by or '____________________'}</b>",
            st['field_line'],
        ),
        Paragraph(
            f"Claimant's Title: ____________________",
            st['field_line'],
        ),
        Paragraph(
            f"Date of Signature: <b>{_date(lw.signed_date)}</b>",
            st['field_line'],
        ),
    ]


def _ca_doc(buf, lw, title_text):
    """Shared SimpleDocTemplate factory for CA forms."""
    return SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        title=f"CA {title_text} — {lw.claimant_name}",
    )


def render_ca_cond_progress(lw) -> io.BytesIO:
    """Cal. Civ. Code §8132 — Conditional Waiver and Release on
    Progress Payment. Verbatim statutory form."""
    st = _styles()
    buf = io.BytesIO()
    doc = _ca_doc(buf, lw, "Conditional Waiver (Progress)")
    flow = [
        Paragraph("CONDITIONAL WAIVER AND RELEASE ON PROGRESS PAYMENT",
                   st['title']),
        Paragraph(_CA_NOTICE_CONDITIONAL, st['ca_notice']),
    ]
    flow.extend(_ca_id_block(lw, st, include_through_date=True))
    flow.append(Paragraph("<b>Conditional Waiver and Release</b>",
                          st['section_label']))
    flow.append(Paragraph(
        "This document waives and releases lien, stop payment notice, "
        "and payment bond rights the claimant has for labor and "
        "service provided, and equipment and material delivered, to "
        "the customer on this job through the Through Date of this "
        "document.",
        st['body'],
    ))
    flow.extend(_ca_check_block(lw, st))
    flow.append(Paragraph("<b>Exceptions</b>", st['section_label']))
    flow.append(Paragraph(
        "This document does not affect any of the following:",
        st['body'],
    ))
    for txt in (
        "(1) Retentions.",
        "(2) Extras for which the claimant has not received payment.",
        "(3) The following progress payments for which the claimant "
        "has previously given a conditional waiver and release but "
        "has not received payment: ____________________",
        "(4) Contract rights, including (A) a right based on "
        "rescission, abandonment, or breach of contract, and (B) "
        "the right to recover compensation for work not compensated "
        "by the payment.",
    ):
        flow.append(Paragraph(txt, st['field_line']))
    flow.extend(_ca_signature(lw, st))
    flow.append(Paragraph(
        "Form: Cal. Civ. Code §8132. Mandatory statutory form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


def render_ca_uncond_progress(lw) -> io.BytesIO:
    """Cal. Civ. Code §8134 — Unconditional Waiver and Release on
    Progress Payment. Verbatim statutory form."""
    st = _styles()
    buf = io.BytesIO()
    doc = _ca_doc(buf, lw, "Unconditional Waiver (Progress)")
    flow = [
        Paragraph("UNCONDITIONAL WAIVER AND RELEASE ON PROGRESS PAYMENT",
                   st['title']),
        Paragraph(_CA_NOTICE_UNCONDITIONAL, st['ca_notice']),
    ]
    flow.extend(_ca_id_block(lw, st, include_through_date=True))
    flow.append(Paragraph("<b>Unconditional Waiver and Release</b>",
                          st['section_label']))
    flow.append(Paragraph(
        "This document waives and releases lien, stop payment notice, "
        "and payment bond rights the claimant has for labor and "
        "service provided, and equipment and material delivered, to "
        "the customer on this job through the Through Date of this "
        "document. The claimant has received the following progress "
        f"payment: <b>{_money(lw.amount)}</b>.",
        st['body'],
    ))
    flow.append(Paragraph("<b>Exceptions</b>", st['section_label']))
    flow.append(Paragraph(
        "This document does not affect any of the following:",
        st['body'],
    ))
    for txt in (
        "(1) Retentions.",
        "(2) Extras for which the claimant has not received payment.",
        "(3) Contract rights, including (A) a right based on "
        "rescission, abandonment, or breach of contract, and (B) "
        "the right to recover compensation for work not compensated "
        "by the payment.",
    ):
        flow.append(Paragraph(txt, st['field_line']))
    flow.extend(_ca_signature(lw, st))
    flow.append(Paragraph(
        "Form: Cal. Civ. Code §8134. Mandatory statutory form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


def render_ca_cond_final(lw) -> io.BytesIO:
    """Cal. Civ. Code §8136 — Conditional Waiver and Release on
    Final Payment. Verbatim statutory form."""
    st = _styles()
    buf = io.BytesIO()
    doc = _ca_doc(buf, lw, "Conditional Waiver (Final)")
    flow = [
        Paragraph("CONDITIONAL WAIVER AND RELEASE ON FINAL PAYMENT",
                   st['title']),
        Paragraph(_CA_NOTICE_CONDITIONAL, st['ca_notice']),
    ]
    # Final forms omit Through Date.
    flow.extend(_ca_id_block(lw, st, include_through_date=False))
    flow.append(Paragraph("<b>Conditional Waiver and Release</b>",
                          st['section_label']))
    flow.append(Paragraph(
        "This document waives and releases lien, stop payment notice, "
        "and payment bond rights the claimant has for labor and "
        "service provided, and equipment and material delivered, to "
        "the customer on this job. Rights based upon labor or service "
        "provided, or equipment or material delivered, pursuant to a "
        "written change order that has been fully executed by the "
        "parties prior to the date that this document is signed by "
        "the claimant, are waived and released by this document, "
        "unless listed as an Exception below.",
        st['body'],
    ))
    flow.extend(_ca_check_block(lw, st))
    flow.append(Paragraph("<b>Exceptions</b>", st['section_label']))
    flow.append(Paragraph(
        "This document does not affect any of the following:",
        st['body'],
    ))
    flow.append(Paragraph(
        "Disputed claims for extras in the amount of: ____________________",
        st['field_line'],
    ))
    flow.extend(_ca_signature(lw, st))
    flow.append(Paragraph(
        "Form: Cal. Civ. Code §8136. Mandatory statutory form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


def render_ca_uncond_final(lw) -> io.BytesIO:
    """Cal. Civ. Code §8138 — Unconditional Waiver and Release on
    Final Payment. Verbatim statutory form."""
    st = _styles()
    buf = io.BytesIO()
    doc = _ca_doc(buf, lw, "Unconditional Waiver (Final)")
    flow = [
        Paragraph("UNCONDITIONAL WAIVER AND RELEASE ON FINAL PAYMENT",
                   st['title']),
        Paragraph(_CA_NOTICE_UNCONDITIONAL, st['ca_notice']),
    ]
    flow.extend(_ca_id_block(lw, st, include_through_date=False))
    flow.append(Paragraph("<b>Unconditional Waiver and Release</b>",
                          st['section_label']))
    flow.append(Paragraph(
        "This document waives and releases lien, stop payment notice, "
        "and payment bond rights the claimant has for all labor and "
        "service provided, and equipment and material delivered, to "
        "the customer on this job. Rights based upon labor or service "
        "provided, or equipment or material delivered, pursuant to a "
        "written change order that has been fully executed by the "
        "parties prior to the date that this document is signed by "
        "the claimant, are waived and released by this document, "
        "unless listed as an Exception below. The claimant has been "
        "paid in full.",
        st['body'],
    ))
    flow.append(Paragraph("<b>Exceptions</b>", st['section_label']))
    flow.append(Paragraph(
        "This document does not affect the following:",
        st['body'],
    ))
    flow.append(Paragraph(
        "Disputed claims for extras in the amount of: ____________________",
        st['field_line'],
    ))
    flow.extend(_ca_signature(lw, st))
    flow.append(Paragraph(
        "Form: Cal. Civ. Code §8138. Mandatory statutory form.",
        st['notice'],
    ))
    doc.build(flow)
    buf.seek(0)
    return buf


# Map: (state, waiver_type) -> renderer function
_RENDERERS = {
    # Florida — §713.20 (2 forms; CA-style waiver_type values map onto
    # them: progress = partial, final = final; conditional behavior
    # via the §713.20(7) check rider).
    ('FL', 'cond_partial'):   render_fl_progress,
    ('FL', 'uncond_partial'): render_fl_progress,
    ('FL', 'cond_final'):     render_fl_final,
    ('FL', 'uncond_final'):   render_fl_final,
    # California — §§8132, 8134, 8136, 8138 (4 mandatory forms, 1:1
    # with our waiver_type enum).
    ('CA', 'cond_partial'):   render_ca_cond_progress,
    ('CA', 'uncond_partial'): render_ca_uncond_progress,
    ('CA', 'cond_final'):     render_ca_cond_final,
    ('CA', 'uncond_final'):   render_ca_uncond_final,
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
            f"Currently supported: FL, CA (all 4 waiver_type values each)."
        )
    return fn(lw)
