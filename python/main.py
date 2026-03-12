"""FastAPI app entrypoint with SQLModel."""
import os
import io
import warnings
from contextlib import asynccontextmanager

import cv2
import numpy as np
import torch
import torch_directml
from fastapi import Depends, File, FastAPI, HTTPException, UploadFile
from PIL import Image
from sqlmodel import Session, select
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")

import pytesseract
import json
import anthropic
import base64

_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- device ---
device = "cpu"

# --- load model once at module level ---
_processor = AutoProcessor.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    min_pixels=256 * 28 * 28,  # floor: don't over-shrink small images
    max_pixels=1280 * 28 * 28,  # cap: biggest win for CPU speed
)
_model = Qwen2VLForConditionalGeneration.from_pretrained(
    "prithivMLmods/Callisto-OCR3-2B-Instruct",
    torch_dtype=torch.float32,  # half precision, cuts memory ~50%
)
_model = _model.to(device)
_model.eval()  # disable dropout etc, slight speedup on inference


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    """Convert a PIL image to an OpenCV BGR ndarray."""
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv_to_pil(image: np.ndarray) -> Image.Image:
    """Convert an OpenCV BGR ndarray to a PIL image."""
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


# Minimum size for Callisto/Qwen2-VL so the vision encoder's patch grid is valid (avoids "input must be 4-dimensional").
_MIN_OCR_HEIGHT = 224
_MIN_OCR_WIDTH = 224


def _ensure_min_size(image: Image.Image, min_w: int = _MIN_OCR_WIDTH, min_h: int = _MIN_OCR_HEIGHT) -> Image.Image:
    """Pad image with white so both dimensions are at least min_w and min_h. Prevents degenerate crops from breaking the vision model."""
    w, h = image.size
    if w >= min_w and h >= min_h:
        return image
    new_w = max(w, min_w)
    new_h = max(h, min_h)
    out = Image.new("RGB", (new_w, new_h), (255, 255, 255))
    out.paste(image, (0, 0))
    return out


def deskew_and_enhance(image: Image.Image) -> Image.Image:
    """
    No-op for now: skew/enhance commented out. Only chopping (answer_regions) is used.
    Ensures RGB for downstream.
    """
    # --- skew + CLAHE commented out to avoid confusing errors; re-enable when needed ---
    cv_img = _pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype("float32")
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            rect = np.zeros((4, 2), dtype="float32")
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]
            (tl, tr, br, bl) = rect
            maxWidth = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            maxHeight = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(cv_img, M, (maxWidth, maxHeight))
        else:
            warped = cv_img
    else:
        warped = cv_img
    lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return _cv_to_pil(enhanced)


def run_ocr(image: Image.Image, subject: str, questions: str) -> str:
    messages = [
        {
            "role" : "system",
            "content" : [
                {"type" : "text",
                "text" : "You are a transcription bot. Do not add any extra characters or explanation to your response other than what you see."
                }
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {
                    "type": "text",
                    "text": f"Transcribe all handwritten characters in this image exactly as they are written. This includes math notation.",
                },
            ],
        }
    ]

    text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _processor(
        text=[text],
        images=[image],
        padding=True,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():  # don't track gradients, saves memory + speed
        generated_ids = _model.generate(**inputs, max_new_tokens=1024)

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
async def ocr(
    file: UploadFile = File(..., description="Image or PDF file"),
    session: Session = Depends(get_session),
):
    """
    OCR endpoint that uses worksheet-defined answer regions.

    Looks up worksheet id=1, chops by (start%, end%) vertical bands from
    `answer_regions`, runs ensure_min_size on each crop and Callisto on each band.
    Segments are concatenated in order. No skew/enhance (commented out).
    """
    content = await file.read()
    content_type = (file.content_type or "").lower()

    # Load base image
    if content_type == "application/pdf":
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(content)
        if not pages:
            raise HTTPException(status_code=400, detail="PDF has no pages")
        base_image = pages[0].convert("RGB")
    else:
        base_image = Image.open(io.BytesIO(content)).convert("RGB")

    # For now, hard-code worksheet id=1 as requested
    worksheet = session.get(Worksheet, 1)
    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet id=1 not found")

    # Deskew and enhance the full page first
    processed = deskew_and_enhance(base_image)
    width, height = processed.size

    regions = worksheet.answer_regions or []
    if not regions:
        # If no regions configured, just OCR the whole page (ensure_min_size before model)
        full = _ensure_min_size(processed)
        text = run_ocr(full, worksheet.subject, json.dumps(worksheet.questions))
        return OCRResult(text=text)

    segments = []
    print(regions)
    for start_pct, end_pct in reversed(regions):
        # Clamp percentages to [0, 100]
        start = max(0, min(100, start_pct))
        end = max(0, min(100, end_pct))
        if end <= start:
            continue

        y1 = int(height * (start / 100.0))
        y2 = int(height * (end / 100.0))
        crop = processed.crop((0, y1, width, y2))
        crop = _ensure_min_size(crop)  # avoid thin crops breaking Qwen2-VL conv3d
        crop.save(rf"C:\Users\curti\learnical\debug_crop{y1}.png")
        segment_text = run_ocr(crop, worksheet.subject, json.dumps(worksheet.questions))
        print(segment_text)
        if segment_text:
            segments.append(segment_text.strip())

    combined = "\n\n".join(segments).strip()
    return OCRResult(text=combined)


def build_grading_payload(worksheet: Worksheet, ocr_text: str) -> dict:
    """Shape sent to the local grading AI."""
    return {
        "worksheet_id": worksheet.id,
        "worksheet_identifier": worksheet.identifier,
        "subject": worksheet.subject,
        "questions": worksheet.questions,
        "ocr_text": ocr_text,
    }


def call_grader(payload: dict) -> dict:  # no image param anymore
    questions_str = json.dumps(payload["questions"], indent=2)

    prompt = f"""You are grading a student worksheet for subject: {payload["subject"]}.

    Here are the questions and correct answers:
    {questions_str}

    Here is the OCR transcription of the student's handwritten answers:
    {payload["ocr_text"]}

    Return ONLY a JSON object in exactly this format, no other text:
    {{
    "questions": [
        {{
        "question_id": 1,
        "student_answer": "what the student wrote",
        "score": 0.8,
        "max_score": 1.0,
        "feedback": "short feedback string"
        }}
    ],
    "total_score": 0.75,
    "max_score": 5.0
    }}"""

    response = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
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

    # OCR the uploaded image
    content = await file.read()
    image = Image.open(io.BytesIO(content)).convert("RGB")
    ocr_text = run_ocr(image, worksheet.subject, json.dumps(worksheet.questions))
    print(ocr_text)
    # Prepare payload and delegate grading to AI
    payload = build_grading_payload(worksheet, ocr_text)
    grading_result = call_grader(payload)
    print(grading_result)
    # `StudentWorksheet.marks` is a dict; the grader returns `questions` as a list.
    # Normalize into a dict keyed by question_id so DB + Pydantic match the model.
    questions = grading_result.get("questions", [])
    if isinstance(questions, list):
        marks = {}
        for idx, q in enumerate(questions, start=1):
            if isinstance(q, dict):
                qid = q.get("question_id", idx)
                marks[str(qid)] = q
    elif isinstance(questions, dict):
        marks = questions
    else:
        marks = {}
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