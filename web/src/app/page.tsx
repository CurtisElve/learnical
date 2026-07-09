import Link from "next/link";

const features = [
  {
    href: "/solve",
    title: "Step-by-step tutor",
    body: "Type any question or snap a photo. Learnical walks through the method one step at a time, explaining the why behind each move.",
    cta: "Ask a question",
  },
  {
    href: "/scan",
    title: "Scan & grade worksheets",
    body: "Upload a photo of finished handwritten work. Every question is graded on the final answer, the method, and how much work was shown.",
    cta: "Grade a worksheet",
  },
  {
    href: "/progress",
    title: "Progress dashboard",
    body: "Streaks, subject percentiles, and skill mastery — so students and teachers can both see what to practice next.",
    cta: "View progress",
  },
];

export default function Home() {
  return (
    <div className="flex flex-col gap-12">
      <section className="pt-8 text-center">
        <h1 className="text-4xl font-bold tracking-tight">
          Homework that <span className="text-emerald-600">teaches back</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-zinc-600">
          Learnical explains every problem in steps, grades handwritten work on the
          reasoning — not just the answer — and builds practice around what each
          student actually needs.
        </p>
      </section>

      <section className="grid gap-6 sm:grid-cols-3">
        {features.map((f) => (
          <Link
            key={f.href}
            href={f.href}
            className="group flex flex-col rounded-2xl border border-zinc-200 p-6 transition hover:border-emerald-400 hover:shadow-md"
          >
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-2 flex-1 text-sm text-zinc-600">{f.body}</p>
            <span className="mt-4 text-sm font-medium text-emerald-600 group-hover:underline">
              {f.cta} →
            </span>
          </Link>
        ))}
      </section>
    </div>
  );
}
