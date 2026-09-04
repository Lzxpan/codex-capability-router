"""Phase 1 Skill inventory、Basic Profile cache 與 content fingerprint。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .discovery import (
    _canonical_skill_id,
    _frontmatter,
    _skill_candidates,
    _skill_source_label,
    discover_plugin_skill_declarations,
    discover_plugin_skill_root_specs,
    discover_skill_roots,
)
from .existence import ExistenceEvidence, ExistenceEvidenceState, MetadataQuality, classify_metadata_quality
from .skill_plan import RootPlanSnapshot, SkillRootSpec, build_skill_root_plan
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .host_exposure import HostSkillExposureEnvelope
from .models import (
    CapabilityKind,
    CapabilityRecord,
    CapabilityStatus,
    DiscoveryDiagnostic,
    DiscoveryResult,
)
from .registry import merge_capability_records
from .routing import _is_controller

# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：正式 high-recall Skill pool 仍可能以 metadata gate 遺漏存在的 Skill。
# 修改原因：beta.3 的 existence-only contract 禁止 metadata quality 造成 capability starvation。
# 修改後功能：formal high-recall pool 保留所有 present 且 identity resolved 的 Skill；legacy retrieval 與 handoff 維持相容邊界。
# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：inventory 以 Host exposure evidence 作為 Skill availability gate，缺少 Host evidence 的 trusted-root Skill 會被降為 unknown。
# 修改原因：Skill availability 與 Provider availability 分離；trusted root 的合法 discovery/handoff safety 才是 Skill formal availability 基礎。
# 修改後功能：trusted-root valid record 直接進入 formal availability，Host exposure 僅保存 optional observation；仍保留 bounded diagnostics、reference-only metrics 與 Python non-semantic boundary。


# ponytail: cache 只保留記憶體中的 Basic Profile；若未來需要跨程序持久化，先補 privacy/eviction 規格再加入 storage。
PROFILE_FORMAT_VERSION = "phase1-basic-profile-v1"
_CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES = 32768


@dataclass(frozen=True)
class BasicProfile:
    """提供給後續 route 流程的短 Skill 名片，不保存完整 SKILL.md。"""

    id: str
    name: str
    description: str | None
    version: str | None
    status: CapabilityStatus
    source: str
    provenance: tuple[str, ...]
    fingerprint: str
    stale: bool = False
    metadata_quality: MetadataQuality = MetadataQuality.OPAQUE
    source_binding: "SkillSourceBinding | None" = None


@dataclass(frozen=True)
class SkillSourceBinding:
    """一個 canonical Skill 唯一採用的 authoritative physical source。"""

    canonical_skill_id: str
    path: Path
    source: str
    provenance: tuple[str, ...] = ()
    source_kind: str = ""
    root_kind: str = ""
    scope: str = ""
    plugin_identity: str | None = None
    alternate_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(self, "alternate_paths", tuple(Path(path) for path in self.alternate_paths))
        if not self.canonical_skill_id.strip() or not self.source.strip():
            raise ValueError("SkillSourceBinding requires identity and source")


@dataclass(frozen=True)
class _SkillSourceMaterial:
    skill_id: str
    path: Path
    raw: bytes
    source: str
    spec: SkillRootSpec


@dataclass(frozen=True)
class SelectedSkillRefreshResult:
    """單一 selected Skill 的 bounded、immutable refresh 結果。"""

    snapshot: "SkillInventorySnapshot"
    skill_id: str
    source_reads: int
    semantic_digest_changed: bool


@dataclass(frozen=True)
class EnrichedProfile:
    """初選候選需要時才建立的最小補充資料，不保存完整 SKILL.md。"""

    id: str
    summary: str
    limitations: tuple[str, ...]
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class PossibleRelevanceDiagnostic:
    """retrieval-recalled unknown profile 的公開、非正式相關性診斷。"""

    id: str
    availability_state: str
    possible_relevance_reason: str
    exclusion_reason: str

    def __post_init__(self) -> None:
        """限制 diagnostic 只能描述 unknown profile 的 bounded public evidence。"""

        if not isinstance(self.id, str) or _CANONICAL_ID.fullmatch(self.id) is None:
            raise ValueError("possible relevance diagnostic requires a canonical Skill ID")
        if self.availability_state != CapabilityStatus.UNKNOWN.value:
            raise ValueError("possible relevance diagnostic must remain unknown")
        for value, field_name in (
            (self.possible_relevance_reason, "possible_relevance_reason"),
            (self.exclusion_reason, "exclusion_reason"),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError(f"{field_name} must be bounded text")
            if "/" in value or "\\" in value or any(
                marker in value.casefold() for marker in ("api_key=", "password=", "secret=", "token=")
            ):
                raise ValueError(f"{field_name} contains private or sensitive text")

    def to_mapping(self) -> dict[str, str]:
        """輸出不含 full instructions/path 的 bounded diagnostic。"""

        return {
            "id": self.id,
            "availability_state": self.availability_state,
            "possible_relevance_reason": self.possible_relevance_reason,
            "exclusion_reason": self.exclusion_reason,
        }


@dataclass(frozen=True)
class RetrievalBudget:
    """整條 route 共用的 expanded retrieval 次數 contract。"""

    expanded_retrievals_used: int = 0

    def __post_init__(self) -> None:
        """只允許尚未使用或已使用一次，拒絕第三輪 retrieval 狀態。"""

        if isinstance(self.expanded_retrievals_used, bool) or self.expanded_retrievals_used not in (0, 1):
            raise ValueError("expanded_retrievals_used must be 0 or 1")

    def consume_expanded(self) -> "RetrievalBudget":
        """消耗唯一一次 expanded retrieval budget。"""

        if self.expanded_retrievals_used == 1:
            raise ValueError("expanded retrieval budget is exhausted")
        return RetrievalBudget(expanded_retrievals_used=1)


@dataclass(frozen=True)
class RetrievalResult:
    """Candidate Retrieval 結果；不包含 selected、rejected 或 final outcome。"""

    candidates: tuple[BasicProfile, ...] = ()
    enriched_profiles: tuple[EnrichedProfile, ...] = ()
    budget: RetrievalBudget = field(default_factory=RetrievalBudget)
    # 新增欄位置於既有 positional fields 之後，保留 beta.4 compatibility。
    unknown_profiles: tuple[BasicProfile, ...] = ()


@dataclass
class ProfileCache:
    """記憶體 Profile cache；active 與 stale metadata 分開保存。"""

    _active: dict[str, BasicProfile] = field(default_factory=dict, repr=False)
    _stale: dict[str, BasicProfile] = field(default_factory=dict, repr=False)

    def get(self, capability_id: str) -> BasicProfile | None:
        """取得目前可見 Profile；stale entry 不會由此方法返回。"""

        return self._active.get(capability_id)

    def get_stale(self, capability_id: str) -> BasicProfile | None:
        """取得最近一次失效的 Profile metadata，供 invalidation 測試與診斷使用。"""

        return self._stale.get(capability_id)


@dataclass(frozen=True)
class SkillInventory:
    """本次 refresh 的存在 inventory、Basic Profiles 與 handoff eligibility 結果。"""

    records: tuple[CapabilityRecord, ...] = ()
    profiles: tuple[BasicProfile, ...] = ()
    available_records: tuple[CapabilityRecord, ...] = ()
    diagnostics: tuple[DiscoveryDiagnostic, ...] = ()
    partial: bool = False
    _skill_bindings: dict[str, SkillSourceBinding] = field(default_factory=dict, repr=False, compare=False)
    host_exposed_skill_ids: tuple[str, ...] = ()
    router_available_skill_ids: tuple[str, ...] = ()
    # 新增欄位置於既有欄位之後，保留既有 positional compatibility。
    trusted_root_skill_ids: tuple[str, ...] = ()
    # present 是 existence scope；available 僅保留 legacy handoff-ready scope。
    present_records: tuple[CapabilityRecord, ...] = ()
    existence_evidence: tuple[ExistenceEvidence, ...] = ()
    raw_evidence_count: int = 0
    physical_declaration_count: int = 0
    filesystem_present_count: int = 0
    runtime_entity_count: int = 0
    package_declared_count: int = 0
    canonical_unique_count: int = 0
    controller_self_count: int = 0
    metadata_sufficient_count: int = 0
    metadata_sparse_count: int = 0
    metadata_opaque_count: int = 0
    identity_unresolved_count: int = 0
    semantically_considered_count: int = 0
    never_considered_count: int = 0
    discovery_metrics: tuple[tuple[str, int], ...] = ()

    @property
    def _skill_paths(self) -> dict[str, Path]:
        """Compatibility projection derived solely from selected source bindings."""

        return {skill_id: binding.path for skill_id, binding in self._skill_bindings.items()}

    def source_binding(self, skill_id: str) -> SkillSourceBinding | None:
        """回傳 profile 與 handoff 共用的唯一 physical source binding。"""

        return self._skill_bindings.get(skill_id)

    @property
    def skill_raw_evidence_count(self) -> int:
        """回傳 source evidence rows；不把它誤稱為 canonical Skill 數。"""

        return self.raw_evidence_count

    @property
    def skill_canonical_unique_count(self) -> int:
        """回傳 canonical logical Skill 數。"""

        return self.canonical_unique_count

    def blind_metrics(self) -> dict[str, int]:
        """輸出不含 UI expected count 的 Skill source-derived metrics。"""

        return {
            "skill_raw_evidence_count": self.raw_evidence_count,
            "skill_physical_declaration_count": self.physical_declaration_count,
            "skill_filesystem_present_count": self.filesystem_present_count,
            "skill_runtime_entity_count": self.runtime_entity_count,
            "skill_package_declared_count": self.package_declared_count,
            "skill_canonical_unique_count": self.canonical_unique_count,
            "skill_controller_self_count": self.controller_self_count,
            "skill_metadata_sufficient_count": self.metadata_sufficient_count,
            "skill_metadata_sparse_count": self.metadata_sparse_count,
            "skill_metadata_opaque_count": self.metadata_opaque_count,
            "skill_identity_unresolved_count": self.identity_unresolved_count,
            "skill_semantically_considered_count": self.semantically_considered_count,
            "skill_never_considered_count": self.never_considered_count,
        }


@dataclass(frozen=True)
class SkillInventorySnapshot:
    """一次 root-plan refresh 的 immutable Skill inventory cache snapshot。"""

    inventory: SkillInventory
    root_plan_fingerprint: str
    inventory_fingerprint: str
    source_fingerprint: str
    discovery_metrics: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        """驗證 snapshot digest，確保 route 不會把不同 plan 當成同一份 cache。"""

        if not isinstance(self.inventory, SkillInventory):
            raise TypeError("SkillInventorySnapshot requires SkillInventory")
        for name, value in (
            ("root_plan_fingerprint", self.root_plan_fingerprint),
            ("inventory_fingerprint", self.inventory_fingerprint),
            ("source_fingerprint", self.source_fingerprint),
        ):
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a SHA-256 digest")
        object.__setattr__(self, "discovery_metrics", tuple(self.discovery_metrics))

    @property
    def skill_never_considered_count(self) -> int:
        """提供 zero-miss audit 的唯讀 projection。"""

        return self.inventory.never_considered_count


@dataclass
class SkillInventoryCache:
    """caller-owned session cache；不跨 session persistent，也不保存完整 SKILL.md。"""

    snapshot: SkillInventorySnapshot | None = None
    root_plan_build_count: int = 0
    skill_inventory_refresh_count: int = 0
    filesystem_root_visit_count: int = 0
    plugin_manifest_open_count: int = 0
    skill_file_open_count: int = 0
    cached_inventory_reuse_count: int = 0

    def get_or_refresh(
        self,
        root_plan: RootPlanSnapshot,
        *,
        source_fingerprint: str = "",
        refresh: bool = False,
        runtime: DiscoveryResult | None = None,
        cli: DiscoveryResult | None = None,
        manual: DiscoveryResult | None = None,
        host_exposure: HostSkillExposureEnvelope | None = None,
        plugin_manifests: Sequence[Mapping[str, object]] = (),
    ) -> SkillInventorySnapshot:
        """同一 plan/source state 重用 snapshot；明確 source change 才 refresh。"""

        if not isinstance(root_plan, RootPlanSnapshot):
            raise TypeError("SkillInventoryCache requires RootPlanSnapshot")
        source_digest = _source_fingerprint(source_fingerprint, runtime, cli, manual, host_exposure, plugin_manifests)
        if (
            not refresh
            and self.snapshot is not None
            and self.snapshot.root_plan_fingerprint == root_plan.fingerprint
            and self.snapshot.source_fingerprint == source_digest
        ):
            self.cached_inventory_reuse_count += 1
            return self.snapshot
        self.root_plan_build_count += 1
        self.skill_inventory_refresh_count += 1
        snapshot = refresh_skill_inventory_snapshot(
            root_plan,
            runtime=runtime,
            cli=cli,
            manual=manual,
            host_exposure=host_exposure,
            plugin_manifests=plugin_manifests,
            source_fingerprint=source_digest,
        )
        self.snapshot = snapshot
        metrics = dict(snapshot.discovery_metrics)
        self.filesystem_root_visit_count += metrics.get("filesystem_root_count", 0)
        self.skill_file_open_count += metrics.get("skill_files_opened", 0)
        return snapshot

    def invalidate(self) -> None:
        """由明確 reload/source event 清除當前 session snapshot。"""

        self.snapshot = None


def refresh_skill_inventory(
    roots: Sequence[Path],
    *,
    cache: ProfileCache | None = None,
    runtime: DiscoveryResult | None = None,
    cli: DiscoveryResult | None = None,
    manual: DiscoveryResult | None = None,
    host_exposure: HostSkillExposureEnvelope | None = None,
    plugin_manifests: Sequence[Mapping[str, object]] = (),
    root_plan: RootPlanSnapshot | None = None,
) -> SkillInventory:
    """重新 discovery/merge 明確 roots，並以本次來源更新 Skill Profile cache。

    使用方式：每次 route 前傳入當次 runtime/CLI/manual discovery 結果；函式
    不從 cache 推導 availability，也不執行 command、安裝能力或保存原始文件。
    """

    active_cache = cache or ProfileCache()
    if root_plan is not None:
        if not isinstance(root_plan, RootPlanSnapshot):
            raise TypeError("root_plan must be a RootPlanSnapshot")
        # beta.7 path：root plan 已在 init/refresh 完成 Plugin container compression；
        # 這裡只做一次 plan-defined bounded traversal，不重新展開 child roots。
        root_result = discover_skill_roots(root_plan)
        plugin_roots: tuple[Path, ...] = ()
        plugin_root_result = DiscoveryResult()
    else:
        # beta.7 compatibility path 仍接受既有 explicit roots，但 production
        # inventory 也改用一個 Plugin container root，不把 child directory 擴成 roots。
        root_specs = tuple(
            SkillRootSpec(
                root,
                "CALLER_DECLARED_SKILL_ROOT",
                "TRUSTED_RUNTIME_DECLARED_ROOT",
                provenance=("caller",),
            )
            for root in roots
        )
        plugin_specs = discover_plugin_skill_root_specs(plugin_manifests)
        plan = build_skill_root_plan(
            include_fixed_global=False,
            additional_roots=root_specs,
            plugin_roots=plugin_specs,
        )
        root_result = discover_skill_roots(plan)
        plugin_roots: tuple[Path, ...] = ()
        plugin_root_result = DiscoveryResult()
    plugin_declared_result = discover_plugin_skill_declarations(plugin_manifests)
    source_results = tuple(
        result
        for result in (runtime, cli, root_result, plugin_root_result, plugin_declared_result, manual)
        if result is not None
    )
    raw_skill_records = tuple(
        record
        for result in source_results
        for record in result.records
        if record.kind == CapabilityKind.SKILL
    )
    merged = merge_capability_records(
        tuple(record for result in source_results for record in result.records)
    )
    records = tuple(
        sorted(
            (record for record in merged.records if record.kind == CapabilityKind.SKILL),
            key=lambda record: (record.id.casefold(), record.id),
        )
    )
    local_records: dict[str, CapabilityRecord] = {}
    for local_record in (*root_result.records, *plugin_root_result.records):
        local_records.setdefault(local_record.id, local_record)
    if root_plan is not None:
        source_materials = _read_allowlisted_skill_sources_for_plan(root_plan)
    else:
        source_materials = (
            _read_allowlisted_skill_sources_for_specs(
                tuple(
                    SkillRootSpec(
                        root,
                        "CALLER_DECLARED_SKILL_ROOT",
                        "TRUSTED_RUNTIME_DECLARED_ROOT",
                        provenance=("caller",),
                    )
                    for root in roots
                ),
                source_prefix="skill-root",
            )
            + _read_allowlisted_skill_sources_for_specs(plugin_specs, source_prefix="plugin-skill-root")
        )
    source_bindings = _select_source_bindings(records, source_materials)
    source_diagnostics = tuple(
        DiscoveryDiagnostic(
            "multiple_physical_skill_sources",
            "canonical Skill has multiple authoritative physical sources; one binding selected",
            record.source,
        )
        for record in records
        if len({str(material.path.resolve()).casefold() for material in source_materials if material.skill_id == record.id}) > 1
    )
    material_by_path = {
        str(material.path.resolve()).casefold(): material
        for material in source_materials
    }
    host_exposed_ids: tuple[str, ...] = ()
    if host_exposure is not None:
        from .host_exposure import HostSkillExposureEnvelope

        if not isinstance(host_exposure, HostSkillExposureEnvelope):
            raise TypeError("host_exposure must be a trusted HostSkillExposureEnvelope")
        # Host exposure 只記錄 observed IDs；不改寫 trusted-root formal availability。
        host_exposed_ids = host_exposure.exposed_ids
    # 只有 discovery 與同一 refresh 內可讀的 handoff target 都存在，才算本次
    # trusted-root formal availability；避免檔案在 discovery/read 之間消失時
    # 先被誤報為 available，並把真正的 handoff safety 留給 selection validator。
    trusted_root_ids = frozenset(local_records)
    handoff_ready_ids = trusted_root_ids.intersection(source_bindings)
    profiles = tuple(
        _refresh_profile(
            active_cache,
            record,
            source_bindings.get(record.id),
            local_records.get(record.id),
            material_by_path,
        )
        for record in records
    )
    current_ids = {profile.id for profile in profiles}
    for capability_id in tuple(active_cache._active):
        if capability_id in current_ids:
            continue
        active_cache._stale[capability_id] = replace(active_cache._active.pop(capability_id), stale=True)

    available_records = tuple(
        record
        for record in records
        if record.id in handoff_ready_ids
        and not _is_controller(record)
        and not record.routing_support
    )
    present_records = tuple(record for record in records if not record.routing_support)
    profiles_by_id = {profile.id: profile for profile in profiles}
    existence_evidence = _skill_existence_evidence(
        raw_skill_records,
        profiles_by_id,
    )
    evidence_by_state: dict[ExistenceEvidenceState, set[str]] = {
        state: set() for state in ExistenceEvidenceState
    }
    for evidence in existence_evidence:
        evidence_by_state[evidence.state].add(evidence.identity)
    present_by_id = {record.id: record for record in present_records}
    present_profiles = tuple(
        profile
        for profile in profiles
        if profile.id in present_by_id and not _is_controller_record(present_by_id[profile.id])
    )
    metadata_sufficient_count = sum(profile.metadata_quality == MetadataQuality.SUFFICIENT for profile in present_profiles)
    metadata_sparse_count = sum(profile.metadata_quality == MetadataQuality.SPARSE for profile in present_profiles)
    metadata_opaque_count = sum(profile.metadata_quality == MetadataQuality.OPAQUE for profile in present_profiles)
    identity_unresolved_count = sum(not bool(profile.id.strip()) for profile in present_profiles)
    diagnostics = tuple(
        diagnostic
        for result in source_results
        for diagnostic in result.diagnostics
    ) + merged.diagnostics + source_diagnostics
    return SkillInventory(
        records=records,
        profiles=profiles,
        available_records=available_records,
        diagnostics=diagnostics,
        partial=any(result.partial for result in source_results),
        _skill_bindings=source_bindings,
        trusted_root_skill_ids=tuple(sorted(trusted_root_ids, key=lambda value: (value.casefold(), value))),
        host_exposed_skill_ids=host_exposed_ids,
        router_available_skill_ids=tuple(record.id for record in available_records),
        present_records=present_records,
        existence_evidence=existence_evidence,
        raw_evidence_count=len(existence_evidence),
        physical_declaration_count=len(evidence_by_state[ExistenceEvidenceState.FILESYSTEM_PRESENT]),
        filesystem_present_count=len(evidence_by_state[ExistenceEvidenceState.FILESYSTEM_PRESENT]),
        runtime_entity_count=len(evidence_by_state[ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT]),
        package_declared_count=len(evidence_by_state[ExistenceEvidenceState.PACKAGE_DECLARED_PRESENT]),
        canonical_unique_count=len(records),
        controller_self_count=sum(_is_controller_record(record) for record in records),
        metadata_sufficient_count=metadata_sufficient_count,
        metadata_sparse_count=metadata_sparse_count,
        metadata_opaque_count=metadata_opaque_count,
        identity_unresolved_count=identity_unresolved_count,
        semantically_considered_count=len(present_profiles),
        never_considered_count=0,
        discovery_metrics=_sum_discovery_metrics(root_result, plugin_root_result),
    )


def refresh_skill_inventory_snapshot(
    root_plan: RootPlanSnapshot,
    *,
    runtime: DiscoveryResult | None = None,
    cli: DiscoveryResult | None = None,
    manual: DiscoveryResult | None = None,
    host_exposure: HostSkillExposureEnvelope | None = None,
    plugin_manifests: Sequence[Mapping[str, object]] = (),
    source_fingerprint: str = "",
) -> SkillInventorySnapshot:
    """在 init/refresh 建立 immutable snapshot；ordinary route 應直接重用它。"""

    if not isinstance(root_plan, RootPlanSnapshot):
        raise TypeError("root_plan must be a RootPlanSnapshot")
    inventory = refresh_skill_inventory(
        (),
        cache=ProfileCache(),
        runtime=runtime,
        cli=cli,
        manual=manual,
        host_exposure=host_exposure,
        plugin_manifests=plugin_manifests,
        root_plan=root_plan,
    )
    digest = _source_fingerprint(source_fingerprint, runtime, cli, manual, host_exposure, plugin_manifests)
    return SkillInventorySnapshot(
        inventory=inventory,
        root_plan_fingerprint=root_plan.fingerprint,
        inventory_fingerprint=_inventory_fingerprint(inventory),
        source_fingerprint=digest,
        discovery_metrics=inventory.discovery_metrics,
    )


def refresh_selected_skill_snapshot(
    snapshot: SkillInventorySnapshot,
    skill_id: str,
) -> SelectedSkillRefreshResult:
    """只重讀已綁定的 selected Skill，建立新的 immutable snapshot。

    這是 handoff mismatch 的 bounded recovery；不重建 RootPlan、不開 Plugin
    manifest，也不觸碰任何未選定 Skill。來源消失時只嘗試 snapshot 已保留的
    alternate authoritative paths，絕不搜尋新路徑。
    """

    if not isinstance(snapshot, SkillInventorySnapshot):
        raise TypeError("snapshot must be a SkillInventorySnapshot")
    inventory = snapshot.inventory
    profile = next((item for item in inventory.profiles if item.id == skill_id), None)
    binding = inventory.source_binding(skill_id)
    if profile is None or binding is None:
        raise ValueError("selected Skill has no authoritative source binding")
    selected_path = None
    raw = None
    for path in (binding.path, *binding.alternate_paths):
        try:
            candidate = path.read_bytes()
            candidate.decode("utf-8")
        except (OSError, UnicodeError):
            continue
        selected_path = path
        raw = candidate
        break
    if selected_path is None or raw is None:
        raise ValueError("selected Skill instructions are unavailable")
    refreshed_binding = replace(
        binding,
        path=selected_path,
        alternate_paths=tuple(path for path in (binding.path, *binding.alternate_paths) if path != selected_path),
    )
    refreshed_profile = replace(
        profile,
        fingerprint=_fingerprint_fields(
            profile.id,
            profile.name,
            profile.description,
            profile.version,
            raw,
        ),
        stale=False,
        source_binding=refreshed_binding,
    )
    profiles = tuple(refreshed_profile if item.id == skill_id else item for item in inventory.profiles)
    bindings = dict(inventory._skill_bindings)
    bindings[skill_id] = refreshed_binding
    refreshed_inventory = replace(inventory, profiles=profiles, _skill_bindings=bindings)
    refreshed_snapshot = replace(
        snapshot,
        inventory=refreshed_inventory,
        inventory_fingerprint=_inventory_fingerprint(refreshed_inventory),
        discovery_metrics=refreshed_inventory.discovery_metrics,
    )
    public_before = _profile_public_digest(profile)
    public_after = _profile_public_digest(refreshed_profile)
    return SelectedSkillRefreshResult(
        refreshed_snapshot,
        skill_id,
        1,
        public_before != public_after,
    )


def _profile_public_digest(profile: BasicProfile) -> tuple[object, ...]:
    """只比較可能影響 semantic selection 的 public profile fields。"""

    return (
        profile.id,
        profile.name,
        profile.description,
        profile.version,
        profile.status.value,
        profile.source,
        profile.provenance,
        profile.metadata_quality.value,
    )


def _sum_discovery_metrics(*results: DiscoveryResult) -> tuple[tuple[str, int], ...]:
    """合併 root discovery counters，避免 Plugin/root metrics 互相覆蓋。"""

    totals: dict[str, int] = {}
    for result in results:
        for key, value in result.discovery_metrics:
            totals[key] = totals.get(key, 0) + value
    return tuple(sorted(totals.items()))


def _inventory_fingerprint(inventory: SkillInventory) -> str:
    """只以 canonical public records/profiles 計算 inventory fingerprint。"""

    payload = {
        "records": [record.to_mapping() for record in inventory.records],
        "profiles": [
            {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "version": profile.version,
                "status": profile.status.value,
                "source": profile.source,
                "provenance": list(profile.provenance),
                "fingerprint": profile.fingerprint,
                "metadata_quality": profile.metadata_quality.value,
            }
            for profile in inventory.profiles
        ],
        "metrics": inventory.blind_metrics(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fingerprint(
    requested: str,
    runtime: DiscoveryResult | None,
    cli: DiscoveryResult | None,
    manual: DiscoveryResult | None,
    host_exposure: HostSkillExposureEnvelope | None,
    plugin_manifests: Sequence[Mapping[str, object]],
) -> str:
    """計算 source state digest；不把 task text 或完整 Skill body 放入 cache key。"""

    if requested:
        if len(requested) == 64 and all(char in "0123456789abcdef" for char in requested):
            return requested
        return hashlib.sha256(requested.encode("utf-8")).hexdigest()
    payload: dict[str, object] = {
        "runtime": None if runtime is None else runtime.to_registry_json(),
        "cli": None if cli is None else cli.to_registry_json(),
        "manual": None if manual is None else manual.to_registry_json(),
        "host_exposure": None if host_exposure is None else host_exposure.to_mapping(),
        "plugin_manifests": [dict(manifest) for manifest in plugin_manifests],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_controller_record(record: CapabilityRecord) -> bool:
    """共用 Router self/controller boundary，避免 source metric 重複猜測。"""

    return _is_controller(record)


def _skill_existence_evidence(
    raw_records: Sequence[CapabilityRecord],
    profiles_by_id: Mapping[str, BasicProfile],
) -> tuple[ExistenceEvidence, ...]:
    """將 raw Skill records 轉成 typed source evidence，不做 semantic dedupe。"""

    evidence: list[ExistenceEvidence] = []
    for record in raw_records:
        metadata_sufficient = bool(
            (profile := profiles_by_id.get(record.id))
            and profile.name.strip()
            and profile.description
            and profile.description.strip()
        )
        source = record.source
        if source.startswith("plugin-skill-root:"):
            evidence.extend(
                (
                    ExistenceEvidence(
                        record.id,
                        ExistenceEvidenceState.PACKAGE_DECLARED_PRESENT,
                        source,
                        metadata_sufficient,
                    ),
                    ExistenceEvidence(
                        record.id,
                        ExistenceEvidenceState.FILESYSTEM_PRESENT,
                        source,
                        metadata_sufficient,
                    ),
                )
            )
        elif source.startswith("skill-root:"):
            evidence.append(
                ExistenceEvidence(
                    record.id,
                    ExistenceEvidenceState.FILESYSTEM_PRESENT,
                    source,
                    metadata_sufficient,
                )
            )
        elif source.startswith("plugin-declared:"):
            evidence.append(
                ExistenceEvidence(
                    record.id,
                    ExistenceEvidenceState.PACKAGE_DECLARED_PRESENT,
                    source,
                    metadata_sufficient,
                )
            )
        elif source.startswith(("runtime:", "cli:")):
            evidence.append(
                ExistenceEvidence(
                    record.id,
                    ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT,
                    source,
                    metadata_sufficient,
                )
            )
        else:
            evidence.append(
                ExistenceEvidence(
                    record.id,
                    ExistenceEvidenceState.DECLARATION_ONLY,
                    source,
                    metadata_sufficient,
                    resolved=False,
                )
            )
    return tuple(
        sorted(
            evidence,
            key=lambda item: (item.identity.casefold(), item.identity, item.state.value, item.source),
        )
    )


def build_enriched_profile(
    inventory: SkillInventory,
    profile: BasicProfile,
) -> EnrichedProfile | None:
    """只讀取指定候選的完整 SKILL.md，轉成 bounded summary metadata。"""

    skill_path = inventory._skill_paths.get(profile.id)
    if skill_path is None:
        return None
    try:
        text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    metadata = _frontmatter(text)
    if metadata is None:
        return None
    summary = _safe_enriched_text(metadata.get("summary"))
    if summary is None:
        summary = _safe_enriched_text(metadata.get("description"))
    if summary is None:
        summary = _safe_enriched_text(_body_summary(text))
    if summary is None:
        return None
    return EnrichedProfile(
        id=profile.id,
        summary=summary,
        limitations=_safe_enriched_texts(metadata.get("limitations")),
        requirements=_safe_enriched_texts(metadata.get("requirements")),
    )


def retrieve_candidates(
    inventory: SkillInventory,
    task_summary: str,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    budget: RetrievalBudget | None = None,
    use_expanded: bool = False,
    task_analysis_items: Sequence[str] = (),
) -> RetrievalResult:
    """以 Basic/既有 Enriched 文字召回候選，不執行 final Skill Selection。

    小型 inventory 全部保留；大型 inventory 依 task_summary 與每個 work part
    分開做 bounded token overlap。explicit available Skill 直接加入，但仍受
    inventory eligibility hard gate 約束。
    """

    _require_bounded_text(task_summary, "task_summary")
    for part in work_parts:
        _require_bounded_text(part, "work_part")
    for item in task_analysis_items:
        _require_bounded_text(item, "task_analysis_item")
    for capability_id in explicit_skill_ids:
        _require_explicit_id(capability_id)

    current_budget = budget or RetrievalBudget()
    if use_expanded:
        current_budget = current_budget.consume_expanded()
    # Semantic recall sees every present logical Skill; handoff-ready paths are
    # checked later by the full-instruction boundary.
    present_records = inventory.present_records or inventory.available_records
    available_ids = {record.id for record in present_records if not _is_controller(record) and not record.routing_support}
    profiles = tuple(profile for profile in inventory.profiles if profile.id in available_ids)
    # 只有目前未進入 formal available inventory 的 recalled profile 才能進 diagnostic；
    # trusted-root valid Skill 已在 refresh 時升格為 available，不會因 Host 缺失而誤入這裡。
    unknown_profiles = tuple(
        profile
        for profile in inventory.profiles
        if profile.status == CapabilityStatus.UNKNOWN and profile.id not in available_ids
    )
    profiles_by_id = {profile.id.casefold(): profile for profile in profiles}
    all_profiles_by_id = {profile.id.casefold(): profile for profile in inventory.profiles}
    records_by_id = {record.id: record for record in inventory.records}
    known_by_id = {profile.id: profile for profile in known_enriched_profiles}

    search_inputs = _deduplicate_search_inputs((task_summary, *work_parts, *task_analysis_items))
    if len(inventory.profiles) <= _SMALL_INVENTORY_LIMIT:
        matched_ids = {profile.id for profile in profiles}
        matched_unknown_ids = {profile.id for profile in unknown_profiles}
    else:
        threshold = 1 if use_expanded else 2
        matched_ids: set[str] = set()
        matched_unknown_ids: set[str] = set()
        for work in search_inputs:
            terms = _search_terms(work)
            if not terms:
                continue
            for profile in inventory.profiles:
                enriched = known_by_id.get(profile.id)
                search_text = _profile_search_text(profile, records_by_id.get(profile.id), enriched)
                if _term_overlap(terms, search_text) >= threshold:
                    if profile.id in available_ids:
                        matched_ids.add(profile.id)
                    else:
                        matched_unknown_ids.add(profile.id)

    for requested_id in explicit_skill_ids:
        profile = profiles_by_id.get(requested_id.casefold())
        if profile is not None:
            matched_ids.add(profile.id)
        unknown_profile = all_profiles_by_id.get(requested_id.casefold())
        if unknown_profile is not None:
            matched_unknown_ids.add(unknown_profile.id)

    candidates = tuple(profile for profile in profiles if profile.id in matched_ids)
    description_counts: dict[str, int] = {}
    for profile in candidates:
        if profile.description:
            key = _normalize_search_text(profile.description)
            description_counts[key] = description_counts.get(key, 0) + 1

    enriched_profiles: list[EnrichedProfile] = []
    for profile in candidates:
        existing = known_by_id.get(profile.id)
        if existing is not None:
            enriched_profiles.append(existing)
            continue
        record = records_by_id.get(profile.id)
        description_key = _normalize_search_text(profile.description or "")
        needs_enrichment = (
            not profile.description
            or len(profile.description.strip()) < _ENRICH_DESCRIPTION_MIN_LENGTH
            or description_counts.get(description_key, 0) > 1
            or bool(record and (record.limitations or record.requires))
        )
        if not needs_enrichment:
            continue
        enriched = build_enriched_profile(inventory, profile)
        if enriched is not None:
            enriched_profiles.append(enriched)

    return RetrievalResult(
        candidates=candidates,
        unknown_profiles=tuple(profile for profile in unknown_profiles if profile.id in matched_unknown_ids),
        enriched_profiles=tuple(enriched_profiles),
        budget=current_budget,
    )


def _deduplicate_search_inputs(values: Sequence[str]) -> tuple[str, ...]:
    """依既有 NFKC/casefold 規則去除 retrieval input 的 exact duplicates。"""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize_search_text(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def serialize_recalled_unknown_profiles(profiles: Sequence[BasicProfile]) -> bytes:
    """以固定 canonical JSON/UTF-8 bytes 序列化 unknown profile metadata。"""

    payload = [
        {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "version": profile.version,
            "status": profile.status.value,
            "source": profile.source,
            "provenance": list(profile.provenance),
            "fingerprint": profile.fingerprint,
            "stale": profile.stale,
        }
        for profile in sorted(profiles, key=lambda item: (item.id.casefold(), item.id))
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_possible_relevance_diagnostics(
    profiles: Sequence[BasicProfile],
    reasons: Mapping[str, str],
    *,
    budget_bytes: int | None = None,
) -> tuple[tuple[PossibleRelevanceDiagnostic, ...], str]:
    """建立 recalled-unknown diagnostics；超過固定 bytes budget 時整批略過。"""

    configured_budget = (
        DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES
        if budget_bytes is None
        else budget_bytes
    )
    if isinstance(configured_budget, bool) or not isinstance(configured_budget, int) or configured_budget < 0:
        raise ValueError("possible relevance budget must be a non-negative integer")
    if not isinstance(reasons, Mapping):
        raise ValueError("possible relevance reasons must be a mapping")
    for skill_id in reasons:
        if not isinstance(skill_id, str) or _CANONICAL_ID.fullmatch(skill_id) is None:
            raise ValueError("possible relevance reason key must be a canonical Skill ID")
    if any(profile.status != CapabilityStatus.UNKNOWN for profile in profiles):
        raise ValueError("possible relevance diagnostics require unknown profiles")
    if len(serialize_recalled_unknown_profiles(profiles)) > configured_budget:
        return (), "skipped_context_budget"
    profile_ids = {profile.id for profile in profiles}
    diagnostics: list[PossibleRelevanceDiagnostic] = []
    for skill_id in sorted(profile_ids & set(reasons), key=lambda value: (value.casefold(), value)):
        reason = reasons[skill_id]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            raise ValueError("possible relevance reason must be bounded text")
        if any(marker in reason.casefold() for marker in ("api_key=", "password=", "secret=", "token=")):
            raise ValueError("possible relevance reason contains sensitive text")
        diagnostics.append(
            PossibleRelevanceDiagnostic(
                id=skill_id,
                availability_state="unknown",
                possible_relevance_reason=reason.strip(),
                exclusion_reason="trusted-root availability and handoff evidence is insufficient; formal selection is blocked",
            )
        )
    return tuple(diagnostics), "produced"


_SMALL_INVENTORY_LIMIT = 32
_ENRICH_DESCRIPTION_MIN_LENGTH = 32
_SEARCH_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+")
_SEARCH_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})


def _profile_search_text(
    profile: BasicProfile,
    record: CapabilityRecord | None,
    enriched: EnrichedProfile | None,
) -> str:
    """組合一般搜尋文字；不以固定 taxonomy 或 Skill ID mapping 決定結果。"""

    values: list[str] = [profile.id, profile.name, profile.description or ""]
    if record is not None:
        values.extend((*record.categories, *record.triggers, *record.provides, *record.preferred_for))
    if enriched is not None:
        values.extend((enriched.summary, *enriched.limitations, *enriched.requirements))
    return _normalize_search_text(" ".join(values))


def _search_terms(text: str) -> tuple[str, ...]:
    """將 task/work part 轉成 bounded general-purpose search terms。"""

    terms = []
    for term in _SEARCH_TOKEN_PATTERN.findall(_normalize_search_text(text)):
        if term in _SEARCH_STOPWORDS or (term.isascii() and len(term) < 2):
            continue
        if term not in terms:
            terms.append(term)
    return tuple(terms)


def _term_overlap(terms: Sequence[str], text: str) -> int:
    """計算一般 token/substring 命中數，不建立人工 ID 對照表。"""

    return sum(term in text for term in terms)


def _normalize_search_text(value: str) -> str:
    """固定中英文文字的 bounded search normalization。"""

    return unicodedata.normalize("NFKC", value).casefold().strip()


def _body_summary(text: str) -> str | None:
    """從完整文件取第一個 bounded body line 作為最後 fallback summary。"""

    delimiters = [index for index, line in enumerate(text.splitlines()) if line.strip() == "---"]
    if len(delimiters) < 2:
        return None
    for line in text.splitlines()[delimiters[1] + 1 :]:
        candidate = line.strip()
        if candidate:
            return candidate
    return None


def _safe_enriched_text(value: object) -> str | None:
    """保留短且非敏感 enriched metadata，拒絕 path/secret-like content。"""

    if not isinstance(value, str):
        return None
    text = value.strip()
    folded = text.casefold()
    if (
        not text
        or len(text) > 512
        or "\x00" in text
        or "/" in text
        or "\\" in text
        or any(marker in folded for marker in ("api_key=", "password=", "secret=", "token="))
    ):
        return None
    return text


def _safe_enriched_texts(value: object) -> tuple[str, ...]:
    """驗證 bounded enriched list，不保存未信任原始結構。"""

    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(text for item in values[:8] if (text := _safe_enriched_text(item)) is not None)


def _require_bounded_text(value: object, field: str) -> None:
    """驗證 task summary/work part 不含空值、path 或 private metadata。"""

    if not isinstance(value, str) or not value.strip() or len(value) > 2048 or "/" in value or "\\" in value:
        raise ValueError(f"{field} must be bounded text")


def _require_explicit_id(value: object) -> None:
    """驗證 explicit Skill ID，不接受 private path 或 raw metadata。"""

    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 128
        or "/" in value
        or "\\" in value
        or "skill.md" in value.casefold()
        or _CANONICAL_ID.fullmatch(value.strip()) is None
    ):
        raise ValueError("explicit skill ID must be a bounded canonical ID")


def _refresh_profile(
    cache: ProfileCache,
    record: CapabilityRecord,
    binding: SkillSourceBinding | None,
    local_record: CapabilityRecord | None,
    material_by_path: Mapping[str, _SkillSourceMaterial] | None = None,
) -> BasicProfile:
    """用目前 record 與明確 root 的 SKILL.md 更新單一 Basic Profile。"""

    material = None if binding is None or material_by_path is None else material_by_path.get(
        str(binding.path.resolve()).casefold()
    )
    content = b"" if material is None else material.raw
    profile_record = record
    if local_record is not None:
        profile_record = replace(
            record,
            description=record.description if record.description is not None else local_record.description,
            version=record.version if record.version is not None else local_record.version,
        )
    fingerprint = _fingerprint(profile_record, content)
    previous = cache.get(record.id)
    if previous is not None and previous.fingerprint != fingerprint:
        cache._stale[record.id] = replace(previous, stale=True)
    profile = BasicProfile(
        id=record.id,
        name=profile_record.name,
        description=profile_record.description,
        version=profile_record.version,
        status=profile_record.status,
        source=profile_record.source,
        provenance=profile_record.provenance,
        fingerprint=fingerprint,
        metadata_quality=classify_metadata_quality(
            name=profile_record.name,
            description=profile_record.description,
        ),
        source_binding=binding,
    )
    cache._active[record.id] = profile
    return profile


def _select_source_bindings(
    records: Sequence[CapabilityRecord],
    materials: Sequence[_SkillSourceMaterial],
) -> dict[str, SkillSourceBinding]:
    """依 merged record 的既有 authority winner 建立唯一 source binding。

    `record.source` 是 registry 已驗證的 authority decision；path 僅作同一
    source 下的 deterministic tie-breaker，不另建 filesystem precedence。
    """

    grouped: dict[str, list[_SkillSourceMaterial]] = {}
    for material in materials:
        grouped.setdefault(material.skill_id, []).append(material)
    bindings: dict[str, SkillSourceBinding] = {}
    for record in records:
        raw_candidates = tuple(grouped.get(record.id, ()))
        candidates = _unique_source_materials(raw_candidates)
        if not candidates:
            continue
        selected = [material for material in raw_candidates if material.source == record.source]
        if not selected:
            selected = candidates
        selected_material = min(selected, key=_source_material_sort_key)
        alternate_paths = tuple(
            material.path
            for material in sorted(candidates, key=_source_material_sort_key)
            if material.path != selected_material.path
        )
        bindings[record.id] = SkillSourceBinding(
            canonical_skill_id=record.id,
            path=selected_material.path,
            source=selected_material.source,
            provenance=record.provenance,
            source_kind=selected_material.spec.source_kind,
            root_kind=selected_material.spec.root_kind,
            scope=selected_material.spec.scope,
            plugin_identity=selected_material.spec.plugin_identity,
            alternate_paths=alternate_paths,
        )
    return bindings


def _unique_source_materials(materials: Sequence[_SkillSourceMaterial]) -> tuple[_SkillSourceMaterial, ...]:
    """同一 canonical ID 的 exact physical duplicate 只保留一份。"""

    unique: dict[str, _SkillSourceMaterial] = {}
    for material in materials:
        key = str(material.path.resolve()).casefold()
        unique.setdefault(key, material)
    return tuple(unique.values())


def _source_material_sort_key(material: _SkillSourceMaterial) -> tuple[object, ...]:
    """同 authority source 的 deterministic tie-break，不以目錄遍歷順序決定。"""

    return (
        material.source.casefold(),
        material.spec.root_kind,
        material.spec.scope,
        material.spec.plugin_identity or "",
        str(material.path.resolve()).casefold(),
    )


def _fingerprint(record: CapabilityRecord, skill_md: bytes) -> str:
    """以 canonical profile fields、格式版本與原始 SKILL.md bytes 計算 SHA-256。"""

    return _fingerprint_fields(record.id, record.name, record.description, record.version, skill_md)


def fingerprint_profile_content(profile: BasicProfile, skill_md: bytes) -> str:
    """依既有 Phase 1 fingerprint contract 驗證 handoff 當下的 Profile 內容。"""

    return _fingerprint_fields(profile.id, profile.name, profile.description, profile.version, skill_md)


def _fingerprint_fields(
    capability_id: str,
    name: str,
    description: str | None,
    version: str | None,
    skill_md: bytes,
) -> str:
    """共用 BasicProfile 與 final handoff 的 SHA-256 canonical input。"""

    canonical = json.dumps(
        {
            "profile_format_version": PROFILE_FORMAT_VERSION,
            "id": capability_id,
            "name": name,
            "description": description,
            "version": version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(canonical)
    digest.update(b"\0")
    digest.update(skill_md)
    return digest.hexdigest()


def _read_allowlisted_skill_contents(
    roots: Sequence[Path],
    *,
    source_prefix: str = "skill-root",
) -> tuple[dict[tuple[str, str], bytes], dict[str, Path]]:
    """只讀取 caller 明確 roots 的直接 Skill entries，回傳 bytes 與 deterministic path。"""

    result: dict[tuple[str, str], bytes] = {}
    paths: dict[str, Path] = {}
    for root_index, root in enumerate(roots):
        source = f"{source_prefix}:{root_index}"
        try:
            candidates = (
                [root]
                if (root / "SKILL.md").is_file()
                else sorted(root.iterdir(), key=lambda path: (path.name.casefold(), path.name))
            )
        except OSError:
            continue
        for candidate in candidates:
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.is_file() or skill_file.is_symlink():
                continue
            try:
                raw = skill_file.read_bytes()
                text = raw.decode("utf-8")
                metadata = _frontmatter(text)
            except (OSError, UnicodeError):
                continue
            # beta.5：存在性與 metadata 品質分離。SKILL.md 可讀且目錄 basename
            # 是 stable identity 時，malformed frontmatter 仍保留 handoff bytes；
            # 完整 handoff validation 仍在後續階段執行。
            capability_id = _canonical_skill_id(metadata, candidate) if metadata is not None else candidate.name
            if not isinstance(capability_id, str) or _CANONICAL_ID.fullmatch(capability_id) is None:
                capability_id = candidate.name
            if isinstance(capability_id, str) and _CANONICAL_ID.fullmatch(capability_id):
                result.setdefault((source, capability_id), raw)
                paths.setdefault(capability_id, skill_file)
    return result, paths


def _read_allowlisted_skill_sources_for_plan(
    plan: RootPlanSnapshot,
) -> tuple[_SkillSourceMaterial, ...]:
    """依 frozen plan 讀取 bounded source material，保留每個實體來源。"""

    return _read_allowlisted_skill_sources_for_specs(plan.roots, source_prefix="skill-root")


def _read_allowlisted_skill_sources_for_specs(
    specs: Sequence[SkillRootSpec],
    *,
    source_prefix: str,
) -> tuple[_SkillSourceMaterial, ...]:
    """讀取明確 root specs 的 exact SKILL.md，不做 package-wide search。"""

    materials: list[_SkillSourceMaterial] = []
    for root_index, spec in enumerate(specs):
        try:
            candidates = _skill_candidates(spec)
        except OSError:
            continue
        for candidate in candidates:
            source = _skill_source_label(spec, source_prefix, root_index, candidate)
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.is_file() or skill_file.is_symlink():
                continue
            try:
                raw = skill_file.read_bytes()
                text = raw.decode("utf-8")
                metadata = _frontmatter(text)
            except (OSError, UnicodeError):
                continue
            capability_id = _canonical_skill_id(metadata, candidate) if metadata is not None else candidate.name
            if not isinstance(capability_id, str) or _CANONICAL_ID.fullmatch(capability_id) is None:
                capability_id = candidate.name
            if isinstance(capability_id, str) and _CANONICAL_ID.fullmatch(capability_id):
                materials.append(_SkillSourceMaterial(capability_id, skill_file, raw, source, spec))
    return tuple(materials)


def _read_allowlisted_skill_contents_for_plan(
    plan: RootPlanSnapshot,
) -> tuple[dict[tuple[str, str], bytes], dict[str, Path]]:
    """依 immutable root plan 讀取 bounded handoff bytes，不重新建立或壓縮 roots。"""

    result: dict[tuple[str, str], bytes] = {}
    paths: dict[str, Path] = {}
    for root_index, spec in enumerate(plan.roots):
        try:
            candidates = _skill_candidates(spec)
        except OSError:
            continue
        for candidate in candidates:
            source = _skill_source_label(spec, "skill-root", root_index, candidate)
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.is_file() or skill_file.is_symlink():
                continue
            try:
                raw = skill_file.read_bytes()
                text = raw.decode("utf-8")
                metadata = _frontmatter(text)
            except (OSError, UnicodeError):
                continue
            capability_id = _canonical_skill_id(metadata, candidate) if metadata is not None else candidate.name
            if not isinstance(capability_id, str) or _CANONICAL_ID.fullmatch(capability_id) is None:
                capability_id = candidate.name
            if isinstance(capability_id, str) and _CANONICAL_ID.fullmatch(capability_id):
                result.setdefault((source, capability_id), raw)
                paths.setdefault(capability_id, skill_file)
    return result, paths


def _read_allowlisted_skill_contents_for_specs(
    specs: Sequence[SkillRootSpec],
) -> tuple[dict[tuple[str, str], bytes], dict[str, Path]]:
    """依 manifest 宣告的 Plugin Skill roots 讀取一層 bounded handoff bytes。

    這個相容路徑保留 declaration 順序，避免既有 explicit caller roots 的
    first-root precedence 被 RootPlan 的 canonical path 排序改變；它不會展開
    Plugin package，也不會把 child Skill directory 重新建立成 root。
    """

    result: dict[tuple[str, str], bytes] = {}
    paths: dict[str, Path] = {}
    for root_index, spec in enumerate(specs):
        try:
            candidates = _skill_candidates(spec)
        except OSError:
            continue
        for candidate in candidates:
            source = _skill_source_label(spec, "plugin-skill-root", root_index, candidate)
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.is_file() or skill_file.is_symlink():
                continue
            try:
                raw = skill_file.read_bytes()
                text = raw.decode("utf-8")
                metadata = _frontmatter(text)
            except (OSError, UnicodeError):
                continue
            capability_id = _canonical_skill_id(metadata, candidate) if metadata is not None else candidate.name
            if not isinstance(capability_id, str) or _CANONICAL_ID.fullmatch(capability_id) is None:
                capability_id = candidate.name
            if isinstance(capability_id, str) and _CANONICAL_ID.fullmatch(capability_id):
                result.setdefault((source, capability_id), raw)
                paths.setdefault(capability_id, skill_file)
    return result, paths
