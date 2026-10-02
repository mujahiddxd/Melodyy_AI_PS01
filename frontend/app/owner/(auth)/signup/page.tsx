"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthShell } from "@/components/owner/AuthShell";
import { Field } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError, setToken } from "@/lib/api";
import { cleanPhone, EMAIL_RE, PHONE_RE } from "@/lib/format";
import type { AuthResponse } from "@/lib/types";

export default function OwnerSignupPage() {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ name?: string; contact?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const c = contact.trim();
    const isEmail = c.includes("@");
    const next: typeof errors = {};
    if (!name.trim()) next.name = "Enter your name";
    if (isEmail ? !EMAIL_RE.test(c) : !PHONE_RE.test(cleanPhone(c))) {
      next.contact = "Enter a valid email or 10-digit mobile number";
    }
    if (password.length < 6) next.password = "Password must be at least 6 characters";
    setErrors(next);
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      const res = await api<AuthResponse>("/auth/owner/signup", {
        method: "POST",
        json: {
          name: name.trim(),
          email: isEmail ? c : null,
          phone: isEmail ? null : cleanPhone(c),
          password,
        },
      });
      setToken("owner", res.access_token);
      toast.show("Account created. Let's set up your shop.", "success");
      router.replace("/owner/setup");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Could not sign up. Please try again.", "error");
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="It takes a minute. You'll set up the shop next.">
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        <Field label="Your name" htmlFor="name" error={errors.name}>
          <input id="name" className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Email or phone" htmlFor="contact" error={errors.contact}>
          <input
            id="contact"
            className="input"
            autoComplete="username"
            placeholder="you@example.com or 9876543210"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password} hint="At least 6 characters">
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Creating…" : "→ Sign up"}
        </button>
        <p className="text-center text-muted">
          Already have an account?{" "}
          <Link href="/owner/login" className="font-semibold text-lavender-deep underline">
            Log in
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
