"""Validated HTTP request and response models for the AI-DND API."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator, model_validator

from api.local_model_config import DEFAULT_LOCAL_MODEL, LocalModelName

from api.local_model_config import DEFAULT_LOCAL_MODEL, LocalModelName


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    engine: Literal["AI-DND"] = "AI-DND"
    model: LocalModelName = DEFAULT_LOCAL_MODEL
    # Present only while the cloud chain is on: every model that may answer, in order.
    model_chain: list[str] | None = None


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
                  "disengage", "dodge", "help", "hide", "influence", "magic", "search", "study", "utilize", "convert_spell_slot", "activate_rage", "extend_rage",
                  "second_wind", "action_surge", "lay_on_hands", "divine_smite", "divine_sense", "cunning_action", "steady_aim", "uncanny_dodge",
                  "martial_arts_strike", "flurry_of_blows", "flurry_strike", "patient_defense", "step_of_the_wind",
                  "uncanny_metabolism", "set_deflect_attacks"]
    resource: Literal["action", "bonus"] = "action"
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    distance_ft: int | None = Field(default=None, gt=0, strict=True)
    trigger: ReadyTriggerInput | None = None
    response: ReadyResponseInput | None = None
    opportunity_id: str | None = None
    ability: str | None = None
    form: str | None = None
    slot_level: int | None = Field(default=None, ge=1, le=9, strict=True)
    reckless_attack: StrictBool | None = None
    metamagic: Literal["quickened_spell"] | None = None
    healing_amount: int | None = Field(default=None, gt=0, strict=True)
    remove_poisoned: StrictBool | None = None
    sacred_weapon: StrictBool | None = None
    radiant_damage: StrictBool | None = None
    cunning_option: Literal["dash", "disengage"] | None = None
    cunning_strike: Literal["poison", "trip", "withdraw"] | None = None
    cunning_strike_move_ft: int | None = Field(default=None, gt=0, strict=True)
    uncanny_dodge_enabled: StrictBool | None = None
    stunning_strike: StrictBool | None = None
    open_hand_technique: Literal["push", "topple"] | None = None
    spend_focus: StrictBool | None = None
    deflect_mode: Literal["off", "reduce", "redirect"] | None = None

    @model_validator(mode="after")
    def monk_fields_stay_on_their_steps(self):
        set_fields = {name for name in ("stunning_strike", "open_hand_technique", "spend_focus", "deflect_mode") if getattr(self, name) is not None}
        strikes = {"martial_arts_strike", "flurry_of_blows", "flurry_strike"}
        allowed = ({"stunning_strike", "open_hand_technique"} if self.kind in strikes
                   else {"stunning_strike"} if self.kind in {"attack", "continue_attack"}
                   else {"spend_focus"} if self.kind in {"patient_defense", "step_of_the_wind"}
                   else {"deflect_mode"} if self.kind == "set_deflect_attacks" else set())
        if set_fields - allowed:
            raise ValueError("This step does not take that Monk field.")
        if self.kind == "set_deflect_attacks" and self.deflect_mode is None:
            raise ValueError("Deflect Attacks needs a setting.")
        if self.kind in strikes and not self.target_id:
            raise ValueError("An Unarmed Strike needs a target.")
        return self

    @model_validator(mode="after")
    def slot_selection_requires_magic(self):
        if self.kind in {"lay_on_hands", "divine_smite", "divine_sense"}:
            allowed = {"lay_on_hands": {"healing_amount", "remove_poisoned"}, "divine_smite": {"slot_level"}, "divine_sense": set()}[self.kind]
            if self.resource != "bonus" or "resource" not in self.model_fields_set or self.model_fields_set - {"kind", "resource"} - allowed:
                raise ValueError("This Paladin feature requires one explicit Bonus Action and only its own fields.")
            if self.kind == "lay_on_hands" and (self.remove_poisoned is False or (self.healing_amount is None and not self.remove_poisoned)):
                raise ValueError("Lay On Hands needs Hit Points to restore, removing Poisoned, or both.")
            return self
        if self.healing_amount is not None or self.remove_poisoned is not None:
            raise ValueError("Only Lay On Hands takes these fields.")
        if (self.sacred_weapon is not None or self.radiant_damage is not None) and self.kind not in {"attack", "continue_attack"}:
            raise ValueError("Sacred Weapon choices belong on an attack of the Attack action.")
        if self.kind in {"activate_rage", "extend_rage"}:
            if self.resource != "bonus" or self.model_fields_set != {"kind", "resource"}:
                raise ValueError("Rage requires one explicit Bonus Action and no other step fields.")
            return self
        if self.kind == "second_wind":
            if self.resource != "bonus" or "resource" not in self.model_fields_set or self.model_fields_set - {"kind", "resource", "distance_ft"}:
                raise ValueError("Second Wind requires one explicit Bonus Action and at most a Tactical Shift distance.")
            return self
        if self.kind == "action_surge":
            if self.model_fields_set != {"kind"}:
                raise ValueError("Action Surge takes no other step fields.")
            return self
        if self.kind == "cunning_action":
            if self.resource != "bonus" or self.cunning_option is None or self.model_fields_set != {"kind", "resource", "cunning_option"}:
                raise ValueError("Cunning Action requires one explicit Bonus Action and one option.")
            return self
        if self.kind == "steady_aim":
            if self.resource != "bonus" or self.model_fields_set != {"kind", "resource"}:
                raise ValueError("Steady Aim requires one explicit Bonus Action and no other step fields.")
            return self
        if self.kind == "uncanny_dodge":
            if self.uncanny_dodge_enabled is None or self.model_fields_set != {"kind", "uncanny_dodge_enabled"}:
                raise ValueError("Uncanny Dodge takes only its on or off choice.")
            return self
        if (self.cunning_option is not None or self.uncanny_dodge_enabled is not None
                or ((self.cunning_strike is not None or self.cunning_strike_move_ft is not None) and self.kind not in {"attack", "continue_attack"})):
            raise ValueError("These Rogue fields belong to their own step or to an attack.")
        if self.kind == "convert_spell_slot":
            if self.slot_level not in {1, 2, 3} or self.resource != "action":
                raise ValueError("Slot conversion requires a supported slot level and no action resource override.")
            if self.model_fields_set - {"kind", "slot_level", "resource"}:
                raise ValueError("Slot conversion accepts only its slot selection.")
            return self
        if self.metamagic is not None and (self.kind != "magic" or self.ability != "Magic Missile"):
            raise ValueError("Quickened Spell is only supported for Magic Missile.")
        if self.reckless_attack is not None and self.kind not in {"attack", "continue_attack", "react"}:
            raise ValueError("Reckless Attack is only a choice on an attack roll.")
        if self.slot_level is not None and self.kind != "magic":
            raise ValueError("Only a Magic action can select a spell slot.")
        return self


class CombatActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[EconomyStepInput] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def conversion_is_single_step(self):
        if any(step.kind in {"activate_rage", "extend_rage"} for step in self.steps) and len(self.steps) != 1:
            raise ValueError("Rage must be submitted as one explicit step.")
        if any(step.kind in {"second_wind", "action_surge"} for step in self.steps) and len(self.steps) != 1:
            raise ValueError("Second Wind and Action Surge must be submitted as one explicit step.")
        if any(step.kind in {"lay_on_hands", "divine_smite", "divine_sense"} for step in self.steps) and len(self.steps) != 1:
            raise ValueError("Lay On Hands, Divine Smite and Divine Sense must be submitted as one explicit step.")
        if any(step.kind in {"cunning_action", "steady_aim", "uncanny_dodge"} for step in self.steps) and len(self.steps) != 1:
            raise ValueError("Cunning Action, Steady Aim and Uncanny Dodge must be submitted as one explicit step.")
        if any(step.kind == "convert_spell_slot" for step in self.steps) and len(self.steps) != 1:
            raise ValueError("Slot conversion must be submitted as one explicit step.")
        monk_steps = {"martial_arts_strike", "flurry_of_blows", "flurry_strike", "patient_defense", "step_of_the_wind",
                      "uncanny_metabolism", "set_deflect_attacks"}
        if any(step.kind in monk_steps for step in self.steps) and len(self.steps) != 1:
            raise ValueError("A Monk feature must be submitted as one explicit step.")
        return self


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    interaction_mode: Literal["say", "do", "ask_dm"] | None = None
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    action_id: UUID | None = None
    combat_action: CombatActionInput | None = None
    check_feature: Literal["primal_knowledge", "tactical_mind"] | None = None
    combat_id: str | None = Field(default=None, min_length=1, max_length=128)
    combat_round: int | None = Field(default=None, ge=1, strict=True)
    combat_turn_index: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def complete_combat_context(self):
        fields = (self.combat_id, self.combat_round, self.combat_turn_index)
        if self.check_feature is not None and (
            self.interaction_mode != "do" or self.combat_action is not None
            or any(value is not None for value in fields)
        ):
            raise ValueError("A check feature requires an ordinary Do check without combat context.")
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

    check_feature: Literal["primal_knowledge", "tactical_mind"] | None = Field(default=None, exclude_if=lambda value: value is None)
    original_ability: Literal["dexterity", "wisdom", "charisma"] | None = Field(default=None, exclude_if=lambda value: value is None)
    tactical_mind_roll: int | None = Field(default=None, ge=1, le=10, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def consistent_check_feature(self):
        # Historical receipts validate their public annotation here, never live Rage.
        if self.check_feature != "tactical_mind" and self.tactical_mind_roll is not None:
            raise ValueError("A Tactical Mind roll requires its check feature.")
        if self.check_feature is None:
            if self.original_ability is not None:
                raise ValueError("Original ability requires a check feature.")
            return self
        if self.check_feature == "tactical_mind":
            if (self.original_ability is not None or not self.action_id or not self.resolution_id
                    or not self.resolution_id.startswith(self.action_id + ":skill_check:")):
                raise ValueError("Invalid Tactical Mind check annotation.")
            return self
        originals = {"Acrobatics": "dexterity", "Intimidation": "charisma",
                     "Perception": "wisdom", "Stealth": "dexterity", "Survival": "wisdom"}
        if (self.skill not in originals or self.ability != "strength"
                or self.original_ability != originals[self.skill]
                or not self.action_id or not self.resolution_id
                or not self.resolution_id.startswith(self.action_id + ":skill_check:")):
            raise ValueError("Invalid Primal Knowledge check annotation.")
        return self


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

    previous_level: int = Field(ge=1, le=5)
    new_level: int = Field(ge=1, le=5)
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
        "spend_hit_die",
        "second_wind",
        "lay_on_hands",
        "divine_sense",
    ]
    form: Literal[
        "heavenly_wings", "inner_radiance", "necrotic_shroud"
    ] | None = None
    ancestry: Literal["cloud", "fire", "frost", "hill", "stone", "storm"] | None = None
    armed: bool | None = None
    healing_amount: int | None = Field(default=None, gt=0, strict=True)
    remove_poisoned: StrictBool | None = None
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
        if (self.action == "lay_on_hands") != (self.healing_amount is not None or self.remove_poisoned is True) or self.remove_poisoned is False:
            raise ValueError("Lay On Hands needs Hit Points to restore, removing Poisoned, or both, and nothing else takes them.")
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


class LevelUpConIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constitution: int = Field(strict=True, ge=2, le=2)


class LevelUpStrengthIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=2, le=2)


class LevelUpIntelligenceIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intelligence: int = Field(strict=True, ge=2, le=2)


class LevelUpWisdomIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wisdom: int = Field(strict=True, ge=2, le=2)


class LevelUpCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    charisma: int = Field(strict=True, ge=2, le=2)


class LevelUpStrengthConstitutionIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=1, le=1)
    constitution: int = Field(strict=True, ge=1, le=1)


class LevelUpStrengthIntelligenceIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=1, le=1)
    intelligence: int = Field(strict=True, ge=1, le=1)


class LevelUpStrengthWisdomIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=1, le=1)
    wisdom: int = Field(strict=True, ge=1, le=1)


class LevelUpStrengthCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=1, le=1)
    charisma: int = Field(strict=True, ge=1, le=1)


class LevelUpConstitutionIntelligenceIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constitution: int = Field(strict=True, ge=1, le=1)
    intelligence: int = Field(strict=True, ge=1, le=1)


class LevelUpConstitutionWisdomIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constitution: int = Field(strict=True, ge=1, le=1)
    wisdom: int = Field(strict=True, ge=1, le=1)


class LevelUpConstitutionCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constitution: int = Field(strict=True, ge=1, le=1)
    charisma: int = Field(strict=True, ge=1, le=1)


class LevelUpIntelligenceWisdomIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intelligence: int = Field(strict=True, ge=1, le=1)
    wisdom: int = Field(strict=True, ge=1, le=1)


class LevelUpIntelligenceCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intelligence: int = Field(strict=True, ge=1, le=1)
    charisma: int = Field(strict=True, ge=1, le=1)


class LevelUpWisdomCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wisdom: int = Field(strict=True, ge=1, le=1)
    charisma: int = Field(strict=True, ge=1, le=1)


class LevelUpDexterityIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dexterity: int = Field(strict=True, ge=2, le=2)


class LevelUpStrengthDexterityIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: int = Field(strict=True, ge=1, le=1)
    dexterity: int = Field(strict=True, ge=1, le=1)


class LevelUpDexterityConstitutionIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dexterity: int = Field(strict=True, ge=1, le=1)
    constitution: int = Field(strict=True, ge=1, le=1)


class LevelUpDexterityIntelligenceIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dexterity: int = Field(strict=True, ge=1, le=1)
    intelligence: int = Field(strict=True, ge=1, le=1)


class LevelUpDexterityWisdomIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dexterity: int = Field(strict=True, ge=1, le=1)
    wisdom: int = Field(strict=True, ge=1, le=1)


class LevelUpDexterityCharismaIncrease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dexterity: int = Field(strict=True, ge=1, le=1)
    charisma: int = Field(strict=True, ge=1, le=1)


class LevelUpAsiChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feat: Literal["Ability Score Improvement"]
    increase: (
        LevelUpStrengthIncrease |
        LevelUpDexterityIncrease |
        LevelUpConIncrease |
        LevelUpIntelligenceIncrease |
        LevelUpWisdomIncrease |
        LevelUpCharismaIncrease |
        LevelUpStrengthDexterityIncrease |
        LevelUpStrengthConstitutionIncrease |
        LevelUpStrengthIntelligenceIncrease |
        LevelUpStrengthWisdomIncrease |
        LevelUpStrengthCharismaIncrease |
        LevelUpDexterityConstitutionIncrease |
        LevelUpDexterityIntelligenceIncrease |
        LevelUpDexterityWisdomIncrease |
        LevelUpDexterityCharismaIncrease |
        LevelUpConstitutionIntelligenceIncrease |
        LevelUpConstitutionWisdomIncrease |
        LevelUpConstitutionCharismaIncrease |
        LevelUpIntelligenceWisdomIncrease |
        LevelUpIntelligenceCharismaIncrease |
        LevelUpWisdomCharismaIncrease
    )


class LevelUpChoices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=1, max_length=1)
    cantrips: list[StrictStr] = Field(min_length=1, max_length=1)
    asi: LevelUpAsiChoice


class LevelUpFiveChoices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=2, max_length=2)


class SorcererLevel2Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepared_spells: list[StrictStr] = Field(min_length=2, max_length=2)
    metamagic: list[StrictStr] = Field(min_length=2, max_length=2)


class SorcererLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepared_spells: list[StrictStr] = Field(min_length=2, max_length=2)
    subclass_id: StrictStr


class BarbarianLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_id: Literal["berserker"]
    primal_knowledge_skill: Literal["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"]


class BarbarianLevel4Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asi: LevelUpAsiChoice


class BarbarianLevel2Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FighterLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_id: Literal["champion"]


class MonkLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_id: Literal["open_hand"]


class MonkLevelChoices(BaseModel):
    """Levels 2 and 5 have no choices and level 4 is the ordinary ASI: the same strict objects as Barbarian."""
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)
    level_2: BarbarianLevel2Choices = Field(alias="2")
    level_3: MonkLevel3Choices = Field(default_factory=lambda: None, alias="3", exclude_if=lambda value: value is None)
    level_4: BarbarianLevel4Choices = Field(default_factory=lambda: None, alias="4", exclude_if=lambda value: value is None)
    level_5: BarbarianLevel2Choices = Field(default_factory=lambda: None, alias="5", exclude_if=lambda value: value is None)


class FighterLevelChoices(BaseModel):
    """Levels 2 and 5 have no choices and level 4 is the ordinary ASI: the same strict objects as Barbarian."""
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)
    level_2: BarbarianLevel2Choices = Field(alias="2")
    level_3: FighterLevel3Choices = Field(default_factory=lambda: None, alias="3", exclude_if=lambda value: value is None)
    level_4: BarbarianLevel4Choices = Field(default_factory=lambda: None, alias="4", exclude_if=lambda value: value is None)
    level_5: BarbarianLevel2Choices = Field(default_factory=lambda: None, alias="5", exclude_if=lambda value: value is None)


class PaladinLevel2Choices(BaseModel):
    """Cantrips exist only with Blessed Warrior: exactly two, and the step owner checks them against the Cleric list."""
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=1, max_length=1)
    fighting_style: Literal["Archery", "Defense", "Dueling", "Great Weapon Fighting", "Two-Weapon Fighting", "Blessed Warrior"]
    cantrips: list[StrictStr] = Field(default_factory=lambda: None, min_length=2, max_length=2, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def cantrips_follow_the_option(self):
        if (self.fighting_style == "Blessed Warrior") != (self.cantrips is not None):
            raise ValueError("Blessed Warrior takes exactly two cantrips and a Fighting Style feat takes none.")
        return self


class PaladinLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=1, max_length=1)
    subclass_id: Literal["oath_of_devotion"]


class PaladinLevel4Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=1, max_length=1)
    asi: LevelUpAsiChoice


class PaladinLevel5Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spells: list[StrictStr] = Field(min_length=1, max_length=1)


class PaladinLevelChoices(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)
    level_2: PaladinLevel2Choices = Field(alias="2")
    level_3: PaladinLevel3Choices = Field(default_factory=lambda: None, alias="3", exclude_if=lambda value: value is None)
    level_4: PaladinLevel4Choices = Field(default_factory=lambda: None, alias="4", exclude_if=lambda value: value is None)
    level_5: PaladinLevel5Choices = Field(default_factory=lambda: None, alias="5", exclude_if=lambda value: value is None)


class RogueLevel3Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_id: Literal["assassin"]


class RogueLevelChoices(BaseModel):
    """Levels 2 and 5 have no choices and level 4 is the ordinary ASI: the same strict objects as Barbarian."""
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)
    level_2: BarbarianLevel2Choices = Field(alias="2")
    level_3: RogueLevel3Choices = Field(default_factory=lambda: None, alias="3", exclude_if=lambda value: value is None)
    level_4: BarbarianLevel4Choices = Field(default_factory=lambda: None, alias="4", exclude_if=lambda value: value is None)
    level_5: BarbarianLevel2Choices = Field(default_factory=lambda: None, alias="5", exclude_if=lambda value: value is None)


class BarbarianLevelChoices(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)
    level_2: BarbarianLevel2Choices = Field(alias="2")
    # Start 3-5 only; the creation validator requires each exactly through the starting level (omitted is None, explicit null is
    # rejected). Level 4 is the earned-level-4 ASI bundle; level 5 has no choices (the same empty strict object as level 2).
    level_3: BarbarianLevel3Choices = Field(default_factory=lambda: None, alias="3", exclude_if=lambda value: value is None)
    level_4: BarbarianLevel4Choices = Field(default_factory=lambda: None, alias="4", exclude_if=lambda value: value is None)
    level_5: BarbarianLevel2Choices = Field(default_factory=lambda: None, alias="5", exclude_if=lambda value: value is None)


class SorcererLevelChoices(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)

    # Omitted steps have an internal sentinel; explicitly supplied null is invalid.
    # Factories keep the public schema non-nullable without a null default.
    level_2: SorcererLevel2Choices = Field(default_factory=lambda: None, alias="2")
    level_3: SorcererLevel3Choices = Field(default_factory=lambda: None, alias="3")
    level_4: LevelUpChoices = Field(default_factory=lambda: None, alias="4")
    level_5: LevelUpFiveChoices = Field(default_factory=lambda: None, alias="5")


class CharacterCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["custom", "random"]
    starting_level: int = Field(default=1, ge=1, le=5, strict=True)
    level_choices: SorcererLevelChoices | BarbarianLevelChoices | FighterLevelChoices | MonkLevelChoices | RogueLevelChoices | PaladinLevelChoices | None = None
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
        steps = (
            set(self.level_choices.model_dump(by_alias=True, exclude_none=True))
            if self.level_choices is not None else set()
        )
        if self.mode == "random":
            if self.starting_level != 1 or self.level_choices is not None:
                raise ValueError("Random creation supports level 1 without level choices only.")
        else:
            if self.starting_level > 1:
                if self.character_class == "Barbarian":
                    if self.starting_level not in (2, 3, 4, 5) or not isinstance(self.level_choices, BarbarianLevelChoices):
                        raise ValueError("Barbarian supports only the exact level2 to level5 choice bundle for its starting level.")
                elif self.character_class == "Fighter":
                    # {"2": {}} is the same strict body for both classes and the union resolves it to the first; nothing else is shared.
                    shared_start_two = self.starting_level == 2 and isinstance(self.level_choices, BarbarianLevelChoices)
                    if self.starting_level not in (2, 3, 4, 5) or not (shared_start_two or isinstance(self.level_choices, FighterLevelChoices)):
                        raise ValueError("Fighter supports only the exact level2 to level5 choice bundle for its starting level.")
                elif self.character_class == "Paladin":
                    if self.starting_level not in (2, 3, 4, 5) or not isinstance(self.level_choices, PaladinLevelChoices):
                        raise ValueError("Paladin supports only the exact level2 to level5 choice bundle for its starting level.")
                elif self.character_class == "Rogue":
                    shared_start_two = self.starting_level == 2 and isinstance(self.level_choices, BarbarianLevelChoices)
                    if self.starting_level not in (2, 3, 4, 5) or not (shared_start_two or isinstance(self.level_choices, RogueLevelChoices)):
                        raise ValueError("Rogue supports only the exact level2 to level5 choice bundle for its starting level.")
                elif self.character_class == "Monk":
                    # {"2": {}} resolves to the first strict body, and a bundle up to level 2 is shared the same way.
                    shared_start_two = self.starting_level == 2 and isinstance(self.level_choices, BarbarianLevelChoices)
                    if self.starting_level not in (2, 3, 4, 5) or not (shared_start_two or isinstance(self.level_choices, MonkLevelChoices)):
                        raise ValueError("Monk supports only the exact level2 to level5 choice bundle for its starting level.")
                elif self.character_class == "Sorcerer":
                    if not isinstance(self.level_choices, SorcererLevelChoices):
                        raise ValueError("Sorcerer requires its own per-level choices.")
                else:
                    raise ValueError("Higher starting levels are unsupported for this class.")
            if steps != {str(level) for level in range(2, self.starting_level + 1)}:
                raise ValueError("Level choices must contain exactly the steps through the starting level.")
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


class SorcererSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class SorcererStartingLevel2Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepared_spell_count: int
    prepared_spell_ids: list[str]
    metamagic_count: int
    metamagic_options: list[str]


class SorcererStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepared_spell_count: int
    prepared_spell_ids: list[str]
    subclass_options: list[SorcererSubclassOption]


class SorcererStartingLevel4Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]
    cantrip_count: int
    cantrip_ids: list[str]
    supported_asi_choices: list[LevelUpAsiChoice]


class SorcererStartingLevel5Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]


class SorcererEffectsPendingByLevel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)

    level_1: list[str] = Field(alias="1")
    level_2: list[str] = Field(alias="2")
    level_3: list[str] = Field(alias="3")
    level_4: list[str] = Field(alias="4")
    level_5: list[str] = Field(alias="5")


class SorcererStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_starting_levels: list[int]
    level_2: SorcererStartingLevel2Options
    level_3: SorcererStartingLevel3Options
    level_4: SorcererStartingLevel4Options
    level_5: SorcererStartingLevel5Options
    effects_pending_by_level: SorcererEffectsPendingByLevel


class BarbarianStartingLevel2Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choices: BarbarianLevel2Choices
    effects_supported: list[str]
    effects_pending: list[str]


class BarbarianStartingSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["berserker"]
    name: str


class BarbarianStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_options: list[BarbarianStartingSubclassOption]
    primal_knowledge_skill_options: list[str]
    effects_supported: list[str]
    effects_pending: list[str]


class BarbarianStartingLevel4Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_asi_choices: list[LevelUpAsiChoice]
    effects_supported: list[str]
    effects_pending: list[str]


class BarbarianStartingLevel5Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effects_supported: list[str]
    effects_pending: list[str]


class BarbarianStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_starting_levels: list[int]
    level_2: BarbarianStartingLevel2Options
    level_3: BarbarianStartingLevel3Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_4: BarbarianStartingLevel4Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_5: BarbarianStartingLevel5Options | None = Field(default=None, exclude_if=lambda value: value is None)


class FighterStartingSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["champion"]
    name: str


class FighterStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_options: list[FighterStartingSubclassOption]
    effects_supported: list[str]
    effects_pending: list[str]


class FighterStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_starting_levels: list[int]
    level_2: BarbarianStartingLevel2Options
    level_3: FighterStartingLevel3Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_4: BarbarianStartingLevel4Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_5: BarbarianStartingLevel5Options | None = Field(default=None, exclude_if=lambda value: value is None)


class PaladinStartingLevel2Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]
    fighting_style_options: list[str]
    blessed_warrior_cantrip_count: int
    blessed_warrior_cantrip_ids: list[str]
    effects_supported: list[str]
    effects_pending: list[str]


class PaladinStartingSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["oath_of_devotion"]
    name: str


class PaladinStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]
    subclass_options: list[PaladinStartingSubclassOption]
    effects_supported: list[str]
    effects_pending: list[str]


class RogueStartingSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["assassin"]
    name: str


class RogueStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_options: list[RogueStartingSubclassOption]
    effects_supported: list[str]
    effects_pending: list[str]


class PaladinStartingLevel4Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]
    supported_asi_choices: list[LevelUpAsiChoice]
    effects_supported: list[str]
    effects_pending: list[str]


class PaladinStartingLevel5Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_spell_count: int
    prepared_spell_ids: list[str]
    effects_supported: list[str]
    effects_pending: list[str]


class PaladinStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_starting_levels: list[int]
    level_2: PaladinStartingLevel2Options
    level_3: PaladinStartingLevel3Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_4: PaladinStartingLevel4Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_5: PaladinStartingLevel5Options | None = Field(default=None, exclude_if=lambda value: value is None)


class RogueStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_starting_levels: list[int]
    level_2: BarbarianStartingLevel2Options
    level_3: RogueStartingLevel3Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_4: BarbarianStartingLevel4Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_5: BarbarianStartingLevel5Options | None = Field(default=None, exclude_if=lambda value: value is None)


class MonkStartingSubclassOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["open_hand"]
    name: str


class MonkStartingLevel3Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subclass_options: list[MonkStartingSubclassOption]
    effects_supported: list[str]
    effects_pending: list[str]


class MonkStartingCreationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_starting_levels: list[int]
    level_2: BarbarianStartingLevel2Options
    level_3: MonkStartingLevel3Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_4: BarbarianStartingLevel4Options | None = Field(default=None, exclude_if=lambda value: value is None)
    level_5: BarbarianStartingLevel5Options | None = Field(default=None, exclude_if=lambda value: value is None)


class CharacterCreationCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sorcerer_starting_creation: SorcererStartingCreationOptions | None = None
    barbarian_starting_creation: BarbarianStartingCreationOptions | None = None
    fighter_starting_creation: FighterStartingCreationOptions | None = None
    paladin_starting_creation: PaladinStartingCreationOptions | None = None
    rogue_starting_creation: RogueStartingCreationOptions | None = None
    monk_starting_creation: MonkStartingCreationOptions | None = None
    races: dict[str, Any]
    classes: dict[str, Any]
    backgrounds: dict[str, Any]
    ability_score_methods: list[dict[str, Any]]
    alignments: list[dict[str, Any]]
    origin_feats: dict[str, Any]
    spells_catalog: dict[str, Any]
    skills: dict[str, Any]
    equipment_rules: dict[str, Any]
    languages: dict[str, Any]


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


class LevelUpApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    campaign_id: UUID
    expected_revision: int = Field(strict=True, ge=0)
    target_level: int = Field(strict=True, ge=2, le=5)
    choices: LevelUpChoices | LevelUpFiveChoices | SorcererLevel2Choices | SorcererLevel3Choices | BarbarianLevel2Choices | BarbarianLevel3Choices | BarbarianLevel4Choices | FighterLevel3Choices | MonkLevel3Choices | RogueLevel3Choices | PaladinLevel2Choices | PaladinLevel3Choices | PaladinLevel4Choices | PaladinLevel5Choices

    @model_validator(mode="after")
    def choices_match_target(self):
        expected = {2: (SorcererLevel2Choices, BarbarianLevel2Choices, PaladinLevel2Choices), 3: (SorcererLevel3Choices, BarbarianLevel3Choices, FighterLevel3Choices, MonkLevel3Choices, RogueLevel3Choices, PaladinLevel3Choices),
                    4: (LevelUpChoices, BarbarianLevel4Choices, PaladinLevel4Choices), 5: (LevelUpFiveChoices, BarbarianLevel2Choices, PaladinLevel5Choices)}[self.target_level]
        if not isinstance(self.choices, expected):
            raise ValueError("Level-up choice shape does not match target level.")
        return self

    @field_validator("action_id", "campaign_id")
    @classmethod
    def require_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("A UUID4 identity is required.")
        return value


class LevelUpPreviewResponse(BaseModel):
    session_id: str
    campaign_id: str | None
    revision: int | None
    status: Literal["ready", "blocked"]
    reason: str | None
    target_level: Literal[2, 3, 4, 5] = 4
    class_name: str | None = None
    from_level: int | None = None
    metamagic_options: list[str] = Field(default_factory=list)
    subclass_options: list[SorcererSubclassOption] = Field(default_factory=list)
    primal_knowledge_skill_options: list[str] | None = Field(default=None, exclude_if=lambda value: value is None)
    fighting_style_options: list[str] | None = Field(default=None, exclude_if=lambda value: value is None)
    effects_supported: list[str] = Field(default_factory=list)
    choices_required: dict[str, int] = Field(default_factory=dict)
    cantrip_ids: list[str] = Field(default_factory=list)
    prepared_spell_ids: list[str] = Field(default_factory=list)
    supported_asi_choices: list[LevelUpAsiChoice] = Field(default_factory=list)
    capacity: dict[str, Any] | None = None
    effects_pending: list[str] = Field(default_factory=list)


class LevelUpAppliedResult(BaseModel):
    status: Literal["applied"]
    reason: None = None
    changes: list[dict[str, Any]]
    effects_pending: list[str]


class LevelUpCommandResult(BaseModel):
    session_id: str
    action_id: str
    state: dict[str, Any]
    result: LevelUpAppliedResult
