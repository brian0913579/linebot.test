import secrets as py_secrets
import time
from sortedcontainers import SortedDict

# token_manager.py

TOKENS = {}

def generate_token(user_id):
    token_open = py_secrets.token_urlsafe(16)
    token_close = py_secrets.token_urlsafe(16)
    
    # Store user_id, action, and expiry for both tokens
    TOKENS[token_open] = (user_id, 'open', time.time() + 300)
    TOKENS[token_close] = (user_id, 'close', time.time() + 300)
    
    return token_open, token_close

def clean_expired_tokens():
    current_time = time.time()
    expired_tokens = list(TOKENS.keys())  
    for token in expired_tokens:
        _, _, expiry = TOKENS[token]
        if expiry <= current_time:
            del TOKENS[token]