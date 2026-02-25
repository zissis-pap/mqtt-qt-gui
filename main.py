"""
MQTT Monitor — Entry Point
"""
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from main_window import MainWindow

STYLESHEET = """
QWidget {
    background-color: #1a1b26;
    color: #c0caf5;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #1a1b26;
}

QSplitter::handle {
    background-color: #3d405b;
}

QGroupBox {
    border: 1px solid #3d405b;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    color: #7aa2f7;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #24283b;
    border: 1px solid #3d405b;
    border-radius: 3px;
    padding: 4px 6px;
    color: #c0caf5;
    selection-background-color: #7aa2f7;
    selection-color: #1a1b26;
}

QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #7aa2f7;
}

QLineEdit:disabled, QSpinBox:disabled {
    background-color: #1a1b26;
    color: #565f89;
    border-color: #292e42;
}

QPushButton {
    background-color: #24283b;
    border: 1px solid #3d405b;
    border-radius: 4px;
    padding: 5px 14px;
    color: #c0caf5;
    min-width: 60px;
}

QPushButton:hover {
    background-color: #292e42;
    border-color: #7aa2f7;
}

QPushButton:pressed {
    background-color: #1f2335;
}

QPushButton:disabled {
    color: #565f89;
    border-color: #292e42;
}

QPushButton#btn_connect {
    background-color: #9ece6a;
    color: #1a1b26;
    font-weight: bold;
    border: none;
}

QPushButton#btn_connect:hover {
    background-color: #b9f27c;
}

QPushButton#btn_connect[connected="true"] {
    background-color: #f7768e;
    color: #1a1b26;
}

QPushButton#btn_connect[connected="true"]:hover {
    background-color: #ff99aa;
}

QPushButton#btn_publish {
    background-color: #7aa2f7;
    color: #1a1b26;
    font-weight: bold;
    border: none;
}

QPushButton#btn_publish:hover {
    background-color: #9db8f8;
}

QComboBox {
    background-color: #24283b;
    border: 1px solid #3d405b;
    border-radius: 3px;
    padding: 4px 6px;
    color: #c0caf5;
    min-width: 72px;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #c0caf5;
    width: 0;
    height: 0;
}

QComboBox QAbstractItemView {
    background-color: #24283b;
    border: 1px solid #3d405b;
    selection-background-color: #7aa2f7;
    selection-color: #1a1b26;
}

QCheckBox {
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3d405b;
    border-radius: 2px;
    background-color: #24283b;
}

QCheckBox::indicator:checked {
    background-color: #7aa2f7;
    border-color: #7aa2f7;
}

QTableView {
    background-color: #1a1b26;
    alternate-background-color: #1e2030;
    border: 1px solid #3d405b;
    gridline-color: #292e42;
    selection-background-color: #2d3149;
    selection-color: #c0caf5;
}

QTableView::item {
    padding: 2px 6px;
    border: none;
}

QHeaderView::section {
    background-color: #24283b;
    color: #7aa2f7;
    border: none;
    border-right: 1px solid #3d405b;
    border-bottom: 1px solid #3d405b;
    padding: 4px 6px;
    font-weight: bold;
}

QScrollBar:vertical {
    background-color: #1a1b26;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #3d405b;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #565f89;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1a1b26;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #3d405b;
    border-radius: 5px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #565f89;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QListWidget {
    background-color: #1a1b26;
    border: 1px solid #3d405b;
    alternate-background-color: #1e2030;
}

QListWidget::item {
    padding: 3px 6px;
    border-bottom: 1px solid #292e42;
}

QListWidget::item:selected {
    background-color: #2d3149;
}

QLabel {
    background: transparent;
    color: #c0caf5;
}

QLabel#lbl_section {
    color: #7aa2f7;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QStatusBar {
    background-color: #24283b;
    border-top: 1px solid #3d405b;
    color: #c0caf5;
}

QStatusBar::item {
    border: none;
}

QMenuBar {
    background-color: #24283b;
    border-bottom: 1px solid #3d405b;
}

QMenuBar::item {
    padding: 4px 10px;
}

QMenuBar::item:selected {
    background-color: #292e42;
}

QMenu {
    background-color: #24283b;
    border: 1px solid #3d405b;
}

QMenu::item {
    padding: 5px 20px;
}

QMenu::item:selected {
    background-color: #2d3149;
}

QMenu::separator {
    height: 1px;
    background-color: #3d405b;
    margin: 2px 0;
}

QToolBar {
    background-color: #24283b;
    border-bottom: 1px solid #3d405b;
    spacing: 4px;
    padding: 2px;
}

QSplitter {
    background-color: #1a1b26;
}
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MQTT Monitor")
    app.setOrganizationName("mqtt-qt-gui")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
