import type { GalleryTruth } from "./TruthSourceAdapter";

function paperNav(value: number | null): string {
  return value === null
    ? "UNKNOWN"
    : value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

export default function LivingWallGalleryStatus({ activeRoom, truth }: { activeRoom: string; truth: GalleryTruth }) {
  return <section className="wall-executive-rail">
    <div><span>ACTIVE ROOM</span><strong>{activeRoom}</strong></div>
    <div><span>FACTORY CONDITION</span><strong>{truth.condition}</strong></div>
    <div><span>MARKET VALIDATION</span><strong>{truth.marketPhase}</strong></div>
    <div><span>PAPER NAV</span><strong>{paperNav(truth.paperNav)}</strong></div>
    <div><span>LIVE EXECUTION</span><strong>FALSE</strong></div>
  </section>;
}
