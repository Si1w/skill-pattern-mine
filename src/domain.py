"""Domain models for the study of skill modifications.

Domain concepts and aggregation semantics follow the ADRs under docs/adr/. Models are
plain data containers; pipeline stages read and write them as JSONL. No
behaviour lives here.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field


# --- Enumerations ---------------------------------------------------------


class RetrievalChannel(StrEnum):
    """A retrieval channel that surfaced a repository (ADR 0002)."""

    INTENT = "intent"  # repository search on topics and description keywords
    MANIFEST = "manifest"  # plugin or marketplace manifest, or registry pointer


class ExclusionReason(StrEnum):
    """Why a candidate repository left the pool; one value per filtering step (ADR 0002)."""

    FORK_THRESHOLD = "fork_threshold"
    NOT_SKILL_CENTRIC = "not_skill_centric"
    AGGREGATOR = "aggregator"
    MANUAL = "manual"


class ChangeStatus(StrEnum):
    """Git file status inside a commit."""

    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class MatchSide(StrEnum):
    """Whether a security rule matched an added or a deleted line (ADR 0007)."""

    ADDED = "added"
    DELETED = "deleted"


class Confidence(StrEnum):
    """Annotator confidence for one pattern label (ADR 0006)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DiffSufficiency(StrEnum):
    """Whether the diff shown to the annotator was complete (ADR 0006)."""

    SUFFICIENT = "sufficient"
    TRUNCATED = "truncated"
    EMPTY = "empty"


class NetChangeStatus(StrEnum):
    """Outcome of a complete monthly endpoint comparison (ADR 0013)."""

    CHANGED = "changed"
    NO_NET_CHANGE = "no_net_change"


class SecurityDirection(StrEnum):
    """Annotator judgement of one security rule match (ADR 0007)."""

    HARDENING = "hardening"
    RELAXATION = "relaxation"
    NEUTRAL = "neutral"
    FALSE_POSITIVE = "false_positive"


class ReferenceKind(StrEnum):
    """Class of a timeline reference line (ADR 0010)."""

    MODEL_RELEASE = "model_release"
    SPEC_MILESTONE = "spec_milestone"
    HARNESS_RELEASE = "harness_release"


# --- Corpus construction (ADR 0002) ---------------------------------------


class TreeEntry(BaseModel):
    """GitHub tree fields needed for screening based on tracked files (ADR 0017)."""

    path: str
    type: Literal["blob", "tree", "commit"]
    mode: str
    sha: str | None = None


class SkillCentricity(BaseModel):
    """Screening counts from a complete frozen tree, before thresholding."""

    tracked_files: int = Field(ge=0)
    skill_files: int = Field(ge=0)
    package_paths: list[str]
    ratio: float | None = Field(ge=0, le=1, description="Undefined for an empty tree.")


class Repository(BaseModel):
    """One candidate upstream repository and the outcome of every filtering step.

    A repository is retained only when screening_complete is true and
    excluded_by is None. Preserve excluded candidates for filtering counts.
    """

    full_name: str = Field(description="GitHub owner/name.")
    channels: list[RetrievalChannel] = Field(
        min_length=1,
        description="All channels that surfaced the repository; preserve overlap.",
    )
    retrieved_at: datetime = Field(
        description="Snapshot time of the search that surfaced it."
    )
    forks_count: int = Field(
        description="GitHub metadata fork count at retrieval; hard threshold input."
    )
    stars_count: int = Field(description="Recorded for description only; not a filter.")
    skill_package_paths: list[str] = Field(
        description="Directories on the default branch that contain a SKILL.md."
    )
    skill_centricity: SkillCentricity | None = Field(
        default=None,
        description="Counts from the complete tree and ratio under ADR 0017; None until measured.",
    )
    screening_complete: bool = Field(default=False)
    aggregator_keyword_hit: bool = Field(
        default=False,
        description="Name, description or topic matched an aggregator keyword.",
    )
    excluded_by: ExclusionReason | None = Field(
        default=None,
        description="First filtering step that removed the repository, or None if retained.",
    )
    exclusion_note: str | None = Field(
        default=None, description="Written reason; required when excluded_by is MANUAL."
    )


class Fork(BaseModel):
    """One public fork with its default branch frozen at retrieval (ADR 0014)."""

    upstream: str = Field(description="Upstream full_name.")
    full_name: str = Field(description="Fork owner/name.")
    owner: str = Field(description="Fork owner login; pseudonymised at release time.")
    created_at: datetime
    pushed_at: datetime
    retrieved_at: datetime
    default_branch: str
    default_branch_sha: str = Field(
        description="Frozen default branch head; mining must not follow a moving ref."
    )


class RetrievalEvidence(BaseModel):
    """One observed route from a discovery query or registry to a repository."""

    channel: RetrievalChannel
    source: str
    path: str | None = None


class RepositorySnapshot(BaseModel):
    """Repository screening with immutable references and discovery evidence."""

    repository: Repository
    github_id: int
    default_branch: str
    default_branch_sha: str | None = None
    tree_sha: str | None = None
    tree_complete: bool = False
    evidence: list[RetrievalEvidence]


class SourceCommit(BaseModel):
    """Commit metadata from GitHub, before origin classification."""

    sha: str
    tree_sha: str
    parent_shas: list[str]
    author_date: AwareDatetime
    committer_date: AwareDatetime
    message: str
    author_login: str | None = None


class ForkComparison(BaseModel):
    """Divergence against a frozen upstream; not a monthly analytical unit."""

    fork: Fork
    github_id: int
    upstream_sha: str
    merge_base_sha: str
    status: Literal["identical", "ahead", "behind", "diverged"]
    ahead_by: int = Field(ge=0)
    behind_by: int = Field(ge=0)
    commits: list[SourceCommit]
    commits_complete: bool
    reused_from: str | None = Field(
        default=None, description="Fork whose complete comparison supplies this identical SHA pair."
    )


class ForkSkip(BaseModel):
    """An unavailable fork omitted from acquisition under ADR 0031."""

    upstream: str
    github_id: int
    full_name: str
    stage: Literal["fork_reconciliation", "fork_metadata", "fork_branch", "fork_comparison"]
    status: Literal[404] = 404
    reason: Literal["http_404"] = "http_404"
    message: str
    default_branch_sha: str | None = None


# --- Source history and monthly comparisons (ADR 0003, 0013, 0014) --------


class ForkExclusion(BaseModel):
    """A frozen fork comparison excluded by explicit API evidence."""

    fork: Fork
    github_id: int
    upstream_sha: str
    reason: Literal["no_common_ancestor"] = "no_common_ancestor"
    endpoint: str
    status: Literal[404] = 404
    message: str
    retrieved_at: AwareDatetime


class FileChange(BaseModel):
    """One file changed between two revisions, with full content on both sides.

    Used for source commits and monthly net diffs. These changed files supply
    labeling context, but complete package revisions are needed for lengths.
    """

    path: str
    previous_path: str | None = Field(default=None, description="Set only for renames.")
    status: ChangeStatus
    patch: str = Field(description="Unified diff hunks for this file.")
    content_before: str | None = Field(description="None for added files.")
    content_after: str | None = Field(description="None for removed files.")
    before_blob_sha: str | None = None
    after_blob_sha: str | None = None
    mode_before: str | None = None
    mode_after: str | None = None
    encoding_before: Literal["utf-8", "base64", "gitlink"] | None = None
    encoding_after: Literal["utf-8", "base64", "gitlink"] | None = None


class Commit(BaseModel):
    """One source commit from a fork's frozen default branch history.

    Retained for endpoint construction and traceability, not directly labeled.
    Filtering and the treatment of merge parents remain separate design decisions.
    """

    upstream: str
    fork_owner: str
    fork_branch: str
    sha: str
    author_date: AwareDatetime = Field(
        description="GitHub commit.author.date, preserved with its UTC offset as provenance."
    )
    committer_date: AwareDatetime = Field(
        description="GitHub commit.committer.date; convert to UTC for month membership (ADR 0015)."
    )
    parent_shas: list[str] = Field(
        description="GitHub parents[].sha in response order; empty for a root commit."
    )
    message: str = Field(
        description="Raw message; footers are kept so authorship trailers stay available."
    )
    is_mechanical: bool = Field(
        description="Recorded maintenance flag; commit kind alone does not establish exclusion."
    )
    is_bot: bool = Field(description="Author matched a bot heuristic (ADR 0003).")
    is_translation: bool = Field(
        description="Change limited to translation; kept out of the main analysis (ADR 0003)."
    )
    files: list[FileChange]


class SecurityMatch(BaseModel):
    """One security rule hit on one diff line (ADR 0007, stage one)."""

    rule_id: str = Field(
        description="Key in security_rules.yaml; category is looked up there."
    )
    path: str
    side: MatchSide
    line: str = Field(description="Matched line text without the diff marker.")


class PackageRevision(BaseModel):
    """Reference to a complete package state in the instance's fork repository.

    Resolve the package subtree at commit_sha, including unchanged files.
    A confirmed absent subtree represents a deleted package; failed retrieval
    must not be interpreted as an empty package.
    """

    commit_sha: str
    package_path: str


class Instance(BaseModel):
    """One skill's monthly net change on a frozen fork default branch.

    ADRs 0013 and 0014 replace commit observations and intermediate label
    unions. instance_id identifies the fork, skill, month and endpoint pair;
    the exact skill identity/rename policy remains to be resolved. Equal net
    diffs in different months are separate observations, not duplicates.
    """

    instance_id: str
    upstream: str
    fork: str = Field(
        description="Fork repository owner/name, used to resolve revision SHAs."
    )
    fork_owner: str
    fork_branch: str = Field(description="Default branch name frozen at retrieval.")
    month: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="UTC calendar month as YYYY-MM, derived from committer time (ADR 0015).",
    )
    skill_package_path: str
    before: PackageRevision = Field(
        description="State before the first eligible monthly modification."
    )
    after: PackageRevision = Field(
        description="State after the last eligible monthly modification."
    )
    source_commit_shas: list[str] = Field(
        min_length=1,
        description="Source history for the comparison, preserving intervening commits for audit.",
    )
    net_change_status: NetChangeStatus = Field(
        description="Establishing no net change requires complete endpoint comparison, never missing data."
    )
    files: list[FileChange] = Field(
        description="Monthly endpoint diff; empty for verified activity with no net change."
    )
    security_matches: list[SecurityMatch] = Field(default_factory=list)
    exclusion_reason: Literal["unresolved_upstream"] | None = Field(
        default=None,
        description="Excluded from main numerators and denominators under ADR 0018 when set.",
    )
    exclusion_note: str | None = Field(
        default=None,
        description="Evidence for exclusion, referring to the preserved source history.",
    )


# --- Taxonomy (ADR 0005) --------------------------------------------------


class PackageFile(BaseModel):
    """One complete tracked file or submodule pointer in a package endpoint."""

    path: str
    sha: str
    mode: str
    encoding: Literal["utf-8", "base64", "gitlink"]
    content: str


class OriginEvidence(BaseModel):
    """An observed package transition and the limits of its origin evidence."""

    commit_sha: str
    parent_sha: str
    kind: Literal["fork_candidate", "upstream", "unresolved"]
    reason: str
    matching_upstream_shas: list[str] = Field(default_factory=list)
    introduced_commit_shas: list[str] = Field(default_factory=list)
    patch_fingerprint: str


class MonthlyRecord(BaseModel):
    """A monthly instance with complete endpoint contents and source evidence."""

    instance: Instance
    before_files: list[PackageFile]
    after_files: list[PackageFile]
    origin_evidence: list[OriginEvidence]
    partial_month: bool


class Pattern(BaseModel):
    """One modification pattern; `name` is the label vocabulary used by the annotator."""

    name: str
    definition: str
    patch_evidence_required: str
    decision_rule: str


class Family(BaseModel):
    """A group of patterns finalised at checkpoint two."""

    name: str
    definition: str
    patterns: list[Pattern]


class Taxonomy(BaseModel):
    """Frozen label vocabulary injected into the labeling system prompt."""

    version: str
    families: list[Family]

    def pattern_names(self) -> list[str]:
        """Flat enum for the output schema; families are derived at aggregation time."""
        return [p.name for f in self.families for p in f.patterns]


class CandidatePattern(BaseModel):
    """A pattern proposed by the model during the iteration stage; retained without edits until checkpoint two."""

    batch_id: int
    time_stratum: int = Field(
        description="Time quantile the batch was drawn from; saturation is judged per stratum."
    )
    proposal: Pattern
    accepted: bool | None = Field(
        default=None,
        description="Human decision at checkpoint two; None until reviewed.",
    )


# --- Labeling (ADR 0006, 0007) -------------------------------------------


class PatternLabel(BaseModel):
    """One assigned pattern and its confidence."""

    name: str = Field(
        description="Must be in Taxonomy.pattern_names(); enforced by the output schema enum."
    )
    confidence: Confidence


class SecurityJudgement(BaseModel):
    """Judgement in stage two of one rule match (ADR 0007)."""

    rule_id: str
    direction: SecurityDirection


class PackageLabels(BaseModel):
    """Labels for one monthly package net diff; records with no net change use empty lists."""

    skill_package_path: str
    patterns: list[PatternLabel]
    diff_sufficiency: DiffSufficiency
    security: list[SecurityJudgement] = Field(default_factory=list)


class LabelingCallOutput(BaseModel):
    """Schema payload for one monthly instance's labeling call (ADR 0006, 0013)."""

    package: PackageLabels


class CallProvenance(BaseModel):
    """Reproducibility fields stored with every label (ADR 0006)."""

    model: str
    system_fingerprint: str | None
    prompt_version: str
    taxonomy_version: str
    effort: str
    request_id: str
    input_tokens: int
    output_tokens: int
    called_at: datetime


class LabelRecord(BaseModel):
    """Monthly labels with call provenance or deterministic output for unchanged endpoints.

    A record with no net change has empty pattern/security lists, EMPTY diff
    sufficiency and no API provenance. API failures are not such records.
    """

    instance_id: str
    labels: PackageLabels
    provenance: CallProvenance | None = Field(
        description="None only for deterministic labels on verified instances with no net change."
    )


# --- Length metrics (ADR 0009) -------------------------------------------


class LengthMeasure(BaseModel):
    """Size of one skill package at one point in time, prose and code separated."""

    chars_prose: int
    chars_code: int = Field(description="Characters inside fenced code blocks.")
    units_prose: int = Field(
        description="Markdown headings plus list items outside code blocks."
    )
    files: int = Field(description="Files in the package.")


class InstanceLength(BaseModel):
    """Baseline and net change for one Instance; relative change is derived at analysis time."""

    instance_id: str
    month: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Same month as the source instance.",
    )
    before: LengthMeasure = Field(
        description="Complete package at Instance.before, including unchanged files."
    )
    after: LengthMeasure = Field(
        description="Complete package at Instance.after; equals before for activity with no net change."
    )


# --- Validation (ADR 0008) -----------------------------------------------


class AuditRecord(BaseModel):
    """One auditor's independent labels for one sampled Instance; never substituted into analysis."""

    instance_id: str
    auditor_id: str
    time_stratum: int
    patterns: list[str] = Field(
        description="Pattern names; confidence is not collected from auditors."
    )
    security: list[SecurityJudgement] = Field(default_factory=list)


# --- Timeline (ADR 0010) -------------------------------------------------


class ReferenceEvent(BaseModel):
    """One dated reference line, loaded from configs/ after manual verification."""

    date: datetime
    kind: ReferenceKind
    vendor: str | None = Field(
        default=None,
        description="anthropic or openai for model releases; None otherwise.",
    )
    label: str = Field(description="Text drawn on the figure.")
    source_url: str = Field(description="Announcement used to verify the date.")
