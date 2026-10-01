// Original BizYukti marks: a location-pin teardrop with ripple rings ("demand spreading from a place").

export function PinMark({ size = 26, fill = '#FB2462', hole = '#FFFFFF' }: { size?: number; fill?: string; hole?: string }) {
  return (
    <svg width={size} height={Math.round(size * 1.2)} viewBox="0 0 30 36" aria-hidden="true" focusable="false">
      <path d="M15 1C7.8 1 2 6.7 2 13.7 2 23.2 15 35 15 35s13-11.8 13-21.3C28 6.7 22.2 1 15 1z" fill={fill} />
      <circle cx="15" cy="13.5" r="5" fill={hole} />
    </svg>
  )
}

export function Logo({ inverted }: { inverted?: boolean }) {
  return (
    <span className={`logo${inverted ? ' is-inverted' : ''}`}>
      <PinMark hole={inverted ? '#0004ED' : '#FFFFFF'} />
      <span className="logo-word">Biz<b>Yukti</b></span>
    </span>
  )
}

export function HeroMotif({ tags = true }: { tags?: boolean }) {
  return (
    <div className="hero-art" aria-hidden="true">
      <svg viewBox="0 0 400 400" width="100%" height="100%" focusable="false">
        {[184, 146, 108, 70].map((r, i) => (
          <circle key={r} cx="200" cy="232" r={r} fill="none" stroke="#FFFFFF" strokeOpacity={0.14 + i * 0.09} strokeWidth="2" />
        ))}
        <ellipse cx="200" cy="318" rx="62" ry="12" fill="#000" fillOpacity="0.2" />
        <path d="M200 78c-50 0-90 39.5-90 88.5 0 66 90 150 90 150s90-84 90-150c0-49-40-88.5-90-88.5z" fill="#FB2462" />
        <circle cx="200" cy="165" r="32" fill="#0004ED" />
        <rect x="302" y="118" width="30" height="30" transform="rotate(45 317 133)" fill="#FD9833" stroke="#141414" strokeWidth="3" />
        <circle cx="92" cy="128" r="12" fill="#7AF444" stroke="#141414" strokeWidth="3" />
      </svg>
      {tags ? (
        <>
          <span className="hero-tag tag-1"><strong>184</strong> supporters</span>
          <span className="hero-tag tag-2">Shop, 850 sq ft</span>
          <span className="hero-tag tag-3">92% local fit</span>
        </>
      ) : null}
    </div>
  )
}
