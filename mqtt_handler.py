import ssl
import time
import traceback
from paho.mqtt import client as mqtt
from config_module import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, 
    MQTT_PASSWORD, MQTT_CAFILE, MQTT_TOPIC
)
from logger_config import get_logger

# Configure logger
logger = get_logger(__name__)

# MQTT client connection constants
MAX_RETRIES = 3
RETRY_DELAY = 0.5
CONNECT_TIMEOUT = 5

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
    
    # Set callback handlers for better error logging
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    
    return client, ssl_context

def on_connect(client, userdata, flags, rc):
    """Callback for when the client receives a CONNACK response from the server"""
    rc_codes = {
        0: "Connection successful",
        1: "Connection refused - incorrect protocol version",
        2: "Connection refused - invalid client identifier",
        3: "Connection refused - server unavailable",
        4: "Connection refused - bad username or password",
        5: "Connection refused - not authorized"
    }
    if rc == 0:
        logger.info("Connected to MQTT broker successfully")
    else:
        error_message = rc_codes.get(rc, f"Unknown error code: {rc}")
        logger.error(f"Failed to connect to MQTT broker: {error_message}")

def on_publish(client, userdata, mid):
    """Callback for when a message is published"""
    logger.debug(f"Message {mid} published successfully")

def on_disconnect(client, userdata, rc):
    """Callback for when the client disconnects from the server"""
    if rc != 0:
        logger.warning(f"Unexpected disconnection from MQTT broker, code: {rc}")
    else:
        logger.debug("Disconnected from MQTT broker successfully")

def send_garage_command(action):
    """
    Send command to garage door controller via MQTT with retry logic
    
    Args:
        action (str): 'open' or 'close' to control the garage door
        
    Returns:
        tuple: (success (bool), error_message (str or None))
    """
    mqtt_cmd = 'up' if action == 'open' else 'down'
    client = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Create client
            client, _ = create_mqtt_client()
            
            # Set a connect timeout
            client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=10)
            
            # Start the network loop in a separate thread
            client.loop_start()
            
            # Wait for connection or timeout
            start_time = time.time()
            while not client.is_connected() and time.time() - start_time < CONNECT_TIMEOUT:
                time.sleep(0.1)
            
            if not client.is_connected():
                raise TimeoutError(f"Connection timed out after {CONNECT_TIMEOUT}s")
            
            # Send command with QoS 1 for guaranteed delivery
            result = client.publish(MQTT_TOPIC, mqtt_cmd, qos=1)
            
            # Wait for the message to be published
            if not result.is_published():
                result.wait_for_publish(timeout=2.0)
            
            if not result.is_published():
                raise Exception("Failed to publish message within timeout period")
            
            logger.info(f"Garage command '{action}' sent successfully")
            return True, None
            
        except Exception as e:
            error_msg = f"Attempt {attempt}/{MAX_RETRIES} failed: {str(e)}"
            logger.warning(error_msg)
            
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                detailed_error = f"Failed to send MQTT command after {MAX_RETRIES} attempts: {str(e)}"
                logger.error(detailed_error)
                logger.error(traceback.format_exc())
                return False, detailed_error
        finally:
            if client and client.is_connected():
                client.loop_stop()
                client.disconnect()
    
    # This should never be reached due to the returns in the loop
    return False, "Unknown error occurred"