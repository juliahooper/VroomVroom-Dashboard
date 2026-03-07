/**
 * White speech-bubble style badge: heart icon + count, with "Like count" label underneath.
 * Positioned middle-right of viewport via CSS.
 */
export default function LikeCountBadge({ count = 0 }) {
  return (
    <div className="like-count-badge" aria-label={`Like count: ${count}`}>
      <div className="like-count-badge__bubble">
        <span className="like-count-badge__heart" aria-hidden>
          <svg viewBox="0 0 24 24" fill="currentColor" className="like-count-badge__svg">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
          </svg>
        </span>
        <span className="like-count-badge__number">{Number(count)}</span>
      </div>
      <div className="like-count-badge__label">Like count</div>
    </div>
  )
}
