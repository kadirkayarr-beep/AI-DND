import re
with open('game.py', 'r', encoding='utf-8') as f:
    source = f.read()
lines = source.split('\n')
exec_lines = []
for line in lines:
    # Stop at character creation input() call, not at the print before it
    if line.startswith('print("===') and 'KARAKTER' in line:
        break
    exec_lines.append(line)
final_source = '\n'.join(exec_lines)
# Remove the __main__ block
final_source = re.sub(r'if __name__ == "__main__":.*', '', final_source, flags=re.DOTALL)
# Check if run_player_turn is defined after the character creation section
# It should be - let's check the full source
full_lines = source.split('\n')
char_creation_idx = None
for i, line in enumerate(full_lines):
    if 'KARAKTER' in line and line.startswith('print("==='):
        char_creation_idx = i
        break
print(f"Character creation at line: {char_creation_idx}")
print(f"Total lines: {len(full_lines)}")
# Find run_player_turn definition
for i, line in enumerate(full_lines):
    if 'def run_player_turn' in line:
        print(f"run_player_turn defined at line: {i+1}")
        break
