"""Prepare local independent annotation forms without suggested judgments."""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
import sys

import yaml

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
sys.path.insert(0, str(LEGACY / "src"))
from eval.rebuttal.models import BlindTask, Settings
from eval.label import rq4
from analysis.build_instances import build_patch

HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Independent annotation</title>
<style>body{font:16px system-ui;margin:24px;color:#172b3a;background:#f6f8fa}button,select,input,textarea{font:inherit;padding:7px;margin:4px}header{position:sticky;top:0;background:#f6f8fa;padding:8px;z-index:2}main{display:grid;grid-template-columns:55% 45%;gap:15px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px;max-height:75vh;overflow:auto}.label{display:block;font-size:14px;padding:3px}.line{padding:12px;background:white;border:1px solid #ccd5dd;margin:8px 0}textarea{width:90%;height:90px}#forms{max-height:75vh;overflow:auto}.warning{color:#8b3410}h2{font-size:20px}</style>
<header><h1 id="title"></h1><p id="instructions"></p><label>Rater ID <input id="rater" placeholder="A or B" autocomplete="off"></label><button id="previous">Previous</button><input id="position" type="number" min="1" style="width:80px"><button id="jump">Go</button><button id="next">Next</button><button id="export">Export ratings JSON</button><p id="progress"></p></header>
<main><section><h2 id="taskTitle"></h2><pre id="patch"></pre></section><section id="forms"></section></main>
<script id="payload" type="application/json">PAYLOAD</script>
<script>
const data=JSON.parse(document.getElementById('payload').textContent), $=id=>document.getElementById(id);
let pos=0,ratings={},activeRater='';
$('title').textContent=data.mode==='blind'?'Independent blind annotation':'Security match audit';
$('instructions').textContent=data.mode==='blind'?'Read the patch and apply the fixed taxonomy independently. No model predictions are included. An empty label set is valid only after explicit review. Record evidence and uncertainty; do not discuss judgments before both raters export.':'Read the full patch. For every matched line classify textual meaning and direction relative to the prior version. Select uncertain when context is insufficient. A match is not a vulnerability. Complete every line before marking the instance reviewed.';
function key(){return data.run_id+'-'+data.mode+'-'+activeRater;}
function persist(){if(!activeRater)return;try{localStorage.setItem(key(),JSON.stringify(ratings));}catch(e){alert('Browser storage unavailable or full. Export JSON now to preserve work.');}}
function current(){return ratings[data.tasks[pos].task_id]||{task_id:data.tasks[pos].task_id,labels:[],evidence:'',uncertainty:'',matches:{},complete:false};}
function save(value){if(!activeRater){alert('Enter a rater ID before annotating.');render();return;}ratings[value.task_id]=value;persist();progress();}
function progress(){const done=Object.values(ratings).filter(r=>r.complete).length;$('progress').textContent=`Task ${pos+1}/${data.tasks.length}; ${done} explicitly completed. Export regularly; keep this file private.`;}
function el(tag,text){const node=document.createElement(tag);if(text)node.textContent=text;return node;}
function select(options,value,update){const node=el('select');for(const option of ['',...options]){const item=el('option',option||'Choose a judgment');item.value=option;node.appendChild(item);}node.value=value||'';node.onchange=()=>update(node.value);return node;}
function render(){const task=data.tasks[pos];$('position').value=pos+1;$('taskTitle').textContent=task.task_id;$('patch').textContent=task.patch;$('forms').replaceChildren();let state=current();
 if(data.mode==='blind'){for(const family of data.taxonomy.families){$('forms').appendChild(el('h2',family.name));for(const pattern of family.patterns){const label=el('label');label.className='label';const box=el('input');box.type='checkbox';box.checked=state.labels.includes(pattern.name);box.onchange=()=>{state.labels=box.checked?[...state.labels,pattern.name]:state.labels.filter(x=>x!==pattern.name);state.complete=false;save(state);};label.append(box,document.createTextNode(pattern.name));label.title=pattern.definition+' '+(pattern.decision_rule||'');$('forms').appendChild(label);const details=el('details');details.appendChild(el('summary','Definition and decision rule'));details.appendChild(el('p',label.title));$('forms').appendChild(details);}}}
 else {for(const match of task.matches){const card=el('div');card.className='line';card.appendChild(el('p',match.match_id+' | '+match.path+' | patch line '+match.patch_line));card.appendChild(el('pre',match.context||match.snippet));const rating=state.matches[match.match_id]||{meaning:'',direction:'',evidence:''};
 const update=()=>{state.matches[match.match_id]=rating;state.complete=false;save(state);};
 card.appendChild(select(['operational_instruction','security_guardrail','benign_example_or_documentation','irrelevant_match','uncertain'],rating.meaning,v=>{rating.meaning=v;update();}));
 card.appendChild(select(['authority_expansion_or_risk_encouragement','hardening','no_clear_change','mixed','uncertain'],rating.direction,v=>{rating.direction=v;update();}));
 const notes=el('textarea');notes.placeholder='Evidence and interpretation of before/after context';notes.value=rating.evidence;notes.oninput=()=>{rating.evidence=notes.value;update();};card.appendChild(notes);$('forms').appendChild(card);}}
 for(const field of ['evidence','uncertainty']){const box=el('textarea');box.placeholder=field==='evidence'?'Overall evidence (required to mark complete)':'Uncertainty, missing context, or exposure to prior annotations';box.value=state[field];box.oninput=()=>{state[field]=box.value;state.complete=false;save(state);};$('forms').appendChild(box);}
 const finish=el('button','Mark this task reviewed');finish.onclick=()=>{if(!state.evidence.trim()){alert('Record evidence, including why no label applies if applicable.');return;}if(data.mode==='security'&&task.matches.some(m=>!state.matches[m.match_id]?.meaning||!state.matches[m.match_id]?.direction)){alert('Complete both classifications for every matched line.');return;}state.complete=true;save(state);};$('forms').appendChild(finish);progress();}
$('rater').onchange=()=>{activeRater=$('rater').value.trim();try{ratings=JSON.parse(localStorage.getItem(key())||'{}');}catch(e){ratings={};}render();};
$('previous').onclick=()=>{pos=Math.max(0,pos-1);render();};$('next').onclick=()=>{pos=Math.min(data.tasks.length-1,pos+1);render();};$('jump').onclick=()=>{pos=Math.max(0,Math.min(data.tasks.length-1,Number($('position').value)-1));render();};
$('export').onclick=()=>{if(!activeRater){alert('Enter rater ID.');return;}const exportData={run_id:data.run_id,mode:data.mode,rater:activeRater,exported_at:new Date().toISOString(),sample_size:data.tasks.length,ratings:Object.values(ratings)};const url=URL.createObjectURL(new Blob([JSON.stringify(exportData,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download=data.mode+'-'+activeRater+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};render();
</script></html>'''


def write_form(path, payload):
    encoded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    path.write_text(HTML.replace("PAYLOAD", encoded))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run_id", required=True)
    args = parser.parse_args()
    out = LEGACY / "data/rebuttal" / args.run_id / "human"
    out.mkdir(parents=True, exist_ok=False)
    settings = Settings.model_validate(yaml.safe_load((LEGACY / "configs/rebuttal.yaml").read_text()))
    candidates = sorted((LEGACY / "data/label/inputs").glob("*.json"))
    chosen = random.Random(settings.seed).sample(candidates, settings.blind_sample_size)
    taxonomy = json.loads((LEGACY / "skills/iter-taxonomy-build/taxonomy.json").read_text())
    tasks, mapping = [], []
    originals = {}
    for path in candidates:
        data = json.loads(path.read_text())
        originals[data["modification_id"]] = data
    for i, path in enumerate(chosen):
        data = json.loads(path.read_text())
        task_id = f"B{i+1:03d}"
        task = BlindTask(task_id=task_id, patch=rq4.redact_snippet(build_patch(data['files'])))
        tasks.append(task.model_dump(exclude={"labels", "evidence", "uncertainty"}))
        mapping.append({"task_id": task_id, "record": path.name, "instance_id": data["modification_id"],
                        "in_bootstrap_sample": (LEGACY / "data/label/sample" / path.name).exists()})
    manifest = {"seed": settings.seed, "population": len(candidates), "sample_size": len(tasks),
                "selection": "simple random sample without replacement from all candidates",
                "inclusion_probability": len(tasks) / len(candidates),
                "held_out_status": "not claimed; taxonomy iteration membership is unavailable",
                "mapping": mapping}
    (out / "coordinator_blind_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_form(out / "blind.html", {"run_id": args.run_id, "mode": "blind", "taxonomy": taxonomy, "tasks": tasks})
    matches = {}
    with (LEGACY / "eval/tables-and-figures/rq4-security-matches.csv").open() as stream:
        for match in csv.DictReader(stream):
            key = (match["instance_id"], match["path"], match["patch_line"])
            matches.setdefault(key, []).append(match)
    positive_ids = sorted({key[0] for key in matches})
    security_tasks, security_mapping = [], []
    for i, identity in enumerate(positive_ids):
        task_id = f"S{i+1:03d}"
        line_tasks = []
        for j, (key, values) in enumerate((k, v) for k, v in matches.items() if k[0] == identity):
            file = next(f for f in originals[identity]["files"] if f["filename"] == key[1])
            patch_lines = (file.get("patch") or "").splitlines()
            position = int(key[2]) - 1
            context = "\n".join(f"{'>>' if k == position else '  '} {k+1}: {patch_lines[k]}"
                                for k in range(max(0, position - 8), min(len(patch_lines), position + 9)))
            line_tasks.append({"match_id": f"L{j+1:03d}", "path": key[1], "patch_line": key[2],
                               "snippet": values[0]["snippet"], "context": rq4.redact_snippet(context)})
            security_mapping.append({"task_id": task_id, "match_id": f"L{j+1:03d}", "instance_id": identity,
                                     "path": key[1], "patch_line": key[2], "rules": [v["rule_id"] for v in values]})
        security_tasks.append({"task_id": task_id, "patch": rq4.redact_snippet(build_patch(originals[identity]["files"])), "matches": line_tasks})
    write_form(out / "security.html", {"run_id": args.run_id, "mode": "security", "tasks": security_tasks})
    (out / "coordinator_security_manifest.json").write_text(json.dumps(security_mapping, indent=2))
    (out / "README.md").write_text(f'''# Independent human annotation

Two raters independently complete the same {len(tasks)} blind tasks and the same {len(security_tasks)} security instances ({len(matches)} distinct matched lines). Open [blind.html](blind.html) and [security.html](security.html) locally. Enter separate rater IDs A and B, annotate, explicitly mark tasks reviewed, and export JSON regularly. Browser storage is a convenience, not a backup. Do not share ratings before independent exports are complete.

Blind annotation applies the fixed taxonomy to the patch. No model labels, predictions or rationale are present in the form. Record label evidence or an explicit reason for an empty set. Hover or expand each label to read its definition. Note insufficient context rather than guessing. This checks taxonomy application, not independent open coding or exhaustive taxonomy validity.

Security annotation distinguishes textual meaning from change direction. Read the full patch around every line. A security guardrail can match a rule while reducing risk. Examples and quoted commands need context. Use uncertain when the prior state is not observable. The security set is a census of detector-positive instances; it cannot estimate detector recall or the rate of vulnerabilities among all adaptations.

Both raters must disclose previous exposure to these records or model answers and relevant expertise. Coordinator manifests contain original identities and bootstrap membership; do not send them to raters. The sample is not claimed as held out from taxonomy development because the iteration log is missing. Model-output anchoring is reduced only to the extent that raters have not previously seen those answers.

After both exports, adjudicate disagreements while model outputs remain hidden, save adjudicated evidence, then compare against original predictions. Do not treat missing/incomplete tasks as negative labels or agreements. Return four files: blind-A.json, blind-B.json, security-A.json and security-B.json. No judgments have been prefilled.

Sampling: seed {settings.seed}, simple random sample without replacement, n={len(tasks)}, N={len(candidates)}. The approximate 95% worst-case margin is 5 percentage points for one overall binary proportion with finite-population correction, not for every label's precision or recall.
''')
    provenance = {"source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "sample_size": len(tasks), "security_instances": len(security_tasks), "security_lines": len(matches)}
    (out / "preparation.json").write_text(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
