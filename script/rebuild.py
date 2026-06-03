from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from Basement.runner import build_parser, run

if __name__ == '__main__':
    results = run(build_parser('rebuild').parse_args())
    for r in results: print(r)
