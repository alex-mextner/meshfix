"""Small public API and serialized-output checks for the audit, after compare.py."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

import meshfix
import numpy as np

from compare import cube, concat, inspect, hash_mesh

out = Path("audit-output")
out.mkdir(exist_ok=True)
rows = {}
cli = Path("build/meshfix").resolve()
v, f = cube()
with tempfile.TemporaryDirectory() as wd:
    tmp = Path(wd)
    for offset in (0., 1000., 1e6, 1e8):
        p, t = concat((v+offset, f), (v+offset+[1,1,0], f))
        obj, stl = tmp/"in.obj", tmp/"fixed.stl"
        obj.write_text("".join("v %.17g %.17g %.17g\n"%tuple(a) for a in p)
                       + "".join("f %d %d %d\n"%tuple(a+1) for a in t))
        res = subprocess.run([cli,obj,"-o",stl,"--report","json"], capture_output=True,text=True,timeout=10)
        raw = stl.read_bytes()
        count = struct.unpack_from("<I", raw, 80)[0]
        xyz = [struct.unpack_from("<9f",raw,84+50*i+12) for i in range(count)]
        p2 = np.reshape(xyz, (-1,3))
        t2 = np.arange(len(p2)).reshape((-1,3))
        roundtrip = subprocess.run([cli,stl,"--analyze","--report","json"],capture_output=True,text=True,timeout=10)
        rows["serialized_"+str(offset)] = {"repair_exit":res.returncode,"reported":json.loads(res.stdout),
            "saved_stl":inspect(p2,t2),"readback_exit":roundtrip.returncode,
            "readback_report":json.loads(roundtrip.stdout)}
    malformed = tmp/"empty.obj"
    malformed.write_text("# intentionally empty surface\n")
    rejected = subprocess.run([cli,malformed,"--analyze"],capture_output=True,text=True,timeout=10)
    rows["empty_file"] = {"exit":rejected.returncode,"stderr":rejected.stderr}
for label, data in (("fractional-index", np.asarray(f,float)+.25), ("negative-index", [[-1,1,2]])):
    try:
        meshfix.repair(v, data)
        rows[label] = {"accepted":True}
    except Exception as exc:
        rows[label] = {"error_type":type(exc).__name__, "message":str(exc)}
p1,t1,_ = meshfix.repair(v,f,flags=0)
rows["no_flags_valid_unchanged"] = hash_mesh(p1,t1) == hash_mesh(v,f)
p,t = concat(cube(), cube(.5,(.25,)*3))
p1,t1,rep = meshfix.repair(p,t,flags=int(meshfix.Fix.NESTED_SHELLS))
rows["nested_only"] = {"native":rep.to_dict(), "measured":inspect(p1,t1)}
seen = []
def cancel(stage, fraction):
    seen.append(stage)
    return stage == "weld"
try:
    meshfix.repair(v,f,progress=cancel)
except meshfix.MeshfixError as exc:
    rows["cancel"] = {"status":exc.status,"seen":seen}
fd, log = tempfile.mkstemp(prefix="meshfix-contracts-", suffix=".log")
os.close(fd)
print("Log", log, flush=True)
output = json.dumps(rows, indent=2)
Path(log).write_text(output)
(out/"contracts.json").write_text(output)
print({k: v.get("readback_exit") if isinstance(v,dict) else v for k,v in rows.items()})
print("Log", log)
