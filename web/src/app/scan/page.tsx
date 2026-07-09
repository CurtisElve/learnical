"use client";

import { useState } from "react";
import { gradeWorksheet, type StudentWorksheet, type QuestionMark } from "@/lib/api";

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-28 shrink-0 text-zinc-600">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-zinc-100">
        <div
          className="h-2 rounded-full bg-emerald-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-right font-medium">{pct}%</span>
    </div>
  );
}

function MarkCard({ id, mark }: { id: string; mark: QuestionMark }) {
  return (
    <div className="rounded-xl border border-zinc-200 p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="font-semibold">Question {id}</h3>
        <span className="text-sm font-bold text-emerald-700">
          {Math.round(mark.score * 100)}%
        </span>
      </div>
      {mark.transcription && (
        <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-50 p-3 font-mono text-sm whitespace-pre-wrap">
          {mark.transcription}
        </pre>
      )}
      <div className="mt-4 flex flex-col gap-2">
        <ScoreBar label="Final answer" value={mark.final_answer_score} />
        <ScoreBar label="Method" value={mark.method_score} />
        <ScoreBar label="Work shown" value={mark.work_shown_score} />
      </div>
      <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
        {mark.feedback}
      </p>
    </div>
  );
}

export default function ScanPage() {
  const [worksheetId, setWorksheetId] = useState("");
  const [studentId, setStudentId] = useState("1");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StudentWorksheet | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !worksheetId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await gradeWorksheet(Number(worksheetId), Number(studentId), file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const overall =
    result && result.max_score
      ? Math.round(((result.total_score ?? 0) / result.max_score) * 100)
      : null;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold">Scan &amp; grade</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Upload a photo of a finished worksheet. Each question is graded on the final
          answer, the method, and how much work was shown — so teachers see the
          student&apos;s thinking, not just a score.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Worksheet ID
            <input
              type="number"
              min={1}
              value={worksheetId}
              onChange={(e) => setWorksheetId(e.target.value)}
              placeholder="e.g. 1"
              className="rounded-lg border border-zinc-300 p-2.5 focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Student ID
            <input
              type="number"
              min={1}
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              className="rounded-lg border border-zinc-300 p-2.5 focus:border-emerald-500 focus:outline-none"
            />
          </label>
        </div>

        <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-300 p-10 text-sm text-zinc-500 hover:border-emerald-400">
          {file ? (
            <span className="font-medium text-zinc-800">📄 {file.name}</span>
          ) : (
            <>
              <span className="text-3xl">📷</span>
              <span>Click to upload a photo or PDF of the worksheet</span>
            </>
          )}
          <input
            type="file"
            accept="image/*,.pdf"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <button
          type="submit"
          disabled={loading || !file || !worksheetId}
          className="self-end rounded-lg bg-emerald-600 px-6 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
        >
          {loading ? "Grading…" : "Grade it"}
        </button>
      </form>

      {error && (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>
      )}

      {loading && (
        <p className="text-sm text-zinc-500">
          Reading the handwriting and checking every step…
        </p>
      )}

      {result && (
        <div className="flex flex-col gap-4">
          {overall !== null && (
            <div className="flex items-center justify-between rounded-xl border-2 border-emerald-500 bg-emerald-50 p-5">
              <div>
                <h2 className="font-semibold">Overall</h2>
                <p className="text-sm text-emerald-900">
                  {result.total_score} / {result.max_score} points
                </p>
              </div>
              <span className="text-3xl font-bold text-emerald-700">{overall}%</span>
            </div>
          )}
          {Object.entries(result.marks).map(([id, mark]) => (
            <MarkCard key={id} id={id} mark={mark} />
          ))}
        </div>
      )}
    </div>
  );
}
