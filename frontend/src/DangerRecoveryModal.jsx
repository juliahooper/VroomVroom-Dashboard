import { createPortal } from 'react-dom'

/**
 * Modal shown when PC metrics reach danger threshold.
 * User can start emergency recovery (opens Vroom Vroom video on PC) or cancel.
 * Rendered via portal to document.body so it's never blocked by parent styles/events.
 */
export default function DangerRecoveryModal({ onYes, onCancel, isSubmitting }) {
  const content = (
    <div
      className="danger-recovery-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="danger-recovery-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div
        className="danger-recovery-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="danger-recovery-title" className="danger-recovery-modal__title">
          Emergency Recovery Mode
        </h2>
        <p className="danger-recovery-modal__message">
          PC metrics have reached a danger threshold. Begin emergency recovery mode? This will open the Vroom Vroom video in a new tab in your browser.
        </p>
        <div className="danger-recovery-modal__actions">
          <button
            type="button"
            className="danger-recovery-modal__btn danger-recovery-modal__btn--yes"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onYes()
            }}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Starting…' : 'Yes'}
          </button>
          <button
            type="button"
            className="danger-recovery-modal__btn danger-recovery-modal__btn--cancel"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onCancel()
            }}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
  return createPortal(content, document.body)
}
