"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthShell } from "@/components/owner/AuthShell";
import { Field } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import { cleanPhone, EMAIL_RE, PHONE_RE } from "@/lib/format";
import type { AuthResponse } from "@/lib/types";

export default function OwnerLoginPage() {
  const router = useRouter();
  const toast = useToast();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ identifier?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("expired")) {
      toast.show("Your session expired. Please log in again.", "info");
    } else if (getToken("owner")) {
      router.replace("/owner/orders");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const id = identifier.trim();
    const next: typeof errors = {};
    if (!id.includes("@") ? !PHONE_RE.test(cleanPhone(id)) : !EMAIL_RE.test(id)) {
      next.identifier = "Enter a valid email or 10-digit mobile number";
    }
    if (password.length < 6) next.password = "Password must be at least 6 characters";
    setErrors(next);
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      const res = await api<AuthResponse>("/auth/owner/login", { method: "POST", json: { identifier: id, password } });
      setToken("owner", res.access_token);
      router.replace(res.has_shop ? "/owner/orders" : "/owner/setup");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Could not log in. Please try again.", "error");
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Log in to manage your shop.">
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        <Field label="Email or phone" htmlFor="identifier" error={errors.identifier}>
          <input
            id="identifier"
            className="input"
            autoComplete="username"
            placeholder="demo@shop.in or 9876543210"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password}>
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Logging in…" : "→ Log in"}
        </button>
        <p className="text-center text-muted">
          New here?{" "}
          <Link href="/owner/signup" className="font-semibold text-lavender-deep underline">
            Create a shop account
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
