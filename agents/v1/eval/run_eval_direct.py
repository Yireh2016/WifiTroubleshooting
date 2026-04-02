#!/usr/bin/env python3
"""
Direct runner for LangSmith evaluations.
This ensures .env is loaded before any imports.

Usage:
    python3 agents/v1/eval/run_eval_direct.py
"""

import sys
import os
from pathlib import Path

# Get project root (file is at agents/v1/eval/run_eval_direct.py, go up 3 levels)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load .env FIRST, before any other imports
from dotenv import load_dotenv
env_file = PROJECT_ROOT / ".env"
load_dotenv(env_file)

print(f"📁 Project root: {PROJECT_ROOT}")
print(f"📄 Loaded .env from: {env_file}")
project_name = os.getenv('LANGSMITH_PROJECT')
print(f"✓ LANGSMITH_PROJECT={project_name}")
print(f"✓ Experiments will be created in: {project_name} project")
print()

# NOW setup path and import
sys.path.insert(0, str(PROJECT_ROOT))

from agents.v1.eval.run_experiments import run_evaluation

if __name__ == "__main__":
    result = run_evaluation()
    sys.exit(0 if result else 1)
