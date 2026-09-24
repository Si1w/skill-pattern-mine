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
from eval.rebuttal.models import BlindTask, BlindSamplingFrame, Settings
from eval.label import rq4
from analysis.build_instances import build_patch

HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Independent annotation</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box}body{font:15px system-ui;margin:0;padding:16px 20px;color:#172b3a;background:#f6f8fa;height:100vh;display:flex;flex-direction:column;gap:12px}button,select,input,textarea{font:inherit;padding:6px;margin:3px;border:1px solid #bac6d2;border-radius:5px;background:white;color:inherit}button{cursor:pointer}button:hover{background:#e9eff6}button:disabled{cursor:default;opacity:.5}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #0969da;outline-offset:2px}header{flex:none}h1{font-size:21px;margin:0 0 6px}h2{font-size:17px;margin:8px 0}header p{margin:6px 0;max-width:120ch}#progress{font-size:13px;color:#526477}main{display:grid;grid-template-columns:minmax(0,65fr) minmax(270px,35fr);gap:16px;min-height:0;flex:1}main.wide-patch{grid-template-columns:minmax(0,78fr) minmax(250px,22fr)}#patchPane{min-height:0;min-width:0;display:flex;flex-direction:column;--patch-font:13px}.patch-toolbar{border:1px solid #ccd5dd;border-radius:7px 7px 0 0;padding:8px;background:#edf2f7;flex:none}.patch-toolbar label{font-size:13px;white-space:nowrap}.patch-toolbar select{max-width:100%}#patchFile{width:100%;font-size:12px}#patchStats{font-size:12px;color:#526477;margin-top:5px}.legend{font-size:12px;margin:6px 0 0}.legend span{padding:2px 7px;border-radius:3px}.legend .plus{background:#dafbe1;color:#116329}.legend .minus{background:#ffebe9;color:#82071e}#patch,#rawPatch{flex:1;min-height:0;overflow:auto;border:1px solid #ccd5dd;border-top:0;background:white;margin:0;scroll-padding-top:8px}#patch[hidden],#rawPatch[hidden]{display:none}.diff-file{margin:0;border-bottom:1px solid #bac6d2}.diff-file>summary{padding:10px 12px;background:#edf2f7;color:#263b53;cursor:pointer;overflow-wrap:anywhere;font:600 12px ui-monospace,SFMono-Regular,Consolas,monospace}.diff-table{border-collapse:collapse;width:100%;table-layout:fixed;font:var(--patch-font)/1.6 ui-monospace,SFMono-Regular,Consolas,monospace}.diff-table td{vertical-align:top}.old-number,.new-number{width:48px;padding:0 6px;color:#667789;text-align:right;border-right:1px solid #d8e0e7;user-select:none;font-size:11px;background:#f6f8fa}.diff-code{padding:0 10px;white-space:pre-wrap;overflow-wrap:anywhere;tab-size:4}.added .diff-code{background:#e6ffec;color:#16452b}.removed .diff-code{background:#ffebe9;color:#6d2020}.hunk td{background:#ddf0ff;color:#14558a;padding-top:5px;padding-bottom:5px}.meta .diff-code{color:#596b7b;background:#f6f8fa}.no-wrap .diff-table{table-layout:auto}.no-wrap .diff-code{white-space:pre;overflow-wrap:normal}.no-wrap .old-number,.no-wrap .new-number{min-width:48px}.no-wrap #rawPatch{white-space:pre;overflow-wrap:normal}#rawPatch{padding:12px;font:var(--patch-font)/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}#forms{min-height:0;overflow:auto;padding:4px 12px 16px;border:1px solid #ccd5dd;border-radius:7px;background:white}.label{display:block;font-size:14px;padding:3px}#forms details{font-size:12px;color:#526477;margin-left:8px}#forms details summary{cursor:pointer}.line{padding:10px;background:white;border:1px solid #ccd5dd;margin:8px 0}.line pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:10px;font:12px/1.5 ui-monospace,monospace;max-height:40vh;overflow:auto}textarea{width:100%;min-height:90px;resize:vertical}.warning{color:#8b3410}@media(max-width:850px){body{height:auto;min-height:100vh;padding:12px}main,main.wide-patch{display:block}#patchPane{height:70vh}#forms{max-height:none;margin-top:16px}.old-number,.new-number{width:34px;padding:0 3px}}
</style>
<header><h1 id="title"></h1><p id="instructions"></p><label>Rater ID <input id="rater" placeholder="A or B" autocomplete="off"></label><button id="previous">Previous</button><input id="position" type="number" min="1" style="width:80px"><button id="jump">Go</button><button id="next">Next</button><button id="export">Export ratings JSON</button><p id="progress"></p></header>
<main><section id="patchPane"><h2 id="taskTitle"></h2>
<div class="patch-toolbar"><label for="patchFile">Jump to file</label><select id="patchFile"></select>
<button id="previousHunk" title="Jump to the previous diff hunk">Previous change</button><button id="nextHunk" title="Jump to the next diff hunk">Next change</button><button id="widerPatch" aria-pressed="false">Wider patch</button>
<label><input id="wrapPatch" type="checkbox" checked>Wrap lines</label><label>Font <select id="patchFont"><option>12</option><option selected>13</option><option>14</option><option>16</option><option>18</option></select></label><label><input id="rawToggle" type="checkbox">Raw patch</label>
<p class="legend"><span class="minus">− Removed</span> <span class="plus">+ Added</span> Columns: original / modified line</p><div id="patchStats"></div></div>
<div id="patch" aria-label="Patch diff"></div><pre id="rawPatch" hidden></pre></section><section id="forms"></section></main>
<script id="payload" type="application/json">PAYLOAD</script>
<script>
PATCH_VIEW_SCRIPT
</script>
<script>
const data=JSON.parse(document.getElementById('payload').textContent), $=id=>document.getElementById(id);
let pos=0,ratings={},activeRater='';
$('title').textContent=data.mode==='blind'?'Independent blind annotation':'Security match audit';
$('instructions').textContent=data.mode==='blind'?'Read the patch and apply the fixed taxonomy independently. No model predictions are included. An empty label set is valid only after explicit review. Evidence and uncertainty notes are optional; do not discuss judgments before both raters export.':'Read the full patch. For every matched line classify textual meaning and direction relative to the prior version. Select uncertain when context is insufficient. A match is not a vulnerability. Complete every line before marking the instance reviewed.';
function key(){return data.run_id+'-'+data.mode+'-'+activeRater;}
function persist(){if(!activeRater)return;try{localStorage.setItem(key(),JSON.stringify(ratings));}catch(e){alert('Browser storage unavailable or full. Export JSON now to preserve work.');}}
function current(){return ratings[data.tasks[pos].task_id]||{task_id:data.tasks[pos].task_id,labels:[],evidence:'',uncertainty:'',matches:{},complete:false};}
function save(value){if(!activeRater){alert('Enter a rater ID before annotating.');render();return;}ratings[value.task_id]=value;persist();progress();}
function progress(){const done=Object.values(ratings).filter(r=>r.complete).length;$('progress').textContent=`Task ${pos+1}/${data.tasks.length}; ${done} explicitly completed. Export regularly; keep this file private.`;}
function el(tag,text){const node=document.createElement(tag);if(text)node.textContent=text;return node;}
function select(options,value,update){const node=el('select');for(const option of ['',...options]){const item=el('option',option||'Choose a judgment');item.value=option;node.appendChild(item);}node.value=value||'';node.onchange=()=>update(node.value);return node;}
function render(){const task=data.tasks[pos];$('position').value=pos+1;$('taskTitle').textContent=task.task_id;renderPatch(task.patch);$('forms').replaceChildren();let state=current();
 if(data.mode==='blind'){for(const family of data.taxonomy.families){$('forms').appendChild(el('h2',family.name));for(const pattern of family.patterns){const label=el('label');label.className='label';const box=el('input');box.type='checkbox';box.checked=state.labels.includes(pattern.name);box.onchange=()=>{state.labels=box.checked?[...state.labels,pattern.name]:state.labels.filter(x=>x!==pattern.name);state.complete=false;save(state);};label.append(box,document.createTextNode(pattern.name));label.title=pattern.definition+' '+(pattern.decision_rule||'');$('forms').appendChild(label);const details=el('details');details.appendChild(el('summary','Definition and decision rule'));details.appendChild(el('p',label.title));$('forms').appendChild(details);}}}
 else {for(const match of task.matches){const card=el('div');card.className='line';card.appendChild(el('p',match.match_id+' | '+match.path+' | patch line '+match.patch_line));card.appendChild(el('pre',match.context||match.snippet));const rating=state.matches[match.match_id]||{meaning:'',direction:'',evidence:''};
 const update=()=>{state.matches[match.match_id]=rating;state.complete=false;save(state);};
 card.appendChild(select(['operational_instruction','security_guardrail','benign_example_or_documentation','irrelevant_match','uncertain'],rating.meaning,v=>{rating.meaning=v;update();}));
 card.appendChild(select(['authority_expansion_or_risk_encouragement','hardening','no_clear_change','mixed','uncertain'],rating.direction,v=>{rating.direction=v;update();}));
 const notes=el('textarea');notes.placeholder='Evidence and before/after interpretation (optional)';notes.value=rating.evidence;notes.oninput=()=>{rating.evidence=notes.value;update();};card.appendChild(notes);$('forms').appendChild(card);}}
 for(const field of ['evidence','uncertainty']){const box=el('textarea');box.placeholder=field==='evidence'?'Overall evidence (optional)':'Uncertainty or prior exposure (optional)';box.value=state[field];box.oninput=()=>{state[field]=box.value;state.complete=false;save(state);};$('forms').appendChild(box);}
 const finish=el('button','Mark this task reviewed');finish.onclick=()=>{if(data.mode==='security'&&task.matches.some(m=>!state.matches[m.match_id]?.meaning||!state.matches[m.match_id]?.direction)){alert('Complete both classifications for every matched line.');return;}state.complete=true;save(state);};$('forms').appendChild(finish);progress();}
$('rater').onchange=()=>{activeRater=$('rater').value.trim();try{ratings=JSON.parse(localStorage.getItem(key())||'{}');}catch(e){ratings={};}render();};
$('previous').onclick=()=>{pos=Math.max(0,pos-1);render();};$('next').onclick=()=>{pos=Math.min(data.tasks.length-1,pos+1);render();};$('jump').onclick=()=>{pos=Math.max(0,Math.min(data.tasks.length-1,Number($('position').value)-1));render();};
$('export').onclick=()=>{if(!activeRater){alert('Enter rater ID.');return;}const exportData={run_id:data.run_id,mode:data.mode,rater:activeRater,exported_at:new Date().toISOString(),sample_size:data.tasks.length,ratings:Object.values(ratings)};const url=URL.createObjectURL(new Blob([JSON.stringify(exportData,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download=data.mode+'-'+activeRater+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};setupPatchControls();render();
</script></html>'''


def write_form(path, payload):
    encoded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    viewer = (Path(__file__).with_name("patch_view.js")).read_text()
    path.write_text(HTML.replace("PATCH_VIEW_SCRIPT", viewer).replace("PAYLOAD", encoded))


def select_blind_records(records, analyzed_ids, audit_records, bootstrap_records, size, seed):
    """Sample only final instances with no saved audit or bootstrap exposure."""
    if len(set(records.values())) != len(records) or not analyzed_ids <= set(records.values()):
        raise ValueError("Final corpus identities must map uniquely to labeling inputs")
    analyzed = {name for name, identity in records.items() if identity in analyzed_ids}
    audit = analyzed & audit_records
    bootstrap = analyzed & bootstrap_records
    eligible = sorted(analyzed - audit - bootstrap)
    frame = BlindSamplingFrame(candidate_count=len(records), analyzed_count=len(analyzed),
        audit_excluded=len(audit), bootstrap_excluded=len(bootstrap),
        excluded_in_both=len(audit & bootstrap), excluded_union=len(audit | bootstrap),
        eligible_count=len(eligible))
    if size > len(eligible):
        raise ValueError(f"Requested {size} tasks but only {len(eligible)} are eligible")
    return random.Random(seed).sample(eligible, size), frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run_id", required=True)
    args = parser.parse_args()
    out = LEGACY / "data/rebuttal" / args.run_id / "human"
    out.mkdir(parents=True, exist_ok=False)
    settings = Settings.model_validate(yaml.safe_load((LEGACY / "configs/rebuttal.yaml").read_text()))
    candidates = sorted((LEGACY / "data/label/inputs").glob("*.json"))
    corpus_path = LEGACY / "data/analysis/instances.jsonl"
    analyzed_ids = {json.loads(line)["modification_id"] for line in corpus_path.read_text().splitlines() if line}
    audit_files = sorted((LEGACY / "data/audit").glob("*.json"))
    audit_samples = sorted((LEGACY / "data/audit/sample").glob("*.json"))
    bootstrap_files = sorted((LEGACY / "data/label/sample").glob("*.json"))
    if not audit_files or not audit_samples or not bootstrap_files:
        raise ValueError("Saved audit and bootstrap sources are required for exposure exclusion")
    audit_records = {v["record"] for p in audit_files for v in json.loads(p.read_text())["verdicts"]}
    audit_records.update(p.name for p in audit_samples)
    bootstrap_records = {p.name for p in bootstrap_files}
    records = {p.name: json.loads(p.read_text())["modification_id"] for p in candidates}
    chosen_names, frame = select_blind_records(records, analyzed_ids, audit_records,
                                               bootstrap_records, settings.blind_sample_size, settings.seed)
    chosen = [LEGACY / "data/label/inputs" / name for name in chosen_names]
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
    manifest = {"run_id": args.run_id, "seed": settings.seed, "population": frame.eligible_count,
                "frame": frame.model_dump(), "sample_size": len(tasks),
                "selection": "simple random sample without replacement from final instances excluding known audit and bootstrap exposure",
                "inclusion_probability": len(tasks) / frame.eligible_count,
                "audit_overlap": len(set(chosen_names) & audit_records),
                "bootstrap_overlap": len(set(chosen_names) & bootstrap_records),
                "source_sha256": {str(p.relative_to(LEGACY)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [corpus_path, *audit_files, *audit_samples, *bootstrap_files, *candidates]},
                "held_out_status": "not claimed; taxonomy iteration membership is unavailable",
                "mapping": mapping}
    (out / "coordinator_blind_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_form(out / "blind.html", {"run_id": args.run_id, "mode": "blind", "taxonomy": taxonomy, "tasks": tasks})
    matches = {}
    with (LEGACY / "eval/tables-and-figures/rq4-security-matches.csv").open() as stream:
        for match in csv.DictReader(stream):
            key = (match["instance_id"], match["path"], match["patch_line"])
            matches.setdefault(key, []).append(match)
    all_positive_ids = {key[0] for key in matches}
    if not all_positive_ids <= analyzed_ids:
        raise ValueError("Security matches include instances outside the final corpus")
    excluded_ids = {identity for name, identity in records.items() if name in audit_records | bootstrap_records}
    eligible_ids = analyzed_ids - excluded_ids
    matches = {key: values for key, values in matches.items() if key[0] in eligible_ids}
    security_scope = {"original_positive_instances": len(all_positive_ids),
                      "excluded_instances": len(all_positive_ids & excluded_ids),
                      "eligible_positive_instances": len({key[0] for key in matches}),
                      "eligible_matched_lines": len(matches),
                      "audit_overlap": 0, "bootstrap_overlap": 0,
                      "source_sha256": hashlib.sha256((LEGACY / "eval/tables-and-figures/rq4-security-matches.csv").read_bytes()).hexdigest()}
    (out / "security_scope.json").write_text(json.dumps(security_scope, indent=2))
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

Blind annotation applies the fixed taxonomy to the patch. No model labels, predictions or rationale are present in the form. Evidence notes are optional. An empty label set still requires explicit review. Hover or expand each label to read its definition. Note insufficient context rather than guessing. This checks taxonomy application, not independent open coding or exhaustive taxonomy validity.

Security annotation distinguishes textual meaning from change direction. Read the full patch around every line. A security guardrail can match a rule while reducing risk. Examples and quoted commands need context. Use uncertain when the prior state is not observable. The security set includes all detector-positive instances in the eligible frame after the same exposure exclusions; it does not represent all original positives and cannot estimate detector recall or the rate of vulnerabilities among all adaptations.

Both raters must disclose previous exposure to these records or model answers and relevant expertise. Coordinator manifests contain original identities and bootstrap membership; do not send them to raters. The sample is not claimed as held out from taxonomy development because the iteration log is missing. Model-output anchoring is reduced only to the extent that raters have not previously seen those answers.

After both exports, adjudicate disagreements while model outputs remain hidden, save adjudicated evidence, then compare against original predictions. Do not treat missing/incomplete tasks as negative labels or agreements. Return four files: blind-A.json, blind-B.json, security-A.json and security-B.json. No judgments have been prefilled.

Sampling: seed {settings.seed}, simple random sample without replacement, n={len(tasks)}, eligible N={frame.eligible_count} after excluding {frame.excluded_union} known exposed records from {frame.analyzed_count} final instances. The inference scope is the eligible subset, not all candidates. Zero-label exclusion validity is not assessed. Rare-label precision is not guaranteed. Old blind runs are superseded and must not be merged by task ID.
''')
    provenance = {"source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "sample_size": len(tasks), "security_instances": len(security_tasks), "security_lines": len(matches)}
    (out / "preparation.json").write_text(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
