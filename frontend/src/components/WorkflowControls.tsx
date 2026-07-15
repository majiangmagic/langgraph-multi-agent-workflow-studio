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
      {controls.map((control) => (
        <label className="workflow-control" key={control.key}>
          <span>{control.label ?? control.key.replaceAll("_", " ")}</span>
          {control.type === "segmented" ? (
            <div className="segmented-control">
              {control.options.map((option) => (
                <button
                  className={values[control.key] === option.value ? "active" : ""}
                  disabled={disabled}
                  key={option.value}
                  onClick={() => onChange(control.key, option.value)}
                  type="button"
                >
                  {option.label ?? option.value}
                </button>
              ))}
            </div>
          ) : (
            <select
              disabled={disabled}
              onChange={(event) => onChange(control.key, event.target.value)}
              value={values[control.key] ?? control.default ?? ""}
            >
              {control.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label ?? option.value}
                </option>
              ))}
            </select>
          )}
        </label>
      ))}
    </div>
  );
}
