import os
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import secretmanager

# Load .env if present for local development
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Function to access secrets from Google Cloud Secret Manager
def get_secret(secret_name):
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(name=secret_path)
    secret_data = response.payload.data.decode("UTF-8")
    return secret_data

# Line Bot Configuration
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or get_secret("line-channel-token2")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET") or get_secret("line-channel-secret2")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET must be set via .env or Secret Manager")

# MQTT Broker Configuration
MQTT_BROKER = os.getenv('MQTT_BROKER', 'bri4nting.duckdns.org')
MQTT_PORT = int(os.getenv('MQTT_PORT', '8883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', 'piuser')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', 'cool.com')
MQTT_CAFILE = os.getenv('MQTT_CAFILE', 'ca.crt')
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'garage/command')

# Location Verification Configuration
PARK_LAT = 24.79155    # Parking lot latitude
PARK_LNG = 120.99442   # Parking lot longitude
MAX_DIST_KM = 0.5      # 500 meters maximum distance

# Time-to-live settings
VERIFY_TTL = 300        # 5 minutes for one-time verification tokens
LOCATION_TTL = 10       # 10 seconds location verification validity

# Flask App Configuration
PORT = int(os.getenv("PORT", 8080))
VERIFY_URL_BASE = os.getenv('VERIFY_URL_BASE', 'https://bri4nting.duckdns.org/verify-location')