from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QStackedWidget,
                               QPushButton, QFrame, QHBoxLayout, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit,
                               QFormLayout)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from gui.plot_panel import PlotPanel
from gui.advanced_settings_page import AdvancedSettingsPage




class MenuButton(QPushButton):
    def __init__(self, text, on_click_callback=None):
        super().__init__(text)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 10px;
                text-align: center;
            }
        """)
        if on_click_callback:
            self.clicked.connect(on_click_callback)

class MenuPage(QWidget):
    # Signals to request navigation
    sig_go_parameters = Signal()
    sig_go_advanced = Signal()
    sig_go_reflines = Signal()
    sig_go_scan = Signal()
    sig_go_centering = Signal()
    sig_go_manual = Signal()
    sig_go_auto = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 6 Buttons equidistant
        self.btn_params = MenuButton("Parameters", self.sig_go_parameters.emit)
        self.btn_advanced = MenuButton("Advanced settings", self.sig_go_advanced.emit)
        self.btn_reflines = MenuButton("Reference lines", self.sig_go_reflines.emit)
        self.btn_scan = MenuButton("Scan", self.sig_go_scan.emit)
        self.btn_centering = MenuButton("Line centering", self.sig_go_centering.emit)
        self.btn_manual = MenuButton("Manual lock", self.sig_go_manual.emit)
        self.btn_auto = MenuButton("Auto-lock", self.sig_go_auto.emit)

        layout.addWidget(self.btn_params)
        layout.addWidget(self.btn_advanced)
        layout.addWidget(self.btn_reflines)
        layout.addWidget(self.btn_scan)
        layout.addWidget(self.btn_centering)
        layout.addWidget(self.btn_manual)
        layout.addWidget(self.btn_auto)

class SubPageContainer(QWidget):
    """
    A generic container for sub-pages that provides a title and a back button.
    """
    sig_back = Signal()

    def __init__(self, title, content_widget=None):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Title
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(lbl_title)
        
        # Content (stretch factor to push back button down)
        if content_widget:
            layout.addWidget(content_widget)
        else:
             layout.addStretch()

        # Back Button centered at bottom
        btn_back = QPushButton("Back")
        btn_back.setFixedWidth(120)
        btn_back.clicked.connect(self.sig_back.emit)
        
        btn_container = QHBoxLayout()
        btn_container.addStretch()
        btn_container.addWidget(btn_back)
        btn_container.addStretch()
        
        layout.addLayout(btn_container)

class ParametersPage(SubPageContainer):
    sig_restore_defaults = Signal()
    sig_parameter_changed = Signal(str, object)  # (param_name, new_value)

    def __init__(self, title="Parameters"):
        super().__init__(title)
        
        # --- Table Setup ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Variable Name", "Hardware Name", "Value", "Scaling"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        
        # Connect cell changed signal (for edits)
        self.table.cellChanged.connect(self.on_cell_changed)
        
        # Parameters Dictionary Reference
        self.params = {} 
        self._is_populating = False # Flag to prevent signal loops during population

        # --- Default Settings Button ---
        self.btn_defaults = QPushButton("Default settings")
        self.btn_defaults.clicked.connect(self.on_defaults_clicked)
        
        # Add to layout (insert before the back button/stretch)
        # Access the layout from SubPageContainer
        # Custom Layout Management
        # SubPageContainer calculates layout: Title(0), Stretch(1), ButtonLayout(2).
        # We want to replace the default Stretch with our expanding content.
        layout = self.layout()
        
        # Remove the default stretch item at index 1
        item = layout.takeAt(1)
        if item:
            del item

        # Create container for Table + Defaults Button
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.table)
        content_layout.addWidget(self.btn_defaults)
        
        # Insert our content at index 1 with a stretch factor of 1
        # This ensures the table expands to fill available space
        layout.insertWidget(1, content_widget, 1)
        
    def load_parameters(self, params_dict):
        """
        Populate the table from a plain dict (from YAML writeable_parameters section).
        params_dict: dict with 'writeable_parameters' key containing {name: {hardware_name, initial_value, scaling}}
        """
        self.params = params_dict.get('writeable_parameters', {})
        self._is_populating = True
        self.table.setRowCount(0)
        
        for name, entry in self.params.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 0: Variable Name (Key in dict)
            item_name = QTableWidgetItem(name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable) # Read Only
            self.table.setItem(row, 0, item_name)
            
            # 1: Hardware Name
            item_hw = QTableWidgetItem(str(entry.get('hardware_name', '')))
            item_hw.setFlags(item_hw.flags() & ~Qt.ItemIsEditable) # Read Only
            self.table.setItem(row, 1, item_hw)
            
            # 2: Value
            val = entry.get('initial_value', 0)
            if isinstance(val, float):
                val_str = f"{val:.6g}" # Use general format
            else:
                val_str = str(val)
                
            item_val = QTableWidgetItem(val_str)
            item_val.setData(Qt.UserRole, name) # Store key for lookup
            self.table.setItem(row, 2, item_val)
            
            # 3: Scaling
            scaling = entry.get('scaling', None)
            scaling_str = str(scaling) if scaling is not None else "None"
            item_scale = QTableWidgetItem(scaling_str)
            item_scale.setFlags(item_scale.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, item_scale)
            
        self._is_populating = False

    def on_cell_changed(self, row, column):
        if self._is_populating:
            return
            
        # Only care about Value column (index 2)
        if column != 2:
            return
            
        item = self.table.item(row, column)
        param_name = item.data(Qt.UserRole)
        new_val_str = item.text()
        
        if param_name in self.params:
            entry = self.params[param_name]
            try:
                # Convert string back to float/int
                val_float = float(new_val_str)
                
                # Check if we should convert to int
                # If scaling is None, it implies it might be an index or boolean-like int
                scaling = entry.get('scaling', None)
                if scaling is None and val_float.is_integer():
                     new_val = int(val_float)
                else:
                     new_val = val_float

                # Emit signal instead of directly calling param.set_value()
                self.sig_parameter_changed.emit(param_name, new_val)
                
            except ValueError:
                # Handle invalid input — ignore for now
                pass

    @Slot()
    def on_defaults_clicked(self):
        """
        Shows a confirmation dialog before emitting the restore defaults signal.
        """
        reply = QMessageBox.question(self, 'Confirm Restore Defaults', 
                                     "Are you sure you want to restore default parameters? This will overwrite all current settings.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.sig_restore_defaults.emit()
                
class ScanPage(QWidget):
    """
    Scan sub-page with voltage-range inputs and start/stop controls.
    """
    sig_start_scan = Signal(float, float, int)
    sig_stop_scan = Signal()
    sig_back = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Title ---
        lbl_title = QLabel("Scan")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(lbl_title)

        # --- Input row ---
        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)

        self.input_start_v = QLineEdit("0.05")
        self.input_start_v.setValidator(QDoubleValidator())
        form_layout.addRow("Start voltage:", self.input_start_v)

        self.input_end_v = QLineEdit("1.75")
        self.input_end_v.setValidator(QDoubleValidator())
        form_layout.addRow("End voltage:", self.input_end_v)

        self.input_num_pts = QLineEdit("40")
        self.input_num_pts.setValidator(QIntValidator(1, 100000))
        form_layout.addRow("Number of points:", self.input_num_pts)

        layout.addLayout(form_layout)

        # --- Button row: Start / Stop ---
        btn_row = QHBoxLayout()
        self.btn_start_scan = QPushButton("Start scan")
        self.btn_stop_scan = QPushButton("Stop scan")
        self.btn_stop_scan.setEnabled(False)
        btn_row.addWidget(self.btn_start_scan)
        btn_row.addWidget(self.btn_stop_scan)
        layout.addLayout(btn_row)

        # Spacer to push back button to the bottom
        layout.addStretch()

        # --- Back button ---
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedWidth(120)
        btn_back_container = QHBoxLayout()
        btn_back_container.addStretch()
        btn_back_container.addWidget(self.btn_back)
        btn_back_container.addStretch()
        layout.addLayout(btn_back_container)

        # --- Internal wiring ---
        self.btn_start_scan.clicked.connect(self._on_start_clicked)
        self.btn_stop_scan.clicked.connect(self._on_stop_clicked)
        self.btn_back.clicked.connect(self.sig_back.emit)

    def _on_start_clicked(self):
        try:
            start_v = float(self.input_start_v.text())
            end_v = float(self.input_end_v.text())
            num_pts = int(self.input_num_pts.text())
        except ValueError:
            return  # Ignore if inputs are invalid

        # Disable start + back, enable stop
        self.btn_start_scan.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_stop_scan.setEnabled(True)

        self.sig_start_scan.emit(start_v, end_v, num_pts)

    def _on_stop_clicked(self):
        self.sig_stop_scan.emit()
        self.set_scan_finished()

    @Slot()
    def set_scan_finished(self):
        """Re-enable buttons after scan completes or is stopped."""
        self.btn_start_scan.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_stop_scan.setEnabled(False)


class LaserControllerPage(QWidget):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- LEFT PANEL: Navigation Stack ---
        self.left_stack = QStackedWidget()
        self.left_stack.setMinimumWidth(350) # Increased width for Table
        
        # 1. Main Menu
        self.menu_page = MenuPage()
        self.left_stack.addWidget(self.menu_page)
        
        # 2. Sub Pages
        self.page_parameters = ParametersPage() # REAL PAGE
        self.page_advanced = AdvancedSettingsPage()
        self.page_scan = ScanPage()
        self.page_centering = SubPageContainer("Line Centering")
        self.page_manual = SubPageContainer("Manual Lock")
        self.page_auto = SubPageContainer("Auto-lock")
        
        self.left_stack.addWidget(self.page_parameters)
        self.left_stack.addWidget(self.page_advanced)
        self.left_stack.addWidget(self.page_scan)
        self.left_stack.addWidget(self.page_centering)
        self.left_stack.addWidget(self.page_manual)
        self.left_stack.addWidget(self.page_auto)
        
        splitter.addWidget(self.left_stack)
        
        # --- RIGHT PANEL: Live Plot Panel ---
        self.plot_panel = PlotPanel()
        splitter.addWidget(self.plot_panel)
        
        # --- WIRING ---
        # Menu -> Pages
        self.menu_page.sig_go_parameters.connect(lambda: self.left_stack.setCurrentWidget(self.page_parameters))
        self.menu_page.sig_go_advanced.connect(lambda: self.left_stack.setCurrentWidget(self.page_advanced))
        self.menu_page.sig_go_scan.connect(lambda: self.left_stack.setCurrentWidget(self.page_scan))
        self.menu_page.sig_go_centering.connect(lambda: self.left_stack.setCurrentWidget(self.page_centering))
        self.menu_page.sig_go_manual.connect(lambda: self.left_stack.setCurrentWidget(self.page_manual))
        self.menu_page.sig_go_auto.connect(lambda: self.left_stack.setCurrentWidget(self.page_auto))
        
        # Reference lines currently does nothing
        self.menu_page.sig_go_reflines.connect(self.on_reflines_clicked)

        # Back Buttons -> Menu
        self.page_parameters.sig_back.connect(self.go_to_menu)
        self.page_advanced.sig_back.connect(self.go_to_menu)
        self.page_scan.sig_back.connect(self.on_scan_back)
        self.page_centering.sig_back.connect(self.go_to_menu)
        self.page_manual.sig_back.connect(self.go_to_menu)
        self.page_auto.sig_back.connect(self.go_to_menu)
        
        # Set Splitter Ratios (Left smaller, Right larger)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        # Initial State
        self.set_connecting_state()

    @Slot()
    def set_connecting_state(self):
        self.set_menu_enabled(False)

    @Slot()
    def set_connected_state(self):
        self.set_menu_enabled(True)

    def set_menu_enabled(self, enabled):
        self.menu_page.btn_params.setEnabled(enabled)
        self.menu_page.btn_advanced.setEnabled(enabled)
        self.menu_page.btn_reflines.setEnabled(enabled)
        self.menu_page.btn_scan.setEnabled(enabled)
        self.menu_page.btn_centering.setEnabled(enabled)
        self.menu_page.btn_manual.setEnabled(enabled)
        self.menu_page.btn_auto.setEnabled(enabled)

    @Slot()
    def go_to_menu(self):
        self.left_stack.setCurrentWidget(self.menu_page)
        
    @Slot()
    def on_scan_back(self):
        """Return to menu from scan page. start_sweep is wired via GeneralManager."""
        self.left_stack.setCurrentWidget(self.menu_page)

    @Slot()
    def on_reflines_clicked(self):
        self.logger.info("Reference Lines button clicked - (No Action implemented)")
