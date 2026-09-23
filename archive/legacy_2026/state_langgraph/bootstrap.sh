#!/bin/bash
# PDFtoBPMN v2.1 — Bootstrap script
# Запуск: bash bootstrap.sh
set -e

echo "=== PDFtoBPMN v2.1 Bootstrap ==="
echo ""

# 1. Git branch
BRANCH="v2-graphrag"
CURRENT=$(git branch --show-current 2>/dev/null || echo "no-git")

if [ "$CURRENT" = "$BRANCH" ]; then
    echo "[OK] Already on branch $BRANCH"
elif [ "$CURRENT" = "no-git" ]; then
    echo "[WARN] Not a git repo. Init first: git init && git add -A && git commit -m 'init'"
    exit 1
else
    echo "[GIT] Creating branch $BRANCH from $CURRENT..."
    git checkout -b "$BRANCH"
    echo "[OK] On branch $BRANCH"
fi

echo ""

# 2. Python deps
echo "[PIP] Installing core dependencies..."
pip install langgraph langchain-core pydantic pyyaml python-dotenv --quiet
echo "[OK] Core deps installed"

echo ""

# 3. Make hooks executable
echo "[HOOKS] Setting permissions..."
chmod +x .cursor/hooks/*.py
echo "[OK] Hooks executable"

echo ""

# 4. Init LangGraph state
echo "[STATE] Initializing dev_state.sqlite..."
python3 -c "
import sys
sys.path.insert(0, '.cursor')
from state.dev_graph import DevGraph
g = DevGraph()
g.update_phase('0_setup', task='TASK-001: validate deployment', status='planned')
g.log_decision(
    title='Bootstrap complete',
    decision='Multi-agent environment deployed, ready for TASK-001',
    context='bootstrap.sh ran successfully'
)
print('[OK] dev_state.sqlite created with initial state')
print(f'     Decisions: {len(g.get_decisions())}')
print(f'     Phase: {g.get_state()[\"phase\"]}')
"

echo ""

# 5. Run smoke test
echo "[TEST] Running LangGraph smoke test..."
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PYTHONPATH=".cursor:." python3 -m pytest tests/test_dev_graph.py -v --tb=short 2>&1 | tail -20

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Open project in Cursor AI"
echo "  2. Type /start in chat (Plan Mode, Opus 4.6)"
echo "  3. Orchestrator will read state and create TASK-001"
echo ""
