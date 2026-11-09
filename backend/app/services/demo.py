from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.platform import add_document, create_case, get_case
from starlette.datastructures import Headers, UploadFile


def _pdf(title: str, lines: list[str]) -> bytes:
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setTitle(title)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(60, 780, title)
    page.setFont("Helvetica", 11)
    for index, line in enumerate(lines):
        page.drawString(60, 740 - index * 24, line)
    page.save()
    return buffer.getvalue()


async def create_demo_case() -> dict:
    case = create_case("Synthetic consistency review", "DEMO-001", "Synthetic documents for a safe live demonstration.", "general")
    documents = [
        ("identity-demo.pdf", ["Synthetic Identity Document", "Full Name: Asha Mehta", "Date of Birth: 1992-04-18", "Address: 14 Lake Road"]),
        ("bank-demo.pdf", ["Synthetic Bank Statement", "Account Holder: Asha Mehta", "Account Number: 1234567890", "Transaction Amount: INR 12500"]),
        ("application-demo.pdf", ["Synthetic Application Form", "Applicant: Asha Mehta", "Date of Birth: 1992-04-18", "Address: 99 Market Street", "Invoice Number: INV-2026-001"]),
    ]
    for filename, lines in documents:
        upload = UploadFile(filename=filename, file=BytesIO(_pdf(filename, lines)), headers=Headers({"content-type": "application/pdf"}))
        await add_document(case["id"], upload)
    return get_case(case["id"])
