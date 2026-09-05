import { FactoryShell } from "./ExpansionWingFactory";
import { useExpansionWingSnapshot } from "./ExpansionWingSnapshotContext";

export default function ExpansionWing(){
  const {snapshot,connection,fixtureMode,snapshotAgeSeconds}=useExpansionWingSnapshot();
  return <FactoryShell snapshot={snapshot} connection={connection} fixtureMode={fixtureMode} snapshotAge={snapshotAgeSeconds}/>;
}
