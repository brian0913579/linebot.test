import logging
import os

from app import create_app

# The Gunicorn worker entry point uses this instance
app = create_app()

if __name__ == "__main__":
    # Local development entry point
    port = int(os.environ.get("PORT", 8080))
    debug = app.config.get("DEBUG_MODE", False)
    logging.info(f"Starting legacy LineBot server on port {port} (Debug: {debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
