import { useEffect, useRef, type ReactNode } from 'react';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/** Side panel with Escape-to-close, focus handling and scroll lock. */
export default function Drawer({ title, onClose, children, footer }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const savedOverflow = document.body.style.overflow;
    const inertElements: [HTMLElement, boolean][] = [];
    let branch: HTMLElement | null = panelRef.current?.parentElement ?? null;
    while (branch && branch !== document.body) {
      for (const sibling of Array.from(branch.parentElement?.children ?? [])) {
        if (sibling !== branch && sibling instanceof HTMLElement) {
          inertElements.push([sibling, sibling.inert]); sibling.inert = true;
        }
      }
      branch = branch.parentElement;
    }
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onCloseRef.current(); }
      if (e.key !== 'Tab') return;
      const controls = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]'
      ) ?? []).filter(el => el.tabIndex >= 0 && el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { e.preventDefault(); panelRef.current?.focus(); return; }
      if (e.shiftKey && (document.activeElement === first || !panelRef.current?.contains(document.activeElement))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !panelRef.current?.contains(document.activeElement))) {
        e.preventDefault(); first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = savedOverflow;
      inertElements.forEach(([element, inert]) => { element.inert = inert; });
      previous?.focus();
    };
  }, []);

  return (
    <div className="drawer">
      <button className="drawer__backdrop" aria-label="إغلاق" tabIndex={-1} onClick={onClose} />
      <div ref={panelRef} tabIndex={-1} className="drawer__panel" role="dialog" aria-modal="true" aria-label={title}>
        <div className="drawer__head">
          <h2 className="drawer__title">{title}</h2>
          <button ref={closeRef} className="btn btn--icon" aria-label="إغلاق" onClick={onClose}>×</button>
        </div>
        <div className="drawer__body">{children}</div>
        {footer && <div className="drawer__foot">{footer}</div>}
      </div>
    </div>
  );
}
