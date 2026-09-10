import { NorthstarGroup, NorthstarDayTrading, NorthstarHistory } from './NorthstarPanels';

export function NorthstarCommand() {
  return <main className="museum-control-room"><NorthstarGroup group="agents"/><NorthstarGroup group="governance"/>
    <NorthstarGroup group="subsystems"/><NorthstarDayTrading/></main>;
}
export function NorthstarCases() {
  return <main className="museum-case-library"><header><h1>Case Library · Retained Evidence</h1>
    <p>CASE DOSSIERS UNAVAILABLE — the governed full-session projection provides retained evidence bindings, not complete case dossiers. Aggregate counts cannot create a case or a MU thesis.</p></header><NorthstarHistory/></main>;
}
export function NorthstarProducts() {
  return <main className="mew-shell"><header className="mew-masthead"><h1>THE EXPANSION WING</h1><p>Twenty-four governed product rooms · observation only · no synthetic activity invented.</p></header>
    <NorthstarGroup group="rooms"/><NorthstarDayTrading/></main>;
}
