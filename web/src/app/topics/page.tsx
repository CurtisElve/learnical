"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listTopics, type Topic } from "@/lib/api";

const SUBJECTS = [
  { value: "math", label: "Math" },
  { value: "science", label: "Science" },
  { value: "english", label: "English" },
];

const GRADES = ["K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];

export default function TopicsPage() {
  const [subject, setSubject] = useState("math");
  const [grade, setGrade] = useState("");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listTopics(subject, grade || undefined)
      .then(setTopics)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load topics"),
      )
      .finally(() => setLoading(false));
  }, [subject, grade]);

  const byUnit = useMemo(() => {
    const groups = new Map<string, Topic[]>();
    for (const t of topics) {
      const key = grade ? t.unit : `Grade ${t.grade} · ${t.unit}`;
      groups.set(key, [...(groups.get(key) ?? []), t]);
    }
    return [...groups.entries()];
  }, [topics, grade]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold">Topic library</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Browse by subject and grade, then build a practice set from any topic.
        </p>
      </div>

      <div className="flex flex-wrap gap-4">
        <div className="flex gap-2">
          {SUBJECTS.map((s) => (
            <button
              key={s.value}
              onClick={() => setSubject(s.value)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                subject === s.value
                  ? "bg-emerald-600 text-white"
                  : "border border-zinc-300 text-zinc-600 hover:border-emerald-400"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <select
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
          aria-label="Grade"
        >
          <option value="">All grades</option>
          {GRADES.map((g) => (
            <option key={g} value={g}>
              Grade {g}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="text-sm text-zinc-500">Loading topics…</p>}
      {error && (
        <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>
      )}
      {!loading && !error && topics.length === 0 && (
        <p className="text-sm text-zinc-500">
          No topics here yet. Run <code>python/seed_topics.py</code> to load the starter
          curriculum.
        </p>
      )}

      <div className="flex flex-col gap-6">
        {byUnit.map(([unit, unitTopics]) => (
          <section key={unit}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {unit}
            </h2>
            <div className="flex flex-col gap-2">
              {unitTopics.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between gap-4 rounded-xl border border-zinc-200 p-4 hover:border-emerald-300"
                >
                  <div>
                    <h3 className="font-medium">{t.name}</h3>
                    {t.description && (
                      <p className="text-sm text-zinc-500">{t.description}</p>
                    )}
                  </div>
                  <Link
                    href={`/practice?topic=${t.id}&name=${encodeURIComponent(t.name)}`}
                    className="shrink-0 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
                  >
                    Practice
                  </Link>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
