"""FastAPI app entrypoint with SQLModel.

OCR and grading are handled by Claude vision in a single call per request:
the page image goes to the model together with the worksheet's questions and
a rubric, and the model returns per-question sub-scores for the final answer,
the method/steps, and how much work the student showed.
"""

import io
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import anthropic
import base64
import cloudinary
import cloudinary.uploader
import cv2
import numpy as np
from fastapi import Depends, File, FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, select

from database import engine, get_session
from models import (
    Example,
    GenerateQuestionsRequest,
    OCRResult,
    PracticeQuestion,
    PracticeRequest,
    PracticeSet,
    Question,
    SQLModel,
    SolveRequest,
    SolveResult,
    Student,
    StudentWorksheet,
    Topic,
    Worksheet,
)

# Resolves ANTHROPIC_API_KEY / auth profile from the environment.
_anthropic = anthropic.Anthropic()
CLAUDE_MODEL = os.getenv("LEARNICAL_MODEL", "claude-opus-4-8")

# Directory for intermediate pipeline images; unset = no debug output.
_DEBUG_DIR = os.getenv("LEARNICAL_DEBUG_DIR")

# Cap the long edge before sending to Claude: keeps requests small while
# staying above the resolution handwriting recognition needs.
_MAX_IMAGE_EDGE = 2000


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    """Convert a PIL image to an OpenCV BGR ndarray."""
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv_to_pil(image: np.ndarray) -> Image.Image:
    """Convert an OpenCV BGR ndarray to a PIL image."""
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def _save_debug_cv(image: np.ndarray, label: str) -> None:
    """Best-effort debug image writer; failures are ignored."""
    if not _DEBUG_DIR:
        return
    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        ts = int(time.time() * 1000)
        cv2.imwrite(os.path.join(_DEBUG_DIR, f"debug_{label}_{ts}.png"), image)
    except Exception:
        pass


def deskew_and_enhance(image: Image.Image) -> Image.Image:
    cv_img = _pil_to_cv(image)
    _save_debug_cv(cv_img, "deskew_orig")

    h, w = cv_img.shape[:2]
    img_area = float(h * w)

    # 1) grayscale + blur
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 2) threshold for bright paper
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _save_debug_cv(thresh, "deskew_thresh")

    # 3) find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # 4) find best contour — approxPolyDP to get real corners
    best_box = None
    best_score = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 0.1 * img_area or area > 0.95 * img_area:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) != 4:
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

    # 5) perspective warp using actual corner points
    dst = np.array([
        [0, 0],
        [page_w - 1, 0],
        [page_w - 1, page_h - 1],
        [0, page_h - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(cv_img, M, (page_w, page_h))

    # 6) CLAHE contrast enhancement
    lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    L2 = clahe.apply(L)
    enhanced = cv2.cvtColor(cv2.merge((L2, A, B)), cv2.COLOR_LAB2BGR)
    _save_debug_cv(enhanced, "deskew_enhanced")

    return _cv_to_pil(enhanced)


def _image_block(image: Image.Image) -> dict:
    """Encode a PIL image as a Claude image content block (JPEG, size-capped)."""
    image = image.convert("RGB")
    long_edge = max(image.size)
    if long_edge > _MAX_IMAGE_EDGE:
        scale = _MAX_IMAGE_EDGE / long_edge
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
        )
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode("utf-8"),
        },
    }


def _load_page_image(content: bytes, content_type: str) -> Image.Image:
    """Decode an uploaded image or PDF (first page) into a PIL image."""
    if (content_type or "").lower() == "application/pdf":
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(content)
        if not pages:
            raise HTTPException(status_code=400, detail="PDF has no pages")
        return pages[0].convert("RGB")
    try:
        return Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode the uploaded image")


def _claude_json(schema: dict, content: list, max_tokens: int = 16000) -> dict:
    """One structured-output Claude call; returns the parsed JSON object."""
    try:
        response = _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        )
    except (anthropic.AuthenticationError, TypeError):
        raise HTTPException(status_code=503, detail="AI service is not configured (missing API key)")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e.__class__.__name__}")
    if response.stop_reason == "refusal":
        raise HTTPException(status_code=422, detail="The model declined this request")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def run_ocr(image: Image.Image) -> str:
    """Transcribe handwriting (including math notation) with Claude vision."""
    try:
        response = _run_ocr_request(image)
    except (anthropic.AuthenticationError, TypeError):
        raise HTTPException(status_code=503, detail="AI service is not configured (missing API key)")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e.__class__.__name__}")
    if response.stop_reason == "refusal":
        raise HTTPException(status_code=422, detail="The model declined this request")
    return next((b.text for b in response.content if b.type == "text"), "").strip()


def _run_ocr_request(image: Image.Image):
    return _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=(
            "You are a transcription assistant. Transcribe exactly what is "
            "written, including math notation. Output only the transcription."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    _image_block(image),
                    {
                        "type": "text",
                        "text": "Transcribe all handwritten and printed content in this image.",
                    },
                ],
            }
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup, using the shared engine from database.py.
    # Real schema changes go through alembic; this only covers fresh databases.
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Learnical", lifespan=lifespan)

# Comma-separated origins; defaults cover local web dev.
_cors_origins = os.getenv("LEARNICAL_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    """
    width_px, height_px = 1200, 1800
    bg_color = (255, 255, 255)
    text_color = (0, 0, 0)

    image = Image.new("RGB", (width_px, height_px), bg_color)
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 32)
    except Exception:
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

        if idx < len(regions):
            start_pct, _ = regions[idx]
        else:
            start_pct = prev_end_pct + 10

        top_gap = (prev_end_pct / 100.0) * height_px
        bottom_gap = (start_pct / 100.0) * height_px

        if bottom_gap - top_gap < 40:
            text_y = max(0, bottom_gap - 40)
        else:
            text_y = top_gap + (bottom_gap - top_gap) / 2.0

        text_x = int(0.08 * width_px)
        prompt_text = f"{idx + 1}. {q.prompt}"

        # Naive word wrap using measured text width.
        max_width = int(0.84 * width_px)
        words = prompt_text.split()
        line = ""
        y = text_y
        for word in words:
            test_line = f"{line} {word}".strip()
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

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    upload_result = cloudinary.uploader.upload(buf)
    return upload_result.get("secure_url") or upload_result.get("url") or "https://placehold.co/800x1200"


def _try_generate_worksheet_image(
    worksheet: Worksheet, regions: list[list[int]], session: Session
) -> str | None:
    """Worksheet image upload needs Cloudinary; skip quietly when unconfigured."""
    try:
        return generate_worksheet_image(worksheet, regions, session)
    except Exception:
        return None


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
    worksheet.image_url = _try_generate_worksheet_image(worksheet, regions, session)
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
):
    """Deskew/enhance the uploaded page and transcribe it with Claude vision."""
    content = await file.read()
    base_image = _load_page_image(content, file.content_type)
    processed = deskew_and_enhance(base_image)
    return OCRResult(text=run_ocr(processed))


# --- Grading ---

_GRADING_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer"},
                    "transcription": {
                        "type": "string",
                        "description": "Everything the student wrote for this question, transcribed verbatim",
                    },
                    "final_answer": {"type": "string"},
                    "final_answer_score": {
                        "type": "number",
                        "description": "0 to 1: is the final answer correct",
                    },
                    "method_score": {
                        "type": "number",
                        "description": "0 to 1: are the steps logically valid and appropriate",
                    },
                    "work_shown_score": {
                        "type": "number",
                        "description": "0 to 1: how completely the student showed their work",
                    },
                    "feedback": {
                        "type": "string",
                        "description": "Short, specific, encouraging feedback naming the exact step where things went wrong, if any",
                    },
                },
                "required": [
                    "question_id",
                    "transcription",
                    "final_answer",
                    "final_answer_score",
                    "method_score",
                    "work_shown_score",
                    "feedback",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}

# Weights for combining rubric sub-scores into a per-question score.
_W_ANSWER, _W_METHOD, _W_WORK = 0.5, 0.3, 0.2


def grade_page(image: Image.Image, worksheet: Worksheet, questions: list[Question]) -> dict:
    """Grade a photographed worksheet page with a single Claude vision call."""
    question_data = [
        {"question_id": q.id, "prompt": q.prompt, "correct_answer": q.answer, "skills": q.skills}
        for q in questions
    ]
    prompt = f"""You are grading a student's handwritten {worksheet.subject} worksheet from the attached photo.

Questions on this worksheet, in page order:
{json.dumps(question_data, indent=2)}

For each question, read the student's handwritten work directly from the image and grade three things independently:
- final_answer_score: 1.0 if the final answer is correct (accept mathematically equivalent forms), 0.0 if wrong, partial credit only for near-misses like sign or rounding slips.
- method_score: whether the steps taken are logically valid and would lead to the answer. A correct answer with invalid steps scores low here; a wrong answer with a sound method and one slip scores high.
- work_shown_score: how completely the student showed their work. Full marks means every meaningful step is on the page; an answer with no work scores near 0 even if correct.

Feedback should point at the exact line where an error occurs so a teacher can understand the student's thinking. If a question was left blank, use empty transcription, all scores 0, and say it was unanswered."""

    result = _claude_json(_GRADING_SCHEMA, [_image_block(image), {"type": "text", "text": prompt}])

    marks: dict = {}
    total = 0.0
    for item in result.get("questions", []):
        score = round(
            _W_ANSWER * item["final_answer_score"]
            + _W_METHOD * item["method_score"]
            + _W_WORK * item["work_shown_score"],
            3,
        )
        total += score
        marks[str(item["question_id"])] = {**item, "score": score, "max_score": 1.0}

    return {"marks": marks, "total_score": round(total, 3), "max_score": float(len(questions))}


@app.post("/grade", response_model=StudentWorksheet)
async def grade_worksheet(
    worksheet_id: int,
    student_id: int,
    file: UploadFile = File(..., description="Worksheet image to grade"),
    session: Session = Depends(get_session),
) -> StudentWorksheet:
    """
    Grade a photographed worksheet for a given student.

    Deskews the photo, then sends it to Claude with the worksheet's questions
    and a rubric. Persists per-question marks with sub-scores for final answer,
    method, and work shown.
    """
    worksheet = session.get(Worksheet, worksheet_id)
    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    questions = [
        q for qid in worksheet.questions if (q := session.get(Question, qid)) is not None
    ]
    if not questions:
        raise HTTPException(status_code=400, detail="Worksheet has no questions")

    content = await file.read()
    image = deskew_and_enhance(_load_page_image(content, file.content_type))
    graded = grade_page(image, worksheet, questions)

    _apply_mastery(student, worksheet, questions, graded, session)

    student_worksheet = StudentWorksheet(
        student_id=student.id,
        worksheet_id=worksheet.id,
        marks=graded["marks"],
        total_score=graded["total_score"],
        max_score=graded["max_score"],
        graded_at=datetime.utcnow(),
    )
    session.add(student_worksheet)
    session.commit()
    session.refresh(student_worksheet)

    return student_worksheet


# --- Mastery model ---

# Exponential moving average step for skill/subject updates: high enough that
# a few worksheets move the needle, low enough that one bad day doesn't erase
# a mastered skill.
_MASTERY_ALPHA = 0.3
_SKILL_START = 50.0  # neutral prior for a skill we've never seen
# Hysteresis so skills don't flap in and out of the mastered list
_MASTERY_ENTER, _MASTERY_EXIT = 90.0, 80.0


def _apply_mastery(
    student: Student,
    worksheet: Worksheet,
    questions: list[Question],
    graded: dict,
    session: Session,
) -> None:
    """Fold one graded worksheet into the student's learning model.

    Updates per-skill scores (EMA of question scores), the mastered list,
    the subject rolling average, and the daily streak. Called inside the
    /grade transaction; the caller commits.
    """
    skills_by_qid = {str(q.id): q.skills for q in questions}

    # 1) Per-skill scores
    learning = dict(student.learning_skills)
    for qid, mark in graded["marks"].items():
        score_pct = float(mark.get("score", 0.0)) * 100.0
        for skill in skills_by_qid.get(qid, []):
            old = float(learning.get(skill, _SKILL_START))
            learning[skill] = round(old + _MASTERY_ALPHA * (score_pct - old), 1)
    student.learning_skills = learning

    # 2) Mastered list with hysteresis
    mastered = set(student.mastered)
    for skill, value in learning.items():
        if value >= _MASTERY_ENTER:
            mastered.add(skill)
        elif value < _MASTERY_EXIT:
            mastered.discard(skill)
    student.mastered = sorted(mastered)

    # 3) Subject rolling average (0-100)
    if graded["max_score"]:
        pct = graded["total_score"] / graded["max_score"] * 100.0
        percentiles = dict(student.subject_percentiles)
        old = percentiles.get(worksheet.subject)
        percentiles[worksheet.subject] = round(
            pct if old is None else float(old) + _MASTERY_ALPHA * (pct - float(old)), 1
        )
        student.subject_percentiles = percentiles

    # 4) Daily streak, derived from the previous graded submission
    today = datetime.utcnow().date()
    last = session.exec(
        select(StudentWorksheet)
        .where(StudentWorksheet.student_id == student.id)
        .order_by(StudentWorksheet.created_at.desc())
    ).first()
    last_day = last.created_at.date() if last else None
    if last_day == today:
        student.streak_days = max(student.streak_days, 1)
    elif last_day == today - timedelta(days=1):
        student.streak_days += 1
    else:
        student.streak_days = 1

    student.updated_at = datetime.utcnow()
    session.add(student)


def _adaptive_difficulty(student: Student, topic: Topic) -> int:
    """Pick a 1-10 practice difficulty from the student's skill levels on a topic."""
    values = [float(student.learning_skills.get(s, _SKILL_START)) for s in topic.skills]
    mean = sum(values) / len(values) if values else _SKILL_START
    return max(1, min(10, round(mean / 10.0)))


# --- Step-by-step tutor ---

_SOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string", "description": "The problem, restated cleanly"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "explanation": {
                        "type": "string",
                        "description": "Why this step is taken, in plain language a student can follow",
                    },
                    "work": {"type": "string", "description": "The math for this step"},
                },
                "required": ["title", "explanation", "work"],
                "additionalProperties": False,
            },
        },
        "answer": {"type": "string"},
        "concept": {
            "type": "string",
            "description": "The underlying concept being exercised, in one or two sentences",
        },
    },
    "required": ["problem", "steps", "answer", "concept"],
    "additionalProperties": False,
}


@app.post("/solve", response_model=SolveResult)
def solve(request: SolveRequest) -> SolveResult:
    """Explain a typed question step by step (the tutor path for web input)."""
    result = _claude_json(
        _SOLVE_SCHEMA,
        [
            {
                "type": "text",
                "text": (
                    "You are a patient tutor. Solve this problem step by step, "
                    "explaining the reasoning behind each step so the student "
                    f"learns the method, not just the answer.\n\nProblem: {request.question}"
                ),
            }
        ],
    )
    return SolveResult(**result)


@app.post("/solve/photo", response_model=SolveResult)
async def solve_photo(
    file: UploadFile = File(..., description="Photo of a single problem"),
    hint: str | None = Form(default=None, description="Optional context from the student"),
) -> SolveResult:
    """Explain a photographed question step by step (the tutor path for camera input)."""
    content = await file.read()
    image = _load_page_image(content, file.content_type)
    text = (
        "You are a patient tutor. Read the problem in this photo, then solve it "
        "step by step, explaining the reasoning behind each step so the student "
        "learns the method, not just the answer."
    )
    if hint:
        text += f"\n\nStudent's note: {hint}"
    result = _claude_json(_SOLVE_SCHEMA, [_image_block(image), {"type": "text", "text": text}])
    return SolveResult(**result)


# --- Curriculum topics ---


@app.get("/topics", response_model=list[Topic])
def list_topics(
    subject: str | None = None,
    grade: str | None = None,
    session: Session = Depends(get_session),
) -> list[Topic]:
    """Browse the topic library, optionally filtered by subject and grade."""
    query = select(Topic)
    if subject:
        query = query.where(Topic.subject == subject)
    if grade:
        query = query.where(Topic.grade == grade)
    return list(session.exec(query.order_by(Topic.subject, Topic.grade, Topic.unit, Topic.name)))


@app.post("/topics", response_model=list[Topic])
def create_topics(topics: list[Topic], session: Session = Depends(get_session)) -> list[Topic]:
    """Create curriculum topics (bulk)."""
    created = []
    for t in topics:
        row = Topic(
            subject=t.subject,
            grade=t.grade,
            unit=t.unit,
            name=t.name,
            description=t.description,
            skills=t.skills,
        )
        session.add(row)
        created.append(row)
    session.commit()
    for row in created:
        session.refresh(row)
    return created


@app.get("/topics/{topic_id}/questions", response_model=list[Question])
def list_topic_questions(topic_id: int, session: Session = Depends(get_session)) -> list[Question]:
    if not session.get(Topic, topic_id):
        raise HTTPException(status_code=404, detail="Topic not found")
    return list(session.exec(select(Question).where(Question.topic_id == topic_id)))


_QUESTION_GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The question as shown to the student"},
                    "answer": {"type": "string", "description": "The correct answer, concise"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "difficulty": {"type": "integer", "description": "1 (easiest) to 10 (hardest)"},
                    "height": {
                        "type": "integer",
                        "description": "Vertical space the worked answer needs on a page: 1 short, 2 medium, 3 long",
                    },
                },
                "required": ["prompt", "answer", "skills", "difficulty", "height"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def _persist_generated_questions(
    items: list[dict], topic_id: int | None, session: Session
) -> list[Question]:
    rows = []
    for item in items:
        row = Question(
            topic_id=topic_id,
            prompt=item["prompt"],
            answer=item["answer"],
            skills=item["skills"],
            difficulty=max(1, min(10, int(item["difficulty"]))),
            height=max(1, min(3, int(item["height"]))),
        )
        session.add(row)
        rows.append(row)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


@app.post("/topics/{topic_id}/generate-questions", response_model=list[Question])
def generate_topic_questions(
    topic_id: int,
    request: GenerateQuestionsRequest,
    session: Session = Depends(get_session),
) -> list[Question]:
    """Generate and store new practice questions for a topic with AI."""
    topic = session.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    count = max(1, min(20, request.count))
    existing = session.exec(
        select(Question.prompt).where(Question.topic_id == topic_id)
    ).all()
    avoid = "\n".join(f"- {p}" for p in existing[:40])

    prompt = f"""Write {count} original practice questions for this curriculum topic.

Subject: {topic.subject}
Grade: {topic.grade}
Unit: {topic.unit}
Topic: {topic.name}
Description: {topic.description or "-"}
Skill tags to draw from: {json.dumps(topic.skills)}
Target difficulty: {max(1, min(10, request.difficulty))} on a 1-10 scale (vary slightly around it).

Rules:
- Questions must be solvable with pencil and paper by a grade {topic.grade} student.
- Answers must be exact and unambiguous.
- Prompts must be plain text (no LaTeX; use / for division and ^ for exponents).
- Do not repeat any of these existing questions:
{avoid or "- (none yet)"}"""

    result = _claude_json(_QUESTION_GEN_SCHEMA, [{"type": "text", "text": prompt}])
    return _persist_generated_questions(result.get("questions", []), topic_id, session)


# --- Practice / test generation ---


def _build_practice_set(
    title: str, subject: str, questions: list[Question], session: Session
) -> PracticeSet:
    worksheet = Worksheet(
        title=title,
        subject=subject,
        questions=[q.id for q in questions],
    )
    worksheet.answer_regions = _compute_answer_regions(worksheet.questions, session)
    worksheet.image_url = _try_generate_worksheet_image(worksheet, worksheet.answer_regions, session)
    session.add(worksheet)
    session.commit()
    session.refresh(worksheet)

    return PracticeSet(
        worksheet_id=worksheet.id,
        title=worksheet.title,
        subject=worksheet.subject,
        image_url=worksheet.image_url,
        questions=[
            PracticeQuestion(
                id=q.id, prompt=q.prompt, answer=q.answer, skills=q.skills, difficulty=q.difficulty
            )
            for q in questions
        ],
    )


@app.post("/practice/generate", response_model=PracticeSet)
def generate_practice(
    request: PracticeRequest, session: Session = Depends(get_session)
) -> PracticeSet:
    """
    Assemble a practice test from one or more topics.

    Pulls questions near the requested difficulty from the topic bank first;
    when the bank runs short (and generate_missing is set), AI generates the
    rest and adds them to the bank. The set is stored as a Worksheet, so it can
    be printed, handed out, and photo-graded like any other worksheet.
    """
    topics = [t for tid in request.topic_ids if (t := session.get(Topic, tid)) is not None]
    if not topics:
        raise HTTPException(status_code=404, detail="No matching topics found")

    # Adaptive mode: target each topic at the student's current skill level
    student = session.get(Student, request.student_id) if request.student_id else None
    if request.student_id and not student:
        raise HTTPException(status_code=404, detail="Student not found")

    num = max(1, min(30, request.num_questions))
    per_topic = max(1, num // len(topics))

    chosen: list[Question] = []
    for topic in topics:
        difficulty = _adaptive_difficulty(student, topic) if student else request.difficulty
        bank = list(session.exec(select(Question).where(Question.topic_id == topic.id)))
        bank.sort(key=lambda q: abs(q.difficulty - difficulty))
        take = bank[:per_topic]
        missing = per_topic - len(take)
        if missing > 0 and request.generate_missing:
            gen = generate_topic_questions(
                topic.id,
                GenerateQuestionsRequest(count=missing, difficulty=difficulty),
                session,
            )
            take = take + gen
        chosen.extend(take)

    chosen = chosen[:num]
    if not chosen:
        raise HTTPException(
            status_code=400,
            detail="No questions available for these topics (and generation is disabled)",
        )

    title = request.title or f"Practice: {', '.join(t.name for t in topics)}"
    return _build_practice_set(title, topics[0].subject, chosen, session)


@app.post("/practice/from-upload", response_model=PracticeSet)
async def practice_from_upload(
    file: UploadFile = File(..., description="Photo or PDF of course content"),
    num_questions: int = Form(default=5),
    subject: str = Form(default="math"),
    difficulty: int = Form(default=5),
    session: Session = Depends(get_session),
) -> PracticeSet:
    """
    Generate a practice test from uploaded course content (textbook page,
    lesson notes, an old test). Questions are grounded in what the upload
    actually covers.
    """
    content = await file.read()
    image = _load_page_image(content, file.content_type)

    count = max(1, min(20, num_questions))
    prompt = f"""The attached image is course content a student is studying (textbook page, notes, or an old assignment).

Write {count} original practice questions that test exactly the concepts and methods this content covers — same subject matter, same techniques, but new numbers and phrasing. Target difficulty {max(1, min(10, difficulty))} on a 1-10 scale.

Rules:
- Do not copy questions verbatim from the content; write fresh ones.
- Answers must be exact and unambiguous.
- Prompts must be plain text (no LaTeX; use / for division and ^ for exponents)."""

    result = _claude_json(
        _QUESTION_GEN_SCHEMA, [_image_block(image), {"type": "text", "text": prompt}]
    )
    questions = _persist_generated_questions(result.get("questions", []), None, session)
    if not questions:
        raise HTTPException(status_code=502, detail="Question generation returned nothing")

    title = f"Practice from upload: {file.filename or 'course content'}"
    return _build_practice_set(title, subject, questions, session)
