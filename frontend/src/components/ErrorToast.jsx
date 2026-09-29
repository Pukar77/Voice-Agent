import { AlertIcon, CloseIcon } from './icons.jsx'

export function ErrorToast({ message, onDismiss }) {
  if (!message) return null

  return (
    <div className="toast" role="alert">
      <span className="toast__icon">
        <AlertIcon width={18} height={18} />
      </span>

      <p className="toast__text">{message}</p>

      <button type="button" className="toast__close" onClick={onDismiss} aria-label="Dismiss">
        <CloseIcon width={16} height={16} />
      </button>
    </div>
  )
}
