import Link from "next/link";
import type { ReactNode } from "react";
import { MockBadge } from "@/components/ui/MockBadge";

// DESIGN.md section 6: auth = 50/50 split, left lavender panel with headline, right cream form.
export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <main className="grid min-h-screen md:grid-cols-2">
      <section className="flex flex-col justify-between gap-10 bg-lavender p-8 md:p-12">
        <Link href="/" className="font-display text-xl">
          Hinglish Order Desk
        </Link>
        <div>
          <p className="eyebrow !text-ink/70">For shopkeepers</p>
          <h1 className="mt-3 text-4xl leading-tight md:text-6xl">
            Your kirana,{" "}
            <span className="relative inline-block">
              <span className="absolute inset-x-0 bottom-1 h-[40%] bg-butter" aria-hidden />
              <span className="relative">on chat.</span>
            </span>
          </h1>
          <p className="mt-5 max-w-md text-lg">
            Customers order in Hinglish. You get a clean, stock-checked bill.
          </p>
        </div>
        <MockBadge>DEMO</MockBadge>
      </section>
      <section className="flex items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-md">
          <h2 className="text-3xl">{title}</h2>
          <p className="mb-6 mt-1 text-muted">{subtitle}</p>
          {children}
        </div>
      </section>
    </main>
  );
}
