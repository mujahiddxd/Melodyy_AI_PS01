import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="card max-w-md text-center">
        <EmptyState
          title="Page not found"
          hint="The page you are looking for does not exist or may have been moved."
          action={
            <Link href="/" className="btn-primary mt-2">
              ← Return home
            </Link>
          }
        />
      </div>
    </main>
  );
}
