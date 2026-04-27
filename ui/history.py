from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QIcon, QFont
from datetime import datetime

class HistoryItemWidget(QWidget):
    def __init__(self, sql: str, status: str, timestamp: datetime, parent=None):
        super().__init__(parent)
        self.sql = sql
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Status Icon/Label
        self.icon_label = QLabel()
        self.set_status(status)
        layout.addWidget(self.icon_label)

        # SQL Text (truncated)
        content_layout = QVBoxLayout()
        content_layout.setSpacing(0)
        
        sql_display = sql.replace("\n", " ").strip()
        if len(sql_display) > 60:
            sql_display = sql_display[:57] + "..."
            
        self.sql_label = QLabel(sql_display)
        self.sql_label.setStyleSheet("font-weight: 500; color: #374151;")
        
        time_str = timestamp.strftime("%H:%M:%S")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("font-size: 10px; color: #9ca3af;")
        
        content_layout.addWidget(self.sql_label)
        content_layout.addWidget(self.time_label)
        
        layout.addLayout(content_layout, 1)
        
    def set_status(self, status: str):
        if status == "success":
            self.icon_label.setText("✓")
            self.icon_label.setStyleSheet("color: #059669; font-weight: bold; font-size: 14px;")
        elif status == "error":
            self.icon_label.setText("✗")
            self.icon_label.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 14px;")
        else:
            self.icon_label.setText("○")
            self.icon_label.setStyleSheet("color: #9ca3af; font-weight: bold; font-size: 14px;")

class HistoryWidget(QWidget):
    query_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f3f4f6; border-bottom: 1px solid #e5e7eb;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        
        title = QLabel("Query History")
        title.setStyleSheet("font-weight: bold; color: #4b5563; font-size: 12px; text-transform: uppercase;")
        header_layout.addWidget(title)
        
        layout.addWidget(header)

        # List
        self.list = QListWidget()
        self.list.setStyleSheet("""
            QListWidget { border: none; background: white; }
            QListWidget::item { border-bottom: 1px solid #f3f4f6; }
            QListWidget::item:selected { background: #eff6ff; }
        """)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list)

    def add_entry(self, sql: str, status: str = "pending"):
        timestamp = datetime.now()
        item = QListWidgetItem(self.list)
        # Use a high size hint so the widget fits
        item.setSizeHint(QSize(0, 44))
        
        widget = HistoryItemWidget(sql, status, timestamp)
        self.list.addItem(item)
        self.list.setItemWidget(item, widget)
        self.list.scrollToBottom()
        return item

    def update_last_entry(self, status: str):
        if self.list.count() > 0:
            item = self.list.item(self.list.count() - 1)
            widget = self.list.itemWidget(item)
            if isinstance(widget, HistoryItemWidget):
                widget.set_status(status)

    def _on_item_clicked(self, item: QListWidgetItem):
        widget = self.list.itemWidget(item)
        if isinstance(widget, HistoryItemWidget):
            self.query_selected.emit(widget.sql)
