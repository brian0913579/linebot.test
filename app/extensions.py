from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Define the global Limiter instance
limiter = Limiter(
    key_func=get_remote_address, storage_uri="memory://", default_limits=[]
)
