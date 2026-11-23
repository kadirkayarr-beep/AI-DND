import json,sys,ast
sys.path[:0]=[sys.argv[1]+"/ai-dnd/scripts", sys.argv[1]+"/ai-dnd/scripts/engine_split"]
from inventory import top_level_index
from pathlib import Path
idx=top_level_index(Path(sys.argv[1])/"ai-dnd/game.py")
names=set()
import glob
for f in glob.glob(sys.argv[1]+"/ai-dnd/scripts/engine_split/batches/*.txt")+glob.glob(sys.argv[2]+"/*.txt"):
    names|={l.strip() for l in open(f,encoding="utf-8") if l.strip()}
for e in idx:
    if e["kind"] in ("function","class","assign") and e["name"] not in names:
        print(e["kind"], e["name"], e["lines"])
