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

BRANCH="feature/batch10a-10c-operating-superbatch"
LIVE=Path(os.getenv("IIOS_LIVE_CHECKOUT","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE=Path(os.getenv("IIOS_10A_10C_WORKTREE","/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10a-10c-operating")).expanduser()
FRONTEND=WORKTREE/"FRONT END"; DIST=FRONTEND/"dist"; PREVIEW_HOST="127.0.0.1"; PREVIEW_PORT=5176
STATE_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"market-validation"; TELEMETRY_DIR=Path.home()/"Library"/"Application Support"/"IIOS"/"telemetry"
LAUNCH_DIR=Path.home()/"Library"/"LaunchAgents"; LOG_DIR=Path.home()/"Library"/"Logs"/"IIOS"
OPERATING_LABEL="com.iios.operating-superbatch"; OPERATING_INTERVAL_SECONDS=1800; OPERATING_PLIST=LAUNCH_DIR/f"{OPERATING_LABEL}.plist"
PARENT_PLISTS={
"9O":LAUNCH_DIR/"com.iios.daily-factory-episode.plist","9P":LAUNCH_DIR/"com.iios.chief-intelligence-office.plist","9Q":LAUNCH_DIR/"com.iios.experiment-ab-laboratory.plist","9R":LAUNCH_DIR/"com.iios.data-expansion-factory.plist","9S":LAUNCH_DIR/"com.iios.agent-performance-league.plist","9T":LAUNCH_DIR/"com.iios.market-regime-intelligence.plist"}


def _configure():
    base.BRANCH=BRANCH;base.LIVE=LIVE;base.WORKTREE=WORKTREE;base.FRONTEND=FRONTEND;base.DIST=DIST;base.PREVIEW_HOST=PREVIEW_HOST;base.PREVIEW_PORT=PREVIEW_PORT

def _hash(path:Path): return base._hash(path)
def _cleanup():
    cache=WORKTREE/"scripts"/"__pycache__"
    if cache.exists(): shutil.rmtree(cache)

def _build(npm:str):
    base._run([npm,"ci"],cwd=FRONTEND)
    base._run([npm,"exec","eslint","--","src/LiveFactoryBrowser.tsx","src/LivingFactoryExperience.tsx","src/CharacterStoryEngine.tsx","src/InteractiveCaseTheater.tsx","src/DailyFactoryEpisode.tsx","src/ChiefIntelligenceOffice.tsx","src/ExperimentABLaboratory.tsx","src/DataExpansionFactory.tsx","src/AgentPerformanceLeague.tsx","src/MarketRegimeIntelligence.tsx","src/OperatingSuperbatch.tsx","src/MarketValidationStackPanel.tsx"],cwd=FRONTEND)
    base._run([npm,"run","build"],cwd=FRONTEND)

def _publish_parents(python:Path):
    for script,out in [("iios_chief_intelligence_office.py","chief_intelligence_office.json"),("iios_experiment_ab_laboratory.py","experiment_ab_laboratory.json"),("iios_data_expansion_factory.py","data_expansion_factory.json"),("iios_agent_performance_league.py","agent_performance_league.json")]:
        base._run([str(python),str(WORKTREE/"scripts"/script),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--output",str(DIST/out)],cwd=WORKTREE)
    base._run([str(python),str(WORKTREE/"scripts"/"iios_market_regime_intelligence.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--output",str(DIST/"market_regime_intelligence.json")],cwd=WORKTREE)
    episode=STATE_DIR/"browser"/"daily_factory_episode.json"
    if episode.exists(): shutil.copy2(episode,DIST/"daily_factory_episode.json")

def _publish_once(python:Path):
    base._run([str(python),str(WORKTREE/"scripts"/"iios_operating_superbatch_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--browser-dir",str(DIST)],cwd=WORKTREE)
    return json.loads((DIST/"unified_production_browser.json").read_text())

def _install(python:Path):
    LAUNCH_DIR.mkdir(parents=True,exist_ok=True);LOG_DIR.mkdir(parents=True,exist_ok=True)
    payload={"Label":OPERATING_LABEL,"ProgramArguments":[str(python),str(WORKTREE/"scripts"/"iios_operating_superbatch_publisher.py"),"--state-dir",str(STATE_DIR),"--telemetry-dir",str(TELEMETRY_DIR),"--browser-dir",str(DIST)],"WorkingDirectory":str(WORKTREE),"RunAtLoad":True,"StartInterval":OPERATING_INTERVAL_SECONDS,"ProcessType":"Background","EnvironmentVariables":{"PYTHONUNBUFFERED":"1"},"StandardOutPath":str(LOG_DIR/"operating-superbatch.out.log"),"StandardErrorPath":str(LOG_DIR/"operating-superbatch.err.log")}
    tmp=OPERATING_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as h: plistlib.dump(payload,h,sort_keys=True)
    tmp.replace(OPERATING_PLIST);domain=f"gui/{os.getuid()}";base._run(["launchctl","bootout",domain,str(OPERATING_PLIST)],check=False,capture=True);base._run(["launchctl","bootstrap",domain,str(OPERATING_PLIST)]);base._run(["launchctl","kickstart","-k",f"{domain}/{OPERATING_LABEL}"])

def _health():
    time.sleep(2)
    try:return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)
    except RuntimeError:
        domain=f"gui/{os.getuid()}";base._run(["launchctl","kickstart","-k",f"{domain}/{base.LABEL}"],check=False,capture=True);time.sleep(2);return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health",attempts=80)

def main()->int:
    if sys.platform!="darwin": raise SystemExit("10A-10C activation is macOS-only for this IIOS runtime")
    _configure();_cleanup();git=base._require_command("git");npm=base._require_command("npm");base._require_command("launchctl")
    print("IIOS BATCH 10A–10C — OPERATING SUPERBATCH ACTIVATION");print("Parent Batch 9T: PRESERVED");print("Existing Backend 8002: UNCHANGED");print("Operating mode: GOVERNED PAPER / RESEARCH ONLY");print("Live execution: FALSE")
    protected=base._protected_hashes();parents={k:_hash(v) for k,v in PARENT_PLISTS.items()};branch_before,status_before=base._prepare_worktree(git);python=base._resolve_python();_build(npm)
    backend=base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status",attempts=4)
    if backend.get("read_only_aggregation") is not True: raise SystemExit("Backend 8002 is not read-only")
    _publish_parents(python);u=_publish_once(python);s=u.get("safety") or {}
    for key in ("browser_is_command_surface","backend_write_permission","auto_advance_capital","broker_connection_authority","capital_authority","trade_execution_permission","live_execution"):
        if s.get(key) is not False: raise SystemExit(f"10A safety contract violated: {key}")
    _install(python);base._install_preview_agent(python);health=_health()
    if health.get("backend_access")!="READ_ONLY_GET_ONLY" or health.get("live_execution") is not False: raise SystemExit("10A-10C preview safety failed")
    if base._protected_hashes()!=protected: raise SystemExit("Protected 9G-9J worker changed")
    if {k:_hash(v) for k,v in PARENT_PLISTS.items()}!=parents: raise SystemExit("One or more 9O-9T workers changed")
    if base._capture([git,"branch","--show-current"],cwd=LIVE)!=branch_before or base._capture([git,"status","--porcelain"],cwd=LIVE)!=status_before: raise SystemExit("Live checkout changed")
    opener=shutil.which("open")
    if opener: base._run([opener,f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"],check=False)
    print(json.dumps({"status":"BATCH10A_10C_OPERATING_SUPERBATCH_PREVIEW","preview_url":f"http://{PREVIEW_HOST}:{PREVIEW_PORT}","parent_9t_preserved":True,"backend_8002_unchanged":True,"prior_workers_unchanged":True,"operating_launch_agent":OPERATING_LABEL,"paper_qualification_status":(u.get("paper_qualification") or {}).get("status"),"live_capital_mode":False,"capital_authority":False,"trade_execution_permission":False,"live_execution":False,"worktree":str(WORKTREE)},indent=2,sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
