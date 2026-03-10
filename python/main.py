"""FastAPI app entrypoint with SQLModel."""
import os
import io
import warnings
from contextlib import asynccontextmanager

import torch
from fastapi import Depends, File, FastAPI, HTTPException, UploadFile
from PIL import Image
from sqlmodel import Session, select
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

from qwen_vl_utils import process_vision_info

warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")

import pytesseract
import json
import anthropic
import base64
_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- device ---
device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

# --- load model once at module level ---
_processor = AutoProcessor.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    min_pixels=256 * 28 * 28,  # floor: don't over-shrink small images
    max_pixels=1280 * 28 * 28,  # cap: biggest win for CPU speed
)
_model = Qwen2VLForConditionalGeneration.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    torch_dtype=torch.float16,  # half precision, cuts memory ~50%
    device_map="auto",
)
_model.eval()  # disable dropout etc, slight speedup on inference


def run_ocr(image: Image.Image) -> str:
    """Generic OCR helper using the local Qwen model."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {
                    "type": "text",
                    "text": "Transcribe every word and symbol you see in this image. "
                    "Output only the transcribed text, nothing else.",
                },
            ],
        }
    ]

    text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)
    inputs = _processor(
        text=[text],
        images=image_inputs,
        videos=None,
        padding=True,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():  # don't track gradients, saves memory + speed
        generated_ids = _model.generate(**inputs, max_new_tokens=512)

    generated_ids_trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated_ids)]
    return _processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0].strip()


from database import engine, get_session
from models import Example, OCRResult, SQLModel, Student, StudentWorksheet, Worksheet


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup, using the shared engine from database.py
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


@app.post("/students", response_model=Student)
def create_student(student: Student, session: Session = Depends(get_session)) -> Student:
    """Create a new student profile."""
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@app.get("/students/{student_id}", response_model=Student)
def get_student(student_id: int, session: Session = Depends(get_session)) -> Student:
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@app.post("/worksheets", response_model=Worksheet)
def create_worksheet(worksheet: Worksheet, session: Session = Depends(get_session)) -> Worksheet:
    """Create a worksheet definition, including questions JSON."""
    session.add(worksheet)
    session.commit()
    session.refresh(worksheet)
    return worksheet


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


def build_grading_payload(worksheet: Worksheet, image_b64: str) -> dict:
    """Shape sent to the grading AI."""
    return {
        "worksheet_id": worksheet.id,
        "worksheet_identifier": worksheet.identifier,
        "subject": worksheet.subject,
        "questions": worksheet.questions,
        "image_b64": image_b64,
    }


def call_grader(payload: dict) -> dict:
    questions_str = json.dumps(payload["questions"], indent=2)
    image_b64 = payload["image_b64"]

    system_prompt = (
        "You are a strict but fair teacher grading a handwritten worksheet. "
        "You can see the original printed worksheet image and know the canonical questions and correct answers. "
        "Grade the student's handwritten work directly from the image — do not rely solely on any OCR or assumptions. "
        "Be concise with feedback and focus on mathematical correctness and the specific learning skills."
    )

    user_text = f"""
Subject: {payload["subject"]}

Here are the questions and correct answers as structured JSON:
{questions_str}

Using ONLY the student's handwritten work visible in the attached image, detect what the student wrote for each question,
grade it, and return ONLY a JSON object in exactly this format, with no extra text or markdown:
{{
  "questions": [
    {{
      "question_id": 1,
      "student_answer": "what the student actually wrote",
      "score": 0.8,
      "max_score": 1.0,
      "feedback": "short feedback string about this one question"
    }}
  ],
  "total_score": 0.75,
  "max_score": 5.0
}}
"""

    response = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": user_text,
                    },
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


@app.post("/grade", response_model=StudentWorksheet)
async def grade_worksheet(
    worksheet_id: int,
    student_id: int,
    file: UploadFile = File(..., description="Worksheet image to grade"),
    session: Session = Depends(get_session),
) -> StudentWorksheet:
    """
    Grade a worksheet image for a given student.

    This endpoint:
    - Fetches the Worksheet + Student from the DB
    - Runs OCR on the uploaded image
    - Sends a structured payload to the grader
    - Persists a StudentWorksheet row with per-question marks
    """
    worksheet = session.get(Worksheet, worksheet_id)
    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Read the uploaded image and send it directly to the grader (no local OCR in this flow)
    content = await file.read()
    image_b64 = base64.b64encode(content).decode("utf-8")

    # Prepare payload and delegate grading to AI
    payload = build_grading_payload(worksheet, image_b64)
    grading_result = call_grader(payload)
    # Grader returns questions as a list; StudentWorksheet.marks expects a dict keyed by question_id
    questions_list = grading_result.get("questions", [])
    marks = {
        str(q.get("question_id", i + 1)): q
        for i, q in enumerate(questions_list)
    }
    total_score = grading_result.get("total_score")
    max_score = grading_result.get("max_score")

    # Persist graded attempt to the database
    student_worksheet = StudentWorksheet(
        student_id=student.id,
        worksheet_id=worksheet.id,
        marks=marks,
        total_score=total_score,
        max_score=max_score,
    )
    session.add(student_worksheet)
    session.commit()
    session.refresh(student_worksheet)

    return student_worksheet