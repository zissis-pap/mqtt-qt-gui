"""
Data models for the MQTT message table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QVariant,
)
from PyQt6.QtGui import QColor, QFont

from mqtt_client import MqttMessage

# Maximum number of messages kept in memory.
MAX_MESSAGES = 2000

# Tokyo Night topic colour palette (8 distinct colours).
_TOPIC_COLOURS = [
    "#7aa2f7",  # blue
    "#9ece6a",  # green
    "#e0af68",  # orange
    "#bb9af7",  # purple
    "#f7768e",  # red
    "#2ac3de",  # cyan
    "#ff9e64",  # amber
    "#73daca",  # teal
]

_COLUMNS = ["Timestamp", "Topic", "Payload", "QoS", "Retain"]
_COL_TS, _COL_TOPIC, _COL_PAYLOAD, _COL_QOS, _COL_RETAIN = range(5)


class MessageTableModel(QAbstractTableModel):
    """
    Stores up to MAX_MESSAGES MQTT messages and exposes them via the
    QAbstractTableModel interface.  Supports a substring filter that
    matches against topic and payload.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._messages: list[MqttMessage] = []
        self._filtered_indices: list[int] = []   # indices into _messages
        self._filter: str = ""

        # topic -> colour string
        self._topic_colours: dict[str, str] = {}
        self._colour_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, msg: MqttMessage) -> None:
        """Append a new message; evict the oldest if at capacity."""
        if len(self._messages) >= MAX_MESSAGES:
            self._evict_oldest()

        new_idx = len(self._messages)
        self._messages.append(msg)
        self._assign_colour(msg.topic)

        if self._matches_filter(msg):
            visible_row = len(self._filtered_indices)
            self.beginInsertRows(QModelIndex(), visible_row, visible_row)
            self._filtered_indices.append(new_idx)
            self.endInsertRows()

    def clear(self) -> None:
        """Remove all messages."""
        self.beginResetModel()
        self._messages.clear()
        self._filtered_indices.clear()
        self.endResetModel()

    def set_filter(self, text: str) -> None:
        """Rebuild filtered view for *text* (substring, case-insensitive)."""
        self.beginResetModel()
        self._filter = text.lower()
        self._filtered_indices = [
            i for i, m in enumerate(self._messages) if self._matches_filter(m)
        ]
        self.endResetModel()

    def message_at(self, visual_row: int) -> MqttMessage | None:
        """Return the MqttMessage shown at *visual_row* in the filtered view."""
        if 0 <= visual_row < len(self._filtered_indices):
            return self._messages[self._filtered_indices[visual_row]]
        return None

    def topic_colour(self, topic: str) -> str | None:
        """Hex colour string assigned to *topic*, or None."""
        return self._topic_colours.get(topic)

    @property
    def total_count(self) -> int:
        return len(self._messages)

    # ------------------------------------------------------------------
    # QAbstractTableModel overrides
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._filtered_indices)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(_COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _COLUMNS[section]
        return QVariant()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return QVariant()

        msg = self.message_at(index.row())
        if msg is None:
            return QVariant()

        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(msg, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == _COL_TOPIC:
                colour = self._topic_colours.get(msg.topic)
                if colour:
                    return QColor(colour)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (_COL_QOS, _COL_RETAIN):
                return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.UserRole:
            # Expose the full MqttMessage for convenience.
            return msg

        return QVariant()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _display_data(self, msg: MqttMessage, col: int) -> str:
        match col:
            case _ if col == _COL_TS:
                return msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
            case _ if col == _COL_TOPIC:
                return msg.topic
            case _ if col == _COL_PAYLOAD:
                # Truncate long payloads in the table cell.
                p = msg.payload
                return p if len(p) <= 120 else p[:117] + "…"
            case _ if col == _COL_QOS:
                return str(msg.qos)
            case _ if col == _COL_RETAIN:
                return "R" if msg.retain else ""
            case _:
                return ""

    def _assign_colour(self, topic: str) -> None:
        if topic not in self._topic_colours:
            colour = _TOPIC_COLOURS[self._colour_counter % len(_TOPIC_COLOURS)]
            self._topic_colours[topic] = colour
            self._colour_counter += 1

    def _matches_filter(self, msg: MqttMessage) -> bool:
        if not self._filter:
            return True
        return (
            self._filter in msg.topic.lower()
            or self._filter in msg.payload.lower()
        )

    def _evict_oldest(self) -> None:
        """Remove the oldest message (index 0) and update filtered indices."""
        # Check if the oldest message is visible.
        was_visible = 0 in self._filtered_indices

        self._messages.pop(0)

        # Shift all stored indices down by 1; remove the now-invalid 0 entry.
        new_filtered: list[int] = []
        for idx in self._filtered_indices:
            if idx == 0:
                continue  # This was the evicted message.
            new_filtered.append(idx - 1)

        if was_visible:
            # Remove the first visible row.
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._filtered_indices = new_filtered
            self.endRemoveRows()
        else:
            self._filtered_indices = new_filtered
