type SettingsHeaderProps = {
  title: string;
  saving: boolean;
  onSave: () => void;
};

export function SettingsHeader({ title, saving, onSave }: SettingsHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
      <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save"}
      </button>
    </header>
  );
}
