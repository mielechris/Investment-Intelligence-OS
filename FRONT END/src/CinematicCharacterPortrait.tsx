import { useId, type ReactNode } from "react";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import "./CinematicCharacterPortrait.css";

type HumanCastKey = Exclude<LivingCastKey, "max">;
type PortraitVariant = "card" | "desk" | "scene" | "boss";

type Props = {
  characterKey: LivingCastKey;
  active?: boolean;
  reacting?: boolean;
  variant?: PortraitVariant;
  showLabel?: boolean;
};

type HumanConfig = {
  skin: string;
  skinShadow: string;
  hair: string;
  suit: string;
  shirt: string;
  tie: string;
  accent: string;
  hairStyle: "slick" | "wave" | "crop" | "cap" | "silver" | "bald" | "side";
  accessory: "document" | "yield" | "calculator" | "headset" | "tanker" | "weather" | "dossier" | "ledger";
  glasses?: boolean;
  beard?: boolean;
  cigar?: boolean;
};

const HUMAN_CONFIG: Record<HumanCastKey, HumanConfig> = {
  policy: {
    skin: "#a96f4f",
    skinShadow: "#5c3426",
    hair: "#18110d",
    suit: "#111314",
    shirt: "#d1c0a7",
    tie: "#7a251f",
    accent: "#c58a3d",
    hairStyle: "slick",
    accessory: "document",
  },
  macro: {
    skin: "#98664b",
    skinShadow: "#4e3024",
    hair: "#252019",
    suit: "#101617",
    shirt: "#c6c0aa",
    tie: "#3d5c4b",
    accent: "#8ca078",
    hairStyle: "side",
    accessory: "yield",
    glasses: true,
  },
  fundamentals: {
    skin: "#b37c5d",
    skinShadow: "#64402f",
    hair: "#3a2c20",
    suit: "#171818",
    shirt: "#d7c9b2",
    tie: "#6a4a2c",
    accent: "#c5a46b",
    hairStyle: "crop",
    accessory: "calculator",
    glasses: true,
  },
  market_structure: {
    skin: "#9d6b4f",
    skinShadow: "#533426",
    hair: "#14110f",
    suit: "#0c1518",
    shirt: "#b8c3bd",
    tie: "#315c63",
    accent: "#6d9992",
    hairStyle: "wave",
    accessory: "headset",
  },
  commodities: {
    skin: "#ad7552",
    skinShadow: "#5e3928",
    hair: "#2b2118",
    suit: "#211d14",
    shirt: "#cbb88f",
    tie: "#715629",
    accent: "#ad8743",
    hairStyle: "cap",
    accessory: "tanker",
    beard: true,
  },
  geo_weather: {
    skin: "#9f6d54",
    skinShadow: "#56372a",
    hair: "#201914",
    suit: "#11191a",
    shirt: "#bcc5b6",
    tie: "#395e52",
    accent: "#668e82",
    hairStyle: "crop",
    accessory: "weather",
    beard: true,
  },
  skeptic: {
    skin: "#98614b",
    skinShadow: "#4e2b24",
    hair: "#15100e",
    suit: "#1a0d0f",
    shirt: "#c4aea1",
    tie: "#7e221f",
    accent: "#a33e37",
    hairStyle: "bald",
    accessory: "dossier",
    beard: true,
    cigar: true,
  },
  portfolio: {
    skin: "#a97353",
    skinShadow: "#59372a",
    hair: "#19140f",
    suit: "#101418",
    shirt: "#d2c6ad",
    tie: "#9d7a39",
    accent: "#b19456",
    hairStyle: "slick",
    accessory: "ledger",
  },
};

function Hair({ style, fill }: { style: HumanConfig["hairStyle"]; fill: string }) {
  switch (style) {
    case "slick":
      return <path className="ccp-hair" fill={fill} d="M82 100c6-39 29-58 63-57 35 1 57 22 60 57-20-14-39-20-61-20-23 0-42 7-62 20Z" />;
    case "side":
      return <path className="ccp-hair" fill={fill} d="M79 104c6-41 31-62 67-60 29 2 50 17 57 46-20-10-40-14-60-12-25 2-44 11-64 26Z" />;
    case "wave":
      return <path className="ccp-hair" fill={fill} d="M78 101c5-34 24-56 58-59 30-3 54 12 66 45-15-8-27-12-38-12-8-13-21-15-37-8-18 8-32 19-49 34Z" />;
    case "crop":
      return <path className="ccp-hair" fill={fill} d="M84 89c13-37 37-50 65-47 26 3 43 17 52 43-38-13-78-11-117 4Z" />;
    case "cap":
      return <g className="ccp-cap"><path fill={fill} d="M79 91c4-31 28-51 62-51 35 0 59 20 64 51H79Z" /><path d="M72 92h142" /><path d="M112 53h64" /></g>;
    case "silver":
      return <path className="ccp-hair" fill={fill} d="M78 103c4-37 24-59 58-62 35-3 61 17 68 53-15-7-27-11-37-12-12-15-27-18-46-8-17 8-30 17-43 29Z" />;
    case "bald":
      return <path className="ccp-hair ccp-hair--bald" fill={fill} d="M97 74c18-27 71-31 95 2-18-8-34-11-50-10-16 0-31 3-45 8Z" />;
  }
}

function Accessory({ kind, accent }: { kind: HumanConfig["accessory"]; accent: string }) {
  const common = { stroke: accent };
  switch (kind) {
    case "document":
      return <g className="ccp-prop" {...common}><path d="M180 218h42v67h-42z" /><path d="M188 231h26M188 242h26M188 253h21M188 264h25" /><path d="M76 259l29-20 24 35" /></g>;
    case "yield":
      return <g className="ccp-prop" {...common}><path d="M178 240h48v42h-48z" /><path d="M184 269l9-11 10 5 8-19 10 7" /><path d="M68 240c15-11 31-13 47-5" /></g>;
    case "calculator":
      return <g className="ccp-prop" {...common}><rect x="180" y="229" width="42" height="57" rx="3" /><path d="M188 238h26v10h-26zM189 256h5M200 256h5M211 256h5M189 267h5M200 267h5M211 267h5M189 278h16" /></g>;
    case "headset":
      return <g className="ccp-prop" {...common}><path d="M89 122c0-37 24-63 57-63 34 0 57 25 57 62" /><path d="M89 116h-12v35h13M203 116h12v35h-13M207 149l19 10" /><path d="M70 263h51M70 274h70M70 285h42" /></g>;
    case "tanker":
      return <g className="ccp-prop" {...common}><path d="M175 247h45v31h-45z" /><path d="M179 247l8-15h20l9 15M186 258h20M185 268h28" /><circle cx="185" cy="282" r="5" /><circle cx="211" cy="282" r="5" /></g>;
    case "weather":
      return <g className="ccp-prop" {...common}><circle cx="200" cy="255" r="29" /><path d="M171 255h58M200 226v58M180 237c13 10 27 10 40 0M180 273c13-10 27-10 40 0" /><path d="M74 264l14-18 14 14 15-25" /></g>;
    case "dossier":
      return <g className="ccp-prop ccp-prop--red" {...common}><path d="M176 235h49v51h-49z" /><path d="M184 244h26M184 255h33M184 266h21" /><path d="M181 278l37-35M218 278l-37-35" /></g>;
    case "ledger":
      return <g className="ccp-prop" {...common}><path d="M176 231h48v57h-48z" /><path d="M185 242h30M185 254h23M185 266h28M185 278h16" /><path d="M82 251l11-12 10 8 13-20 13 10" /></g>;
  }
}

function HumanPortrait({ characterKey, idPrefix }: { characterKey: HumanCastKey; idPrefix: string }) {
  const config = HUMAN_CONFIG[characterKey];
  return (
    <svg viewBox="0 0 280 340" aria-hidden="true">
      <defs>
        <linearGradient id={`${idPrefix}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2b180c" />
          <stop offset="0.48" stopColor="#0a0705" />
          <stop offset="1" stopColor="#020202" />
        </linearGradient>
        <radialGradient id={`${idPrefix}-lamp`} cx="50%" cy="0%" r="75%">
          <stop offset="0" stopColor="#d58a31" stopOpacity=".38" />
          <stop offset=".48" stopColor="#7d3914" stopOpacity=".08" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${idPrefix}-skin`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={config.skin} />
          <stop offset=".62" stopColor={config.skin} />
          <stop offset="1" stopColor={config.skinShadow} />
        </linearGradient>
        <linearGradient id={`${idPrefix}-suit`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={config.suit} />
          <stop offset="1" stopColor="#030303" />
        </linearGradient>
        <filter id={`${idPrefix}-grain`} x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency=".78" numOctaves="2" seed="7" result="noise" />
          <feColorMatrix in="noise" type="saturate" values="0" result="gray" />
          <feComponentTransfer in="gray" result="faded"><feFuncA type="table" tableValues="0 .10" /></feComponentTransfer>
          <feBlend in="SourceGraphic" in2="faded" mode="soft-light" />
        </filter>
        <filter id={`${idPrefix}-shadow`} x="-30%" y="-30%" width="160%" height="170%">
          <feDropShadow dx="0" dy="11" stdDeviation="9" floodColor="#000" floodOpacity=".72" />
        </filter>
      </defs>

      <rect className="ccp-frame-bg" x="9" y="8" width="262" height="324" rx="3" fill={`url(#${idPrefix}-bg)`} />
      <rect className="ccp-frame-light" x="9" y="8" width="262" height="324" rx="3" fill={`url(#${idPrefix}-lamp)`} />
      <g className="ccp-wood" opacity=".28"><path d="M28 8v324M78 8v324M128 8v324M178 8v324M228 8v324" /><path d="M9 292h262" /></g>
      <g className="ccp-smoke" opacity=".24"><path d="M234 65c-21-17-6-29 4-43" /><path d="M244 87c-22-13-8-29 0-42" /></g>

      <g filter={`url(#${idPrefix}-shadow)`}>
        <path className="ccp-shoulders" fill={`url(#${idPrefix}-suit)`} d="M48 330c3-71 36-111 92-111 57 0 89 40 93 111H48Z" />
        <path className="ccp-shirt" fill={config.shirt} d="M113 226l27 24 27-24 17 104H96l17-104Z" />
        <path className="ccp-lapel" d="M91 233l49 51 49-51M140 284v46" />
        <path className="ccp-tie" fill={config.tie} d="M133 250h14l8 18-15 39-15-39 8-18Z" />
        <rect className="ccp-neck" x="119" y="190" width="43" height="48" rx="16" fill={`url(#${idPrefix}-skin)`} />
        <ellipse className="ccp-ear" cx="87" cy="139" rx="12" ry="19" fill={config.skinShadow} />
        <ellipse className="ccp-ear" cx="197" cy="139" rx="12" ry="19" fill={config.skinShadow} />
        <path className="ccp-face" fill={`url(#${idPrefix}-skin)`} d="M91 113c0-46 23-72 52-72 34 0 57 25 57 72v42c0 40-25 70-57 70-31 0-52-30-52-70v-42Z" />
        <path className="ccp-face-shadow" d="M145 45c35 8 51 34 49 75l-4 48c-10 24-26 39-47 47 14-27 17-55 12-82-5-30-8-58-10-88Z" />
        <Hair style={config.hairStyle} fill={config.hair} />
        <path className="ccp-brow" d="M107 125c9-7 19-8 29-3M154 122c10-5 20-4 29 3" />
        <g className="ccp-eyes"><ellipse cx="122" cy="137" rx="5" ry="3" /><ellipse cx="169" cy="137" rx="5" ry="3" /><circle cx="122" cy="137" r="1.3" /><circle cx="169" cy="137" r="1.3" /></g>
        <path className="ccp-nose" d="M144 137v25l-7 5 13 1" />
        <path className="ccp-mouth" d="M125 184c12 7 27 7 39 0" />
        <path className="ccp-cheek" d="M101 157c7 5 13 7 20 7M174 164c7-1 13-3 20-8" />
        {config.glasses ? <g className="ccp-glasses"><rect x="103" y="128" width="35" height="20" rx="4" /><rect x="151" y="128" width="35" height="20" rx="4" /><path d="M138 137h13" /></g> : null}
        {config.beard ? <path className="ccp-beard" fill={config.hair} d="M105 168c8 39 24 57 40 57 18 0 34-19 43-58-13 14-27 20-42 20-15 0-28-6-41-19Z" /> : null}
        {config.cigar ? <g className="ccp-cigar"><path d="M161 185l45 13" /><path d="M204 195l19 6" /><circle cx="224" cy="201" r="3" /><path d="M225 196c12-14-5-18 3-31" /></g> : null}
        <Accessory kind={config.accessory} accent={config.accent} />
      </g>
      <rect className="ccp-grain" x="9" y="8" width="262" height="324" rx="3" filter={`url(#${idPrefix}-grain)`} />
    </svg>
  );
}

function MaxPortrait({ idPrefix }: { idPrefix: string }) {
  return (
    <svg viewBox="0 0 300 340" aria-hidden="true">
      <defs>
        <linearGradient id={`${idPrefix}-max-bg`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#32190b" /><stop offset=".52" stopColor="#0b0704" /><stop offset="1" stopColor="#020202" /></linearGradient>
        <radialGradient id={`${idPrefix}-max-lamp`} cx="45%" cy="0" r="82%"><stop offset="0" stopColor="#dc9138" stopOpacity=".42" /><stop offset=".55" stopColor="#8f4319" stopOpacity=".08" /><stop offset="1" stopColor="#000" stopOpacity="0" /></radialGradient>
        <linearGradient id={`${idPrefix}-max-fur`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#a66d3f" /><stop offset=".55" stopColor="#7d4a2d" /><stop offset="1" stopColor="#3d2518" /></linearGradient>
        <filter id={`${idPrefix}-max-grain`} x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".75" numOctaves="2" seed="11" result="n" /><feColorMatrix in="n" type="saturate" values="0" /><feComponentTransfer><feFuncA type="table" tableValues="0 .12" /></feComponentTransfer><feBlend in="SourceGraphic" mode="soft-light" /></filter>
        <filter id={`${idPrefix}-max-shadow`} x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="12" stdDeviation="10" floodColor="#000" floodOpacity=".78" /></filter>
      </defs>
      <rect x="9" y="8" width="282" height="324" rx="3" fill={`url(#${idPrefix}-max-bg)`} />
      <rect x="9" y="8" width="282" height="324" rx="3" fill={`url(#${idPrefix}-max-lamp)`} />
      <g className="ccp-wood" opacity=".28"><path d="M36 8v324M92 8v324M148 8v324M204 8v324M260 8v324" /><path d="M9 289h282" /></g>
      <g className="ccp-smoke" opacity=".33"><path d="M245 94c-22-16-4-32 1-47" /><path d="M257 119c-25-17-7-33-1-49" /></g>
      <g filter={`url(#${idPrefix}-max-shadow)`}>
        <path className="ccp-max-suit" d="M43 332c3-75 43-118 107-118 65 0 104 43 108 118H43Z" />
        <path className="ccp-max-shirt" d="M116 225l34 33 34-33 21 107H95l21-107Z" />
        <path className="ccp-max-lapel" d="M83 234l67 63 67-63M150 297v35" />
        <path className="ccp-max-tie" d="M140 259h20l10 23-20 43-20-43 10-23Z" />
        <path className="ccp-max-ear" fill={`url(#${idPrefix}-max-fur)`} d="M76 91C40 69 43 31 80 42l34 37Z" />
        <path className="ccp-max-ear" fill={`url(#${idPrefix}-max-fur)`} d="M224 91c36-22 33-60-4-49l-34 37Z" />
        <path className="ccp-max-head" fill={`url(#${idPrefix}-max-fur)`} d="M72 105c0-50 32-78 78-78s78 28 78 78v54c0 49-34 78-78 78s-78-29-78-78v-54Z" />
        <path className="ccp-max-shadow" d="M154 31c46 8 70 38 68 87l-5 54c-14 31-35 50-65 61 18-38 23-74 15-109-8-37-11-68-13-93Z" />
        <path className="ccp-max-wrinkle" d="M92 88c18-15 36-17 55-6M154 82c20-11 39-8 55 7M112 103c-9 15-10 27-4 39M191 103c8 16 9 28 3 39" />
        <path className="ccp-max-brow" d="M99 116l34 8M201 116l-34 8" />
        <g className="ccp-max-eyes"><ellipse cx="119" cy="133" rx="7" ry="5" /><ellipse cx="181" cy="133" rx="7" ry="5" /><circle cx="119" cy="133" r="2" /><circle cx="181" cy="133" r="2" /></g>
        <ellipse className="ccp-max-muzzle" cx="150" cy="174" rx="48" ry="34" />
        <path className="ccp-max-nose" d="M132 157c12-10 24-10 36 0-3 17-33 17-36 0Z" />
        <path className="ccp-max-mouth" d="M150 170v21M150 191c-13 9-27 7-36-3M150 191c13 9 27 7 36-3" />
        <path className="ccp-max-cigar" d="M188 185l50 16M236 198l20 6" />
        <circle className="ccp-max-ember" cx="258" cy="205" r="4" />
        <path className="ccp-max-cigar-smoke" d="M258 197c15-16-7-23 5-42 9-14-5-21 4-36" />
        <path className="ccp-max-collar" d="M102 226h96l-12 35h-72l-12-35Z" />
        <circle className="ccp-max-tag" cx="150" cy="253" r="14" />
        <text className="ccp-max-tag-text" x="150" y="258" textAnchor="middle">M</text>
      </g>
      <rect className="ccp-grain" x="9" y="8" width="282" height="324" rx="3" filter={`url(#${idPrefix}-max-grain)`} />
    </svg>
  );
}

export default function CinematicCharacterPortrait({
  characterKey,
  active = false,
  reacting = false,
  variant = "card",
  showLabel = false,
}: Props) {
  const reactId = useId().replaceAll(":", "");
  const member = LIVING_CAST[characterKey];
  let portrait: ReactNode;
  if (characterKey === "max") {
    portrait = <MaxPortrait idPrefix={`ccp-${reactId}`} />;
  } else {
    portrait = <HumanPortrait characterKey={characterKey} idPrefix={`ccp-${reactId}`} />;
  }

  return (
    <figure
      className={`ccp-portrait ccp-portrait--${characterKey} ccp-portrait--${variant} ${active ? "is-active" : ""} ${reacting ? "is-reacting" : ""}`}
      role="img"
      aria-label={`${member.displayName}, ${member.governedRole}`}
    >
      <div className="ccp-portrait__art">{portrait}</div>
      {showLabel ? (
        <figcaption>
          <span>{member.title}</span>
          <strong>{member.displayName}</strong>
          <em>{member.governedRole}</em>
        </figcaption>
      ) : null}
    </figure>
  );
}
