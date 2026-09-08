"use client";

export function Field(props: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-700 dark:text-ink-300">{props.label}</span>
      <input
        type={props.type}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        autoComplete={props.autoComplete}
        required={props.required}
        className="w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition-colors focus:border-index-500 focus:ring-1 focus:ring-index-500 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
      />
      {props.hint && <span className="mt-1 block text-xs text-ink-400">{props.hint}</span>}
    </label>
  );
}
