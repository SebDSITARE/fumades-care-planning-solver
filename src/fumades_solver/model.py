from __future__ import annotations
from collections import defaultdict
from .io import minutes, hhmm


def solve_cp_sat(problem: dict) -> tuple[list[dict], dict]:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError("OR-Tools n'est pas installe. Executer: python -m pip install -e .") from exc

    cfg=problem["config"]
    day_start=minutes(cfg["planning_day_start"]); day_end=minutes(cfg["planning_day_end"])
    cares={x["care_code"]:x for x in problem["care_types"]}
    resources={x["resource_id"]:x for x in problem["resources"] if x.get("active","1") in ("1","true","TRUE")}
    stays={x["stay_id"]:x for x in problem["stays"]}
    transitions={(x["from_sector"],x["to_sector"]):int(x["minutes"]) for x in problem["transitions"]}
    compat=defaultdict(list)
    for x in problem["compatibilities"]:
        if x.get("active","1") in ("1","true","TRUE") and x["resource_id"] in resources:
            compat[(x["care_code"],x["sector"])].append(x["resource_id"])
    workforce={x["pool_id"]:x for x in problem["workforce"]}

    model=cp_model.CpModel(); tasks={}; assumptions={}
    resource_intervals=defaultdict(list); patient_intervals=defaultdict(list); workforce_intervals=defaultdict(list)
    objective=[]

    def pool_for(care,sector):
        pools=[p for p in care.get("workforce_pool","").split("|") if p]
        if len(pools)<=1: return pools[0] if pools else None
        exact=[p for p in pools if p.endswith("_"+sector)]
        return exact[0] if exact else pools[0]

    for req in problem["requests"]:
        care=cares[req["care_code"]]
        if care["mode_plan"]!="AVEC_RESSOURCE": continue
        dur=int(care["occupancy_minutes"]); key=req["request_id"]
        start=model.NewIntVar(day_start,day_end-dur,f"start_{key}")
        end=model.NewIntVar(day_start+dur,day_end,f"end_{key}")
        model.Add(end==start+dur)
        assump=model.NewBoolVar(f"required_{key}"); model.AddAssumption(assump); assumptions[assump.Index()]=key
        choices=[]
        eligible=compat[(req["care_code"],req["sector"])]
        for rid in eligible:
            res=resources[rid]; present=model.NewBoolVar(f"use_{key}_{rid}")
            interval=model.NewOptionalIntervalVar(start,dur,end,present,f"int_{key}_{rid}")
            model.Add(start>=minutes(res["open_start"])).OnlyEnforceIf(present)
            model.Add(end<=minutes(res["open_end"])).OnlyEnforceIf(present)
            resource_intervals[(req["service_date"],rid)].append(interval)
            choices.append((rid,present,interval))
        model.Add(sum(p for _,p,_ in choices)==1).OnlyEnforceIf(assump)
        if req.get("locked_start"): model.Add(start==minutes(req["locked_start"]))
        if req.get("locked_resource"):
            for rid,p,_ in choices: model.Add(p==int(rid==req["locked_resource"]))
        mandatory=model.NewIntervalVar(start,dur,end,f"patient_{key}")
        patient_intervals[(req["service_date"],req["stay_id"])].append((req,start,end,mandatory))
        pool=pool_for(care,req["sector"])
        if pool and pool in workforce: workforce_intervals[(req["service_date"],pool)].append(mandatory)
        pref=req.get("preferred_start") or stays[req["stay_id"]].get("preferred_start")
        if pref:
            dev=model.NewIntVar(0,day_end-day_start,f"dev_{key}"); model.AddAbsEquality(dev,start-minutes(pref))
            objective.append(int(cfg["objective_weights"].get("preferred_start_deviation",100))*dev)
        tasks[key]={"request":req,"care":care,"start":start,"end":end,"choices":choices}

    for (d,rid),intervals in resource_intervals.items():
        cap=int(resources[rid]["capacity"])
        if cap==1: model.AddNoOverlap(intervals)
        else: model.AddCumulative(intervals,[1]*len(intervals),cap)
    for key,items in patient_intervals.items():
        model.AddNoOverlap([x[3] for x in items])
        for i in range(len(items)):
            for j in range(i+1,len(items)):
                ra,sa,ea,_=items[i]; rb,sb,eb,_=items[j]
                gap_ab=transitions.get((ra["sector"],rb["sector"]),0); gap_ba=transitions.get((rb["sector"],ra["sector"]),0)
                order=model.NewBoolVar(f"order_{ra['request_id']}_{rb['request_id']}")
                model.Add(sb>=ea+gap_ab).OnlyEnforceIf(order)
                model.Add(sa>=eb+gap_ba).OnlyEnforceIf(order.Not())
        irrig=[x for x in items if cares[x[0]["care_code"]].get("vr_entry_first","0") in ("1","true","TRUE")]
        for irr in irrig:
            for other in items:
                if other is not irr and other[0]["sector"]=="VR": model.Add(irr[2]<=other[1])
        if len(items)>1:
            min_s=model.NewIntVar(day_start,day_end,"min_"+key[0]+"_"+key[1]); max_e=model.NewIntVar(day_start,day_end,"max_"+key[0]+"_"+key[1])
            model.AddMinEquality(min_s,[x[1] for x in items]); model.AddMaxEquality(max_e,[x[2] for x in items])
            span=model.NewIntVar(0,day_end-day_start,"span_"+key[0]+"_"+key[1]); model.Add(span==max_e-min_s)
            objective.append(int(cfg["objective_weights"].get("patient_path_span",10))*span)
    if cfg["rule_switches"].get("enforce_workforce_pools",True):
        for (d,pool),intervals in workforce_intervals.items(): model.AddCumulative(intervals,[1]*len(intervals),int(workforce[pool]["capacity"]))
    if objective: model.Minimize(sum(objective))

    solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=float(cfg.get("max_solve_seconds",60)); solver.parameters.num_search_workers=int(cfg.get("num_search_workers",8))
    status=solver.Solve(model); status_name=solver.StatusName(status)
    diagnostics={"status":status_name,"engine":"cp-sat","wall_time_seconds":solver.WallTime(),"objective":solver.ObjectiveValue() if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None}
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        core=solver.SufficientAssumptionsForInfeasibility() if status==cp_model.INFEASIBLE else []
        diagnostics["unsat_core"]=[assumptions.get(abs(x),str(x)) for x in core]
        return [],diagnostics
    rows=[]
    for req in problem["requests"]:
        stay=stays[req["stay_id"]]; base={"status":"PROPOSE","service_date":req["service_date"],"stay_id":req["stay_id"],"client_ref":stay["client_ref"],"primary_orientation":stay["primary_orientation"],"secondary_orientation":stay.get("secondary_orientation",""),"request_id":req["request_id"],"care_code":req["care_code"],"sector":req["sector"],"mode_plan":req["mode_plan"],"locked":bool(req.get("locked_start") or req.get("locked_resource")),"engine":"cp-sat"}
        if req["request_id"] in tasks:
            t=tasks[req["request_id"]]; base["start"]=hhmm(solver.Value(t["start"])); base["end"]=hhmm(solver.Value(t["end"])); base["resource_id"]=next(r for r,p,_ in t["choices"] if solver.Value(p))
        else: base.update({"start":"","end":"","resource_id":"SANS_CRENEAU" if req["mode_plan"]=="SANS_CRENEAU" else ""})
        rows.append(base)
    rows.sort(key=lambda x:(x["service_date"],x["stay_id"],x["start"] or "99:99",x["request_id"]))
    return rows,diagnostics
