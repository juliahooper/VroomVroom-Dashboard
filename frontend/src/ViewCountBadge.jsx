/**
 * White speech-bubble style badge: eye icon + count, with "View count" label underneath.
 * Same styling as LikeCountBadge.
 */
export default function ViewCountBadge({ count = 0 }) {
  return (
    <div className="like-count-badge view-count-badge" aria-label={`View count: ${count}`}>
      <div className="like-count-badge__bubble">
        <span className="like-count-badge__icon" aria-hidden>
          <svg viewBox="0 0 24 24" fill="currentColor" className="like-count-badge__svg">
            <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z" />
          </svg>
        </span>
        <span className="like-count-badge__number">{Number(count)}</span>
      </div>
      <div className="like-count-badge__label">View count</div>
    </div>
  )
}
