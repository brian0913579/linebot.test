import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    log_handler = RotatingFileHandler('app.log', maxBytes=10 * 1024 * 1024, backupCount=3)
    log_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    app.logger.addHandler(log_handler)
    app.logger.addHandler(console_handler)