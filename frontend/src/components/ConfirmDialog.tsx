import { AlertTriangle, X } from "lucide-react";
import { useEffect, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({ open, title, description, confirmLabel = "删除", onCancel, onConfirm }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog className="confirm-dialog" onCancel={onCancel} ref={dialogRef}>
      <button className="dialog-close" onClick={onCancel} title="关闭" type="button"><X size={17} /></button>
      <AlertTriangle className="dialog-warning" size={22} />
      <h3>{title}</h3>
      <p>{description}</p>
      <div className="dialog-actions">
        <button className="secondary-button" onClick={onCancel} type="button">取消</button>
        <button className="danger-button" onClick={onConfirm} type="button">{confirmLabel}</button>
      </div>
    </dialog>
  );
}
