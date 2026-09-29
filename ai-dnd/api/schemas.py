"""Validated HTTP request and response models for the AI-DND API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    engine: Literal["AI-DND"] = "AI-DND"
    model: Literal["qwen3:8b"] = "qwen3:8b"


class SessionResponse(BaseModel):
    session_id: str
    state: dict[str, Any]


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    target_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be empty.")
        return value

    @field_validator("target_id")
    @classmethod
    def target_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Target ID must not be blank.")
        return cleaned


class CombatParticipantState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    kind: Literal["player", "npc"]
    name: str = Field(min_length=1, max_length=120)
    current_hp: int = Field(ge=0)
    max_hp: int = Field(ge=1)
    armor_class: int = Field(ge=0)
    status: str
    primary_action_available: bool
    is_current_actor: bool


class CombatStateProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
    status: Literal["active", "ended"]
    round: int = Field(ge=0)
    initiative_order: list[str]
    current_turn_index: int = Field(ge=0)
    current_actor_id: str | None = None
    turn_owner: str | None = None
    participants: list[str]
    participant_records: list[CombatParticipantState]
    target_id: str | None = None
    end_reason: str | None = None


class CombatAttackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str | None = None
    status: str | None = None
    success: bool | None = None
    outcome: str | None = None
    actor: str | None = None
    actor_name: str | None = None
    target: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    weapon: str | None = None
    attack_roll: int | None = None
    attack_bonus: int | None = None
    attack_total: int | None = None
    target_ac: int | None = None
    critical: bool | None = None
    damage: int | None = None
    target_hp_before: int | None = None
    target_hp_after: int | None = None
    target_status: str | None = None


class CombatTurnResult(CombatAttackResult):
    combat_started: bool | None = None
    combat_ended: bool | None = None
    end_reason: str | None = None
    current_actor_id: str | None = None
    turn_owner: str | None = None
    enemy_action: CombatAttackResult | None = None
    enemy_actions: list[CombatAttackResult] | None = None


class CombatHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    turn_index: int = Field(ge=0)
    result: CombatTurnResult


class SkillCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str = Field(min_length=1, max_length=40)
    ability: Literal[
        "strength",
        "dexterity",
        "constitution",
        "intelligence",
        "wisdom",
        "charisma",
    ]
    d20: int = Field(ge=1, le=20)
    proficient: bool
    ability_modifier: int
    proficiency_modifier: int = Field(ge=0)
    total_modifier: int
    total: int
    difficulty: Literal["easy", "medium", "hard", "very_hard", "extreme"]
    dc: int = Field(ge=1, le=30)
    outcome: Literal["critical_success", "success", "failure", "critical_failure"]


class QuestOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    quest_id: str
    transition: Literal[
        "accepted", "objective_progress", "objective_completed", "completed", "cancelled"
    ]
    objective_id: str | None = None
    source_event_id: str
    turn_index: int = Field(ge=0)


class QuestObjectiveState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    status: Literal["active", "completed", "cancelled"]
    progress: int = Field(ge=0)
    required_count: int = Field(ge=1, le=1000)


class QuestObjectiveOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    kind: Literal["visit_location", "defeat_entity", "acquire_item"]
    target: str = Field(min_length=1, max_length=160)
    required_count: int = Field(ge=1, le=1000)


class QuestState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quest_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    status: Literal["accepted", "completed", "cancelled"]
    giver_npc_id: str | None = Field(default=None, max_length=120)
    objectives: list[QuestObjectiveState]


class QuestOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quest_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    giver_npc_id: str | None = Field(default=None, max_length=120)
    objectives: list[QuestObjectiveOffer]


class QuestCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    state: dict[str, Any]
    quest: QuestState
    outcome: QuestOutcome | None


class TurnResponse(BaseModel):
    session_id: str
    narration: str
    state: dict[str, Any]
    combat_result: CombatTurnResult | None = None
    combat_history_entry: CombatHistoryEntry | None = None
    skill_check_result: SkillCheckResult | None = None
    quest_outcomes: list[QuestOutcome] = []


class CharacterCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["custom", "random"]
    name: str | None = Field(default=None, min_length=1, max_length=40)
    race: str | None = None
    character_class: str | None = Field(default=None, alias="class")

    @field_validator("name")
    @classmethod
    def character_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Character name must not be blank.")
        return cleaned

    @model_validator(mode="after")
    def fields_must_match_creation_mode(self) -> "CharacterCreateInput":
        if self.mode == "custom":
            if self.name is None or self.race is None or self.character_class is None:
                raise ValueError(
                    "Custom character creation requires a name, race, and class."
                )
        elif any(
            value is not None
            for value in (self.name, self.race, self.character_class)
        ):
            raise ValueError(
                "Random character creation does not accept custom character fields."
            )
        return self


class CharacterCreationOptions(BaseModel):
    races: list[str]
    classes: list[str]


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    character: CharacterCreateInput | None = None

    @field_validator("name")
    @classmethod
    def campaign_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Campaign name must not be blank.")
        return cleaned


class CampaignSummary(BaseModel):
    campaign_id: str
    name: str
    created_at: str
    updated_at: str
    last_played_at: str
    save_version: int
    character_name: str
    character_race: str
    character_class: str
    character_level: int
    location: str


class CampaignHistoryEntry(BaseModel):
    player_message: str
    narration: str
    created_at: str


class CampaignDetailResponse(BaseModel):
    campaign: CampaignSummary
    state: dict[str, Any]
    history: list[CampaignHistoryEntry]
    combat_history: list[CombatHistoryEntry]


class CampaignSessionResponse(BaseModel):
    campaign_id: str
    session_id: str
    name: str
    state: dict[str, Any]
    history: list[CampaignHistoryEntry]
    combat_history: list[CombatHistoryEntry]