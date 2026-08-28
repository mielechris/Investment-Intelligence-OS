import Batch10BCommandLayer from "./Batch10BCommandLayer";
import Batch10DOperationsBoard from "./Batch10DOperationsBoard";
import FactoryIntelligenceExperienceShell from "./FactoryIntelligenceExperienceShell";
import PaperFundOperationsDock from "./PaperFundOperationsDock";

export default function PaperFundOperationsShell() {
  return (
    <>
      <Batch10BCommandLayer />
      <Batch10DOperationsBoard />
      <FactoryIntelligenceExperienceShell />
      <PaperFundOperationsDock />
    </>
  );
}
