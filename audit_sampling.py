import os
import json

directory = 'books/charak_samhita'
files = sorted([f for f in os.listdir(directory) if f.endswith('.json')])

# Sample 50 files (every 12.8 files, so every 13th)
sample_indices = [i * 13 for i in range(50) if i * 13 < len(files)]
sampled_files = [files[i] for i in sample_indices]

schema_drift = []
truncation_findings = []
all_keys = set()

for filename in sampled_files:
    path = os.path.join(directory, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Check schema
            current_keys = set(data.keys())
            if not all_keys:
                all_keys = current_keys
            elif current_keys != all_keys:
                schema_drift.append({
                    'file': filename,
                    'keys': list(current_keys),
                    'missing': list(all_keys - current_keys),
                    'extra': list(current_keys - all_keys)
                })
            
            # Check truncation
            if 'text' in data:
                text_content = data['text']
                length = len(text_content)
                # Check if it's suspiciously close to a round number like 2000
                is_truncated = False
                if length >= 1900 and length <= 2100:
                    is_truncated = True
                
                # Check for abrupt ending
                last_chars = text_content[-20:]
                truncation_findings.append({
                    'file': filename,
                    'length': length,
                    'last_chars': last_chars,
                    'potential_truncation': is_truncated
                })
            else:
                truncation_findings.append({
                    'file': filename,
                    'error': 'No text field'
                })
                
    except Exception as e:
        schema_drift.append({'file': filename, 'error': str(e)})

print(json.dumps({
    'total_files_checked': len(sampled_files),
    'common_keys': list(all_keys),
    'schema_drift': schema_drift,
    'truncation_findings': truncation_findings
}, indent=2))
