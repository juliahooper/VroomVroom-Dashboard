/**
 * Modal shown when PC metrics reach danger threshold.
 * User can start emergency recovery (opens Vroom Vroom video on PC) or cancel.
 */
export default function DangerRecoveryModal({ onYes, onCancel, isSubmitting }) {
  return (
    <div className="danger-recovery-overlay" role="dialog" aria-modal="true" aria-labelledby="danger-recovery-title">
      <div className="danger-recovery-modal">
        <h2 id="danger-recovery-title" className="danger-recovery-modal__title">
          Emergency Recovery Mode
        </h2>
        <p className="danger-recovery-modal__message">
          PC metrics have reached a danger threshold. Begin emergency recovery mode? This will open the Vroom Vroom video on the PC.
        </p>
        <div className="danger-recovery-modal__actions">
          <button
            type="button"
            className="danger-recovery-modal__btn danger-recovery-modal__btn--yes"
            onClick={onYes}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Starting…' : 'Yes'}
          </button>
          <button
            type="button"
            className="danger-recovery-modal__btn danger-recovery-modal__btn--cancel"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
