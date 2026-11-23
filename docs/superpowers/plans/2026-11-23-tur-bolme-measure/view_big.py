"""Print blocks with n >= MIN lines from a block_io.py output file."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
path, mn = sys.argv[1], int(sys.argv[2])
for line in open(path, encoding="utf-8"):
    if not line[:3].strip().isdigit():
        continue
    head, kind_etc = line.split(" | ", 3)[:3], line.split(" | ", 3)[3]
    kind, i, o, rr, mk, outs, late, ins, nl = kind_etc.rsplit(" | ", 8)
    if int(head[2]) >= mn:
        print(f"{head[0].strip()} {head[1]} n={head[2]} in={i} out={o} r/r={rr} [{mk}] {kind[:45]} :: {outs[:120]} || late={late.strip()[:60]}")
