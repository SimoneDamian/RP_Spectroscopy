from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QGroupBox, QScrollArea, QPushButton,
                                QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                                QCheckBox, QLineEdit, QFrame)
from PySide6.QtCore import Qt, Signal, Slot
from copy import deepcopy


class AdvancedSettingsPage(QWidget):
    """
    Displays a scrollable list of QGroupBox widgets, one per ui_label group
    found in the advanced_settings section of the board YAML.
    Each group box contains a QTableWidget with Key/Value columns.

    Emits sig_advanced_setting_changed(dict) with the full updated settings
    whenever the user edits a value.
    """
    sig_back = Signal()
    sig_advanced_setting_changed = Signal(dict)
    sig_restore_defaults = Signal()

    def __init__(self):
        super().__init__()
        self._settings = {}       # deep copy of the live settings dict
        self._is_populating = False

        # --- Layout ---
        outer = QVBoxLayout(self)

        # Title
        title = QLabel("Advanced Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        outer.addWidget(title)

        # Scroll area for group boxes
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._scroll_content)
        outer.addWidget(self._scroll, 1)

        # Default Settings button
        self.btn_defaults = QPushButton("Default settings")
        self.btn_defaults.clicked.connect(self.on_defaults_clicked)

        # Back button
        btn_back = QPushButton("Back")
        btn_back.setFixedWidth(120)
        btn_back.clicked.connect(self.sig_back.emit)

        btn_container = QHBoxLayout()
        btn_container.addStretch()
        btn_container.addWidget(self.btn_defaults)
        btn_container.addWidget(btn_back)
        btn_container.addStretch()
        outer.addLayout(btn_container)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @Slot(dict)
    def load_advanced_settings(self, settings: dict):
        """Populate the page from the advanced_settings dict."""
        self._is_populating = True
        self._settings = deepcopy(settings)

        # Clear previous group boxes
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Build a QGroupBox + QTableWidget for every top-level key
        for group_key, group_data in self._settings.items():
            if not isinstance(group_data, dict):
                continue
            ui_label = group_data.get("ui_label", group_key)

            if group_key == "unlock_detection":
                group_box = self._build_unlock_detection_group(group_key, group_data)
                self._scroll_layout.addWidget(group_box)
                continue
            elif group_key == "gui_visualization":
                group_box = self._build_gui_visualization_group(group_key, group_data)
                self._scroll_layout.addWidget(group_box)
                continue

            group_box = QGroupBox(ui_label)
            gbox_layout = QVBoxLayout(group_box)

            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["Setting", "Value"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)

            # Flatten nested dicts into rows
            rows = []
            self._flatten(group_data, prefix="", rows=rows)

            table.setRowCount(len(rows))
            for i, (dot_path, val) in enumerate(rows):
                # Setting name (read-only)
                key_item = QTableWidgetItem(dot_path)
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, 0, key_item)

                # Value (editable)
                val_item = QTableWidgetItem(str(val))
                val_item.setData(Qt.UserRole, (group_key, dot_path))
                table.setItem(i, 1, val_item)

            # Auto-size rows
            table.resizeRowsToContents()

            # Connect edits
            table.cellChanged.connect(self._on_cell_changed)

            gbox_layout.addWidget(table)
            self._scroll_layout.addWidget(group_box)

        self._is_populating = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_unlock_detection_group(self, group_key, group_data):
        ui_label = group_data.get("ui_label", "Unlock Detection Logic")
        group_box = QGroupBox(ui_label)
        gbox_layout = QVBoxLayout(group_box)
        gbox_layout.setSpacing(10)

        for sub_key, sub_data in group_data.items():
            if sub_key == "ui_label" or not isinstance(sub_data, dict):
                continue
                
            gui_name = sub_data.get("gui_name", sub_key)
            header_lbl = QLabel(gui_name)
            header_lbl.setStyleSheet("font-weight: bold; margin-top: 5px;")
            gbox_layout.addWidget(header_lbl)
            
            # Horizontal line separator
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            gbox_layout.addWidget(line)
            
            for item_key, item_data in sub_data.items():
                if item_key == "gui_name" or not isinstance(item_data, dict):
                    continue
                    
                item_gui_name = item_data.get("gui_name", item_key)
                description = item_data.get("description", "")
                
                row_layout = QHBoxLayout()
                lbl = QLabel(item_gui_name)
                if description:
                    lbl.setToolTip(description)
                row_layout.addWidget(lbl)
                
                row_layout.addStretch()
                
                dot_path = f"{sub_key}.{item_key}"
                
                if "enabled" in item_data:
                    cb = QCheckBox()
                    cb.setChecked(item_data["enabled"])
                    # Use lambda with default args to capture current loop variables
                    cb.toggled.connect(lambda checked, gk=group_key, dp=f"{dot_path}.enabled": self._on_form_widget_changed(gk, dp, checked))
                    row_layout.addWidget(cb)
                    
                if "threshold" in item_data:
                    le = QLineEdit(str(item_data["threshold"]))
                    le.setFixedWidth(80)
                    le.editingFinished.connect(lambda gk=group_key, dp=f"{dot_path}.threshold", w=le: self._on_form_widget_changed(gk, dp, w.text()))
                    row_layout.addWidget(le)
                elif "num_points" in item_data:
                    le = QLineEdit(str(item_data["num_points"]))
                    le.setFixedWidth(80)
                    le.editingFinished.connect(lambda gk=group_key, dp=f"{dot_path}.num_points", w=le: self._on_form_widget_changed(gk, dp, w.text()))
                    row_layout.addWidget(le)
                    
                gbox_layout.addLayout(row_layout)
                
        return group_box

    def _build_gui_visualization_group(self, group_key, group_data):
        ui_label = group_data.get("ui_label", "Plotting")
        group_box = QGroupBox(ui_label)
        gbox_layout = QVBoxLayout(group_box)
        gbox_layout.setSpacing(10)

        for sub_key, sub_data in group_data.items():
            if sub_key == "ui_label" or not isinstance(sub_data, dict):
                continue
                
            gui_name = sub_data.get("gui_name", sub_key)
            header_lbl = QLabel(gui_name)
            header_lbl.setStyleSheet("font-weight: bold; margin-top: 5px;")
            gbox_layout.addWidget(header_lbl)
            
            # Horizontal line separator
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            gbox_layout.addWidget(line)
            
            # Row for the item
            row_layout = QHBoxLayout()
            item_gui_name = sub_data.get("gui_name", sub_key)
            description = sub_data.get("description", "")
            
            lbl = QLabel(item_gui_name)
            if description:
                lbl.setToolTip(description)
            row_layout.addWidget(lbl)
            row_layout.addStretch()
            
            # Check for specific entries
            if "enabled" in sub_data:
                cb = QCheckBox()
                cb.setChecked(sub_data["enabled"])
                cb.toggled.connect(lambda checked, gk=group_key, dp=f"{sub_key}.enabled": self._on_form_widget_changed(gk, dp, checked))
                row_layout.addWidget(cb)
                
            for num_key in ["fast", "slow"]:
                if num_key in sub_data:
                    row_layout.addWidget(QLabel(f"{num_key}:"))
                    le = QLineEdit(str(sub_data[num_key]))
                    le.setFixedWidth(60)
                    le.editingFinished.connect(lambda gk=group_key, dp=f"{sub_key}.{num_key}", w=le: self._on_form_widget_changed(gk, dp, w.text()))
                    row_layout.addWidget(le)
                    
            if "unit" in sub_data:
                row_layout.addWidget(QLabel(sub_data["unit"]))
                
            gbox_layout.addLayout(row_layout)
            
        return group_box

    def _on_form_widget_changed(self, group_key, dot_path, raw_value):
        """Handle edits from custom form widgets (QCheckBox, QLineEdit)."""
        if self._is_populating:
            return
            
        new_val = self._parse_value(raw_value) if isinstance(raw_value, str) else raw_value
        self._set_nested(self._settings[group_key], dot_path, new_val)
        self.sig_advanced_setting_changed.emit(deepcopy(self._settings))

    def _flatten(self, data: dict, prefix: str, rows: list):
        """
        Recursively walk a nested dict and produce (dot_path, leaf_value) tuples.
        Skips the 'ui_label' key. Dicts with a 'value' key are treated as leaf
        parameters; `options` is stored alongside for display but the editable
        cell is just the value.
        """
        for key, val in data.items():
            if key == "ui_label":
                continue

            path = f"{prefix}.{key}" if prefix else key

            if isinstance(val, dict):
                if "value" in val:
                    # Leaf parameter — show value, options are informational
                    rows.append((path, val["value"]))
                else:
                    # Nested group — recurse
                    self._flatten(val, path, rows)
            else:
                rows.append((path, val))

    def _on_cell_changed(self, row, column):
        """Handle edits in any group table."""
        if self._is_populating:
            return
        if column != 1:
            return

        # Determine which table emitted this
        table = self.sender()
        item = table.item(row, column)
        if not item:
            return

        meta = item.data(Qt.UserRole)
        if not meta:
            return
        group_key, dot_path = meta
        new_text = item.text()

        # Parse value back into correct type
        new_val = self._parse_value(new_text)

        # Update internal settings dict
        self._set_nested(self._settings[group_key], dot_path, new_val)

        self.sig_advanced_setting_changed.emit(deepcopy(self._settings))

    @staticmethod
    def _parse_value(text: str):
        """Convert a string back to bool / int / float / list / str."""
        stripped = text.strip()

        # Bool
        if stripped.lower() in ("true", "false"):
            return stripped.lower() == "true"

        # List (comma-separated or [...])
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        if "," in stripped:
            parts = [p.strip() for p in stripped.split(",")]
            parsed = []
            for p in parts:
                try:
                    parsed.append(float(p) if "." in p else int(p))
                except ValueError:
                    parsed.append(p)
            return parsed

        # Int / Float
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped  # keep as string

    @staticmethod
    def _set_nested(d: dict, dot_path: str, value):
        """Set a value in a nested dict using a dot-separated path."""
        keys = dot_path.split(".")
        for k in keys[:-1]:
            d = d[k]
        # If the leaf is a dict with a 'value' key, set that
        if isinstance(d.get(keys[-1]), dict) and "value" in d[keys[-1]]:
            d[keys[-1]]["value"] = value
        else:
            d[keys[-1]] = value

    @Slot()
    def on_defaults_clicked(self):
        """
        Shows a confirmation dialog before emitting the restore defaults signal.
        """
        reply = QMessageBox.question(self, 'Confirm Restore Defaults',
                                     "Are you sure you want to restore default advanced settings? This will overwrite all current settings.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.sig_restore_defaults.emit()
