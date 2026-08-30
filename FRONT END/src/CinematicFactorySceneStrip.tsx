import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import CinematicRoomScene from "./CinematicRoomScene";
import LiveFactoryEpisodeV74 from "./LiveFactoryEpisodeV74";
import LivingCharacterBehaviorV7 from "./LivingCharacterBehaviorV7";
import PersistedStateReconstructionV732 from "./PersistedStateReconstructionV732";
import SceneDirectionV73 from "./SceneDirectionV73";
import "./CinematicFactorySceneStrip.css";

type Props = {
  view: "floor" | "control";
};

export default function CinematicFactorySceneStrip({ view }: Props) {
  return (
    <>
      <section className="cfs-strip cfs-strip--illustrated" aria-label="IIOS cinematic headquarters presentation layer">
        <header className="cfs-strip__truth">
          <span>HEADQUARTERS ATMOSPHERE · ILLUSTRATED PRESENTATION LAYER</span>
          <strong>CHARACTER SCENES ≠ PERSISTED AGENT ACTIVITY</strong>
        </header>

        <div className="cfs-strip__rooms cfs-strip__rooms--four">
          <article className="cfs-scene cfs-scene--pit cfs-scene--painted">
            <CinematicRoomScene station="radar" />
            <header><span>THE INTELLIGENCE PIT</span><em>{view === "floor" ? "OPERATIONS VIEW" : "OBSERVATION VIEW"}</em></header>
            <div className="cfs-painted-cast cfs-painted-cast--pit">
              <CinematicCharacterPortrait characterKey="policy" variant="scene" />
              <CinematicCharacterPortrait characterKey="market_structure" variant="scene" />
              <CinematicCharacterPortrait characterKey="commodities" variant="scene" />
            </div>
            <div className="cfs-console" aria-hidden="true"><i /><i /><i /><i /><i /></div>
            <blockquote>NARRATIVE · “AY, I’M WALKIN’ HERE. READ THE FUCKIN’ RECEIPTS BEFORE YOU FALL IN LOVE.”</blockquote>
            <footer>FRANKIE · MIKEY · TONY</footer>
          </article>

          <article className="cfs-scene cfs-scene--war-room cfs-scene--painted">
            <CinematicRoomScene station="research" />
            <header><span>THE MACRO WAR ROOM</span><em>RATES · WEATHER · GEOPOLITICS</em></header>
            <div className="cfs-painted-cast cfs-painted-cast--war">
              <CinematicCharacterPortrait characterKey="macro" variant="scene" />
              <CinematicCharacterPortrait characterKey="geo_weather" variant="scene" />
            </div>
            <div className="cfs-war-map" aria-hidden="true"><i /><i /><i /><i /></div>
            <blockquote>NARRATIVE · “EVERYBODY’S A FUCKIN’ GENIUS UNTIL RATES, WEATHER, OR SOME ASSHOLE WITH A MISSILE CHANGES THE RULES.”</blockquote>
            <footer>BENNY · STORMY SAL</footer>
          </article>

          <article className="cfs-scene cfs-scene--commission cfs-scene--painted">
            <CinematicRoomScene station="committee" />
            <header><span>THE COMMISSION</span><em>GOVERNED SYNTHESIS</em></header>
            <div className="cfs-painted-cast cfs-painted-cast--commission">
              <CinematicCharacterPortrait characterKey="fundamentals" variant="scene" />
              <CinematicCharacterPortrait characterKey="skeptic" variant="scene" />
              <CinematicCharacterPortrait characterKey="portfolio" variant="scene" />
            </div>
            <div className="cfs-commission-table" aria-hidden="true"><i /><i /><i /></div>
            <blockquote>NARRATIVE · “GOOD STORY, PAISAN. NOW SHOW US THE PART THAT SURVIVES JOHNNY WITHOUT SHITTIN’ THE BED.”</blockquote>
            <footer>VINNY · JOHNNY · PAULIE</footer>
          </article>

          <article className="cfs-scene cfs-scene--max cfs-scene--painted">
            <header><span>MAX’S OFFICE</span><em>COMMAND OVERLOOK</em></header>
            <div className="cfs-max-office-set" aria-hidden="true"><i /><i /><i /><i /></div>
            <div className="cfs-painted-max">
              <CinematicCharacterPortrait characterKey="max" variant="boss" />
            </div>
            <div className="cfs-max-desk-v2" aria-hidden="true"><i /><i /><i /></div>
            <blockquote>NARRATIVE · “I’M HERE FOR THE SNACKS AND THE DOWNSIDE. YOU GOT NO RECEIPTS? FUCK OUTTA MY OFFICE.”</blockquote>
            <footer>MAX IS NOT A FIDUCIARY. MAX IS ALSO NOT HR.</footer>
          </article>
        </div>
      </section>

      <LivingCharacterBehaviorV7 view={view} />
      <LiveFactoryEpisodeV74 view={view} />
      <SceneDirectionV73 view={view} />
      <PersistedStateReconstructionV732 view={view} />
    </>
  );
}
