"use client";

import { Spinner } from "@/components/ui/Spinner";
import { useCustomer } from "@/lib/customer";
import { maskPhone } from "@/lib/format";

/** Guest -> "Verify phone"; verified -> masked phone + log out. */
export function CustomerBar({ onVerify }: { onVerify: () => void }) {
  const { customer, loading, logout } = useCustomer();
  if (loading) return <Spinner label="Checking verification…" />;
  if (!customer) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <span className="badge border-2 border-ink bg-white">Guest</span>
        <button type="button" className="btn-primary !py-2" onClick={onVerify}>
          → Verify phone
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="badge border-2 border-ink bg-mint">✓ Verified {maskPhone(customer.phone)}</span>
      <button type="button" className="btn-secondary !py-2 text-sm" onClick={logout}>
        Log out
      </button>
    </div>
  );
}
