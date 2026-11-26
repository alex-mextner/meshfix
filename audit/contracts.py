"""Small public API and serialized-output checks for the audit, after compare.py."""
import json
import os
from pathlib import Path
import struct
import sys
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
p,t = concat(cube(), cube(1,(.37,.43,.29)))
for sep in (0,10):
    p1,t1,r = meshfix.repair(p,t,flags=int(meshfix.Fix.CHECK_SELF_INTERSECTIONS),separation=sep)
    rows["diagnostic_separation_" + str(sep)] = {"native_pairs":r.self_intersecting_pairs,
        "independent_pairs":inspect(p1,t1)["crossings"],"unchanged":hash_mesh(p,t)==hash_mesh(p1,t1)}
p = v*np.array([100,.001,.001])
p1,t1,r = meshfix.repair(p,f,min_component_faces=0,weld_tolerance=0)
rows["thin_components_only_thresholds_off"] = {"native":r.to_dict(),"input":inspect(p,f),"measured":inspect(p1,t1)}
code = """import meshfix
v=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
f=[[0.1,2.1,1.1],[0.1,1.1,3.1],[0.1,3.1,2.1],[1.1,2.1,3.1]]
try:
 p,t,r=meshfix.repair(v,f,flags=0)
 print(t)
except Exception as e:
 print(type(e).__name__,str(e))
"""
for mode, args in (("numpy",[]),("no_site_packages",["-S"])):
    result = subprocess.run([sys.executable,*args,"-c",code],capture_output=True,text=True,timeout=10)
    rows["fractional_indices_"+mode] = {"exit":result.returncode,"stdout":result.stdout,"stderr":result.stderr}
# OBJ planar U with known area 7. A fan cannot cover this polygon without crossing its notch.
with tempfile.TemporaryDirectory() as wd:
    tmp = Path(wd)
    ring = [(0,0),(3,0),(3,3),(2,3),(2,1),(1,1),(1,3),(0,3)]
    n = len(ring)
    coords = [(x,y,z) for z in (0,1) for x,y in ring]
    polygons = [list(reversed(range(n))), list(range(n,2*n))]
    polygons += [[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    src, dst = tmp/"u.obj",tmp/"out.obj"
    src.write_text("".join("v %s %s %s\n" % a for a in coords) +
                   "".join("f "+" ".join(str(i+1) for i in loop)+"\n" for loop in polygons))
    rep = meshfix.repair_file(src,dst, flags=0)
    vs,fs = [],[]
    for line in dst.read_text().splitlines():
        part=line.split()
        if part[0]=="v": vs.append(list(map(float,part[1:])))
        if part[0]=="f": fs.append([int(x)-1 for x in part[1:]])
    triangles=np.array(vs)[fs]
    lid=triangles[(triangles[:,:,2]==1).all(axis=1)]
    area=np.linalg.norm(np.cross(lid[:,1]-lid[:,0],lid[:,2]-lid[:,0]),axis=1).sum()/2
    rows["concave_obj"]={"reference_lid_area":7,"triangulated_lid_area":float(area),
                         "native":rep.to_dict(),"measured":inspect(vs,fs)}
for off in (0., 1e12):
    base = np.array([[0,0,0],[1,0,0],[0,0,1]],float)
    v2 = np.vstack((base,base+[0,.0005,0]))+[off,0,0]
    f2 = [[0,1,2],[3,4,5]]
    p,t,r = meshfix.repair(v2,f2,flags=int(meshfix.Fix.WELD),weld_tolerance=.001)
    rows["translated_weld_"+str(off)] = {"vertices":len(p),"merged":r.vertices_merged,
        "reported_tolerance":r.weld_tolerance_used}
output=json.dumps(rows,indent=2)
Path(log).write_text(output)
(out/"contracts.json").write_text(output)
print("Completed extra checks. Log",log)
