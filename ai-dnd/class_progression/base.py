"""Default progression hooks. A class overrides only what it has; an unregistered class gets this behaviour (level 1, no effects)."""
from __future__ import annotations

from typing import Any


EXTRA_ATTACK_ATTACKS = 2  # Extra Attack: two attacks instead of one (Barbarian PDF 51, Fighter PDF 91, both level 5)


class ClassProgression:
    name: str | None = None  # the character["class"] value
    supported_level = 1  # highest level this class can reach; character_progression.MAX_SUPPORTED_LEVEL still caps it
    selected_asi = False  # True when the ordinary level-4 Ability Score Improvement path is open to this class
    extra_attack_level: int | None = None  # the class level whose APPLIED choices grant Extra Attack

    # Saved-state validation, in the order character_progression.validate_saved calls them.
    def validate_class_fields(self, player: dict[str, Any]) -> None:
        """Runs for EVERY registered class on EVERY character: refuse this class's own fields wherever they do not belong."""

    def validate_state(self, player: dict[str, Any], world: dict[str, Any]) -> None:
        """Runs for this class before the applied level is checked."""

    def validate_applied(self, player: dict[str, Any], world: dict[str, Any], applied: int) -> None:
        """Runs for this class after the applied level was admitted against its table. A class without its own rules claims nothing."""
        if player.get("metamagic") or "subclass_id" in player:
            raise ValueError("Kayıt bu sınıf için doğrulanmamış ilerleme seçimi iddia ediyor.")

    def validate_asi_storage(self, player: dict[str, Any], *, saved: bool) -> None:
        """Class extra after a stored ordinary ASI record was admitted."""

    # Pure views.
    def disclosure(self, level: int, **adopted: Any) -> dict[str, list[str]]:
        return {"supported": [], "pending": []}

    def adoption(self, world: dict[str, Any]) -> dict[str, bool]:
        """Keyword flags for `disclosure` read from world state during a level-up preview."""
        return {}

    def capacity(self, character: dict[str, Any]) -> dict[str, Any] | None:
        """Spell resources at the applied level; None for a class without them."""
        return None

    def progression_path_verified(self, character: dict[str, Any]) -> bool:
        """The retained path this class needs for its applied features (a subclass choice, say)."""
        return True

    def extra_attack_applied(self, character: Any) -> bool:
        """The one Extra Attack entitlement: applied level, never the numeric XP level or a forged field alone.

        Cheap on purpose (the allowance reads it often); the retained choices behind it are admitted by `validate_saved`.
        """
        return (self.extra_attack_level is not None and isinstance(character, dict) and character.get("class") == self.name
                and type(character.get("level")) is int and type(character.get("progression_level")) is int
                and character["progression_level"] >= self.extra_attack_level and character["level"] >= self.extra_attack_level
                and self.progression_path_verified(character))

    def attacks_per_attack_action(self, character: dict[str, Any]) -> int:
        return EXTRA_ATTACK_ATTACKS if self.extra_attack_applied(character) else 1

    def speed_bonus_ft(self, character: dict[str, Any], world: Any) -> int:
        return 0

    # Rest. `prepare_rest` runs before the clock moves and may refuse; `rest_recovery` runs when the rest is finished.
    def prepare_rest(self, session: Any) -> None:
        """Refuse a rest over invalid class state before anything changes."""

    def rest_recovery(self, session: Any, kind: str) -> None:
        """`kind` is short_rest or long_rest."""

    # Level-up. The hooks below the prerequisite are required once `supported_level` is above 1.
    def level_prerequisite(self, session: Any, target_level: int) -> str | None:
        """Refusal reason for reaching `target_level`, or None."""
        return None

    def choices_required(self, character: dict[str, Any], current: int, target_level: int,
                         prior: dict[str, Any], goal: dict[str, Any]) -> dict[str, int]:
        raise NotImplementedError

    def preview_capacity(self, goal: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def preview_options(self, session: Any, target_level: int) -> dict[str, Any]:
        """Extra preview fields offering the choices."""
        return {}

    def check_choices(self, session: Any, preview: dict[str, Any], choices: dict[str, Any]) -> str | None:
        raise NotImplementedError

    def apply_level(self, session: Any, preview: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def validate_start_choices(self, level: int, level_choices: Any) -> None:
        """Outer shape of a creation bundle above level 1; the default refuses a higher start."""
        raise ValueError("starting_level_class_not_supported")
