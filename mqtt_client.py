"""
MQTT Client — Thread-safe wrapper around paho-mqtt using Qt signals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from paho.mqtt.client import Client, MQTTMessage
    import paho.mqtt.client as mqtt

    # paho >= 2.0 exposes CallbackAPIVersion
    try:
        from paho.mqtt.client import CallbackAPIVersion
        _USE_V2_API = True
    except ImportError:
        _USE_V2_API = False
except ImportError as exc:
    raise ImportError("paho-mqtt is required: pip install paho-mqtt>=2.0") from exc


@dataclass
class MqttMessage:
    """Immutable record of one received MQTT message."""
    timestamp: datetime
    topic: str
    payload: str
    qos: int
    retain: bool


class MqttClient(QObject):
    """
    Thread-safe MQTT client.

    Runs the paho network loop in a background thread and emits Qt signals
    so that the UI can update safely from the main thread.
    """

    # Emitted when the broker connection is established.
    connected = pyqtSignal()

    # Emitted when the client disconnects (cleanly or not).
    disconnected = pyqtSignal()

    # Emitted on connection or protocol errors.
    error_occurred = pyqtSignal(str)

    # Human-readable log line (useful for a debug console).
    log_message = pyqtSignal(str)

    # Emitted for every incoming PUBLISH message.
    message_received = pyqtSignal(MqttMessage)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._subscriptions: dict[str, int] = {}   # topic -> qos
        self._client: Client | None = None
        self._connected = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_to_broker(
        self,
        host: str,
        port: int,
        client_id: str = "",
        username: str = "",
        password: str = "",
        keepalive: int = 60,
        use_tls: bool = False,
    ) -> None:
        """Create a new paho Client and connect asynchronously."""
        self._teardown_client()

        if _USE_V2_API:
            self._client = Client(
                CallbackAPIVersion.VERSION2,
                client_id=client_id or None,
                clean_session=True,
            )
        else:
            self._client = Client(client_id=client_id or None, clean_session=True)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_log = self._on_log

        if username:
            self._client.username_pw_set(username, password or None)

        if use_tls:
            self._client.tls_set()

        try:
            self._client.connect(host, port, keepalive)
            self._client.loop_start()
            self.log_message.emit(f"Connecting to {host}:{port} …")
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def disconnect_from_broker(self) -> None:
        """Request a clean disconnect."""
        if self._client and self._connected:
            self._client.disconnect()

    def subscribe(self, topic: str, qos: int = 0) -> None:
        """Subscribe to *topic* and remember the subscription."""
        self._subscriptions[topic] = qos
        if self._client and self._connected:
            self._client.subscribe(topic, qos)
            self.log_message.emit(f"Subscribed to '{topic}' QoS={qos}")

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from *topic* and forget the subscription."""
        self._subscriptions.pop(topic, None)
        if self._client and self._connected:
            self._client.unsubscribe(topic)
            self.log_message.emit(f"Unsubscribed from '{topic}'")

    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """Publish a message. No-op when not connected."""
        if self._client and self._connected:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.error_occurred.emit(
                    f"Publish failed (rc={result.rc}) on '{topic}'"
                )
            else:
                self.log_message.emit(f"Published to '{topic}' QoS={qos} retain={retain}")
        else:
            self.error_occurred.emit("Cannot publish: not connected.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def subscriptions(self) -> dict[str, int]:
        return dict(self._subscriptions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _teardown_client(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False

    def resubscribe_all(self) -> None:
        """Re-subscribe to all remembered topics (called after reconnect)."""
        for topic, qos in self._subscriptions.items():
            self._client.subscribe(topic, qos)
            self.log_message.emit(f"Re-subscribed to '{topic}' QoS={qos}")

    # ------------------------------------------------------------------
    # paho callbacks — these run in the paho network thread.
    # Qt signals are thread-safe; we emit them directly.
    # ------------------------------------------------------------------

    def _on_connect(self, *args) -> None:
        """
        Handles both paho v1 (client, userdata, flags, rc) and
        v2 (client, userdata, flags, reason_code, properties) signatures.
        """
        # Extract rc / reason_code regardless of position
        rc = None
        reason_code = None

        if len(args) >= 4:
            if _USE_V2_API and hasattr(args[3], "is_failure"):
                reason_code = args[3]
            else:
                rc = args[3]

        success = False
        if reason_code is not None:
            success = not reason_code.is_failure
        elif rc is not None:
            success = rc == 0

        if success:
            self._connected = True
            self.connected.emit()
            self.log_message.emit("Connected to broker.")
            self.resubscribe_all()
        else:
            msg = str(reason_code) if reason_code is not None else mqtt.connack_string(rc or 0)
            self.error_occurred.emit(f"Connection refused: {msg}")

    def _on_disconnect(self, *args) -> None:
        """
        Handles both paho v1 (client, userdata, rc) and
        v2 (client, userdata, disconnect_flags, reason_code, properties) signatures.
        """
        self._connected = False
        self.disconnected.emit()

        # Determine if this was unexpected
        if _USE_V2_API and len(args) >= 4:
            reason_code = args[3]
            if hasattr(reason_code, "is_failure") and reason_code.is_failure:
                self.log_message.emit(f"Disconnected unexpectedly: {reason_code}")
            else:
                self.log_message.emit("Disconnected cleanly.")
        else:
            rc = args[2] if len(args) >= 3 else 0
            if rc != 0:
                self.log_message.emit(f"Disconnected unexpectedly (rc={rc}).")
            else:
                self.log_message.emit("Disconnected cleanly.")

    def _on_message(self, *args) -> None:
        """
        Handles both paho v1 (client, userdata, message) and
        v2 (client, userdata, message) — same positional structure.
        """
        msg: MQTTMessage = args[2] if len(args) >= 3 else args[-1]
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload_str = repr(msg.payload)

        mqtt_msg = MqttMessage(
            timestamp=datetime.now(),
            topic=msg.topic,
            payload=payload_str,
            qos=msg.qos,
            retain=bool(msg.retain),
        )
        self.message_received.emit(mqtt_msg)

    def _on_log(self, *args) -> None:
        """Forward paho log lines to our log_message signal."""
        # args: (client, userdata, level, buf) for v1; same for v2
        buf = args[-1] if args else ""
        self.log_message.emit(f"[paho] {buf}")
