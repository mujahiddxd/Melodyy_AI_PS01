"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui/EmptyState";
import { MockBadge } from "@/components/ui/MockBadge";

export default function ChatPlaceholder() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-16">
      <EmptyState
        icon="💬"
        title="Chat ordering is coming"
        hint="You'll type or speak your order in Hinglish here. This arrives in Stage 3."
        action={
          <div className="flex flex-col items-center gap-3">
            <MockBadge>PLACEHOLDER</MockBadge>
            <Link href={`/shop/${slug}`} className="btn-secondary">
              ← Back to shop
            </Link>
          </div>
        }
      />
    </main>
  );
}
