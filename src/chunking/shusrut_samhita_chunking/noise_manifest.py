import re

# Patterns to filter out during processing
NOISE_PATTERNS = [
    r'## Indological Truths',
    r'Indological Truths',
    r'data:image/png;base64,.*',
    r'---',
    r'--',
    r'## S\.S\.\s*II\.\s*\d+',
    r'SUGGESTED RESEARCH PROBLEMS.*',
    r'SEND US YOUR SUGGESTIONS.*',
    r'Singhal, G\.D',
    r'PROF\. K\. N\. UDUPA',
    r'Director, Institute of Medical Sciences',
    r'Banaras Hindu University',
    r'Varanasi-5 \(INDIA\)',
    r'Thy right is to work only; but never to its fruits.*?\.',
    r'![Image]\(data:image/.*?\)',
]

def clean_noise(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()
