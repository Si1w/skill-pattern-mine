"""Apply supported claim corrections and preserve the submitted text and diff."""

import difflib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "paper/main.tex"
OUT = ROOT / "legacy/data/rebuttal/manuscript-20260923"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    original = PATH.read_text()
    (OUT / "main.before.tex").write_text(original)
    text = original
    def replace(old, new):
        nonlocal text
        if old not in text:
            raise ValueError("Missing manuscript anchor: " + old[:80])
        text = text.replace(old, new, 1)
    replace(text[text.index("Our key findings reveal a reuse paradox:"):text.index("% Commit messages mostly state")],
        "Our findings characterize modifications to discovery metadata, behavioral instructions, and tool or language targets within the selected downstream branches. Multiple adaptation families occur in 56.1\\% of instances, but co-occurrence within a branch does not establish dependency between edits. Added text matches security-related detection rules in 18.6\\% of instances; these matches identify content for contextual review rather than confirmed vulnerabilities.\n")
    start = text.index("Our analysis exposes a fundamental mismatch")
    end = text.index("% This systematic interdependence", start)
    replace(text[start:end], "Our analysis describes how selected downstream branches modify published skills, including metadata, procedures, constraints, and tool or language targets. Procedure, decision, and policy labels frequently co-occur in the pooled corpus, although this pattern depends on repository composition and branch aggregation. Added text triggers security-related rules in 209 of 1,126 adaptation instances (18.6\\%), which does not establish malicious intent, exploitability, or bypass of code review. Commit messages describe functional outcomes more often than the customization rationale represented by the patch-derived labels.\n\n")
    replace("We also release RADAR, a simple, lightweight, implication-driven review checklist that helps developers assess skill adaptations across different aspects.", "The released materials support inspection and replication of the descriptive analyses; proposed tooling implications have not been evaluated for effectiveness.")
    for rq, new in {
        "RQ1": "We identify 46 adaptation patterns in 13 families. Lifecycle (40.9\\%) and procedure (40.8\\%) are the most prevalent families in the pooled corpus, followed by decision and policy. These rankings describe the selected modified branches and depend on repository composition; they do not establish that skills generally require modification for reuse.",
        "RQ2": "SKILL.md is modified in 898 of 1,126 instances (79.8\\%), while script surfaces are modified in 262 (23.3\\%). These frequencies describe observed changes, not the relative execution importance of documentation and code. Script availability differs across upstream packages and must be considered when interpreting the comparison.",
        "RQ3": "Exactly 494 of 1,126 instances (43.9\\%) contain one adaptation family and 632 (56.1\\%) contain multiple families. Procedure, decision, and policy frequently co-occur in the pooled branch corpus. A branch can aggregate different commits and skills, so these observations do not establish coordinated editing, technical dependency, or required propagation of changes.",
        "RQ4": "Added text matches security-related rules in 209 of 1,126 instances (18.6\\%). Most matches occur in SKILL.md or bundled documentation. These are indicators for contextual review: the scan does not distinguish risky instructions, benign examples, and security guardrails, nor does it establish an increase in risk relative to upstream content."
    }.items():
        pattern = r"\\begin\{rqanswer\}\{" + rq + r"\}.*?\\end\{rqanswer\}"
        text, count = re.subn(pattern, lambda match: "\\begin{rqanswer}{" + rq + "}\n" + new + "\n\\end{rqanswer}", text, count=1, flags=re.S)
        if count != 1:
            raise ValueError("Missing RQ answer: " + rq)
    replace("    Deduplicate redundant branches & branch comparisons & 1,220 \\\\",
            "    Deduplicate redundant branches & branch comparisons & 1,220 \\\\\n    Retain nonempty final label sets & analyzed instances & 1,126 \\\\")
    anchor = "For each selected repository, we enumerated all public forks through the"
    replace(anchor, "A repository is an upstream project, a fork is a downstream repository, and a branch is a named line of history within a fork. A record is a pipeline artifact; an analyzed adaptation instance is a retained branch comparison with a nonempty final label set. The 1,126 analyzed instances correspond to 945 distinct upstream and fork-owner identities, so instance and fork counts are not interchangeable.\n\n" + anchor)
    replace("$\\alpha$~\\cite{krippendorff2004reliability}, each computed per label as\nbinary present/absent decisions. Table~\\ref{tab:validation-metrics} reports\nboth comparisons.",
            "$\\alpha$~\\cite{krippendorff2004reliability}, using binary present/absent decisions. Cohen's $\\kappa$ is calculated separately for each observed label and then averaged without label weights. Alpha pools all record-label decisions and uses the finite population correction for expected disagreement. Both comparisons in Table~\\ref{tab:validation-metrics} include 46 observed labels. These metrics quantify agreement in a visible-model audit, not accuracy against an independent reference.")
    replace("The validation results confirm both the reliability of the human consensus\nand the quality of the agent labels.", "The validation results describe agreement during correction of model-proposed labels; they do not establish unbiased labeling accuracy.")
    start = text.index("\\subsection{Implications for Downstream Skill Developers and the RADAR Checklist}")
    end = text.index("\\section{Threats to Validity}", start)
    text = text[:start] + text[end:]
    replace("This section discusses the implications of our findings to different stakeholders, as well as a simple RADAR checklist we provide to help downstream skill developers.", "This section discusses possible implications for researchers and engineers. Their effectiveness remains to be evaluated.")
    start = text.index("free-text edits. RQ3's two coupling patterns")
    end = text.index("\\paragraph{Make the automation and security tradeoff explicit.}", start)
    text = text[:start] + "free-text edits. The observed co-occurrences identify candidate cases for studying consistency checking, but do not demonstrate that edits must propagate across families. Future work should evaluate whether such tooling improves adaptation outcomes.\n\n" + text[end:]
    replace("consensus-vs-agent agreement. The reconciliation record indicates this\ndid not dominate, as auditors independently added labels the agent had\nomitted, a pattern inconsistent with simply accepting the agent output;\nwe therefore treat inter-auditor agreement as the primary reliability\nestimate.", "consensus-vs-agent agreement. Corrections to proposed labels do not exclude anchoring or missed-label bias. Independent annotation with model outputs hidden is needed to assess these effects; the existing agreement statistics do not replace that validation.")
    anchor = "\\paragraph{Conclusion Validity.}"
    replace(anchor, "Removing obra/superpowers changes the leading families to lifecycle, script, resource, and retarget. Repository adjustment therefore does not establish a stable ecosystem-wide ranking. Instance-level intervals may understate uncertainty where branches share forks or skills, and branch co-occurrence does not establish atomic coordination. The corpus contains modified branches and provides no denominator for unchanged adoption.\n\n" + anchor)
    start = text.index("We present the first empirical study", text.index("\\section{Conclusion}"))
    end = text.index("\\section{Data Availability}", start)
    text = text[:start] + "We present an empirical study of 1,126 downstream branch adaptation instances from six public skill repositories and a taxonomy of 46 patterns in 13 families. The findings describe modifications to discovery metadata, behavioral instructions, and tool or language targets within the selected corpus. SKILL.md is frequently modified, and multiple families occur in 56.1\\% of instances, but prevalence depends on repository composition and branch aggregation. Added text triggers security-related rules in 18.6\\% of instances; these matches require contextual validation and do not establish vulnerabilities or increased authority. The corpus and analysis materials support further study of downstream adaptation, while independent annotation, behavioral outcomes, and unchanged adoption remain outside the evidence established here.\n\n" + text[end:]
    PATH.write_text(text)
    (OUT / "main.after.tex").write_text(text)
    (OUT / "main.patch").write_text("".join(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile="paper/main.tex.before", tofile="paper/main.tex")))


if __name__ == "__main__":
    main()
