from __future__ import annotations
from collections import defaultdict
from .io import minutes, hhmm


def solve_fallback(problem: dict) -> tuple[list[dict],dict]:
    """Deterministic backtracking used only to verify the pipeline without OR-Tools."""
    cfg=problem["config"]; start_day=minutes(cfg["planning_day_start"]); end_day=minutes(cfg["planning_day_end"])
    cares={x["care_code"]:x for x in problem["care_types"]}; stays={x["stay_id"]:x for x in problem["stays"]}
    resources={x["resource_id"]:x for x in problem["resources"] if x.get("active","1") in ("1","true","TRUE")}
    transitions={(x["from_sector"],x["to_sector"]):int(x["minutes"]) for x in problem["transitions"]}
    compat=defaultdict(list)
    for x in problem["compatibilities"]:
        if x.get("active","1") in ("1","true","TRUE") and x["resource_id"] in resources: compat[(x["care_code"],x["sector"])].append(x["resource_id"])
    tasks=[]
    for req in problem["requests"]:
        c=cares[req["care_code"]]
        if c["mode_plan"]=="AVEC_RESSOURCE":
            tasks.append({"req":req,"dur":int(c["occupancy_minutes"]),"eligible":compat[(req["care_code"],req["sector"])]})
    tasks.sort(key=lambda t:(0 if t["req"].get("locked_start") else 1,len(t["eligible"]),-t["dur"],t["req"]["request_id"]))
    assigned={}; by_resource=defaultdict(list); by_patient=defaultdict(list)

    def overlap(a,b,c,d): return a<d and c<b
    def candidate_times(t):
        r=t["req"]
        if r.get("locked_start"): return [minutes(r["locked_start"])]
        pref=r.get("preferred_start") or stays[r["stay_id"]].get("preferred_start") or cfg["planning_day_start"]
        p=minutes(pref); vals=list(range(start_day,end_day-t["dur"]+1))
        vals.sort(key=lambda x:(abs(x-p),x)); return vals
    def resource_ok(rid,s,e,date):
        res=resources[rid]
        if s<minutes(res["open_start"]) or e>minutes(res["open_end"]): return False
        cap=int(res["capacity"]); concurrent=1
        points=[]
        for a,b,_ in by_resource[(date,rid)]:
            if overlap(s,e,a,b): points.append((a,b))
        if cap==1: return not points
        for minute in range(s,e):
            if 1+sum(1 for a,b in points if a<=minute<b)>cap: return False
        return True
    def patient_ok(req,s,e):
        items=by_patient[(req["service_date"],req["stay_id"])]
        for a,b,other in items:
            if s>=b:
                if s < b+transitions.get((other["sector"],req["sector"]),0): return False
            elif a>=e:
                if a < e+transitions.get((req["sector"],other["sector"]),0): return False
            else: return False
            if cares[req["care_code"]].get("vr_entry_first","0") in ("1","true","TRUE") and other["sector"]=="VR" and e>a: return False
            if cares[other["care_code"]].get("vr_entry_first","0") in ("1","true","TRUE") and req["sector"]=="VR" and b>s: return False
        return True
    def place(i):
        if i==len(tasks): return True
        t=tasks[i]; req=t["req"]; ids=t["eligible"]
        if req.get("locked_resource"): ids=[req["locked_resource"]]
        for s in candidate_times(t):
            e=s+t["dur"]
            if not patient_ok(req,s,e): continue
            for rid in ids:
                if not resource_ok(rid,s,e,req["service_date"]): continue
                assigned[req["request_id"]]=(s,e,rid); by_resource[(req["service_date"],rid)].append((s,e,req)); by_patient[(req["service_date"],req["stay_id"])].append((s,e,req))
                if place(i+1): return True
                by_resource[(req["service_date"],rid)].pop(); by_patient[(req["service_date"],req["stay_id"])].pop(); assigned.pop(req["request_id"],None)
        return False
    ok=place(0)
    if not ok: return [],{"status":"INFEASIBLE","engine":"fallback","failed_requests":[t["req"]["request_id"] for t in tasks if t["req"]["request_id"] not in assigned]}
    rows=[]
    for req in problem["requests"]:
        stay=stays[req["stay_id"]]; row={"status":"PROPOSE","service_date":req["service_date"],"stay_id":req["stay_id"],"client_ref":stay["client_ref"],"primary_orientation":stay["primary_orientation"],"secondary_orientation":stay.get("secondary_orientation",""),"request_id":req["request_id"],"care_code":req["care_code"],"sector":req["sector"],"mode_plan":req["mode_plan"],"locked":bool(req.get("locked_start") or req.get("locked_resource")),"engine":"fallback"}
        if req["request_id"] in assigned:
            s,e,rid=assigned[req["request_id"]]; row.update({"start":hhmm(s),"end":hhmm(e),"resource_id":rid})
        else: row.update({"start":"","end":"","resource_id":"SANS_CRENEAU" if req["mode_plan"]=="SANS_CRENEAU" else ""})
        rows.append(row)
    rows.sort(key=lambda x:(x["service_date"],x["stay_id"],x["start"] or "99:99",x["request_id"]))
    return rows,{"status":"FEASIBLE","engine":"fallback","note":"Moteur local de verification; CP-SAT reste le moteur cible."}
