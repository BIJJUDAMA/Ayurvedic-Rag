import os
import json
import collections

directory = 'books/charak_samhita'
files = [f for f in os.listdir(directory) if f.endswith('.json')]

lengths = collections.Counter()
long_lines = []

for f in files:
    try:
        with open(os.path.join(directory, f), 'r', encoding='utf-8') as file:
            d = json.load(file)
            t = d.get('text', '')
            lines = t.split('\n')
            for l in lines:
                length = len(l)
                lengths[length] += 1
                if length > 2000:
                    long_lines.append((f, length, l[-50:]))
    except:
        pass

# Print top 10 most common lengths > 100
print("Most common lengths > 100:")
for length, count in sorted(lengths.items(), key=lambda x: x[1], reverse=True):
    if length > 100:
        print(f"{length}: {count}")
        if count > 10: # Only first few
            break

# Check for a "wall" at 2000 or similar
print("\nCounts around 2000:")
for length in range(1995, 2005):
    print(f"{length}: {lengths[length]}")

print(f"\nTotal lines > 2000: {len(long_lines)}")
if long_lines:
    print("Sample long line endings:")
    for f, l, end in long_lines[:5]:
        print(f"{f} ({l}): ...{end}")
