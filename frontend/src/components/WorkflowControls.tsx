import type { WorkflowControl, WorkflowInputs } from "../types";

type Props = {
  controls: WorkflowControl[];
  values: WorkflowInputs;
  disabled?: boolean;
  onChange: (key: string, value: string) => void;
};

export function WorkflowControls({ controls, values, disabled, onChange }: Props) {
  if (!controls.length) return null;
  return (
    <div className="workflow-controls" aria-label="工作流参数">
      {controls.map((control) => {
        const type = (control.type || "select").toLowerCase();
        const options = control.options ?? [];
        const value = values[control.key] ?? control.default ?? options[0]?.value ?? "";
        const inputTypes = new Set([
          "text", "search", "number", "range", "date", "time", "datetime-local",
          "color", "email", "url",
        ]);
        const hasOptions = options.length > 0;
        const useSelect = type === "select" || (!inputTypes.has(type) && type !== "segmented" && type !== "toggle" && type !== "checkbox" && type !== "textarea" && hasOptions);
        return (
          <label className={`workflow-control workflow-control-${type}`} key={control.key}>
            <span>{control.label ?? control.key.replaceAll("_", " ")}</span>
            {type === "segmented" && hasOptions ? (
            <div className="segmented-control">
              {options.map((option) => (
                <button
                  className={value === option.value ? "active" : ""}
                  disabled={disabled}
                  key={option.value}
                  onClick={() => onChange(control.key, option.value)}
                  type="button"
                >
                  {option.label ?? option.value}
                </button>
              ))}
            </div>
          ) : type === "toggle" || type === "checkbox" ? (
            <input
              checked={value === (options[0]?.value ?? "true")}
              disabled={disabled}
              onChange={(event) => onChange(
                control.key,
                event.target.checked
                  ? options[0]?.value ?? "true"
                  : options[1]?.value ?? "false",
              )}
              type="checkbox"
            />
          ) : type === "textarea" ? (
            <textarea
              disabled={disabled}
              onChange={(event) => onChange(control.key, event.target.value)}
              placeholder={control.placeholder}
              value={value}
            />
          ) : useSelect ? (
            <select
              disabled={disabled}
              onChange={(event) => onChange(control.key, event.target.value)}
              value={value}
            >
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label ?? option.value}
                </option>
              ))}
            </select>
          ) : (
            <input
              disabled={disabled}
              max={control.max}
              min={control.min}
              onChange={(event) => onChange(control.key, event.target.value)}
              placeholder={control.placeholder}
              step={control.step}
              type={inputTypes.has(type) ? type : "text"}
              value={value}
            />
          )}
          </label>
        );
      })}
    </div>
  );
}
