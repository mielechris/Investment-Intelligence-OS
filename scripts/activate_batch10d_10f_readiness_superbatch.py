#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import sys
import time
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH="feature/batch10d-10f-readiness-superbatch-v2"
LIVE=Path(os.getenv("IIOS_LIVE_CHECKOUT","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE=Path(os.getenv("IIOS_10D_10F_WORKTREE","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10d-10f-readiness")).expanduser()
FRONTEND=WORKTREE/"FRONT END";DIST=FRONTEND/"dist";PREVIEW_HOST="127.0.0.1";PREVIEW_PORT=5176
STATE_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"market-validation";TELEMETRY_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"telemetry"
LAUNCH_DIR=Path.home()/"Library"/"LaunchAgents";LOG_DIR=Path.home()/"Library"/"Logs"/"IIOS"
FINAL_LABEL="com.iios.institutional-browser-artifacts";FINAL_INTERVAL_SECONDS=1800;FINAL_PLIST=LAUNCH_DIR/f"{FINAL_LABEL}.plist"
PRESERVED_PLISTS={"9O":LAUNCH_DIR/"com.iios.daily-factory-episode.plist","9P":LAUNCH_DIR/"com.iios.chief-intelligence-office.plist","9Q":LAUNCH_DIR/"com.iios.experiment-ab-laboratory.plist","9R":LAUNCH_DIR/"com.iios.data-expansion-factory.plist","9S":LAUNCH_DIR/"com.iios.agent-performance-league.plist"}


def _configure():base.BRANCH=BRANCH;base.LIVE=LIVE;base.WORKTREE=WORKTREE;base.FRONTEND=FRONTEND;base.DIST=DIST;base.PREVIEW_HOST=PREVIEW_HOST;base.PREVIEW_PORT=PREVIEW_PORT
def _hash(p:Path):return base._hash(p)
def _cleanup():
    c=WORKTREE/"scripts"/"__pycache__"
    if c.exists():shutil.rmtree(c)
def _build(npm:str):
    base._run([npm,"ci"],cwd=FRONTEND)
    base._run([npm,"exec","eslint","--","src/LiveFactoryBrowser.tsx","src/LivingFactoryExperience.tsx","src/CharacterStoryEngine.tsx","src/InteractiveCaseTheater.tsx","src/DailyFactoryEpisode.tsx","src/ChiefIntelligenceOffice.tsx","src/ExperimentABLaboratory.tsx","src/DataExpansionFactory.tsx","src/AgentPerformanceLeague.tsx","src/MarketRegimeIntelligence.tsx","src/OperatingSuperbatch.tsx","src/ReadinessSuperbatch.tsx","src/MarketValidationStackPanel.tsx"],cwd=FRONTEND);base._run([npm,"run","build"],cwd=FRONTEND)
def _publish(python:Path)->dict:
    base._run([str(python),str(WORKTREE/"scripts"/"iios_final_institutional_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--browser-dir",str(DIST)],cwd=WORKTREE)
    return json.loads((DIST/"governed_capital_readiness.json").read_text())
def _install(python:Path):
    LAUNCH_DIR.mkdir(parents=True,exist_ok=True);LOG_DIR.mkdir(parents=True,exist_ok=True)
    payload={"Label":FINAL_LABEL,"ProgramArguments":[str(python),str(WORKTREE/"scripts"/"iios_final_institutional_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--browser-dir",str(DIST)],"WorkingDirectory":str(WORKTREE),"RunAtLoad":True,"StartInterval":FINAL_INTERVAL_SECONDS,"ProcessType":"Background","EnvironmentVariables":{"PYTHONUNBUFFERED":"1"},"StandardOutPath":str(LOG_DIR/"institutional-browser-artifacts.out.log"),"StandardErrorPath":str(LOG_DIR/"institutional-browser-artifacts.err.log")}
    tmp=FINAL_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as h:plistlib.dump(payload,h,sort_keys=True)
    tmp.replace(FINAL_PLIST);domain=f"gui/{os.getuid()}";base._run(["launchctl","bootout",domain,str(FINAL_PLIST)],check=False,capture=True);base._run(["launchctl","bootstrap",domain,str(FINAL_PLIST)]);base._run(["launchctl","kickstart","-k",f"{domain}/{FINAL_LABEL}"])
def _health():
    time.sleep(2)
    try:return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)
    except RuntimeError:
        domain=f"gui/{os.getuid()}";base._run(["launchctl","kickstart","-k",f"{domain}/{base.LABEL}"],check=False,capture=True);time.sleep(2);return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)

def main()->int:
    if sys.platform!="darwin":raise SystemExit("Final readiness activation is macOS-only for this IIOS runtime")
    _configure();_cleanup();git=base._require_command("git");npm=base._require_command("npm");base._require_command("launchctl")
    print("IIOS FINAL ROADMAP SUPERBATCH — 9T THROUGH 10F ACTIVATION");print("Existing 9O–9S workers: PRESERVED");print("Existing Backend 8002: UNCHANGED");print("Final browser artifact worker: READ-ONLY LOCAL STATE");print("Live capital authorized: FALSE");print("Trade execution permission: FALSE");print("Live execution: FALSE")
    protected=base._protected_hashes();preserved={k:_hash(v) for k,v in PRESERVED_PLISTS.items()};branch_before,status_before=base._prepare_worktree(git);python=base._resolve_python();_build(npm)
    backend=base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status",attempts=4)
    if backend.get("read_only_aggregation") is not True:raise SystemExit("Backend 8002 is not read-only")
    readiness=_publish(python);s=readiness.get("safety") or {}
    for key in ("auto_enable_live","auto_connect_broker","auto_fund_account","legal_acceptance_authority","capital_authority","trade_execution_permission","live_execution"):
        if s.get(key) is not False:raise SystemExit(f"10E safety contract violated: {key}")
    _install(python);base._install_preview_agent(python);health=_health()
    if health.get("backend_access")!="READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:raise SystemExit("Final preview safety boundary failed")
    if base._protected_hashes()!=protected:raise SystemExit("Protected 9G–9J worker changed")
    if {k:_hash(v) for k,v in PRESERVED_PLISTS.items()}!=preserved:raise SystemExit("One or more existing 9O–9S workers changed")
    if base._capture([git,"branch","--show-current"],cwd=LIVE)!=branch_before or base._capture([git,"status","--porcelain"],cwd=LIVE)!=status_before:raise SystemExit("Live checkout changed during final activation")
    opener=shutil.which("open")
    if opener:base._run([opener,f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"],check=False)
    firm=json.loads((DIST/"institutional_investment_firm_os.json").read_text());qual=json.loads((DIST/"paper_performance_qualification.json").read_text())
    print(json.dumps({"status":"IIOS_9T_THROUGH_10F_FINAL_BROWSER_PREVIEW","preview_url":f"http://{PREVIEW_HOST}:{PREVIEW_PORT}","existing_9o_9s_workers_preserved":True,"backend_8002_unchanged":True,"protected_9g_9j_workers_unchanged":True,"final_artifact_launch_agent":FINAL_LABEL,"artifact_refresh_interval_seconds":FINAL_INTERVAL_SECONDS,"paper_qualification_status":qual.get("status"),"capital_readiness_status":readiness.get("status"),"institutional_os_status":firm.get("status"),"live_capital_authorized":False,"capital_authority":False,"trade_execution_permission":False,"broker_connected":False,"live_execution":False,"worktree":str(WORKTREE)},indent=2,sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
