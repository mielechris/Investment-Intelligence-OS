#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import socket
import sys
import time
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH="feature/batch10h-historical-market-intelligence"
LIVE=Path(os.getenv("IIOS_LIVE_CHECKOUT","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE=Path(os.getenv("IIOS_10H_WORKTREE","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10h-historical-market-intelligence")).expanduser()
FRONTEND=WORKTREE/"FRONT END";DIST=FRONTEND/"dist";PREVIEW_HOST="127.0.0.1";PREVIEW_PORT=5176
STATE_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"market-validation";TELEMETRY_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"telemetry";HISTORICAL_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"historical-research"
LAUNCH_DIR=Path.home()/"Library"/"LaunchAgents";LOG_DIR=Path.home()/"Library"/"Logs"/"IIOS"
FINAL_LABEL="com.iios.institutional-browser-artifacts";FINAL_INTERVAL_SECONDS=300;FINAL_PLIST=LAUNCH_DIR/f"{FINAL_LABEL}.plist"
HISTORICAL_LABEL="com.iios.historical-market-intelligence";HISTORICAL_INTERVAL_SECONDS=900;HISTORICAL_PLIST=LAUNCH_DIR/f"{HISTORICAL_LABEL}.plist"
PRESERVED_PLISTS={"9O":LAUNCH_DIR/"com.iios.daily-factory-episode.plist","9P":LAUNCH_DIR/"com.iios.chief-intelligence-office.plist","9Q":LAUNCH_DIR/"com.iios.experiment-ab-laboratory.plist","9R":LAUNCH_DIR/"com.iios.data-expansion-factory.plist","9S":LAUNCH_DIR/"com.iios.agent-performance-league.plist"}


def _configure():base.BRANCH=BRANCH;base.LIVE=LIVE;base.WORKTREE=WORKTREE;base.FRONTEND=FRONTEND;base.DIST=DIST;base.PREVIEW_HOST=PREVIEW_HOST;base.PREVIEW_PORT=PREVIEW_PORT
def _hash(p:Path):return base._hash(p)
def _cleanup():
    c=WORKTREE/"scripts"/"__pycache__"
    if c.exists():shutil.rmtree(c)
def _build(npm:str):
    base._run([npm,"ci"],cwd=FRONTEND)
    base._run([npm,"exec","eslint","--","src/LiveFactoryBrowser.tsx","src/LivingFactoryExperience.tsx","src/CharacterStoryEngine.tsx","src/InteractiveCaseTheater.tsx","src/DailyFactoryEpisode.tsx","src/ChiefIntelligenceOffice.tsx","src/ExperimentABLaboratory.tsx","src/DataExpansionFactory.tsx","src/AgentPerformanceLeague.tsx","src/MarketRegimeIntelligence.tsx","src/OperatingSuperbatch.tsx","src/ReadinessSuperbatch.tsx","src/QualificationWatch.tsx","src/HistoricalMarketIntelligence.tsx","src/MarketValidationStackPanel.tsx"],cwd=FRONTEND)
    base._run([npm,"run","build"],cwd=FRONTEND)
def _plist(label:str,program:list[str],cwd:Path,interval:int,out_name:str)->Path:
    LAUNCH_DIR.mkdir(parents=True,exist_ok=True);LOG_DIR.mkdir(parents=True,exist_ok=True)
    path=LAUNCH_DIR/f"{label}.plist";payload={"Label":label,"ProgramArguments":program,"WorkingDirectory":str(cwd),"RunAtLoad":True,"StartInterval":interval,"ProcessType":"Background","EnvironmentVariables":{"PYTHONUNBUFFERED":"1"},"StandardOutPath":str(LOG_DIR/f"{out_name}.out.log"),"StandardErrorPath":str(LOG_DIR/f"{out_name}.err.log")}
    tmp=path.with_suffix(".tmp.plist")
    with tmp.open("wb") as h:plistlib.dump(payload,h,sort_keys=True)
    tmp.replace(path);domain=f"gui/{os.getuid()}";base._run(["launchctl","bootout",domain,str(path)],check=False,capture=True);base._run(["launchctl","bootstrap",domain,str(path)]);base._run(["launchctl","kickstart","-k",f"{domain}/{label}"]);return path
def _historical_runtime()->Path:
    return WORKTREE/"scripts"/"iios_historical_market_intelligence_runtime.py"
def _run_history(python:Path)->dict:
    base._run([str(python),str(_historical_runtime()),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--research-dir",str(HISTORICAL_DIR),"--targets-per-cycle","3"],cwd=WORKTREE)
    return json.loads((HISTORICAL_DIR/"latest_historical_market_intelligence.json").read_text())
def _publish(python:Path)->dict:
    base._run([str(python),str(WORKTREE/"scripts"/"iios_final_institutional_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--historical-dir",str(HISTORICAL_DIR),"--browser-dir",str(DIST)],cwd=WORKTREE)
    return json.loads((DIST/"historical_market_intelligence.json").read_text())
def _preview_port_open()->bool:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((PREVIEW_HOST,PREVIEW_PORT))==0
def _wait_preview_port_free(timeout_seconds:float=20.0)->None:
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if not _preview_port_open():return
        time.sleep(0.25)
    raise RuntimeError(f"Preview port {PREVIEW_PORT} did not release after bootout")
def _install_preview_agent(python:Path)->None:
    # A prior preview worker can briefly retain 5176 after launchctl bootout.
    # Waiting for the port to actually close prevents the replacement process
    # from crashing with EADDRINUSE and leaving the browser connection refused.
    domain=f"gui/{os.getuid()}"
    base._run(["launchctl","bootout",domain,str(base.PLIST)],check=False,capture=True)
    _wait_preview_port_free()
    base._install_preview_agent(python)
def _health(python:Path):
    time.sleep(2)
    try:return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)
    except RuntimeError:
        # One controlled reinstall is allowed; never loop indefinitely or mask
        # a persistent launchd failure.
        domain=f"gui/{os.getuid()}"
        base._run(["launchctl","bootout",domain,str(base.PLIST)],check=False,capture=True)
        _wait_preview_port_free()
        base._install_preview_agent(python)
        time.sleep(2)
        return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)


def main()->int:
    if sys.platform!="darwin":raise SystemExit("10H activation is macOS-only for this IIOS runtime")
    _configure();_cleanup();git=base._require_command("git");npm=base._require_command("npm");base._require_command("launchctl")
    print("IIOS BATCH 10H — HISTORICAL MARKET INTELLIGENCE ACTIVATION");print("24/7 historical archive research: ENABLED");print("10G qualification + 9T–10F stack: PRESERVED");print("Existing Backend 8002: UNCHANGED");print("Historical research authority: READ ONLY / ADVISORY");print("Capital authority: FALSE");print("Trade execution permission: FALSE");print("Live execution: FALSE")
    protected=base._protected_hashes();preserved={k:_hash(v) for k,v in PRESERVED_PLISTS.items()};branch_before,status_before=base._prepare_worktree(git);python=base._resolve_python();_build(npm)
    backend=base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status",attempts=4)
    if backend.get("read_only_aggregation") is not True:raise SystemExit("Backend 8002 is not read-only")
    research=_run_history(python);s=research.get("safety") or {}
    for key in ("auto_generate_trades","auto_change_thresholds","auto_change_agent_weights","auto_change_model_routing","auto_change_portfolio_exposure","broker_connection_authority","capital_authority","trade_execution_permission","live_execution"):
        if s.get(key) is not False:raise SystemExit(f"10H safety contract violated: {key}")
    if s.get("read_only_research") is not True or s.get("twenty_four_seven_worker") is not True or s.get("human_approval_required") is not True:raise SystemExit("10H read-only/24x7/human approval contract missing")
    historical_program=[str(python),str(_historical_runtime()),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--research-dir",str(HISTORICAL_DIR),"--targets-per-cycle","3"]
    _plist(HISTORICAL_LABEL,historical_program,WORKTREE,HISTORICAL_INTERVAL_SECONDS,"historical-market-intelligence")
    final_program=[str(python),str(WORKTREE/"scripts"/"iios_final_institutional_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--historical-dir",str(HISTORICAL_DIR),"--browser-dir",str(DIST)]
    _plist(FINAL_LABEL,final_program,WORKTREE,FINAL_INTERVAL_SECONDS,"institutional-browser-artifacts")
    browser_research=_publish(python);_install_preview_agent(python);health=_health(python)
    if health.get("backend_access")!="READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:raise SystemExit("10H preview safety boundary failed")
    if base._protected_hashes()!=protected:raise SystemExit("Protected 9G–9J worker changed")
    if {k:_hash(v) for k,v in PRESERVED_PLISTS.items()}!=preserved:raise SystemExit("One or more existing 9O–9S workers changed")
    if base._capture([git,"branch","--show-current"],cwd=LIVE)!=branch_before or base._capture([git,"status","--porcelain"],cwd=LIVE)!=status_before:raise SystemExit("Live checkout changed during 10H activation")
    opener=shutil.which("open")
    if opener:base._run([opener,f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"],check=False)
    cycle=research.get("cycle") if isinstance(research.get("cycle"),dict) else {};summary=research.get("research_summary") if isinstance(research.get("research_summary"),dict) else {}
    print(json.dumps({"status":"BATCH10H_HISTORICAL_MARKET_INTELLIGENCE_PREVIEW","preview_url":f"http://{PREVIEW_HOST}:{PREVIEW_PORT}","historical_research_status":browser_research.get("status"),"historical_worker":HISTORICAL_LABEL,"historical_cycle_interval_seconds":HISTORICAL_INTERVAL_SECONDS,"browser_artifact_refresh_seconds":FINAL_INTERVAL_SECONDS,"last_processed_symbols":cycle.get("processed_symbols"),"studies_ready":summary.get("studies_ready"),"coverage_records":summary.get("coverage_records"),"10g_and_prior_stack_preserved":True,"backend_8002_unchanged":True,"protected_9g_9j_workers_unchanged":True,"capital_authority":False,"trade_execution_permission":False,"broker_connected":False,"live_execution":False,"worktree":str(WORKTREE)},indent=2,sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
