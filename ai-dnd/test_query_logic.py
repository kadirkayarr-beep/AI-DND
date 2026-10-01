import sys
import io

# Test the logic directly without importing the full game
# Copy the relevant functions here

def _detect_query_type(text, npc_target=None):
    text = text.casefold().strip()

    # Self queries
    if any(phrase in text for phrase in (
        "ben kimim", "karakterim kim", "kim oynuyorum",
        "benim adım ne", "benim ismim ne", "karakterimin adı ne", "karakterimin ismi ne",
        "senin adın ne", "senin ismin ne",
        "hangi sınıfım", "sınıfım ne", "hangi class",
        "hangi ırktayım", "ırkım ne", "hangi ırkım",
        "seviyem kaç", "levelim kaç", "kaçıncı seviyedeyim"
    )):
        return "self"

    # Location queries
    if any(phrase in text for phrase in (
        "buranın adı ne", "bu yerin adı ne", "bu yerin ismi ne",
        "neredeyim", "şu an neredeyim", "hangi yerdeyim"
    )):
        return "location"

    # Presence queries
    if any(phrase in text for phrase in (
        "burada kim var", "burada kimler var", "etrafta kim var",
        "kimler burada", "bu odada kim var"
    )):
        return "presence"

    # NPC identity queries (when there's an active NPC context)
    if npc_target and any(phrase in text for phrase in (
        "adın ne", "ismin ne", "kimsin", "adın ne?", "ismin ne?"
    )):
        return "npc_identity"

    return None



def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    # Test scenarios
    npc_target = {"name": "Barmen", "role": "Barmen"}

    print("=== With Active NPC ===")
    tests_with_npc = [
        "adın ne?",
        "senin adın ne?",
        "kimsin?",
        "ismin ne?",
    ]
    for t in tests_with_npc:
        result = _detect_query_type(t, npc_target)
        print(f"  '{t}' -> {result}")

    print("\n=== Without NPC ===")
    tests_without_npc = [
        "adın ne?",
        "senin adın ne?",
        "kimsin?",
        "ismin ne?",
    ]
    for t in tests_without_npc:
        result = _detect_query_type(t, None)
        print(f"  '{t}' -> {result}")

    print("\n=== Self queries (should always be 'self') ===")
    self_tests = [
        "benim adım ne?",
        "senin adın ne?",
        "ben kimim?",
        "karakterimin adı ne?",
    ]
    for t in self_tests:
        result = _detect_query_type(t, npc_target)
        print(f"  '{t}' -> {result}")

    print("\n=== Location queries ===")
    loc_tests = [
        "buranın adı ne?",
        "neredeyim?",
    ]
    for t in loc_tests:
        result = _detect_query_type(t, npc_target)
        print(f"  '{t}' -> {result}")

    print("\n=== Presence queries ===")
    pres_tests = [
        "burada kimler var?",
        "burada kim var?",
    ]
    for t in pres_tests:
        result = _detect_query_type(t, npc_target)
        print(f"  '{t}' -> {result}")

if __name__ == '__main__':
    run_tests()
