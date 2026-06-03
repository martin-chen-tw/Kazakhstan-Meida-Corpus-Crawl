from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from Basement.config import list_newspapers, load_source_configs

if __name__ == '__main__':
    for n in list_newspapers():
        print(n + ': ' + ', '.join(c.lang for c in load_source_configs(n)))
