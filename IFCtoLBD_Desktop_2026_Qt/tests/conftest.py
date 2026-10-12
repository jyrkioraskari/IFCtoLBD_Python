import sys
from pathlib import Path

SUBFOLDER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SUBFOLDER_ROOT.parent

for path in (REPO_ROOT, SUBFOLDER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
