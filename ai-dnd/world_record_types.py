"""Shapes of the saved records world_threads, bold_acts and living_world pass around.

Annotations only: these are TypedDicts, so a record stays a plain dict at run time. A key is
Required only when every producer sets it; any other key is NotRequired. The three modules
import this under TYPE_CHECKING, so nothing here is loaded when the game runs.
"""

from typing import Any, NotRequired, Required, TypedDict


class ThreadTerms(TypedDict):
    pay: int | None
    work_days: int | None
    pay_basis: str | None
    pay_timing: str | None
    deadline_text: str | None


class Thread(TypedDict, total=False):
    """One job record, built by world_threads._open_thread and moved on by the job machine."""

    thread_id: Required[str]
    template_id: Required[str]
    type: Required[str]
    status: Required[str]
    settlement_id: Required[str]
    place_id: Required[str]
    owner_name: Required[str]
    target_place_id: Required[str | None]
    recipient_name: Required[str | None]
    terms: Required[ThreadTerms]
    public_line: Required[str]
    owner_line: Required[str]
    opened_at: Required[int]
    expires_at: Required[int]
    heard_turn: Required[int | None]
    closed_at: Required[int | None]
    night_only: bool
    item_noun: str | None
    status_lines: Any
    offered_turn: int | None
    offered_at: int | None
    declined_turn: int | None
    accepted_at: int | None
    accepted_turn: int | None
    starts_at: int | None
    work_until: int | None
    days_worked: int | None
    shift_seconds: int | None
    shift_until: int | None
    last_paid_day_index: int | None
    paid_cp: int | None
    outcome_known_turn: int | None
    offer_line_turn: int | None
    fires_at: int | None
    xp_due: int | None
    xp_forfeited: bool
    owner_npc_id: str | None
    recipient_npc_id: str | None
    quest_id: str | None
    filled_by_npc_id: str | None
    filled_by_name: str | None
    offer_line: str | None
    job_line: str | None
    letter_line: str | None
    offered_terms_shown: dict[str, Any]
    log: list[dict[str, Any]]
    close_failed: dict[str, Any]
    seal_broken: bool
    parcel_gone: bool
    delivered_late: bool


class ThreadState(TypedDict):
    """world[world_threads.KEY]: seeded by _new_state, extended lazily by ensure and world_happenings."""

    version: int
    seeded: list[str]
    next_number: int
    last_tick: int
    threads: list[Thread]
    history: list[Thread]
    happenings: NotRequired[list[dict[str, Any]]]
    overheard: NotRequired[list[Any]]
    links: NotRequired[list[dict[str, Any]]]
    next_link: NotRequired[int]


class Deed(TypedDict, total=False):
    """One row of the deed ledger, made by bold_acts.remember and world_reactions.promise_broken."""

    kind: Required[str]
    text: Required[str]
    location: Required[str | None]
    victim_id: Required[str | None]
    witnesses: Required[list[str]]
    turn: Required[int]
    at: Required[int]
    heard: Required[list[str]]
    told: Required[list[str]]
    found_at: int
    found_by: Any
    taken_at: int
    seen_near: list[str]
    described: list[str]
    challenged: Any
    hold: dict[str, Any]
    in_fight: Any
    item: Any
    knocked_out: Any
    overheard: Any
    post: Any
    post_shown: Any
    reach: Any
    rumour: Any
    searched_at: int
    searches: Any
    settled: Any
    shown: Any
    till: Any
    watch_id: Any
    watch_shown: Any


class Fire(TypedDict):
    """One burning place, made by bold_acts._burn."""

    location: str | None
    lit_at: int
    stage: int
    feature_id: str | None


class SceneOpening(TypedDict):
    text: str
    tone: str
    event_id: str
    variation_id: str


class AmbientEvent(TypedDict):
    event_id: str
    instance_id: str
    variation_id: str
    event_type: str
    repeat_group: Any
    count: int
    referent_id: NotRequired[str]


class SceneReferent(TypedDict):
    id: str
    scene_id: str
    location_id: str
    kind: str
    description: str
    aliases: list[str]
    source_turn: int
    expires_after_turn: int
    lifecycle: str
    promoted_npc_id: str | None
    event_instance_id: str | None


class SceneRecord(TypedDict):
    id: str
    location_id: str
    parent_location_id: str | None
    kind: str
    materialized: bool
    visit_revision: int
    activity_revision: int
    first_seen_turn: int
    last_visit_turn: int | None
    last_activity_turn: int | None
    last_beat: str | None
    referents: list[SceneReferent]
    opening: NotRequired[SceneOpening]
    ambient_event: NotRequired[AmbientEvent]
