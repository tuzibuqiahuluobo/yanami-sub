"""Run the pinned task-control CLI from any Agent shell or working directory."""
from pathlib import Path
import sys

app = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(app), str(app / "src")]

from finesub.llm.agent.agent_task_control import main

if __name__ == "__main__":
    raise SystemExit(main())
