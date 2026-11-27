from __future__ import annotations
import csv, json
from pathlib import Path


def prepare_output(path: Path):
    if path.exists():
        raise FileExistsError(f"Refus d'ecraser le dossier existant: {path}")
    path.mkdir(parents=True)


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")


def write_schedule(path: Path, rows: list[dict]):
    fields=["status","service_date","stay_id","client_ref","primary_orientation","secondary_orientation","request_id","care_code","sector","mode_plan","start","end","resource_id","locked","engine"]
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def write_infeasibility(path: Path, diagnostics: dict):
    lines=["RAPPORT D'INFAISABILITE - FUMADES SOLVER V1.1","",f"Statut: {diagnostics.get('status')}",f"Moteur: {diagnostics.get('engine')}",""]
    if diagnostics.get("validation_errors"):
        lines.append("Erreurs de coherence:")
        for e in diagnostics["validation_errors"]: lines.append(f"- [{e['code']}] {e['message']} | {e.get('context',{})}")
    if diagnostics.get("unsat_core"):
        lines += ["","Noyau d'hypotheses CP-SAT:"] + [f"- {x}" for x in diagnostics["unsat_core"]]
    if diagnostics.get("failed_requests"):
        lines += ["","Demandes non positionnees:"] + [f"- {x}" for x in diagnostics["failed_requests"]]
    lines += ["","Actions conseillees:","- verifier les postes actifs et compatibilites;","- verifier les horaires sectoriels et effectifs;","- rechercher des rendez-vous verrouilles en conflit;","- ne modifier la nature d'un soin qu'avec validation medicale;","- conserver Nymphea en lecture seule."]
    path.write_text("\n".join(lines),encoding="utf-8")
