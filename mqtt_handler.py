import ssl
import time
import logging
import traceback
from paho.mqtt import client as mqtt
from config_module import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, 
    MQTT_PASSWORD, MQTT_CAFILE, MQTT_TOPIC
)

# Configure logger
logger = logging.getLogger(__name__)

# MQTT Client Setup
def create_mqtt_client():
    """Create and configure MQTT client with SSL settings"""
    # Create SSL context with certificate
    ssl_context = ssl.create_default_context(cafile=MQTT_CAFILE)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    
    # Create MQTT client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set_context(ssl_context)
    
    return client, ssl_context

def send_garage_command(action):
    """
    Send command to garage door controller via MQTT
    
    Args:
        action (str): 'open' or 'close' to control the garage door
        
    Returns:
        tuple: (success (bool), error_message (str or None))
    """
    mqtt_cmd = 'up' if action == 'open' else 'down'
    
    try:
        # Create client
        client, _ = create_mqtt_client()
        
        # Connect with timeout
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        
        # Send command
        logger.info(f"Publishing {mqtt_cmd} command to {MQTT_TOPIC}")
        result = client.publish(MQTT_TOPIC, mqtt_cmd, qos=1)
        
        # Wait for confirmation of delivery
        if not result.is_published():
            result.wait_for_publish(timeout=5)
        
        # Clean disconnect
        client.disconnect()
        logger.info(f"MQTT command sent successfully: {mqtt_cmd}")
        
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to send MQTT command: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Detailed error: {traceback.format_exc()}")
        return False, error_msg