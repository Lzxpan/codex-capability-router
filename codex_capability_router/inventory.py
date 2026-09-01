"""Phase 1 Skill inventory、Basic Profile cache 與 content fingerprint。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .discovery import _canonical_skill_id, _frontmatter, discover_skill_roots
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

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：inventory 以 Host exposure evidence 作為 Skill availability gate，缺少 Host evidence 的 trusted-root Skill 會被降為 unknown。
# 修改原因：Skill availability 與 Provider availability 分離；trusted root 的合法 discovery/handoff safety 才是 Skill formal availability 基礎。
# 修改後功能：trusted-root valid record 直接進入 formal availability，Host exposure 僅保存 optional observation；仍保留 bounded diagnostics、reference-only metrics 與 Python non-semantic boundary。


# ponytail: cache 只保留記憶體中的 Basic Profile；若未來需要跨程序持久化，先補 privacy/eviction 規格再加入 storage。
PROFILE_FORMAT_VERSION = "phase1-basic-profile-v1"
_AVAILABLE_STATUSES = frozenset({CapabilityStatus.INSTALLED, CapabilityStatus.AVAILABLE})
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
    """本次 refresh 的 Skill records、Basic Profiles 與可用 eligibility 結果。"""

    records: tuple[CapabilityRecord, ...] = ()
    profiles: tuple[BasicProfile, ...] = ()
    available_records: tuple[CapabilityRecord, ...] = ()
    diagnostics: tuple[DiscoveryDiagnostic, ...] = ()
    partial: bool = False
    _skill_paths: dict[str, Path] = field(default_factory=dict, repr=False, compare=False)
    host_exposed_skill_ids: tuple[str, ...] = ()
    router_available_skill_ids: tuple[str, ...] = ()
    # 新增欄位置於既有欄位之後，保留既有 positional compatibility。
    trusted_root_skill_ids: tuple[str, ...] = ()


def refresh_skill_inventory(
    roots: Sequence[Path],
    *,
    cache: ProfileCache | None = None,
    runtime: DiscoveryResult | None = None,
    cli: DiscoveryResult | None = None,
    manual: DiscoveryResult | None = None,
    host_exposure: HostSkillExposureEnvelope | None = None,
) -> SkillInventory:
    """重新 discovery/merge 明確 roots，並以本次來源更新 Skill Profile cache。

    使用方式：每次 route 前傳入當次 runtime/CLI/manual discovery 結果；函式
    不從 cache 推導 availability，也不執行 command、安裝能力或保存原始文件。
    """

    active_cache = cache or ProfileCache()
    root_result = discover_skill_roots(roots)
    source_results = tuple(result for result in (runtime, cli, root_result, manual) if result is not None)
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
    for local_record in root_result.records:
        local_records.setdefault(local_record.id, local_record)
    skill_contents, skill_paths = _read_allowlisted_skill_contents(roots)
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
    handoff_ready_ids = trusted_root_ids.intersection(skill_paths)
    records = tuple(
        replace(record, status=CapabilityStatus.AVAILABLE)
        if record.id in trusted_root_ids and record.status == CapabilityStatus.UNKNOWN
        else record
        for record in records
    )
    profiles = tuple(
        _refresh_profile(active_cache, record, skill_contents, local_records.get(record.id))
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
        and record.status in _AVAILABLE_STATUSES
        and not _is_controller(record)
        and not record.routing_support
    )
    diagnostics = tuple(
        diagnostic
        for result in source_results
        for diagnostic in result.diagnostics
    ) + merged.diagnostics
    return SkillInventory(
        records=records,
        profiles=profiles,
        available_records=available_records,
        diagnostics=diagnostics,
        partial=any(result.partial for result in source_results),
        _skill_paths=skill_paths,
        trusted_root_skill_ids=tuple(sorted(trusted_root_ids, key=lambda value: (value.casefold(), value))),
        host_exposed_skill_ids=host_exposed_ids,
        router_available_skill_ids=tuple(record.id for record in available_records),
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
    available_ids = {record.id for record in inventory.available_records}
    profiles = tuple(profile for profile in inventory.profiles if profile.id in available_ids)
    # 只有目前未進入 formal available inventory 的 recalled profile 才能進 diagnostic；
    # trusted-root valid Skill 已在 refresh 時升格為 available，不會因 Host 缺失而誤入這裡。
    unknown_profiles = tuple(
        profile for profile in inventory.profiles if profile.status == CapabilityStatus.UNKNOWN
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
    skill_contents: dict[tuple[str, str], bytes],
    local_record: CapabilityRecord | None,
) -> BasicProfile:
    """用目前 record 與明確 root 的 SKILL.md 更新單一 Basic Profile。"""

    content = skill_contents.get((record.source, record.id))
    if content is None:
        content = next(
            (value for (source, capability_id), value in skill_contents.items() if capability_id == record.id),
            b"",
        )
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
    )
    cache._active[record.id] = profile
    return profile


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
) -> tuple[dict[tuple[str, str], bytes], dict[str, Path]]:
    """只讀取 caller 明確 roots 的直接 Skill entries，回傳 bytes 與 deterministic path。"""

    result: dict[tuple[str, str], bytes] = {}
    paths: dict[str, Path] = {}
    for root_index, root in enumerate(roots):
        source = f"skill-root:{root_index}"
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
                metadata = _frontmatter(raw.decode("utf-8"))
            except (OSError, UnicodeError):
                continue
            if metadata is None:
                continue
            capability_id = _canonical_skill_id(metadata, candidate)
            if isinstance(capability_id, str) and _CANONICAL_ID.fullmatch(capability_id):
                result.setdefault((source, capability_id), raw)
                paths.setdefault(capability_id, skill_file)
    return result, paths
