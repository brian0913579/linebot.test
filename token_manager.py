import secrets
import time
from sortedcontainers import SortedDict

TOKENS = SortedDict()

def generate_token():
    token_open = secrets.token_urlsafe(16)
    token_close = secrets.token_urlsafe(16)
    TOKENS[token_open] = ('open', time.time() + 300)
    TOKENS[token_close] = ('close', time.time() + 300)
    return token_open, token_close

def clean_expired_tokens():
    current_time = time.time()
    expired_tokens = list(TOKENS.keys())  
    for token in expired_tokens:
        _, _, expiry = TOKENS[token]
        if expiry <= current_time:
            del TOKENS[token]