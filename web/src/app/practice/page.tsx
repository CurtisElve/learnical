"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  generatePractice,
  practiceFromUpload,
  type PracticeSet,
} from "@/lib/api";

function QuestionCard({
  index,
  prompt,
  answer,
  difficulty,
  showAnswers,
}: {
  index: number;
  prompt: string;
  answer: string;
  difficulty: number;
  showAnswers: boolean;
}) {
  const [revealed, setRevealed] = useState(false);
  const show = showAnswers || revealed;
  return (
    <div className="rounded-xl border border-zinc-200 p-5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-medium">
          {index + 1}. {prompt}
        </p>
        <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500">
          difficulty {difficulty}/10
        </span>
      </div>
      <div className="mt-3">
        {show ? (
          <p className="rounded-lg bg-emerald-50 p-3 text-sm font-medium text-emerald-900">
            Answer: {answer}
          </p>
        ) : (
          <button
            onClick={() => setRevealed(true)}
            className="text-sm font-medium text-emerald-600 hover:underline print:hidden"
          >
            Show answer
          </button>
        )}
      </div>
    </div>
  );
}

function PracticeContent() {
  const params = useSearchParams();
  const topicId = params.get("topic");
  const topicName = params.get("name");

  const [mode, setMode] = useState<"topic" | "upload">(topicId ? "topic" : "upload");
  const [numQuestions, setNumQuestions] = useState("5");
  const [difficulty, setDifficulty] = useState("5");
  const [subject, setSubject] = useState("math");
  const [studentId, setStudentId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [set, setSet] = useState<PracticeSet | null>(null);
  const [showAnswers, setShowAnswers] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSet(null);
    setShowAnswers(false);
    try {
      if (mode === "topic" && topicId) {
        setSet(
          await generatePractice({
            topicIds: [Number(topicId)],
            numQuestions: Number(numQuestions),
            difficulty: Number(difficulty),
            title: topicName ? `Practice: ${topicName}` : undefined,
            studentId: studentId ? Number(studentId) : undefined,
          }),
        );
      } else if (mode === "upload" && file) {
        setSet(
          await practiceFromUpload(file, Number(numQuestions), subject, Number(difficulty)),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div className="print:hidden">
        <h1 className="text-2xl font-bold">Practice generator</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Build a practice test from a library topic, or upload course content
          (textbook page, notes, old test) and get fresh questions on the same material.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4 print:hidden">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode("topic")}
            disabled={!topicId}
            className={`rounded-full px-4 py-1.5 text-sm font-medium disabled:opacity-40 ${
              mode === "topic"
                ? "bg-emerald-600 text-white"
                : "border border-zinc-300 text-zinc-600"
            }`}
          >
            {topicName ? `Topic: ${topicName}` : "From a topic"}
          </button>
          <button
            type="button"
            onClick={() => setMode("upload")}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${
              mode === "upload"
                ? "bg-emerald-600 text-white"
                : "border border-zinc-300 text-zinc-600"
            }`}
          >
            From uploaded content
          </button>
        </div>

        {mode === "topic" && !topicId && (
          <p className="text-sm text-zinc-500">
            Pick a topic from the <a href="/topics" className="text-emerald-600 underline">topic library</a> first.
          </p>
        )}

        {mode === "upload" && (
          <>
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-300 p-8 text-sm text-zinc-500 hover:border-emerald-400">
              {file ? (
                <span className="font-medium text-zinc-800">📄 {file.name}</span>
              ) : (
                <span>📷 Upload a photo or PDF of the material to practice</span>
              )}
              <input
                type="file"
                accept="image/*,.pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm font-medium">
              Subject
              <select
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="rounded-lg border border-zinc-300 p-2 focus:border-emerald-500 focus:outline-none"
              >
                <option value="math">Math</option>
                <option value="science">Science</option>
                <option value="english">English</option>
              </select>
            </label>
          </>
        )}

        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Questions
            <input
              type="number"
              min={1}
              max={20}
              value={numQuestions}
              onChange={(e) => setNumQuestions(e.target.value)}
              className="w-24 rounded-lg border border-zinc-300 p-2 focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <label
            className={`flex flex-col gap-1 text-sm font-medium ${
              studentId && mode === "topic" ? "opacity-40" : ""
            }`}
          >
            Difficulty: {difficulty}/10
            <input
              type="range"
              min={1}
              max={10}
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
              disabled={Boolean(studentId) && mode === "topic"}
              className="w-48 accent-emerald-600"
            />
          </label>
          {mode === "topic" && (
            <label className="flex flex-col gap-1 text-sm font-medium">
              Adapt to student
              <input
                type="number"
                min={1}
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                placeholder="Student ID"
                title="When set, difficulty follows this student's skill levels for the topic"
                className="w-28 rounded-lg border border-zinc-300 p-2 focus:border-emerald-500 focus:outline-none"
              />
            </label>
          )}
          <button
            type="submit"
            disabled={loading || (mode === "topic" ? !topicId : !file)}
            className="ml-auto rounded-lg bg-emerald-600 px-6 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
          >
            {loading ? "Generating…" : "Generate practice"}
          </button>
        </div>
      </form>

      {error && (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700 print:hidden">
          {error}
        </p>
      )}
      {loading && (
        <p className="text-sm text-zinc-500 print:hidden">
          Writing questions tailored to this material…
        </p>
      )}

      {set && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold">{set.title}</h2>
              <p className="text-xs text-zinc-500">
                Worksheet #{set.worksheet_id} — hand it out, then photo-grade it on the
                Scan &amp; Grade page.
              </p>
            </div>
            <div className="flex gap-2 print:hidden">
              <button
                onClick={() => setShowAnswers((s) => !s)}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:border-emerald-400"
              >
                {showAnswers ? "Hide answers" : "Answer key"}
              </button>
              <button
                onClick={() => window.print()}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:border-emerald-400"
              >
                Print
              </button>
            </div>
          </div>
          {set.questions.map((q, i) => (
            <QuestionCard
              key={q.id}
              index={i}
              prompt={q.prompt}
              answer={q.answer}
              difficulty={q.difficulty}
              showAnswers={showAnswers}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PracticePage() {
  return (
    <Suspense>
      <PracticeContent />
    </Suspense>
  );
}
