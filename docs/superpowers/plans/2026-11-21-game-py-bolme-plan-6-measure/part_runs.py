import ast,sys,glob
for f in sorted(glob.glob(sys.argv[1]+"/ai-dnd/game_parts/*.py")):
    lines=open(f,encoding="utf-8").read().split("\n")
    if lines and lines[-1]=="": lines=lines[:-1]
    tree=ast.parse("\n".join(lines)+"\n"); inside=set()
    for n in tree.body:
        s=min([n.lineno]+[d.lineno for d in getattr(n,"decorator_list",[])]); inside.update(range(s,n.end_lineno+1))
    run=0; mx=0; over=0
    for i,l in enumerate(lines+["x"],1):
        if i<=len(lines) and not l.strip() and i not in inside: run+=1
        else:
            if run>2: over+=run-2
            mx=max(mx,run); run=0
    print(f.split("/")[-1], "max_run", mx, "lines_over_2", over)
