import os
import json

directory = 'books/charak_samhita'
files = sorted([f for f in os.listdir(directory) if f.endswith('.json')])

# Sample 50 files (every 13th)
sample_indices = [i * 13 for i in range(50) if i * 13 < len(files)]
sampled_files = [files[i] for i in sample_indices]

line_length_findings = []

for filename in sampled_files:
    path = os.path.join(directory, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'text' in data:
                text_content = data['text']
                lines = text_content.split('\n')
                max_line_len = max(len(l) for l in lines) if lines else 0
                suspicious_lines = [len(l) for l in lines if len(l) > 1900 and len(l) < 2100]
                
                line_length_findings.append({
                    'file': filename,
                    'max_line_length': max_line_len,
                    'suspicious_lines_count': len(suspicious_lines),
                    'suspicious_lengths': suspicious_lines
                })
    except Exception as e:
        pass

print(json.dumps(line_length_findings, indent=2))
