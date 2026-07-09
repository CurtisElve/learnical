**Learnical: The AI Math Tutor**

Learnical is an intelligent education platform built to bridge the gap between getting an answer and actually understanding the math. By using advanced OCR and logical reasoning engines, Learnical provides students with a complete step by step learning journey for any mathematical problem.

**🚀 Key Features**

**📷 Smart OCR and Automatic Grading**

Simply upload a photo or scan of your handwritten math homework. Learnical does not just look at the final result. It analyzes every line of your work, identifying exactly where a calculation might have gone wrong and providing targeted feedback.

**🧠 Step by Step Logic Checking**

Our AI breaks down complex problems into manageable chunks. It verifies the logical flow of each step, ensuring that students understand the why behind every transformation and formula used.

**🎨 Visual Interactive Learning**

Every solution comes with a dynamic visual example. Whether it is a 3D plot of a multivariable function or an interactive slider for a linear equation, Learnical provides a hands on way to visualize the methods used.

**✍️ Instant Problem Solving**

Stuck on a new concept? Learnical can generate full, detailed solutions to any math problem, serving as a 24/7 digital tutor that guides you through the process rather than just giving you the answer.

**📖 How it Works**

Capture: Take a photo of your math problem or your attempted solution.

Analyze: Learnical identifies the mathematical symbols and the logical structure of the work.

Grade and Guide: The AI flags errors in logic and provides the correct steps.

Interact: Explore the generated visual example to master the underlying concept.

...

**⚙️ Running the backend**

```bash
cd python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...            # required for OCR, grading, and the tutor
export DATABASE_URL=postgresql+psycopg2://...  # optional; defaults to local SQLite
.venv/bin/uvicorn main:app --port 8000
```

Optional environment variables:

- `LEARNICAL_MODEL` — Claude model to use (default `claude-opus-4-8`)
- `LEARNICAL_DEBUG_DIR` — directory for intermediate image-pipeline debug output (off by default)
- Cloudinary credentials (`CLOUDINARY_URL`) are needed only for worksheet image generation

Key endpoints: `POST /grade` (photo → rubric-graded marks: final answer, method, work shown),
`POST /solve` and `POST /solve/photo` (step-by-step tutor), `POST /ocr` (transcription),
`POST /worksheets` and `POST /questions` (content authoring).

**🌐 Running the web app**

```bash
cd web
npm install
npm run dev            # http://localhost:3000, expects the backend on :8000
```

Set `NEXT_PUBLIC_API_URL` (see `web/.env.example`) if the backend runs elsewhere, and add
your web origin to `LEARNICAL_CORS_ORIGINS` on the backend if it isn't localhost:3000.

Pages: `/solve` (step-by-step tutor, typed or photo), `/scan` (upload a worksheet photo for
rubric grading), `/progress` (streak, subjects, skills).

**📚 Topic library & practice generation**

```bash
cd python
.venv/bin/python seed_topics.py     # load the starter curriculum (math gr. 1-8 + science/english)
.venv/bin/alembic upgrade head      # existing databases only; fresh DBs get the schema automatically
```

- `GET /topics?subject=&grade=` — browse the curriculum library
- `POST /topics/{id}/generate-questions` — AI writes new bank questions for a topic
- `POST /practice/generate` — build a practice test from topics (auto-generates when the bank runs short)
- `POST /practice/from-upload` — upload a textbook page / notes / old test and get fresh questions on the same material

Every practice set is stored as a Worksheet, so it can be printed, handed out, and
photo-graded through `/grade` like any other worksheet. On the web: `/topics` to browse,
`/practice` to generate, reveal the answer key, and print.

**🧠 Mastery loop**

Every photo-graded worksheet updates the student's learning model automatically:

- **Skill scores** — each question's rubric score feeds an exponential moving average per skill tag (new skills start at 50/100).
- **Mastery badges** — a skill is mastered at ≥90 and only drops off below 80 (hysteresis, so it doesn't flap).
- **Subject averages** — rolling per-subject percentage shown on the Progress page.
- **Streaks** — consecutive days with graded work.

Practice generation closes the loop: pass `student_id` to `POST /practice/generate` (or fill
"Adapt to student" on the web Practice page) and each topic's difficulty is chosen from that
student's current skill levels instead of the manual slider — weak skills get easier sets,
mastered skills get harder ones.

**🤖 Android app**

The Android companion lives in `android/` (Kotlin + Jetpack Compose). Three tabs:

- **Solve** — point the camera at a problem → step-by-step explanation (the Photomath flow)
- **Grade** — photograph a finished worksheet → rubric scores per question
- **Progress** — streak, subject averages, skill levels, mastered badges

Open the folder in Android Studio (it will offer to generate the Gradle wrapper on first
sync). The default API URL is `http://10.0.2.2:8000`, which reaches your machine's
localhost from the emulator. For a physical device on your LAN, build with
`-PapiUrl=http://<your-ip>:8000` and add that origin's needs as required.
