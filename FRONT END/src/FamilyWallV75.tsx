import familyPortrait from "./assets/v75/iios-family-portrait.webp";
import "./FamilyWallV75.css";

export default function FamilyWallV75() {
  return (
    <section className="v75-family-wall" aria-label="V7.5 approved IIOS family portrait">
      <header className="v75-family-wall__header">
        <div>
          <span>V7.5 · FINAL AVATAR INSTALLATION · APPROVED FAMILY WALL</span>
          <h2>THE FAMILY IS IN THE FUCKIN' BUILDING.</h2>
          <p>
            Approved visual canon for MAX, Frankie Fine Print, Benny Basis Points,
            Vinny EBITDA, Mikey Tape, Tony Tanker, Stormy Sal, Johnny No, and
            Paulie Positions.
          </p>
        </div>
        <div className="v75-family-wall__stamp">
          <strong>APPROVED</strong>
          <span>VISUAL CANON</span>
        </div>
      </header>

      <div className="v75-family-wall__truth">
        <span>PRESENTATION ONLY</span>
        <span>ARTWORK ≠ AGENT ACTIVITY</span>
        <span>LIVE EXECUTION · FALSE</span>
        <span>TRADE AUTHORITY · FALSE</span>
        <span>WRITE AUTHORITY · NONE</span>
      </div>

      <figure className="v75-family-wall__frame">
        <img
          src={familyPortrait}
          alt="Approved IIOS Intelligence Factory family portrait featuring MAX, Frankie Fine Print, Benny Basis Points, Vinny EBITDA, Mikey Tape, Tony Tanker, Stormy Sal, Johnny No, and Paulie Positions"
        />
        <figcaption>
          <strong>IIOS INTELLIGENCE FACTORY · THE FAMILY</strong>
          <span>CANONICAL V7.5 CAST ART · NO GOVERNED STATE IS DERIVED FROM THIS IMAGE</span>
        </figcaption>
      </figure>
    </section>
  );
}
