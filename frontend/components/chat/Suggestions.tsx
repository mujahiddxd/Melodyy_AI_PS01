"use client";

// The demo messages (same texts the backend's LLM_MOCK fixtures know).
export const DEMO_SUGGESTIONS: { label: string; text: string }[] = [
  { label: "Hinglish", text: "bhaiya 2 kilo atta, ek Amul butter aur sugar half kilo, tel bhi chahiye" },
  { label: "हिंदी", text: "दो किलो चावल और एक पैकेट नमक भेज दो" },
  { label: "मराठी", text: "दोन किलो तांदूळ आणि अर्धा किलो साखर पाठवा" },
  { label: "Spelling variants", text: "amool butter aur parle g 3 packet" },
  { label: "Unknown + vague", text: "oats aur thoda cheeni" },
  { label: "Gibberish", text: "asdkj qwe zz" },
];

export function Suggestions({ disabled, onPick }: { disabled: boolean; onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-4 py-6 text-center" data-testid="chat-empty">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sky text-2xl">💬</div>
      <div>
        <h2 className="text-2xl">Order the way you talk</h2>
        <p className="mt-1 text-muted">
          Type in Hinglish, Hindi or Marathi. No login needed. Tap an example to try it:
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {DEMO_SUGGESTIONS.map((s) => (
          <button
            key={s.text}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s.text)}
            className="chip max-w-full text-left transition duration-150 hover:-translate-y-0.5 hover:ring-[3px] hover:ring-ink disabled:opacity-50"
          >
            <span className="eyebrow block">✦ {s.label}</span>
            <span className="block break-words">{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
