"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { MockBadge } from "@/components/ui/MockBadge";
import { Spinner } from "@/components/ui/Spinner";
import { getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/owner/orders", label: "Orders", icon: "🧾" },
  { href: "/owner/products", label: "Products", icon: "📦" },
  { href: "/owner/setup", label: "Setup", icon: "⚙️" },
  { href: "/owner/insights", label: "Insights", icon: "📈" },
];

export default function OwnerAppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken("owner")) router.replace("/owner/login");
    else setReady(true);
  }, [router]);

  function logout() {
    setToken("owner", null);
    router.replace("/owner/login");
  }

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Spinner label="Checking your session…" />
      </main>
    );
  }

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 sm:px-6">
      <nav className="flex flex-wrap items-center gap-2 rounded-full bg-white px-4 py-2 shadow-clay print:hidden">
        <Link href="/owner/orders" className="mr-2 font-display text-lg">
          Order Desk
        </Link>
        <div className="flex flex-wrap items-center gap-1">
          {NAV.map((n) => {
            const active = pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold ${
                  active ? "bg-ink text-white" : "hover:bg-cream"
                }`}
              >
                <span aria-hidden>{n.icon}</span>
                {n.label}
              </Link>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <MockBadge>DEMO</MockBadge>
          <button type="button" onClick={logout} className="btn-secondary !px-4 !py-1.5 text-sm">
            Log out
          </button>
          <span aria-hidden className="flex h-9 w-9 items-center justify-center rounded-full bg-sky font-bold">
            S
          </span>
        </div>
      </nav>
      <main className="py-10">{children}</main>
    </div>
  );
}
