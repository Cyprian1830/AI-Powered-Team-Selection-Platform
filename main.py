"""Single entry point for the Team Selection prototype.

    python main.py            # = serve: prepares data if needed, starts API at http://localhost:8000/docs
    python main.py demo       # prints a sample recommendation in the console (no server needed)
    python main.py setup      # (re)generate synthetic data + run ETL
    python main.py test       # run the test suite
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):          # Polish characters on Windows consoles
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from teamselect import config, etl  # noqa: E402


def setup(force: bool = False) -> None:
    if force or not (config.RAW_DIR / "employees.csv").exists():
        print("[setup] generating synthetic data...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_synthetic_data.py"), str(config.RAW_DIR)], check=True)
    if force or not config.DB_PATH.exists():
        print("[setup] running ETL...")
        print(json.dumps(etl.run_all(), indent=2))
    else:
        print(f"[setup] database already exists: {config.DB_PATH}  (use `python main.py setup` to rebuild)")


def demo() -> None:
    from teamselect.explain import explain
    from teamselect.models import ProjectRequest
    from teamselect.repository import EmployeeRepository
    from teamselect.service import recommend

    req = ProjectRequest(**json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8")))
    res = recommend(req, EmployeeRepository())
    print(f"\nEligible: {res.eligible_count}, rejected by hard constraints: {res.rejected_count} {res.rejection_summary}")
    print(f"\n{'Slot':<20}{'ID':<8}{'Role':<20}{'Seniority':<10}{'Score':>6}")
    for m in res.team.members:
        c = m.candidate
        print(f"{m.slot:<20}{c.employee_id:<8}{c.role:<20}{c.seniority:<10}{c.score:>6}")
    print(f"\nTeam score: {res.team.team_score}/100 | uncovered: {res.team.uncovered_technologies or 'none'}")
    print("\n--- Explanation ---")
    print(explain(res)["text"])


def serve(host: str, port: int, reload: bool) -> None:
    setup()
    import uvicorn
    print(f"\n[serve] Open the app: http://localhost:{port}   (API docs: /docs)\n")
    uvicorn.run("teamselect.api:app", host=host, port=port, reload=reload)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", default="serve", choices=["serve", "demo", "setup", "test"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="auto-reload on code changes (serve only)")
    a = p.parse_args()
    if a.command == "setup":
        setup(force=True)
    elif a.command == "demo":
        setup(); demo()
    elif a.command == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))
    else:
        serve(a.host, a.port, a.reload)


if __name__ == "__main__":
    main()
