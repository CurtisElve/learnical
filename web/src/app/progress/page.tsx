"use client";

import { useEffect, useState } from "react";
import { getStudent, type Student } from "@/lib/api";

function Bar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 100));
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 shrink-0 capitalize text-zinc-600">
        {label.replaceAll("_", " ")}
      </span>
      <div className="h-2 flex-1 rounded-full bg-zinc-100">
        <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right font-medium">{pct}%</span>
    </div>
  );
}

export default function ProgressPage() {
  const [studentId, setStudentId] = useState("1");
  const [student, setStudent] = useState<Student | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(id: number) {
    setLoading(true);
    setError(null);
    try {
      setStudent(await getStudent(id));
    } catch (err) {
      setStudent(null);
      setError(err instanceof Error ? err.message : "Could not load student");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(1);
  }, []);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Progress</h1>
          <p className="mt-1 text-sm text-zinc-600">
            Streaks, subject standing, and skills — what to practice next.
          </p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (studentId) load(Number(studentId));
          }}
          className="flex items-center gap-2"
        >
          <input
            type="number"
            min={1}
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
            className="w-24 rounded-lg border border-zinc-300 p-2 text-sm focus:border-emerald-500 focus:outline-none"
            aria-label="Student ID"
          />
          <button
            type="submit"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            Load
          </button>
        </form>
      </div>

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      {error && (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>
      )}

      {student && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between rounded-xl border border-zinc-200 p-5">
            <div>
              <h2 className="font-semibold">{student.name}</h2>
              {student.grade_level && (
                <p className="text-sm text-zinc-500">Grade {student.grade_level}</p>
              )}
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-orange-500">
                🔥 {student.streak_days}
              </p>
              <p className="text-xs text-zinc-500">day streak</p>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-200 p-5">
            <h2 className="font-semibold">By subject</h2>
            <div className="mt-4 flex flex-col gap-2">
              {Object.keys(student.subject_percentiles).length === 0 ? (
                <p className="text-sm text-zinc-500">
                  No subject stats yet — grade a worksheet to get started.
                </p>
              ) : (
                Object.entries(student.subject_percentiles).map(([k, v]) => (
                  <Bar key={k} label={k} value={v <= 1 ? v * 100 : v} />
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-zinc-200 p-5">
            <h2 className="font-semibold">Skills</h2>
            <div className="mt-4 flex flex-col gap-2">
              {Object.keys(student.learning_skills).length === 0 ? (
                <p className="text-sm text-zinc-500">
                  Skills appear here after more graded work.
                </p>
              ) : (
                Object.entries(student.learning_skills)
                  .sort(([, a], [, b]) => b - a)
                  .map(([k, v]) => <Bar key={k} label={k} value={v} />)
              )}
            </div>
            {student.mastered.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {student.mastered.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium capitalize text-emerald-800"
                  >
                    ✓ {skill.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
