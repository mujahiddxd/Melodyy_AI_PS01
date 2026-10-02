"use client";

import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { DemoInbox } from "@/components/customer/DemoInbox";
import { Field } from "@/components/ui/Field";
import { MockBadge } from "@/components/ui/MockBadge";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { useCustomer } from "@/lib/customer";
import { cleanPhone, maskPhone, PHONE_RE } from "@/lib/format";
import type { CustomerAuthResponse, OtpRequestResponse } from "@/lib/types";

const EMPTY = ["", "", "", "", "", ""];

function errorText(e: unknown): string {
  if (!(e instanceof ApiError)) return "Something went wrong. Please try again.";
  switch (e.code) {
    case "OTP_INVALID": {
      const left = Number(e.data.attempts_left ?? 0);
      return left > 0
        ? `Wrong code. ${left} attempt${left === 1 ? "" : "s"} left.`
        : "Wrong code. No attempts left. Tap Resend for a new code.";
    }
    case "OTP_EXPIRED":
      return "This code has expired or was already used. Tap Resend for a new code.";
    case "OTP_TOO_MANY_ATTEMPTS":
      return "Too many wrong attempts. Tap Resend for a new code.";
    default:
      return e.message;
  }
}

export function OtpModal({ onClose, onVerified }: { onClose: () => void; onVerified?: () => void }) {
  const toast = useToast();
  const { signIn } = useCustomer();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phoneInput, setPhoneInput] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [digits, setDigits] = useState<string[]>(EMPTY);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false); // no attempts left / expired: only Resend helps
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<OtpRequestResponse["provider"] | null>(null);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000));

  async function sendCode(target: string): Promise<boolean> {
    setBusy(true);
    try {
      const res = await api<OtpRequestResponse>("/auth/customer/otp/request", { method: "POST", json: { phone: target } });
      setProvider(res.provider);
      const t = Date.now();
      setNow(t); // keep the countdown from starting at 0:31
      setResendAt(t + res.resend_after_seconds * 1000);
      setDigits(EMPTY);
      setCodeError(null);
      setLocked(false);
      if (res.provider === "mock") setInboxOpen(true);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "OTP_RATE_LIMITED") {
        const wait = Number(e.data.retry_after_seconds ?? 30);
        const t = Date.now();
        setNow(t);
        setResendAt(t + wait * 1000);
      }
      const msg = e instanceof ApiError ? e.message : "Could not send the code.";
      if (step === "phone") setPhoneError(msg);
      else setCodeError(msg);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function onPhoneSubmit(ev: FormEvent) {
    ev.preventDefault();
    const p = cleanPhone(phoneInput.trim());
    if (!PHONE_RE.test(p)) {
      setPhoneError("Enter a 10-digit mobile number starting with 6, 7, 8 or 9.");
      return;
    }
    setPhoneError(null);
    setPhone(p);
    if (await sendCode(p)) {
      setStep("code");
      setTimeout(() => boxes.current[0]?.focus(), 50);
    }
  }

  async function submitCode(code: string) {
    setBusy(true);
    setCodeError(null);
    try {
      const res = await api<CustomerAuthResponse>("/auth/customer/otp/verify", { method: "POST", json: { phone, code } });
      signIn(res.access_token, res.customer);
      toast.show("Phone verified.", "success");
      onVerified?.();
      onClose();
    } catch (e) {
      setCodeError(errorText(e));
      const dead =
        e instanceof ApiError &&
        (e.code === "OTP_EXPIRED" || e.code === "OTP_TOO_MANY_ATTEMPTS" || (e.code === "OTP_INVALID" && Number(e.data.attempts_left) === 0));
      setLocked(dead);
      setDigits(EMPTY);
      if (!dead) setTimeout(() => boxes.current[0]?.focus(), 30);
    } finally {
      setBusy(false);
    }
  }

  function setDigit(i: number, raw: string) {
    const v = raw.replace(/\D/g, "");
    if (v.length > 1) return fillAll(v);
    const next = [...digits];
    next[i] = v;
    setDigits(next);
    if (v && i < 5) boxes.current[i + 1]?.focus();
    if (next.every(Boolean)) void submitCode(next.join(""));
  }

  function fillAll(v: string) {
    const next = v.slice(0, 6).split("");
    while (next.length < 6) next.push("");
    setDigits(next);
    boxes.current[Math.min(v.length, 5)]?.focus();
    if (next.every(Boolean)) void submitCode(next.join(""));
  }

  function onKey(i: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[i] && i > 0) boxes.current[i - 1]?.focus();
    if (e.key === "ArrowLeft" && i > 0) boxes.current[i - 1]?.focus();
    if (e.key === "ArrowRight" && i < 5) boxes.current[i + 1]?.focus();
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const v = e.clipboardData.getData("text").replace(/\D/g, "");
    if (v) {
      e.preventDefault();
      fillAll(v);
    }
  }

  return (
    <>
      <Modal title={step === "phone" ? "Verify your phone" : "Enter the code"} onClose={onClose}>
        {step === "phone" ? (
          <form onSubmit={onPhoneSubmit} noValidate className="flex flex-col gap-5">
            <p className="text-muted">We&apos;ll send a 6-digit code. You need it once, before placing an order.</p>
            <Field label="Mobile number" htmlFor="otp-phone" error={phoneError}>
              <div className="flex items-center gap-2">
                <span className="chip font-semibold">+91</span>
                <input
                  id="otp-phone"
                  className="input"
                  inputMode="numeric"
                  autoComplete="tel-national"
                  placeholder="98765 43210"
                  maxLength={14}
                  value={phoneInput}
                  onChange={(e) => setPhoneInput(e.target.value)}
                  autoFocus
                />
              </div>
            </Field>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? "Sending…" : "→ Send code"}
            </button>
          </form>
        ) : (
          <div className="flex flex-col gap-5">
            <p className="text-muted">
              Code sent to <span className="font-semibold text-ink">{maskPhone(phone)}</span>.{" "}
              <button
                type="button"
                className="font-semibold text-lavender-deep underline"
                onClick={() => {
                  setStep("phone");
                  setCodeError(null);
                  setInboxOpen(false);
                }}
              >
                Change number
              </button>
            </p>
            {provider === "mock" && (
              <div className="flex flex-wrap items-center gap-3 rounded-input bg-cream-yellow p-3">
                <MockBadge>MOCK SMS</MockBadge>
                <span className="text-sm">No real SMS in demo mode.</span>
                <button type="button" className="text-sm font-semibold underline" onClick={() => setInboxOpen(true)}>
                  Open demo SMS inbox
                </button>
              </div>
            )}
            <div className="flex justify-between gap-2" role="group" aria-label="6-digit code">
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => {
                    boxes.current[i] = el;
                  }}
                  aria-label={`Digit ${i + 1}`}
                  inputMode="numeric"
                  autoComplete={i === 0 ? "one-time-code" : "off"}
                  maxLength={6}
                  value={d}
                  disabled={busy || locked}
                  onChange={(e) => setDigit(i, e.target.value)}
                  onKeyDown={(e) => onKey(i, e)}
                  onPaste={onPaste}
                  className={`h-14 w-12 rounded-input bg-white text-center font-mono text-2xl font-bold shadow-clay outline-none focus:ring-[3px] focus:ring-ink disabled:opacity-50 sm:w-14 ${
                    codeError ? "ring-[3px] ring-danger" : ""
                  }`}
                />
              ))}
            </div>
            {codeError && (
              <p role="alert" className="rounded-input bg-danger-fill p-3 font-medium text-danger">
                {codeError}
              </p>
            )}
            {busy && <p className="text-sm text-muted">Checking…</p>}
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="btn-secondary !py-2"
                disabled={resendIn > 0 || busy}
                onClick={() => void sendCode(phone)}
              >
                {resendIn > 0 ? `Resend in 0:${String(resendIn).padStart(2, "0")}` : "Resend code"}
              </button>
              <span className="text-sm text-muted">Code valid for 5 minutes</span>
            </div>
          </div>
        )}
      </Modal>
      {inboxOpen && provider === "mock" && step === "code" && <DemoInbox phone={phone} onClose={() => setInboxOpen(false)} />}
    </>
  );
}
