"""Validated HTTP request and response models for the AI-DND API."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    engine: Literal["AI-DND"] = "AI-DND"
    model: Literal["qwen3:8b"] = "qwen3:8b"


class SessionResponse(BaseModel):
    session_id: str
    state: dict[str, Any]


class ReadyTriggerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["actor_moves", "actor_attacks"]
    actor_id: str = Field(min_length=1, max_length=128)


class ReadyResponseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["attack", "move"]
    target_id: str | None = None
    distance_ft: int | None = Field(default=None, gt=0, strict=True)


class EconomyStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["attack", "continue_attack", "move", "dash", "ready", "react", "decline_reaction", "end_turn", "species",
                  "disengage", "dodge", "help", "hide", "influence", "magic", "search", "study", "utilize"]
    resource: Literal["action", "bonus"] = "action"
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    distance_ft: int | None = Field(default=None, gt=0, strict=True)
    trigger: ReadyTriggerInput | None = None
    response: ReadyResponseInput | None = None
    opportunity_id: str | None = None
    ability: str | None = None
    form: str | None = None


class CombatActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[EconomyStepInput] = Field(min_length=1, max_length=8)


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    interaction_mode: Literal["say", "do", "ask_dm"] | None = None
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    action_id: UUID | None = None
    combat_action: CombatActionInput | None = None
    combat_id: str | None = Field(default=None, min_length=1, max_length=128)
    combat_round: int | None = Field(default=None, ge=1, strict=True)
    combat_turn_index: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def complete_combat_context(self):
        fields = (self.combat_id, self.combat_round, self.combat_turn_index)
        if any(v is not None for v in fields) and any(v is None for v in fields):
            raise ValueError("Combat context must include ID, round and turn index.")
        return self

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be empty.")
        return value

    @field_validator("action_id")
    @classmethod
    def action_id_must_be_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.version != 4:
            raise ValueError("Action ID must be a UUIDv4.")
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
    combat_id: str | None = None
    status: Literal["active", "ended", "death_resolution"]
    round: int = Field(ge=0)
    initiative_order: list[str]
    current_turn_index: int = Field(ge=0)
    current_actor_id: str | None = None
    turn_owner: str | None = None
    participants: list[str]
    participant_records: list[CombatParticipantState]
    target_id: str | None = None
    end_reason: str | None = None
    action_economy: dict[str, Any] | None = None


class DeathResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["NORMAL", "PERMADEATH", "IRONMAN"]
    outcome: Literal["rolled_back", "dead"]
    cause: Literal["massive_damage", "failed_death_saves"]
    rolled_back: bool
    terminal: bool


class DeathSaveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roll: int = Field(ge=1, le=20)
    outcome: Literal[
        "success",
        "failure",
        "natural_1",
        "stable",
        "revived",
        "dead",
        "rolled_back",
    ]
    successes: int = Field(ge=0, le=3)
    failures: int = Field(ge=0, le=3)
    stable: bool
    dead: bool
    prone: bool
    action_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    resolution_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    death_resolution: DeathResolutionResult | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class DeathStateProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["NORMAL", "PERMADEATH", "IRONMAN"]
    status: Literal["active", "unconscious", "stable", "dead"]
    successes: int = Field(ge=0, le=3)
    failures: int = Field(ge=0, le=3)
    stable: bool
    dead: bool
    terminal: bool
    prone: bool
    last_death_save: DeathSaveResult | None = None
    last_resolution: DeathResolutionResult | None = None


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
    damage_type: str | None = None
    attack_rolls: list[int] | None = None
    disadvantage: bool | None = None
    hp_damage: int | None = None
    temporary_hp_before: int | None = None
    temporary_hp_absorbed: int | None = None
    temporary_hp_after: int | None = None
    species_effects: list[dict[str, Any]] | None = None
    action_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    resolution_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    critical_state: str | None = Field(default=None, exclude_if=lambda value: value is None)
    resolution: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)
    death_save: DeathSaveResult | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    death_resolution: DeathResolutionResult | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class CombatTurnResult(CombatAttackResult):
    economy_steps: list[dict[str, Any]] | None = None
    combat_id: str | None = None
    combat_status: str | None = None
    round: int | None = None
    current_turn_index: int | None = None
    spell: str | None = None
    casting_ability: str | None = None
    attack_or_save: str | None = None
    save_roll: int | None = None
    save_dc: int | None = None
    healing: int | None = None
    slot_spent: bool | None = None
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
    d20_rolls: list[int] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    advantage: bool | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    proficient: bool
    ability_modifier: int
    proficiency_modifier: int = Field(ge=0)
    total_modifier: int
    total: int
    difficulty: Literal["easy", "medium", "hard", "very_hard", "extreme"]
    dc: int = Field(ge=1, le=30)
    outcome: Literal["success", "failure"]
    disadvantage: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    expertise: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    action_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    resolution_id: str | None = Field(default=None, exclude_if=lambda value: value is None)


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


class LevelUpResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_level: int = Field(ge=1, le=4)
    new_level: int = Field(ge=1, le=4)
    xp_gained: int = Field(ge=1)
    hit_points_gained: int = Field(ge=0)

    @model_validator(mode="after")
    def levels_do_not_go_backwards(self):
        if self.new_level < self.previous_level:
            raise ValueError("A level-up cannot lower the character's level.")
        return self


class AmbientEventActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=36, max_length=36)
    action: Literal["interact", "observe"]

    @field_validator("action_id")
    @classmethod
    def action_id_must_be_uuid4(cls, value: str) -> str:
        try:
            parsed = UUID(value)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Action ID must be a UUIDv4.") from None
        if parsed.version != 4 or str(parsed) != value.lower():
            raise ValueError("Action ID must be a UUIDv4.")
        return str(parsed)


class AmbientEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_instance_id: str = Field(min_length=1, max_length=96)
    action_id: str = Field(min_length=36, max_length=36)
    status: Literal["APPLIED", "REJECTED", "NO_EFFECT", "ALREADY_APPLIED"]
    reason_code: str | None = Field(default=None, max_length=64)
    transition_id: str | None = Field(default=None, max_length=160)
    canonical_event_id: str | None = Field(default=None, max_length=36)


class AmbientEventCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    state: dict[str, Any]
    result: AmbientEventResult


class TurnOutcome(BaseModel):
    """Player-safe receipt of what the turn actually resolved (LR00-P5).

    Only names the player can already see; never hidden IDs, DCs or secrets.
    """

    model_config = ConfigDict(extra="forbid")

    action: str | None = Field(default=None, max_length=48)
    status: str | None = Field(default=None, max_length=48)
    kind: str | None = Field(default=None, max_length=48)
    target_name: str | None = Field(default=None, max_length=120)
    found: bool | None = None
    place_created: bool | None = None


class TurnResponse(BaseModel):
    session_id: str
    action_id: str
    narration: str
    state: dict[str, Any]
    combat_result: CombatTurnResult | None = None
    combat_history_entry: CombatHistoryEntry | None = None
    skill_check_result: SkillCheckResult | None = None
    quest_outcomes: list[QuestOutcome] = []
    level_up: LevelUpResult | None = None
    turn_outcome: TurnOutcome | None = None


class TurnUndoRequest(BaseModel):
    """Undo exactly the last completed turn, named by its action ID (LR00-P7)."""

    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    target_action_id: UUID


class TurnUndoResponse(BaseModel):
    session_id: str
    action_id: str
    undone_action_id: str
    narration: str
    state: dict[str, Any]


class SpeciesTraitActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "healing_hands",
        "celestial_revelation",
        "large_form",
        "adrenaline_rush",
        "cloud_jaunt",
        "arm_giant_ancestry",
        "choose_giant_ancestry",
        "short_rest",
        "long_rest",
    ]
    form: Literal[
        "heavenly_wings", "inner_radiance", "necrotic_shroud"
    ] | None = None
    ancestry: Literal["cloud", "fire", "frost", "hill", "stone", "storm"] | None = None
    armed: bool | None = None
    action_id: UUID | None = None

    @field_validator("action_id")
    @classmethod
    def valid_action_identity(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.version != 4:
            raise ValueError("Action ID must be a UUIDv4.")
        return value

    @model_validator(mode="after")
    def optional_fields_match_action(self) -> "SpeciesTraitActionRequest":
        if (self.action == "celestial_revelation") != (self.form is not None):
            raise ValueError("Choose one Celestial Revelation form.")
        if (self.action == "choose_giant_ancestry") != (self.ancestry is not None):
            raise ValueError("Choose one Giant Ancestry.")
        if self.action != "arm_giant_ancestry" and self.armed is not None:
            raise ValueError("The armed flag is only valid for Giant Ancestry.")
        return self


class SpeciesTraitActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    message: str = Field(min_length=1, max_length=500)
    effects: dict[str, Any]


class SpeciesTraitCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    action_id: str | None = None
    state: dict[str, Any]
    result: SpeciesTraitActionResult


class CharacterCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["custom", "random"]
    name: str | None = Field(default=None, min_length=1, max_length=40)
    race: str | None = None
    character_class: str | None = Field(default=None, alias="class")
    species: str | None = None
    giant_ancestry: Literal["cloud", "fire", "frost", "hill", "stone", "storm"] | None = None
    background: str | None = None
    alignment: str | None = None
    ability_score_method: str | None = None
    ability_scores: dict[str, int] | None = None
    background_ability_bonuses: dict[str, int] | None = None
    proficient_skills: list[str] | None = None
    expertise_skills: list[str] | None = None
    proficient_tools: list[str] | None = None
    origin_feat: str | None = None
    species_bonus_feat: str | None = None
    species_bonus_skills: list[str] | None = None
    fighting_style: str | None = None
    equipment_package: str | None = None
    equipment_choices: list[str] | None = None
    cantrips: list[str] | None = None
    spells: list[str] | None = None
    languages: list[str] | None = None
    background_equipment_option: Literal["A", "B"] | None = None
    origin: str | None = Field(default=None, max_length=240)
    appearance: str | None = Field(default=None, max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    backstory: str | None = Field(default=None, max_length=2000)

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
        custom_fields = (
            self.name,
            self.race,
            self.character_class,
            self.species,
            self.giant_ancestry,
            self.background,
            self.alignment,
            self.ability_score_method,
            self.ability_scores,
            self.background_ability_bonuses,
            self.proficient_skills,
            self.expertise_skills,
            self.proficient_tools,
            self.origin_feat,
            self.species_bonus_feat,
            self.species_bonus_skills,
            self.fighting_style,
            self.equipment_package,
            self.equipment_choices,
            self.cantrips,
            self.spells,
            self.languages,
            self.background_equipment_option,
            self.origin,
            self.appearance,
            self.personality,
            self.backstory,
        )
        if self.mode == "custom":
            if (
                self.name is None
                or (self.race is None and self.species is None)
                or self.character_class is None
            ):
                raise ValueError(
                    "Custom character creation requires a name, race, and class."
                )
            selected_species = self.species or self.race
            if selected_species == "Goliath" and self.giant_ancestry is None:
                raise ValueError("Goliath characters must choose a Giant Ancestry.")
            if selected_species != "Goliath" and self.giant_ancestry is not None:
                raise ValueError("Giant Ancestry is only available to Goliaths.")
        elif any(value is not None for value in custom_fields):
            raise ValueError(
                "Random character creation does not accept custom character fields."
            )
        return self


class CharacterCreationOptions(BaseModel):
    races: list[str]
    classes: list[str]


class CharacterCreationCatalogResponse(BaseModel):
    races: dict[str, Any]
    classes: dict[str, Any]
    backgrounds: dict[str, Any]
    ability_score_methods: list[dict[str, Any]]
    alignments: list[dict[str, Any]]
    origin_feats: dict[str, Any]
    spells_catalog: dict[str, Any]
    skills: dict[str, Any]
    equipment_rules: dict[str, Any]


class CampaignStartSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setting_id: str = Field(min_length=1, max_length=128)
    region_pack_id: str = Field(min_length=1, max_length=128)
    region_id: str = Field(min_length=1, max_length=128)
    starting_location_id: str = Field(min_length=1, max_length=128)

    @field_validator(
        "setting_id",
        "region_pack_id",
        "region_id",
        "starting_location_id",
    )
    @classmethod
    def selection_ids_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Campaign start selections must not be blank.")
        return cleaned


class CampaignStartLocationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    name: str


class CampaignStartRegionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region_pack_id: str
    region_id: str
    name: str
    epoch_id: str
    coverage_status: str
    starting_locations: list[CampaignStartLocationOption]


class CampaignStartSettingOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setting_id: str
    name: str
    regions: list[CampaignStartRegionOption]


class CampaignStartOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: list[CampaignStartSettingOption]


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    character: CharacterCreateInput | None = None
    campaign_start: CampaignStartSelection | None = None
    death_mode: Literal["NORMAL", "PERMADEATH", "IRONMAN"] = "NORMAL"

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
    # Derived from an accepted immutable turn receipt; not a new save field.
    skill_check_result: SkillCheckResult | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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