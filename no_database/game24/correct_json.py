from pathlib import Path

# Input files
json_file = Path("adjust_answers.json")
corrections_file = Path("correct.txt")
output_file = Path("adjust_answers_fixed.json")

# Step 1: read corrections into a dict {line_number: new_line}
corrections = {}
with corrections_file.open("r", encoding="utf-8") as f:
    for raw in f:
        raw = raw.strip()
        if not raw or ":" not in raw:
            continue
        try:
            line_num_str, new_line = raw.split(":", 1)
            line_num = int(line_num_str.strip())
            new_line = new_line.lstrip().rstrip()
            # preserve spacing in new_line (don’t strip it fully)
            corrections[line_num] = new_line.rstrip()
        except ValueError:
            print(f"Skipping malformed line in correct.txt: {raw}")

# Step 2: read the JSON file line by line
with json_file.open("r", encoding="utf-8") as f:
    lines = f.readlines()

# Step 3: replace if line number is in corrections
for i, line in enumerate(lines, start=1):
    if i in corrections:
        # preserve original leading whitespace
        leading = len(line) - len(line.lstrip(" "))
        lines[i-1] = " " * leading + corrections[i] + "\n"

# Step 4: write out to a new file
with output_file.open("w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"Done. Fixed file written to {output_file}")

