"""
Main Window — MQTT Monitor GUI.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from PyQt6.QtCore import (
    QSettings,
    QSize,
    Qt,
    QTimer,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models import MessageTableModel
from mqtt_client import MqttClient, MqttMessage
from storage import FileLogger

_SETTINGS_HOST = "connection/host"
_SETTINGS_PORT = "connection/port"
_SETTINGS_USER = "connection/username"
_SETTINGS_KEEPALIVE = "connection/keepalive"
_SETTINGS_LOG_DIR = "logging/directory"
_SETTINGS_LOG_FILENAME = "logging/filename"
_SETTINGS_GEOMETRY = "window/geometry"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MQTT Monitor")
        self.setMinimumSize(900, 600)

        self._client = MqttClient(self)
        self._model = MessageTableModel(self)
        self._logger: FileLogger | None = None
        self._log_dir = "logs"
        self._log_filename = ""   # empty → auto-generate

        self._build_menu()
        self._build_ui()
        self._build_status_bar()
        self._connect_signals()
        self._load_settings()

        # Refresh the message count in the status bar every second.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        act_export = QAction("&Export to CSV…", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._export_csv)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        root_layout.addWidget(splitter)

        # ── Left panel ──────────────────────────────────────────────────
        left_panel = QWidget()
        left_panel.setMinimumWidth(220)
        left_panel.setMaximumWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._build_connection_group())
        left_layout.addWidget(self._build_subscriptions_group())
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # ── Right panel ──────────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 8, 8, 4)
        right_layout.setSpacing(4)

        right_layout.addLayout(self._build_toolbar_row())
        right_layout.addWidget(self._build_message_table(), stretch=3)
        right_layout.addWidget(self._build_detail_panel(), stretch=1)

        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self._build_publish_group())

        right_layout.addWidget(bottom_widget)

        splitter.addWidget(right_panel)
        splitter.setSizes([260, 700])

    def _build_connection_group(self) -> QGroupBox:
        grp = QGroupBox("Connection")
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)

        # Host
        layout.addWidget(QLabel("Broker Host"))
        self.le_host = QLineEdit("localhost")
        layout.addWidget(self.le_host)

        # Port
        layout.addWidget(QLabel("Port"))
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(1883)
        layout.addWidget(self.sp_port)

        # Username
        layout.addWidget(QLabel("Username"))
        self.le_user = QLineEdit()
        self.le_user.setPlaceholderText("(optional)")
        layout.addWidget(self.le_user)

        # Password
        layout.addWidget(QLabel("Password"))
        self.le_pass = QLineEdit()
        self.le_pass.setPlaceholderText("(optional)")
        self.le_pass.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.le_pass)

        # Client ID
        layout.addWidget(QLabel("Client ID"))
        self.le_client_id = QLineEdit()
        self.le_client_id.setPlaceholderText("(auto-generated)")
        layout.addWidget(self.le_client_id)

        # Keepalive
        layout.addWidget(QLabel("Keepalive (s)"))
        self.sp_keepalive = QSpinBox()
        self.sp_keepalive.setRange(5, 3600)
        self.sp_keepalive.setValue(60)
        layout.addWidget(self.sp_keepalive)

        # TLS
        self.chk_tls = QCheckBox("Use TLS")
        layout.addWidget(self.chk_tls)

        # Connect button
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setProperty("connected", False)
        self.btn_connect.clicked.connect(self._toggle_connection)
        layout.addWidget(self.btn_connect)

        return grp

    def _build_subscriptions_group(self) -> QGroupBox:
        grp = QGroupBox("Subscriptions")
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)

        # New subscription row
        sub_row = QHBoxLayout()
        self.le_sub_topic = QLineEdit()
        self.le_sub_topic.setPlaceholderText("topic/# or sensor/+")
        sub_row.addWidget(self.le_sub_topic, stretch=3)

        self.cb_sub_qos = QComboBox()
        self.cb_sub_qos.addItems(["QoS 0", "QoS 1", "QoS 2"])
        self.cb_sub_qos.setMinimumWidth(72)
        sub_row.addWidget(self.cb_sub_qos, stretch=1)
        layout.addLayout(sub_row)

        self.btn_subscribe = QPushButton("Subscribe")
        self.btn_subscribe.clicked.connect(self._subscribe)
        layout.addWidget(self.btn_subscribe)

        # Subscription list
        self.lst_subscriptions = QListWidget()
        self.lst_subscriptions.setMinimumHeight(100)
        layout.addWidget(self.lst_subscriptions)

        self.btn_unsubscribe = QPushButton("Unsubscribe")
        self.btn_unsubscribe.clicked.connect(self._unsubscribe)
        layout.addWidget(self.btn_unsubscribe)

        return grp

    def _build_toolbar_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.le_filter = QLineEdit()
        self.le_filter.setPlaceholderText("Filter by topic or payload…")
        self.le_filter.setClearButtonEnabled(True)
        self.le_filter.textChanged.connect(self._apply_filter)
        row.addWidget(self.le_filter, stretch=3)

        self.chk_autoscroll = QCheckBox("⬇ Auto-scroll")
        self.chk_autoscroll.setChecked(True)
        row.addWidget(self.chk_autoscroll)

        self.chk_log = QCheckBox("◉ Log")
        self.chk_log.toggled.connect(self._toggle_logging)
        row.addWidget(self.chk_log)

        btn_log_settings = QPushButton("⚙")
        btn_log_settings.setToolTip("Log file settings…")
        btn_log_settings.setFixedWidth(28)
        btn_log_settings.clicked.connect(self._open_log_settings)
        row.addWidget(btn_log_settings)

        btn_clear = QPushButton("Clear")
        btn_clear.setToolTip("Ctrl+L")
        btn_clear.clicked.connect(self._clear_messages)
        row.addWidget(btn_clear)

        return row

    def _build_message_table(self) -> QTableView:
        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)

        # Column widths
        header = self.table.horizontalHeader()
        header.resizeSection(0, 110)  # Timestamp
        header.resizeSection(1, 200)  # Topic
        header.resizeSection(2, 300)  # Payload
        header.resizeSection(3, 40)   # QoS
        header.resizeSection(4, 45)   # Retain
        header.setStretchLastSection(True)

        self.table.selectionModel().selectionChanged.connect(self._on_row_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)

        return self.table

    def _build_detail_panel(self) -> QTextEdit:
        self.detail_panel = QTextEdit()
        self.detail_panel.setReadOnly(True)
        self.detail_panel.setPlaceholderText("Select a row to see the full payload…")
        self.detail_panel.setMaximumHeight(160)
        self.detail_panel.setFont(
            self.detail_panel.font().__class__(
                "Courier New", 11
            )
        )
        return self.detail_panel

    def _build_publish_group(self) -> QGroupBox:
        grp = QGroupBox("Publish")
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)

        # Topic
        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Topic:"))
        self.le_pub_topic = QLineEdit()
        self.le_pub_topic.setPlaceholderText("sensor/temperature")
        topic_row.addWidget(self.le_pub_topic)
        layout.addLayout(topic_row)

        # Payload
        layout.addWidget(QLabel("Payload:"))
        self.te_pub_payload = QTextEdit()
        self.te_pub_payload.setPlaceholderText('{"value": 42}')
        self.te_pub_payload.setMaximumHeight(100)
        layout.addWidget(self.te_pub_payload)

        # QoS / Retain / Publish button row
        btn_row = QHBoxLayout()
        self.cb_pub_qos = QComboBox()
        self.cb_pub_qos.addItems(["QoS 0", "QoS 1", "QoS 2"])
        self.cb_pub_qos.setMinimumWidth(72)
        btn_row.addWidget(self.cb_pub_qos)

        self.chk_pub_retain = QCheckBox("Retain")
        btn_row.addWidget(self.chk_pub_retain)

        btn_row.addStretch()

        self.btn_publish = QPushButton("Publish")
        self.btn_publish.setObjectName("btn_publish")
        self.btn_publish.setToolTip("Ctrl+Enter")
        self.btn_publish.clicked.connect(self._publish)
        btn_row.addWidget(self.btn_publish)

        layout.addLayout(btn_row)

        return grp

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self.lbl_status_conn = QLabel("● Disconnected")
        self.lbl_status_conn.setStyleSheet("color: #f7768e;")
        sb.addWidget(self.lbl_status_conn)

        sb.addWidget(_make_separator())

        self.lbl_status_msgs = QLabel("Messages: 0")
        sb.addWidget(self.lbl_status_msgs)

        sb.addWidget(_make_separator())

        self.lbl_status_log = QLabel("Logging: OFF")
        sb.addWidget(self.lbl_status_log)

        sb.addWidget(_make_separator())

        self.lbl_status_log_path = QLabel("")
        self.lbl_status_log_path.setStyleSheet("color: #565f89;")
        sb.addWidget(self.lbl_status_log_path, 1)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._client.connected.connect(self._on_connected)
        self._client.disconnected.connect(self._on_disconnected)
        self._client.error_occurred.connect(self._on_error)
        self._client.message_received.connect(self._on_message_received)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._clear_messages)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._publish)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

        # Enter in subscription field triggers subscribe
        self.le_sub_topic.returnPressed.connect(self._subscribe)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _toggle_connection(self) -> None:
        if self._client.is_connected:
            self._client.disconnect_from_broker()
        else:
            self._client.connect_to_broker(
                host=self.le_host.text().strip(),
                port=self.sp_port.value(),
                client_id=self.le_client_id.text().strip(),
                username=self.le_user.text().strip(),
                password=self.le_pass.text(),
                keepalive=self.sp_keepalive.value(),
                use_tls=self.chk_tls.isChecked(),
            )

    @pyqtSlot()
    def _on_connected(self) -> None:
        host = self.le_host.text().strip()
        port = self.sp_port.value()
        self.lbl_status_conn.setText(f"● Connected to {host}:{port}")
        self.lbl_status_conn.setStyleSheet("color: #9ece6a;")
        self.btn_connect.setText("Disconnect")
        self.btn_connect.setProperty("connected", True)
        self.btn_connect.style().unpolish(self.btn_connect)
        self.btn_connect.style().polish(self.btn_connect)
        self._set_connection_fields_enabled(False)

    @pyqtSlot()
    def _on_disconnected(self) -> None:
        self.lbl_status_conn.setText("● Disconnected")
        self.lbl_status_conn.setStyleSheet("color: #f7768e;")
        self.btn_connect.setText("Connect")
        self.btn_connect.setProperty("connected", False)
        self.btn_connect.style().unpolish(self.btn_connect)
        self.btn_connect.style().polish(self.btn_connect)
        self._set_connection_fields_enabled(True)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Error: {msg}", 5000)

    def _set_connection_fields_enabled(self, enabled: bool) -> None:
        for widget in (
            self.le_host,
            self.sp_port,
            self.le_user,
            self.le_pass,
            self.le_client_id,
            self.sp_keepalive,
            self.chk_tls,
        ):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _subscribe(self) -> None:
        topic = self.le_sub_topic.text().strip()
        if not topic:
            return
        qos = self.cb_sub_qos.currentIndex()
        self._client.subscribe(topic, qos)
        self._add_subscription_item(topic, qos)
        self.le_sub_topic.clear()

    @pyqtSlot()
    def _unsubscribe(self) -> None:
        items = self.lst_subscriptions.selectedItems()
        if not items:
            return
        for item in items:
            topic = item.data(Qt.ItemDataRole.UserRole)
            self._client.unsubscribe(topic)
            row = self.lst_subscriptions.row(item)
            self.lst_subscriptions.takeItem(row)

    def _add_subscription_item(self, topic: str, qos: int) -> None:
        # Avoid duplicates.
        for i in range(self.lst_subscriptions.count()):
            if self.lst_subscriptions.item(i).data(Qt.ItemDataRole.UserRole) == topic:
                return

        item = QListWidgetItem(f"● {topic}  (QoS {qos})")
        item.setData(Qt.ItemDataRole.UserRole, topic)

        colour = self._model.topic_colour(topic)
        if colour:
            item.setForeground(QColor(colour))

        self.lst_subscriptions.addItem(item)

    def _refresh_subscription_colours(self) -> None:
        """Update list item colours after new topics appear in the model."""
        for i in range(self.lst_subscriptions.count()):
            item = self.lst_subscriptions.item(i)
            topic = item.data(Qt.ItemDataRole.UserRole)
            colour = self._model.topic_colour(topic)
            if colour:
                item.setForeground(QColor(colour))

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    @pyqtSlot(MqttMessage)
    def _on_message_received(self, msg: MqttMessage) -> None:
        self._model.add_message(msg)

        if self._logger:
            try:
                self._logger.store_message(msg)
            except Exception as exc:
                self._on_error(f"Logger error: {exc}")

        # Update subscription list item colour (topic may be new).
        self._refresh_subscription_colours()

        if self.chk_autoscroll.isChecked():
            self.table.scrollToBottom()

    @pyqtSlot()
    def _clear_messages(self) -> None:
        self._model.clear()
        self.detail_panel.clear()

    @pyqtSlot(str)
    def _apply_filter(self, text: str) -> None:
        self._model.set_filter(text)

    # ------------------------------------------------------------------
    # Row selection — detail panel
    # ------------------------------------------------------------------

    def _on_row_selected(self, selected, _deselected) -> None:
        indexes = selected.indexes()
        if not indexes:
            self.detail_panel.clear()
            return

        row = indexes[0].row()
        msg = self._model.message_at(row)
        if msg is None:
            return

        # Attempt JSON pretty-print.
        try:
            obj = json.loads(msg.payload)
            pretty = json.dumps(obj, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pretty = msg.payload

        header = (
            f"Topic:   {msg.topic}\n"
            f"Time:    {msg.timestamp.isoformat(timespec='milliseconds')}\n"
            f"QoS:     {msg.qos}    Retain: {'Yes' if msg.retain else 'No'}\n"
            f"{'─' * 60}\n"
        )
        self.detail_panel.setPlainText(header + pretty)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_table_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        msg = self._model.message_at(index.row())
        if msg is None:
            return

        menu = QMenu(self)

        act_copy_topic = menu.addAction("Copy Topic")
        act_copy_payload = menu.addAction("Copy Payload")
        act_copy_full = menu.addAction("Copy Full Row")
        menu.addSeparator()
        act_pub_to_topic = menu.addAction("Publish to this Topic…")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        clipboard = QApplication.clipboard()

        if action == act_copy_topic:
            clipboard.setText(msg.topic)
        elif action == act_copy_payload:
            clipboard.setText(msg.payload)
        elif action == act_copy_full:
            clipboard.setText(
                f"{msg.timestamp.isoformat()}  {msg.topic}  {msg.payload}  QoS={msg.qos}"
            )
        elif action == act_pub_to_topic:
            self.le_pub_topic.setText(msg.topic)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _publish(self) -> None:
        topic = self.le_pub_topic.text().strip()
        payload = self.te_pub_payload.toPlainText()
        qos = self.cb_pub_qos.currentIndex()
        retain = self.chk_pub_retain.isChecked()

        if not topic:
            self._on_error("Publish topic cannot be empty.")
            return

        self._client.publish(topic, payload, qos=qos, retain=retain)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @pyqtSlot(bool)
    def _toggle_logging(self, enabled: bool) -> None:
        if enabled:
            self._start_logging()
        else:
            self._stop_logging()

    def _start_logging(self) -> None:
        log_dir = self._log_dir or "logs"
        try:
            self._logger = FileLogger(directory=log_dir, filename=self._log_filename)
            self.lbl_status_log.setText("Logging: ON")
            self.lbl_status_log.setStyleSheet("color: #9ece6a;")
            self.lbl_status_log_path.setText(self._logger.info)
        except Exception as exc:
            self._on_error(f"Cannot start logger: {exc}")
            self.chk_log.setChecked(False)

    @pyqtSlot()
    def _open_log_settings(self) -> None:
        dlg = LogSettingsDialog(self._log_dir, self._log_filename, parent=self)
        if dlg.exec():
            self._log_dir, self._log_filename = dlg.result_dir, dlg.result_filename
            # If logging is already active, restart it with the new path.
            if self._logger:
                self._stop_logging()
                self._start_logging()
                self.chk_log.setChecked(True)

    def _stop_logging(self) -> None:
        if self._logger:
            self._logger.close()
            self._logger = None
        self.lbl_status_log.setText("Logging: OFF")
        self.lbl_status_log.setStyleSheet("")
        self.lbl_status_log_path.setText("")

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Messages to CSV",
            "mqtt_export.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Topic", "Payload", "QoS", "Retain"])
                for idx in self._model._filtered_indices:
                    msg = self._model._messages[idx]
                    writer.writerow([
                        msg.timestamp.isoformat(timespec="milliseconds"),
                        msg.topic,
                        msg.payload,
                        msg.qos,
                        "Yes" if msg.retain else "No",
                    ])
            self.statusBar().showMessage(f"Exported to {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Status bar refresh
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _refresh_status(self) -> None:
        total = self._model.total_count
        visible = self._model.rowCount()
        if self._model._filter:
            self.lbl_status_msgs.setText(f"Messages: {visible}/{total}")
        else:
            self.lbl_status_msgs.setText(f"Messages: {total}")

    # ------------------------------------------------------------------
    # QSettings persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        s = QSettings()
        self.le_host.setText(s.value(_SETTINGS_HOST, "localhost"))
        self.sp_port.setValue(int(s.value(_SETTINGS_PORT, 1883)))
        self.le_user.setText(s.value(_SETTINGS_USER, ""))
        self.sp_keepalive.setValue(int(s.value(_SETTINGS_KEEPALIVE, 60)))
        self._log_dir = s.value(_SETTINGS_LOG_DIR, "logs")
        self._log_filename = s.value(_SETTINGS_LOG_FILENAME, "")

        geom = s.value(_SETTINGS_GEOMETRY)
        if geom:
            self.restoreGeometry(geom)

    def _save_settings(self) -> None:
        s = QSettings()
        s.setValue(_SETTINGS_HOST, self.le_host.text())
        s.setValue(_SETTINGS_PORT, self.sp_port.value())
        s.setValue(_SETTINGS_USER, self.le_user.text())
        s.setValue(_SETTINGS_KEEPALIVE, self.sp_keepalive.value())
        s.setValue(_SETTINGS_LOG_DIR, self._log_dir)
        s.setValue(_SETTINGS_LOG_FILENAME, self._log_filename)
        s.setValue(_SETTINGS_GEOMETRY, self.saveGeometry())

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._save_settings()
        self._stop_logging()
        if self._client.is_connected:
            self._client.disconnect_from_broker()
        event.accept()


# ---------------------------------------------------------------------------
# Log settings dialog
# ---------------------------------------------------------------------------

class LogSettingsDialog(QDialog):
    """
    Small dialog for configuring the log file directory and filename.

    After ``exec()`` returns ``QDialog.DialogCode.Accepted``:
        dlg.result_dir      — chosen directory (str)
        dlg.result_filename — chosen filename, or "" for auto-generate (str)
    """

    def __init__(self, current_dir: str, current_filename: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log File Settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Directory ─────────────────────────────────────────────────
        layout.addWidget(QLabel("Log Directory"))
        dir_row = QHBoxLayout()
        self._le_dir = QLineEdit(current_dir or "logs")
        self._le_dir.setPlaceholderText("logs")
        dir_row.addWidget(self._le_dir)
        btn_browse_dir = QPushButton("Browse…")
        btn_browse_dir.setFixedWidth(80)
        btn_browse_dir.clicked.connect(self._browse_directory)
        dir_row.addWidget(btn_browse_dir)
        layout.addLayout(dir_row)

        # ── Filename ───────────────────────────────────────────────────
        layout.addWidget(QLabel("Filename"))
        self._le_filename = QLineEdit(current_filename)
        self._le_filename.setPlaceholderText("leave blank to auto-generate  (e.g. mqtt_20260224_153000.txt)")
        layout.addWidget(self._le_filename)

        hint = QLabel(
            "Tip: use an absolute path in the filename field to ignore the directory above.\n"
            "Leave the filename blank to create a new timestamped file each session."
        )
        hint.setStyleSheet("color: #565f89; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.result_dir = current_dir
        self.result_filename = current_filename

    def _browse_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            self._le_dir.text() or ".",
        )
        if chosen:
            self._le_dir.setText(chosen)

    def accept(self) -> None:
        self.result_dir = self._le_dir.text().strip() or "logs"
        self.result_filename = self._le_filename.text().strip()
        super().accept()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color: #3d405b;")
    return sep
