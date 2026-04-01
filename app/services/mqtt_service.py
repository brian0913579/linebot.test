import logging
import os
import ssl
import time
import traceback

from flask import current_app
from paho.mqtt import client as mqtt

from utils.logger_config import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 0.5
CONNECT_TIMEOUT = 5


def create_mqtt_client():
    cafile = os.environ.get("MQTT_CAFILE")
    ssl_context = ssl.create_default_context(cafile=cafile)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    client = mqtt.Client()
    client.username_pw_set(
        current_app.config["MQTT_USERNAME"], current_app.config["MQTT_PASSWORD"]
    )
    client.tls_set_context(ssl_context)

    client.on_connect = _on_connect
    client.on_publish = _on_publish
    client.on_disconnect = _on_disconnect
    return client, ssl_context


def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker successfully")
    elif rc == 4:
        logging.error("Failed to connect to MQTT broker: bad username or password")
    else:
        logging.error(f"Failed to connect to MQTT broker: {mqtt.connack_string(rc)}")


def _on_publish(client, userdata, mid):
    logger.debug(f"Message {mid} published successfully")


def _on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.warning("Unexpected disconnection from MQTT broker")


def send_garage_command(action):
    """
    Send command to garage door controller via MQTT with retry logic.
    Assumes execution within a valid Flask application context.
    """
    mqtt_cmd = "up" if action == "open" else "down"
    client = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client, _ = create_mqtt_client()
            client.connect_async(
                current_app.config["MQTT_BROKER"],
                current_app.config["MQTT_PORT"],
                keepalive=10,
            )

            client.loop_start()

            start_time = time.time()
            while (
                not client.is_connected() and time.time() - start_time < CONNECT_TIMEOUT
            ):
                time.sleep(0.1)

            if not client.is_connected():
                raise TimeoutError(f"Connection timed out after {CONNECT_TIMEOUT}s")

            result = client.publish(current_app.config["MQTT_TOPIC"], mqtt_cmd, qos=1)

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
                detailed_error = (
                    f"Failed to send MQTT command after {MAX_RETRIES} attempts: "
                    f"{str(e)}"
                )
                logger.error(detailed_error)
                logger.error(traceback.format_exc())
                return False, detailed_error
        finally:
            if client and client.is_connected():
                client.loop_stop()
                client.disconnect()
