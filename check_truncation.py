import os
import json

directory = 'books/charak_samhita'
files = [f for f in os.listdir(directory) if f.endswith('.json')]
count = 0

for f in files:
    try:
        with open(os.path.join(directory, f), 'r', encoding='utf-8') as file:
            d = json.load(file)
            t = d.get('text', '')
            
            # Check total text length
            if 1990 <= len(t) <= 2010:
                print(f'Total len match: {f} ({len(t)})')
                count += 1
            
            # Check individual line lengths
            lines = t.split('\n')
            for i, l in enumerate(lines):
                if 1990 <= len(l) <= 2010:
                    # Print first 50 chars of suspicious line to see if it looks truncated
                    print(f'Line match: {f} line {i} ({len(l)}) - {l[:50]}...')
                    count += 1
    except Exception as e:
        print(f"Error processing {f}: {e}")

print(f'Total matches: {count}')
