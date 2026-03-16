"""FastAPI app entrypoint with SQLModel."""
import os
import io
import time
import warnings
from contextlib import asynccontextmanager

import cv2
import numpy as np
import torch
from fastapi import Depends, File, FastAPI, HTTPException, UploadFile
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, select
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")

import pytesseract
import json
import anthropic
import base64
import cloudinary
import cloudinary.uploader

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
    dtype=torch.float32,  # half precision, cuts memory ~50%
)
_model = _model.to(device)
_model.eval()  # disable dropout etc, slight speedup on inference


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    """Convert a PIL image to an OpenCV BGR ndarray."""
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv_to_pil(image: np.ndarray) -> Image.Image:
    """Convert an OpenCV BGR ndarray to a PIL image."""
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def _save_debug_cv(image: np.ndarray, label: str) -> None:
    """Best-effort debug image writer; failures are ignored."""
    try:
        ts = int(time.time() * 1000)
        filename = f"debug_{label}_{ts}.png"
        # Handle grayscale vs color automatically
        cv2.imwrite(filename, image)
    except Exception:
        pass


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
    cv_img = _pil_to_cv(image)
    _save_debug_cv(cv_img, "deskew_orig")

    h, w = cv_img.shape[:2]
    img_area = float(h * w)

    # 1) grayscale + blur
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    _save_debug_cv(gray, "deskew_gray")
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _save_debug_cv(blur, "deskew_blur")

    # 2) threshold for bright paper
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _save_debug_cv(thresh, "deskew_thresh")

    # 3) find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    debug_contours = cv_img.copy()
    cv2.drawContours(debug_contours, contours, -1, (0, 0, 255), 2)
    _save_debug_cv(debug_contours, "deskew_all_contours")

    # 4) find best contour — now using approxPolyDP to get real corners
    best_box = None
    best_score = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 0.1 * img_area or area > 0.95 * img_area:
            continue

        # Try to get 4 real corners from the contour shape
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) != 4:
            # Try convex hull if direct approx didn't give 4 corners
            hull = cv2.convexHull(cnt)
            peri = cv2.arcLength(hull, True)
            approx = cv2.approxPolyDP(hull, 0.02 * peri, True)

        if len(approx) != 4:
            continue

        box = approx.reshape(4, 2).astype("float32")

        # Sanity check aspect ratio
        box_sorted = box[np.argsort(box[:, 1])]
        top_two = box_sorted[:2][np.argsort(box_sorted[:2, 0])]
        bot_two = box_sorted[2:][np.argsort(box_sorted[2:, 0])]
        tl, tr = top_two
        bl, br = bot_two
        pw = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
        ph = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
        if pw <= 0 or ph <= 0:
            continue
        ar = max(pw, ph) / min(pw, ph)
        if not (1.0 <= ar <= 2.5):
            continue

        score = area
        if score > best_score:
            best_score = score
            best_box = (box, tl, tr, br, bl, int(pw), int(ph))

    if best_box is None:
        return image.convert("RGB")

    box, tl, tr, br, bl, page_w, page_h = best_box
    src = np.array([tl, tr, br, bl], dtype="float32")

    debug_box = cv_img.copy()
    cv2.drawContours(debug_box, [src.astype(int)], -1, (0, 255, 0), 3)
    _save_debug_cv(debug_box, "deskew_selected_rect")

    # 5) perspective warp using actual corner points
    dst = np.array([
        [0, 0],
        [page_w - 1, 0],
        [page_w - 1, page_h - 1],
        [0, page_h - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(cv_img, M, (page_w, page_h))
    _save_debug_cv(warped, "deskew_warped")

    # 6) CLAHE contrast enhancement
    lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    L2 = clahe.apply(L)
    enhanced = cv2.cvtColor(cv2.merge((L2, A, B)), cv2.COLOR_LAB2BGR)
    _save_debug_cv(enhanced, "deskew_enhanced")

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
from models import Example, OCRResult, Question, SQLModel, Student, StudentWorksheet, Worksheet


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


def generate_worksheet_image(worksheet: Worksheet, regions: list[list[int]], session: Session) -> str:
    """
    Generate a simple worksheet image with questions drawn in the non-answer regions,
    upload it to Cloudinary, and return the resulting URL.

    This is a first-pass implementation meant to be edited/tuned.
    """
    # Basic page setup (percentage-based layout)
    width_px, height_px = 1200, 1800
    bg_color = (255, 255, 255)
    text_color = (0, 0, 0)

    # Create blank page
    image = Image.new("RGB", (width_px, height_px), bg_color)
    draw = ImageDraw.Draw(image)

    # Try to get a decent default font; fall back to PIL default
    try:
        font = ImageFont.truetype("Arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()

    # For each question, draw the prompt roughly centered in the gap
    # above its answer region, so we don't write inside the region.
    prev_end_pct = 0.0
    for idx, qid in enumerate(worksheet.questions):
        q = session.get(Question, qid)
        if not q:
            continue

        # If we have a matching region, use it; otherwise, just use a default band.
        if idx < len(regions):
            start_pct, _ = regions[idx]
        else:
            start_pct = prev_end_pct + 10

        # Gap for this question is from prev_end_pct to start_pct
        top_gap = (prev_end_pct / 100.0) * height_px
        bottom_gap = (start_pct / 100.0) * height_px

        if bottom_gap - top_gap < 40:
            # Not much room; just nudge text a bit above the start of the region
            text_y = max(0, bottom_gap - 40)
        else:
            # Place text in the middle of the gap
            text_y = top_gap + (bottom_gap - top_gap) / 2.0

        text_x = int(0.08 * width_px)  # 8% from left edge
        prompt_text = f"{idx + 1}. {q.prompt}"

        # Wrap text naively if it's too long (very rough).
        max_width = int(0.84 * width_px)
        words = prompt_text.split()
        line = ""
        y = text_y
        for word in words:
            test_line = f"{line} {word}".strip()
            # Use textbbox to measure text size (textsize may not exist on newer Pillow)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w > max_width and line:
                draw.text((text_x, y), line, fill=text_color, font=font)
                y += h + 4
                line = word
            else:
                line = test_line
        if line:
            draw.text((text_x, y), line, fill=text_color, font=font)

        if idx < len(regions):
            prev_end_pct = regions[idx][1]

    # Encode image to PNG in-memory
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    # Upload to Cloudinary using the configured environment (cloud name, API key/secret, etc.)
    upload_result = cloudinary.uploader.upload(
        buf
    )
    return upload_result.get("secure_url") or upload_result.get("url") or "https://placehold.co/800x1200"


def _compute_answer_regions(question_ids: list[int], session: Session) -> list[list[int]]:
    """
    Compute answer regions from question heights.
    First region: start=4, end=4 + (height_0 * 16).
    Then skip 4; next region starts there, spans (height_1 * 16), and so on.
    """
    regions: list[list[int]] = []
    current: float | None = None
    for qid in question_ids:
        q = session.get(Question, qid)
        if not q:
            continue
        if current is None:
            current = 4.0 * float(q.height)
        start = current
        end = start + (float(q.height) * 16.0)
        regions.append([int(start), int(end)])
        current = end + 4.0 * float(q.height)
    return regions


@app.post("/worksheets", response_model=Worksheet)
def create_worksheet(worksheet: Worksheet, session: Session = Depends(get_session)) -> Worksheet:
    """Create a worksheet. Computes answer_regions from question heights and generates an image."""
    regions = _compute_answer_regions(worksheet.questions, session)
    worksheet.answer_regions = regions
    worksheet.image_url = generate_worksheet_image(worksheet, regions, session)
    session.add(worksheet)
    session.commit()
    session.refresh(worksheet)
    return worksheet


@app.post("/questions", response_model=list[Question])
def create_questions(
    questions: list[Question],
    session: Session = Depends(get_session),
) -> list[Question]:
    """Create multiple questions. Accepts a list of question objects and inserts all into the database."""
    created = []
    for q in questions:
        row = Question(
            prompt=q.prompt,
            answer=q.answer,
            skills=q.skills,
            height=q.height,
            difficulty=q.difficulty,
        )
        session.add(row)
        created.append(row)
    session.commit()
    for row in created:
        session.refresh(row)
    return created


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