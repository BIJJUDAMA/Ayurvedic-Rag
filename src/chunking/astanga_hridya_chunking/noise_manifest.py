import re

# Patterns to filter out during processing
NOISE_PATTERNS = [
    r'## Astanga Hridaya Sutrasthan',
    r'---',
    r'--',
    r'```',
]

def clean_noise(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()
