"""Write the rebuttal tracker from completed, explicitly named analysis runs."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOCAL = "legacy/data/rebuttal/local-final-20260923"
PRS = "legacy/data/rebuttal/full-20260923/prs"
HUMAN = "legacy/annotation"


def read_csv(name):
    with (ROOT / LOCAL / name).open() as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def main():
    summary = json.loads((ROOT / LOCAL / "summary.json").read_text())
    scripts = summary["script_baseline"]
    pr = json.loads((ROOT / PRS / "summary.json").read_text())
    security = json.loads((ROOT / LOCAL / "security_baseline/summary.json").read_text())
    prevalence = read_csv("prevalence.csv")
    aggregation = read_csv("aggregation.csv")
    pairs = read_csv("pairs.csv")
    surfaces = read_csv("surfaces.csv")
    intervals = read_csv("family_fork_intervals.csv")
    agreement = read_csv("agreement.csv")
    pct = lambda n, d: f"{100 * n / d:.1f}%" if d else "undefined"
    lines = [f'''# Rebuttal for paper #1322

Updated: 2026-09-23. Current priority: the submitted study under `legacy/`. Deadline: **2026-09-25** (confirmed by the user; exact cutoff time and timezone remain unconfirmed). Automatic analyses below are complete; human annotation and model reruns are not. Scope and methods: [ADR 0033](docs/adr/0033-prioritize-legacy-rebuttal.md), [ADR 0035](docs/adr/0035-two-day-local-rebuttal-analysis.md), [ADR 0038](docs/adr/0038-apply-exposure-exclusions-to-security-audit.md).

**合作者入口：**请两位标注者统一使用[可共享标注包](legacy/annotation/README.md)。该副本进一步遮盖了 token 格式的字符串，保持相同任务编号和抽样成员；无需 Python 或模型登录。根目录 [README TODO](README.md#rebuttal-todo-september-25)记录分工与截止日期。

**版本更新：**两份共享表单使用 `human-unseen-v2-20260923`。旧盲标样本曾重叠 67 条旧人工审计记录和 82 条 taxonomy 样本；旧安全包覆盖全部 209 个阳性。旧版已停用并保留追溯，任何旧导出需单独保存，不可按 B/S 任务编号直接合并到新版。

## 你现在需要做什么

| 优先级 | 你的任务 | 已准备材料与完成标准 |
| --- | --- | --- |
| 立即开始 | 两人分别独立标注同样的 **293 条**，不要先讨论或查看模型答案 | 打开 [blind.html]({HUMAN}/blind.html)，分别输入 A/B；显式完成每条后定期导出 `blind-A.json`、`blind-B.json`。从最终 1,126 条中排除 488 条旧人工审计或已知 taxonomy 样本，再从剩余 638 条抽取 293 条；与已知旧样本重叠为 0，不含 94 条零标签排除记录。 |
| 同期进行 | 两人独立审计 **109 个安全命中实例、642 条不同命中行** | 打开 [security.html]({HUMAN}/security.html)，逐行区分文本含义和风险变化方向；导出 `security-A.json`、`security-B.json`。这是相同排除规则下剩余阳性实例的全量审计，不代表原始全部 209 个阳性；不要只读关键字。 |
| 标注结束后 | 先保存独立结果，再协调分歧；此时仍不看模型答案 | 保留原始两份结果和协调后的证据。把四份 JSON 交回后，可继续计算 agreement、precision/recall 和安全类别分布。未完成任务不能当作无标签或无风险。 |
| 必须披露 | 两位标注者的背景、是否看过旧标签/答案/样本 | 新版盲标和安全审计均排除了已知旧人工审计及 taxonomy bootstrap 样本，但迭代成员记录缺失，仍不能声称严格 held-out。若同一作者曾见过模型答案，需要披露记忆与暴露风险。 |
| 今天确认 | **截止日期已确定为 9 月 25 日**；补充具体截止时刻、时区、字数限制，以及能否提交新增实验/外部链接 | 不默认按伦敦时间或 AoE 计算；当前英文草稿未按会议字数压缩。 |
| 有条件再做 | 提供可用的模型登录/运行环境，并确定重跑配置和费用上限 | 本机有 Claude CLI，但 `claude auth status --json` 返回 `loggedIn: false`、`authMethod: none`。不要在聊天或文档中粘贴密钥；在本机配置即可。 |
| 稿件检查 | 恢复或确认参考文献来源 | 当前 `paper/skills.bib` 原本为 **0 字节**；已从论文 Git HEAD 恢复[候选副本](legacy/data/rebuttal/manuscript-20260923/skills.recovered-from-HEAD.bib)，覆盖全部 39 个引用键，并在隔离副本中完成编译。请确认能否采用该来源；本次未覆盖你现有的空文件。 |

**293 条的含义：**对剩余 N=638 的有限总体，在简单随机抽样及最保守 p=0.5 下，对一个总体二元比例给出约 95% 置信水平、约 ±4.2 个百分点的抽样精度；这仅适用于剩余 638 条中的一个二元比例，不是全部 1,126 条的保证，也不是每个标签 precision/recall 的精度保证。两个人各标同样的 293 条，样本量仍为 293。两天内若无法全部完成，须报告未完成量和选择机制，不能悄悄更换样本或依据结果停止。[抽样决策](docs/adr/0038-apply-exposure-exclusions-to-security-audit.md)

**执行顺序：**盲标 patch 中位长度为 181 行，62 条超过 1,000 行，最大 18,344 行；请立即计时完成前几条，判断人力是否够用。安全页面已显示每条命中的前后 8 行及标记，完整 patch 保留在左侧，需按语义补查上下文。**9 月 23 日：**开始独立盲标和安全审计，并确认会议规则及模型环境。**9 月 24 日：**争取完成独立标注，先导出原始结果，再协调分歧并计算指标。**9 月 25 日：**优先完成结果核对、英文压缩和提交，预留缓冲；不要把新的大实验留到截止当天。具体日程需以确认后的截止时刻和时区为准。下面的自动分析已完成，不需要你手工复算。[人工操作说明]({HUMAN}/README.md)

## 已经直接完成的工作

| 工作 | 完成情况 | 证据 |
| --- | --- | --- |
| RQ1/RQ2/RQ3 仓库敏感性 | 六仓库分别分析、全部六轮逐仓库排除、46 patterns/13 families、文件类型及全部 family pairs | [prevalence]({LOCAL}/prevalence.csv)、[surfaces]({LOCAL}/surfaces.csv)、[pairs]({LOCAL}/pairs.csv) |
| 分支聚合与子集分析 | 单 family、单 skill、单保留提交、两条件同时满足的敏感性分析 | [aggregation]({LOCAL}/aggregation.csv) |
| fork 聚类不确定性 | 固定六个仓库，在仓库内按 fork 重采样，2,000 次、seed 42；仅给 family prevalence 条件区间 | [intervals]({LOCAL}/family_fork_intervals.csv) |
| 上游 scripts 基线 | 冻结索引中的全部 1,106 packages、历史 baseline trees、已有脚本条件修改率和缺失路径清单 | [packages]({LOCAL}/upstream_script_packages.csv)、[opportunities]({LOCAL}/script_opportunities.csv)、[unmapped]({LOCAL}/script_baseline_unmapped.csv) |
| PR 查询 | 成功读取六仓库的全部可分页 PR 列表，按各原实例采集时间过滤创建/合并时间；区分同名分支候选与 exact head | [PR summary]({PRS}/summary.json)、[associations]({PRS}/associations.csv) |
| agreement 核算 | 明确 κ/α 聚合，验证 α 有限样本修正，补 exact-set agreement 和逐标签质量表 | [agreement]({LOCAL}/agreement.csv)、[per-label]({LOCAL}/agreement_per_label.csv) |
| 原始标签与人工替换的敏感性 | 在相同 1,126 实例上比较 raw model 与 final labels；额外给 1,220 候选计数 | [consensus sensitivity]({LOCAL}/consensus_sensitivity.csv) |
| 安全扫描核对 | 按规则和仓库汇总；读取上游同一文件，检查同规则是否已出现 | [rules]({LOCAL}/security_by_rule.csv)、[repositories]({LOCAL}/security_by_repository.csv)、[baseline]({LOCAL}/security_baseline/summary.json) |
| 人工材料 | 293 条固定随机盲标表单、109 个安全实例表单、隐藏答案、独立导出、操作说明 | [human materials]({HUMAN}/README.md) |
| 论文措辞修订 | 已修改 abstract、intro、RQ1-RQ4 answer boxes、agreement 解释、threats、conclusion，补 Table II 1,126、区分 fork/instance、移除 RADAR 段落 | [main.tex](paper/main.tex)、[本次修改 diff](legacy/data/rebuttal/manuscript-20260923/main.patch) |

## 当前做不了、两天内不应承诺的内容

| 项目 | 实际限制 | Rebuttal 应如何处理 |
| --- | --- | --- |
| 用 AI 代替独立人工验证 | 无法回答评审对 anchoring 和人类独立判断的要求 | 等待两位研究者真实结果；不捏造 precision、recall 或安全 TP。 |
| 严格 held-out taxonomy 验证 | 已知 audit/bootstrap 重合为 0，但后续迭代日志缺失 | 称 independent annotation with model outputs hidden；不能称完整 held-out 或独立 taxonomy 推导。 |
| 原模型的精确复现 | 历史 snapshot/temperature 未完整记录；当前 CLI 未登录 | 可在配置明确后做新配置下的两次运行，但不能声称恢复了原随机过程。目前未执行任何模型重跑。 |
| 完整同一 skill、同一 commit 的验证 | 本地 1,126 个 frozen downstream heads 全部不可用；完整恢复和重新标注尚未完成 | 已做单 skill/单保留提交子集分析，但明确它不等价于原子单位。网络可能支持后续恢复，不能说永远无法做。 |
| 完整安全风险前后对照 | 没有完整 downstream package endpoints，正则也不能判断风险方向 | 已完成上游同文件背景检查；不称其为完整 paired package baseline，不推断风险上升。 |
| 全面消除 repository/skill/developer 聚类 | 已完成 fork 内重复观察敏感性，但共享 skill 和跨仓库开发者相关性仍在 | 明确区间以六个固定仓库为条件，不推广为生态总体区间。 |
| 完整 ever-proposed/merged 比例 | 当前 PR 元数据存在分支复用、删除 head 或历史重写问题 | 报告确定 head 匹配数和候选分支关联数，未找到证据仍属 unresolved。 |
| 漏检率、漏洞可利用性、未修改采用率和 RADAR 效果 | 现有研究没有相应真值、采用分母或行为实验 | 删除或收缩这些主张；阳性审计不能提供 detector recall；两天内不新增这些大实验。 |

## Completed results and interpretation

### Corpus and aggregation

The analyzed corpus contains 1,126 instances from 1,220 candidates, with 94 records excluded after receiving no final labels. Exactly 494/1,126 instances (43.9%) contain one family and 632 (56.1%) contain multiple families. There are 945 distinct upstream/fork-owner identities. Multiple skills occur in 666 instances (59.1%) and multiple retained commits in 667 (59.2%). Commit lists were cleaned, so these are not complete-history commit counts. These results require descriptive co-occurrence language, not a claim of coordinated adaptation. [Evidence]({LOCAL}/aggregation.csv)

### Repository sensitivity and RQ2
''']
    families = ["lifecycle", "procedure", "decision", "policy", "script", "resource", "retarget"]
    comparison = []
    for family in families:
        cells = []
        for group in ["all", "exclude:obra/superpowers"]:
            row = next(r for r in prevalence if r['group'] == group and r['level'] == 'family' and r['label'] == family)
            cells.append(f"{row['count']}/{row['n']} ({100*float(row['prevalence']):.1f}%)")
        comparison.append([family, *cells])
    lines.append(table(["Family", "All instances", "Without obra"], comparison))
    lines.append(f'''

Removing any of the other five repositories preserves the original leading four-family set, although order can change. Removing obra changes that set to lifecycle, script, resource and retarget. SKILL.md modification falls from 898/1,126 (79.8%) to 262/432 (60.6%), while script-surface modification rises from 262/1,126 (23.3%) to 166/432 (38.4%). SKILL.md remains more frequently modified, but the magnitude and family ranking depend strongly on corpus composition. [Per-repository and exclusion tables]({LOCAL}/prevalence.csv), [RQ2 surfaces]({LOCAL}/surfaces.csv)

### Aggregation sensitivity

The following subsets reduce observed aggregation without relabeling patches. They are selected subpopulations, and a single retained commit does not establish that the original branch had only one commit. Interpret their differences as sensitivity, not proof of atomic causality. [Subset pairs]({LOCAL}/pairs.csv)
''')
    pairtable = []
    for group in ["all", "exclude:obra/superpowers", "single_skill", "single_retained_commit", "single_skill_and_retained_commit"]:
        selected = [r for r in pairs if r['group'] == group]
        cells = []
        for first, second in [("procedure", "decision"), ("procedure", "policy"), ("decision", "policy")]:
            row = next(r for r in selected if {r['family_a'], r['family_b']} == {first, second})
            cells.append(f"{row['count']} / {float(row['lift']):.2f}")
        pairtable.append([group, selected[0]['n'], *cells])
    lines.append(table(["Subset", "N", "Procedure + decision: count / lift", "Procedure + policy", "Decision + policy"], pairtable))
    lines.append(f'''

For the 253 instances with one mapped skill and one retained commit, the three highlighted pairs have only 10, 8 and 4 supporting instances. Positive lift alone is insufficient evidence of broad coupling. The matching local downstream Git objects are unavailable for all 1,126 heads; full atomic validation remains incomplete. [History availability]({LOCAL}/history_availability.csv)

### Conditional fork-cluster intervals

The supplementary bootstrap resamples whole forks within each of the six fixed repositories, retaining all branches of each sampled fork (2,000 repetitions; seed 42; percentile 95% intervals). This checks sensitivity to repeated observations within forks. It does not resolve shared skills, cross-repository authors or selection of only six upstreams, and supplies no pairwise lift intervals. [Full interval table]({LOCAL}/family_fork_intervals.csv)
''')
    lines.append(table(["Family", "Prevalence", "Conditional 95% interval"], [[r['family'], f"{float(r['prevalence'])*100:.1f}%", f"{float(r['lower_95'])*100:.1f}% to {float(r['upper_95'])*100:.1f}%"] for r in intervals if r['family'] in families]))
    lines.append(f'''

### Script availability and conditional modification

At the saved index revisions, **30/1,106 packages ({pct(30,1106)})** contain script surfaces under the existing RQ2 classifier. An alternative check using recognized script filename suffixes finds **37/1,106 ({pct(37,1106)})**. These are operational definitions of file availability, not execution traces or ecosystem estimates. Package composition is very unequal: Composio contributes 864 indexed packages. [Package inventory]({LOCAL}/upstream_script_packages.csv)
''')
    lines.append(table(["Repository", "Indexed packages", "With script surfaces", "Historical eligible opportunities", "Changed existing scripts"], [[r[k] for k in ['upstream','indexed_packages','indexed_with_scripts','eligible_opportunities','changed_existing_scripts']] for r in read_csv('script_summary_by_repository.csv')]))
    lines.append(f'''

Historical baseline trees yield **{scripts['branch_skill_opportunities']:,} branch-skill opportunities**, of which **1,384 contain scripts** and **303/1,384 ({pct(303,1384)}) modify a baseline script**; 79 opportunities add a script. There are 1,903 distinct observed package versions, including 343 with scripts. At least one package maps for 1,120/1,126 instances; **369 changed paths across nine instances lack a matching baseline skill root**, and six instances have no mapped opportunity. These exclusions are explicit, so the conditional rate concerns available mapped opportunities, not all modifications. [Opportunities]({LOCAL}/script_opportunities.csv), [unmapped paths]({LOCAL}/script_baseline_unmapped.csv)

### Pull requests

All six upstream PR listing queries succeeded. Applying each instance's original collection timestamp on 2026-04-28 to PR creation and merge times identifies **296/1,126 ({pct(296,1126)}) candidate branch associations**, including **263/1,126 ({pct(263,1126)}) with an exact saved head SHA**. Of these exact-head matches, **20/1,126 ({pct(20,1126)}) have merge evidence before collection**; the broader branch-name matching gives 23. Current PR metadata cannot establish every historical branch state, and branch-name reuse can make the 296 associations ambiguous. Report 263 as directly matched head evidence, not an exhaustive ever-proposed rate; absent evidence is unresolved. [Summary]({PRS}/summary.json), [instance associations]({PRS}/associations.csv), [query coverage]({PRS}/coverage.csv)

### Security scan and upstream file context

The scan has 209 positive instances, 1,562 rule matches and 1,521 distinct added lines. Security-positive prevalence differs by repository and increases to **150/432 (34.7%)** when obra is excluded; this remains regex prevalence, not risk. Rule-specific support is exported with human precision deliberately blank. [Repository counts]({LOCAL}/security_by_repository.csv), [rule counts]({LOCAL}/security_by_rule.csv)

For **767/1,562 matches**, the corresponding baseline file is available. In **496/767 ({pct(496,767)})**, that same rule already matches somewhere in the baseline file, covering **91/209 ({pct(91,209)}) positive instances**. The other 795 matches concern added files without baseline content. This demonstrates why an added-line match is not necessarily the introduction of a new security category, but it does not identify identical instructions, hardening or risk expansion. It is a matched-file context check, not a paired full-package prevalence comparison. Human validation remains necessary. [Baseline evidence]({LOCAL}/security_baseline/matches.csv)

### Agreement and label provenance

Cohen's kappa is the unweighted mean of per-label binary scores over observed labels; alpha pools record-label decisions. The nominal alpha calculation uses finite-rating expected disagreement `2*n_positive*n_negative / (N_ratings*(N_ratings-1))`; zero expected disagreement is undefined. The correction changes neither main Table III alpha at four decimals. Exact-set agreement is informative despite different editing conventions because final label sets can be compared directly. These remain visible-model audits, not an independent gold standard. [Implementation](legacy/eval/rebuttal/main.py), [Krippendorff's reference material](https://www.asc.upenn.edu/krippendorffs-alpha-reliability)
''')
    lines.append(table(["Comparison", "N", "Observed labels", "Macro kappa", "Corrected alpha", "Exact-set agreement"], [[r['comparison'],r['records'],r['observed_labels'],f"{float(r['macro_label_kappa']):.4f}",f"{float(r['alpha_finite']):.4f}",f"{float(r['exact_set_agreement'])*100:.1f}%"] for r in agreement]))
    lines.append(f'''

On the same 1,126 instances, replacing final labels with original model predictions preserves the leading four-family set; the largest family prevalence difference is **14/1,126 = 1.24 percentage points** (spec). This checks consensus replacement, not independent accuracy or repeated-run stability. The 1,220-candidate counts are provided separately to expose denominator changes. [Sensitivity table]({LOCAL}/consensus_sensitivity.csv)

## Manuscript changes and remaining limits

The manuscript now replaces unsupported reuse, control-plane, dependency and security claims with descriptive language. Table II includes 1,126, terminology distinguishes 945 forks from 1,126 instances, agreement aggregation is explicit, anchoring is not dismissed, and RADAR is removed. Original and revised text plus the exact diff are preserved. Supplementary numerical evidence above is in this rebuttal tracker and its data files; it has not all been inserted into the manuscript body. [Manuscript](paper/main.tex), [change diff](legacy/data/rebuttal/manuscript-20260923/main.patch)

The current working tree has a pre-existing empty `paper/skills.bib`, which blocks its unmodified build. A candidate bibliography recovered from the paper repository HEAD contains 69 entries and covers all 39 cited keys. The revised manuscript compiles successfully to 11 pages in an isolated copy using that recovered bibliography, with no unresolved citations. The working bibliography was not overwritten. Confirm this source and venue page limits before treating the manuscript as ready. [Recovered bibliography](legacy/data/rebuttal/manuscript-20260923/skills.recovered-from-HEAD.bib), [build validation](legacy/data/rebuttal/manuscript-20260923/build-validation.json)

## English response draft

This draft contains completed numerical evidence and explicitly marks missing human and model results. It must be shortened to the venue limit after the missing results arrive. The manuscript edits are local revisions, not a claim that an updated submission has been uploaded.

### A: Unit of analysis and agreement

We agree that a branch snapshot may aggregate independent edits. Of 1,126 instances, 666 (59.1%) touch multiple skill directories, and 667 (59.2%) contain multiple retained commits. Exactly 494 (43.9%) contain one family. We have replaced “rarely involve a single family” and restricted the interpretation to observed co-occurrence. In the subset with one skill and one retained commit (n=253), procedure-decision, procedure-policy and decision-policy co-occur in 10, 8 and 4 instances, with lifts of 2.13, 1.35 and 1.10. This is a subset sensitivity check, not same-commit relabeling: the commit lists were filtered and full downstream histories have not been recovered. We therefore do not claim coordinated or interdependent adaptation.

We clarified that kappa is averaged over per-label binary decisions, whereas alpha pools record-label decisions. Both main comparisons contain 46 observed labels. Finite-rating correction leaves the reported main alpha values unchanged at four decimals (0.8722 and 0.8767). Exact-set agreement between auditors is 56.0%. These statistics characterize the existing visible-model audit rather than an unbiased reference set.

### A/C: Repository sensitivity

We completed all six repository exclusions and repository-specific RQ1-RQ3 tables. Removing obra changes the leading families to lifecycle, script, resource and retarget; procedure, decision and policy prevalence decrease from 40.8%, 25.3% and 23.9% to 9.0%, 6.0% and 6.9%. We therefore report repository heterogeneity rather than universal ranking stability. SKILL.md remains more frequently modified outside obra (60.6%, versus 38.4% for scripts). Fork-cluster bootstrap intervals conditional on the six repositories are 37.7-44.2% for lifecycle and 37.8-43.9% for procedure. This accounts for repeated branches within forks but does not fully resolve dependence across shared skills or repository selection.

### A/B/C: Security validation

The 18.6% figure means 209/1,126 instances with regex matches in added text, not confirmed vulnerabilities. There are 1,562 rule matches on 1,521 distinct added lines. In 496 of the 767 matches whose baseline file exists, the same rule already matches that file; this covers 91 positive instances. This context check is not a complete paired package comparison and does not determine risk direction. We have removed claims of malicious injection, expanded authority and bypass of code review. Applying the same exposure exclusions leaves 109 of the 209 positive instances and 642 matched lines for independent assessment. Human outcomes will describe this eligible subset only. Independent human assessment remains pending: **[insert completed audit size, textual categories, risk direction, rule-level precision, agreement and uncertainty]**. No security precision or risk rate is claimed before that assessment.

### B/C: Independent labels and repeatability

We agree that correction of model-proposed labels does not remove anchoring. We restricted validation to the 1,126 analyzed instances and excluded 488 with known prior audit or taxonomy bootstrap exposure. We drew 293 records without replacement from the remaining 638 (seed 42) for two independent raters; predictions and rationales are hidden. The 94 candidates with no final labels are outside this validation frame. Human results are pending: **[insert independent agreement, adjudication, per-label precision/recall and support, annotator exposure]**. Known audit and bootstrap overlap is zero, but later iteration membership is unavailable, so strict held-out status is not claimed. Validation estimates apply to the 638 eligible instances, not the full corpus; exclusion of zero-label candidates is not validated. It validates application of the fixed taxonomy, not its exhaustive coverage. Separate model reruns have not been completed; the original snapshot is not fully recorded and the current runtime is unauthenticated. We will not substitute consistency with consensus for repeated-run stability.

### B: Scripts, PRs and single-family instances

Using the saved upstream index and the existing script-surface definition, 30/1,106 packages (2.7%) contain scripts; a filename-suffix definition gives 37/1,106 (3.3%). Historical baseline trees provide 1,384 branch-skill opportunities with scripts, of which 303 (21.9%) modify existing scripts. Nine instances have partially or wholly unmapped baseline paths, which are excluded and reported. These denominators differ from pooled branch modification rates. We have removed the “absolute control plane” and code-demotion claims.

PR metadata gives 263/1,126 instances (23.4%) with an exact saved head SHA in a PR created before the original observation time, including 20 (1.8%) merged by then. Broader branch-name matching yields 296 candidate associations, but branch reuse and deleted head metadata limit historical completeness. Missing evidence is not proof that a branch was never proposed. Finally, exactly 43.9% of analyzed instances contain one family, which replaces the original inaccurate wording.

### A/B/C: Scope and contributions

We removed “reuse paradox” and abstraction failure as established findings, made the taxonomy explicitly empirical and corpus-bounded, and removed RADAR. Our sample characterizes selected modifications and cannot estimate unchanged adoption, identify why a change was necessary, or demonstrate improved outcomes. Table II now includes 1,126, and the manuscript consistently distinguishes branch instances from forks. Independent annotation and security judgments will be reported only after they have been completed.

## Reproduction and verification

Run commands from the project root with Python 3.12 and the locked root environment. Use a new run ID to preserve completed evidence. The legacy analysis modules are reused without upgrading legacy dependencies.

```bash
uv run --locked python -m unittest discover -s legacy/tests -p test_rebuttal.py -v
uv run --locked python legacy/eval/rebuttal/main.py --run_id NEW_LOCAL_RUN
uv run --locked python legacy/eval/rebuttal/security_baseline.py --run_id NEW_LOCAL_RUN
uv run --locked python legacy/eval/rebuttal/prs.py --run_id NEW_PR_RUN
uv run --locked python legacy/eval/rebuttal/audit_materials.py --run_id NEW_HUMAN_RUN
```

For offline PR recomputation, use the existing PR run ID with `--offline`; it reads saved listings rather than querying GitHub. The local analysis completed a 20-instance pilot and the full corpus. Seven behavioral tests cover alpha's finite-rating correction, undefined constant ratings, root boundaries, preservation of multiple branches within a fork, and blind-sample exclusions and identity integrity. Both form scripts pass JavaScript syntax checking; payload checks verify 293 blind tasks with no model predictions and 109 security tasks. Forms have not been tested in a browser automation environment. Full source hashes, settings, lockfile hash and analysis source snapshots are in [run.json]({LOCAL}/run.json) and [source]({LOCAL}/source/); unavailable root Git metadata is explicitly recorded. Original inputs and published tables were retained.

## Submission gate

- [x] Automatic descriptive analyses, script baseline, PR metadata and agreement checks completed.
- [x] 293 common blind tasks and security forms prepared for two raters.
- [x] Unsupported manuscript claims corrected locally.
- [ ] Independent human ratings, adjudication and final quality metrics completed.
- [ ] Model reruns completed, or their absence stated candidly.
- [ ] Venue rules, word limit, bibliography and final manuscript build checked.
- [ ] Bracketed fields replaced with observed results or explicit limitations.
- [ ] Response reviewed for denominators, historical coverage and no claims of unperformed work.
''')
    (ROOT / "Rebuttal.md").write_text("\n\n".join(lines))


if __name__ == "__main__":
    main()
