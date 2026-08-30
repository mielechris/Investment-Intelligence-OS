import type { LivingCastKey } from "./livingCast";
import { LIVING_CAST } from "./livingCast";
import "./LivingCharacterAvatar.css";

type Props = {
  characterKey: LivingCastKey;
  active?: boolean;
  reacting?: boolean;
  compact?: boolean;
};

function HumanAvatar({ characterKey, active, reacting }: Props) {
  const member = LIVING_CAST[characterKey];
  return (
    <div
      className={`living-avatar living-avatar--${characterKey} ${active ? "is-active" : ""} ${reacting ? "is-reacting" : ""}`}
      aria-label={`${member.displayName}, ${member.governedRole}`}
      role="img"
    >
      <svg viewBox="0 0 120 138" aria-hidden="true">
        <defs>
          <linearGradient id={`coat-${characterKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="currentColor" stopOpacity="0.24" />
            <stop offset="1" stopColor="currentColor" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        <ellipse className="living-avatar__halo" cx="60" cy="68" rx="48" ry="58" />
        <path className="living-avatar__body" d="M27 132c3-29 15-42 33-42s30 13 33 42H27Z" fill={`url(#coat-${characterKey})`} />
        <rect className="living-avatar__neck" x="52" y="78" width="16" height="18" rx="7" />
        <ellipse className="living-avatar__head" cx="60" cy="59" rx="28" ry="31" />
        <path className="living-avatar__hair" d="M34 51c2-22 13-32 28-32 15 0 26 9 28 29-9-6-17-8-27-8-11 0-20 3-29 11Z" />
        <g className="living-avatar__eyes">
          <ellipse cx="50" cy="59" rx="3.5" ry="2.3" />
          <ellipse cx="70" cy="59" rx="3.5" ry="2.3" />
        </g>
        <path className="living-avatar__nose" d="M60 60v8l-3 2h6" />
        <path className="living-avatar__mouth" d="M52 76c5 2 11 2 16 0" />
        <path className="living-avatar__lapel" d="M43 96l17 14 17-14M60 110v20" />

        {characterKey === "policy" ? (
          <g className="living-avatar__accessory">
            <path d="M31 42h58" />
            <path d="M43 31c8-7 26-7 34 0l3 10H40l3-10Z" />
            <path d="M75 92h14v24H75z" />
            <path d="M78 97h8M78 102h8M78 107h8" />
          </g>
        ) : null}

        {characterKey === "macro" ? (
          <g className="living-avatar__accessory">
            <path d="M35 43c9-17 37-23 52-5" />
            <path d="M81 91c8 5 12 13 14 24" />
            <path d="M78 99l5-7 5 7 6-11" />
          </g>
        ) : null}

        {characterKey === "fundamentals" ? (
          <g className="living-avatar__accessory">
            <rect x="43" y="53" width="14" height="10" rx="2" />
            <rect x="63" y="53" width="14" height="10" rx="2" />
            <path d="M57 58h6" />
            <path d="M30 105h17v22H30zM34 110h9M34 115h9M34 120h6" />
          </g>
        ) : null}

        {characterKey === "market_structure" ? (
          <g className="living-avatar__accessory">
            <path d="M84 50c6 4 8 12 7 20" />
            <circle cx="90" cy="69" r="3" />
            <path d="M86 72l8 5" />
            <path d="M26 111h22M26 117h29M26 123h18" />
          </g>
        ) : null}

        {characterKey === "commodities" ? (
          <g className="living-avatar__accessory">
            <path d="M35 44c2-15 12-24 25-24s23 9 25 24" />
            <path d="M31 44h58" />
            <path d="M82 99h12v28H82zM85 104h6M85 109h6" />
          </g>
        ) : null}

        {characterKey === "geo_weather" ? (
          <g className="living-avatar__accessory">
            <path d="M34 60c-1-20 10-32 26-32s27 12 26 32" />
            <path d="M34 59h-6v17h7M86 59h6v17h-7M88 74l8 5" />
            <circle cx="34" cy="109" r="10" />
            <path d="M25 109h18M34 100v18" />
          </g>
        ) : null}

        {characterKey === "skeptic" ? (
          <g className="living-avatar__accessory living-avatar__accessory--red">
            <path d="M38 54h17M65 54h17M55 57h10" />
            <path d="M31 111h20v15H31zM34 114h14M34 118h11" />
            <path d="M75 103l14 18M89 103l-14 18" />
          </g>
        ) : null}

        {characterKey === "portfolio" ? (
          <g className="living-avatar__accessory">
            <path d="M60 109l-5 8 5 11 5-11-5-8Z" />
            <path d="M79 100h15v27H79zM82 105h9M82 111h5M82 117h7" />
          </g>
        ) : null}
      </svg>
      <div className="living-avatar__badge"><span>{member.monogram}</span><i /></div>
    </div>
  );
}

function MaxAvatar({ active, reacting, compact }: Props) {
  return (
    <div className={`living-avatar living-avatar--max ${active ? "is-active" : ""} ${reacting ? "is-reacting" : ""} ${compact ? "is-compact" : ""}`} role="img" aria-label="MAX, bulldog factory foreman">
      <svg viewBox="0 0 140 150" aria-hidden="true">
        <ellipse className="living-avatar__halo" cx="70" cy="72" rx="56" ry="62" />
        <path className="max-avatar__ear max-avatar__ear--left" d="M31 49C15 33 20 15 40 21l12 24Z" />
        <path className="max-avatar__ear max-avatar__ear--right" d="M109 49c16-16 11-34-9-28L88 45Z" />
        <ellipse className="max-avatar__head" cx="70" cy="63" rx="43" ry="39" />
        <g className="max-avatar__brow"><path d="M42 49l17 4" /><path d="M98 49l-17 4" /></g>
        <g className="max-avatar__eyes"><ellipse cx="53" cy="58" rx="4" ry="3" /><ellipse cx="87" cy="58" rx="4" ry="3" /></g>
        <ellipse className="max-avatar__muzzle" cx="70" cy="77" rx="24" ry="16" />
        <path className="max-avatar__nose" d="M61 70c6-5 12-5 18 0-2 8-16 8-18 0Z" />
        <path className="max-avatar__mouth" d="M70 78v7M70 85c-7 5-14 3-18-1M70 85c7 5 14 3 18-1" />
        <path className="max-avatar__body" d="M30 146c2-34 17-49 40-49s38 15 40 49H30Z" />
        <path className="max-avatar__collar" d="M43 103h54l-5 18H48l-5-18Z" />
        <circle className="max-avatar__tag" cx="70" cy="118" r="9" />
        <text x="70" y="122" textAnchor="middle" className="max-avatar__tag-text">M</text>
      </svg>
      <div className="living-avatar__badge"><span>MAX</span><i /></div>
    </div>
  );
}

export default function LivingCharacterAvatar(props: Props) {
  return props.characterKey === "max" ? <MaxAvatar {...props} /> : <HumanAvatar {...props} />;
}
