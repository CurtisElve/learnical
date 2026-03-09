"""FastAPI app entrypoint with SQLModel."""

import io
import warnings
from contextlib import asynccontextmanager
import torch
from fastapi import Depends, File, FastAPI, UploadFile
from PIL import Image
from sqlmodel import Session, select
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- device ---
device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

# --- load model once at module level ---
_processor = AutoProcessor.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    min_pixels=256 * 28 * 28,   # floor: don't over-shrink small images
    max_pixels=512 * 28 * 28,   # cap: biggest win for CPU speed
)
_model = Qwen2VLForConditionalGeneration.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    torch_dtype=torch.float16,  # half precision, cuts memory ~50%
    device_map="auto",
)
_model.eval()  # disable dropout etc, slight speedup on inference


def run_ocr(image: Image.Image) -> str:
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": "Transcribe every word you see in this image. Output only the transcribed text, nothing else."},
        ],
    }]

    text = _processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = _processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():  # don't track gradients, saves memory + speed
        generated_ids = _model.generate(**inputs, max_new_tokens=64)

    generated_ids_trimmed = [
        out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)
    ]
    return _processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0].strip()


from database import engine, get_session
from models import Example, OCRResult, SQLModel


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Learnical", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/examples")
def list_examples(session: Session = Depends(get_session)):
    return {"examples": session.exec(select(Example)).all()}


@app.post("/examples")
def create_example(example: Example, session: Session = Depends(get_session)):
    session.add(example)
    session.commit()
    session.refresh(example)
    return example


@app.post("/ocr", response_model=OCRResult)
async def ocr(file: UploadFile = File(..., description="Image or PDF file")):
    content = await file.read()
    content_type = (file.content_type or "").lower()

    if content_type == "application/pdf":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(content)
        parts = [pytesseract.image_to_string(page) for page in pages]
        text = "\n\n".join(parts).strip()
    else:
        image = Image.open(io.BytesIO(content)).convert("RGB")
        text = run_ocr(image)

    return OCRResult(text=text)