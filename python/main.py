"""FastAPI app entrypoint with SQLModel."""

import io
from contextlib import asynccontextmanager

from fastapi import Depends, File, FastAPI, UploadFile
from PIL import Image
from sqlmodel import Session, select
from transformers import pipeline

import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from database import engine, get_session
from models import Example, OCRResult, SQLModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Learnical", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/examples")
def list_examples(session: Session = Depends(get_session)):
    stmt = select(Example)
    examples = session.exec(stmt).all()
    return {"examples": examples}


@app.post("/examples")
def create_example(example: Example, session: Session = Depends(get_session)):
    session.add(example)
    session.commit()
    session.refresh(example)
    return example


@app.post("/ocr", response_model=OCRResult)
async def ocr(file: UploadFile = File(..., description="Image or PDF file")):
    """Extract text from an uploaded image (PNG, JPEG, etc.) or PDF using Tesseract OCR."""
    content = await file.read()
    content_type = (file.content_type or "").lower()

    if content_type == "application/pdf":
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(content)
        parts = []
        for page in pages:
            parts.append(pytesseract.image_to_string(page))
        text = "\n\n".join(parts).strip()
    else:
        # Treat as image (png, jpeg, webp, gif, etc.)
        image = Image.open(io.BytesIO(content))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        text = pytesseract.image_to_string(image).strip()

    return OCRResult(text=text or "")
