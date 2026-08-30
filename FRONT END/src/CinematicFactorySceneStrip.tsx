import LivingCharacterAvatar from "./LivingCharacterAvatar";
import "./CinematicFactorySceneStrip.css";

type Props = {
  view: "floor" | "control";
};

export default function CinematicFactorySceneStrip({ view }: Props) {
  return (
    <section className="cfs-strip" aria-label="IIOS cinematic headquarters presentation layer">
      <header className="cfs-strip__truth">
        <span>HEADQUARTERS ATMOSPHERE · PRESENTATION LAYER</span>
        <strong>CHARACTER SCENES ≠ PERSISTED AGENT ACTIVITY</strong>
      </header>

      <div className="cfs-strip__rooms">
        <article className="cfs-scene cfs-scene--pit">
          <div className="cfs-scene__lamp" aria-hidden="true" />
          <header><span>THE INTELLIGENCE PIT</span><em>{view === "floor" ? "OPERATIONS VIEW" : "OBSERVATION VIEW"}</em></header>
          <div className="cfs-pit-cast">
            <div><LivingCharacterAvatar characterKey="policy" /><span>FRANKIE</span></div>
            <div><LivingCharacterAvatar characterKey="market_structure" /><span>MIKEY</span></div>
            <div><LivingCharacterAvatar characterKey="commodities" /><span>TONY</span></div>
          </div>
          <div className="cfs-console" aria-hidden="true"><i /><i /><i /><i /><i /></div>
          <blockquote>NARRATIVE · “HEY, I’M WORKIN’ HERE. READ THE DAMN EVIDENCE.”</blockquote>
        </article>

        <article className="cfs-scene cfs-scene--commission">
          <div className="cfs-scene__lamp" aria-hidden="true" />
          <header><span>THE COMMISSION</span><em>GOVERNED SYNTHESIS</em></header>
          <div className="cfs-commission-table" aria-hidden="true"><i /><i /><i /></div>
          <div className="cfs-commission-cast">
            <LivingCharacterAvatar characterKey="fundamentals" />
            <LivingCharacterAvatar characterKey="skeptic" />
            <LivingCharacterAvatar characterKey="portfolio" />
          </div>
          <blockquote>NARRATIVE · “GOOD STORY. NOW SHOW US THE PART THAT SURVIVES JOHNNY.”</blockquote>
        </article>

        <article className="cfs-scene cfs-scene--max">
          <header><span>MAX’S OFFICE</span><em>COMMAND OVERLOOK</em></header>
          <div className="cfs-max-desk">
            <LivingCharacterAvatar characterKey="max" />
            <div className="cfs-max-props" aria-hidden="true"><i /><i /><i /></div>
          </div>
          <blockquote>NARRATIVE · “I’M JUST HERE FOR THE SNACKS. YOU PEOPLE HANDLE THE DOWNSIDE.”</blockquote>
          <footer>MAX IS NOT A FIDUCIARY.</footer>
        </article>
      </div>
    </section>
  );
}
