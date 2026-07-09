"use client";

import { useState } from "react";
import { solve, solvePhoto, type SolveResult } from "@/lib/api";

export default function SolvePage() {
  const [question, setQuestion] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SolveResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() && !file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = file
        ? await solvePhoto(file, question.trim() || undefined)
        : await solve(question.trim());
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold">Step-by-step tutor</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Type a question, or upload a photo of one. You get the method, not just the
          answer.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            file
              ? "Optional note about the photo (e.g. “question 3 only”)"
              : "e.g. Solve for x: 2x + 6 = 14"
          }
          rows={3}
          className="w-full rounded-xl border border-zinc-300 p-4 text-sm focus:border-emerald-500 focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:border-emerald-400">
            {file ? `📷 ${file.name}` : "📷 Upload a photo"}
            <input
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {file && (
            <button
              type="button"
              onClick={() => setFile(null)}
              className="text-sm text-zinc-500 hover:text-red-600"
            >
              Remove
            </button>
          )}
          <button
            type="submit"
            disabled={loading || (!question.trim() && !file)}
            className="ml-auto rounded-lg bg-emerald-600 px-6 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
          >
            {loading ? "Thinking…" : "Explain it"}
          </button>
        </div>
      </form>

      {error && (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>
      )}

      {loading && (
        <p className="text-sm text-zinc-500">
          Working through the problem step by step…
        </p>
      )}

      {result && (
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-zinc-200 p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Problem
            </h2>
            <p className="mt-1 font-medium">{result.problem}</p>
          </div>

          <ol className="flex flex-col gap-4">
            {result.steps.map((step, i) => (
              <li key={i} className="flex gap-4 rounded-xl border border-zinc-200 p-5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-sm font-bold text-emerald-700">
                  {i + 1}
                </span>
                <div>
                  <h3 className="font-semibold">{step.title}</h3>
                  <p className="mt-1 text-sm text-zinc-600">{step.explanation}</p>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-50 p-3 font-mono text-sm">
                    {step.work}
                  </pre>
                </div>
              </li>
            ))}
          </ol>

          <div className="rounded-xl border-2 border-emerald-500 bg-emerald-50 p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
              Answer
            </h2>
            <p className="mt-1 text-lg font-bold">{result.answer}</p>
            <p className="mt-2 text-sm text-emerald-900">{result.concept}</p>
          </div>
        </div>
      )}
    </div>
  );
}
