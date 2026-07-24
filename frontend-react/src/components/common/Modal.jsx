import { X } from 'lucide-react';
import { useEffect } from 'react';

export default function Modal({ title, onClose, children, size = 'md', footer }) {
  // Close on Escape key
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className={`modal ${size === 'lg' ? 'modal-lg' : ''}`} role="dialog" aria-modal="true">
        {(title || onClose) && (
          <div className="modal-header">
            {title && <div className="modal-title">{title}</div>}
            {onClose && (
              <button className="modal-close" onClick={onClose} id="modal-close-btn" aria-label="Close">
                <X size={18} />
              </button>
            )}
          </div>
        )}
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
