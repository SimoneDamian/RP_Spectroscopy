import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QStackedWidget,
                               QPushButton, QFrame, QHBoxLayout, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit,
                               QFormLayout, QScrollArea, QComboBox)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from gui.plot_panel import PlotPanel
from gui.advanced_settings_page import AdvancedSettingsPage
from gui.reference_lines_page import ReferenceLinesPage
from gui.add_reference_line_page import AddReferenceLinePage
from gui.line_centering_page import LineCenteringPage




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
    sig_go_optimization = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Buttons equidistant
        self.btn_params = MenuButton("Parameters", self.sig_go_parameters.emit)
        self.btn_advanced = MenuButton("Advanced settings", self.sig_go_advanced.emit)
        self.btn_reflines = MenuButton("Reference lines", self.sig_go_reflines.emit)
        self.btn_scan = MenuButton("Scan", self.sig_go_scan.emit)
        self.btn_centering = MenuButton("Line centering", self.sig_go_centering.emit)
        self.btn_manual = MenuButton("Manual lock", self.sig_go_manual.emit)
        self.btn_auto = MenuButton("Auto-lock", self.sig_go_auto.emit)
        self.btn_optimization = MenuButton("Optimization", self.sig_go_optimization.emit)

        layout.addWidget(self.btn_params)
        layout.addWidget(self.btn_advanced)
        layout.addWidget(self.btn_reflines)
        layout.addWidget(self.btn_scan)
        layout.addWidget(self.btn_centering)
        layout.addWidget(self.btn_manual)
        layout.addWidget(self.btn_auto)
        layout.addWidget(self.btn_optimization)

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

    def __init__(self, logger, title="Parameters"):
        super().__init__(title)
        self.logger = logger
        
        # --- Table Setup ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Value", "Units", "Min", "Max"])
        
        # Configure column resizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)          # Name column expands
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Value column fits content
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Units column fits content
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Min column fits content
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Max column fits content
        
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
        params_dict: dict with 'writeable_parameters' key containing
        {name: {hardware_name, gui_name, description, type, initial_value, min, max, scaling, units}}
        """
        self.params = params_dict.get('writeable_parameters', {})
        self._is_populating = True
        self.table.setRowCount(0)
        
        for name, entry in self.params.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 0: Name (gui_name from YAML) — read-only, with tooltip
            gui_name = entry.get('gui_name', name)
            item_name = QTableWidgetItem(str(gui_name))
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)  # Read Only
            description = entry.get('description', '')
            if description:
                item_name.setToolTip(str(description))
            self.table.setItem(row, 0, item_name)
            
            # 1: Value (initial_value) — editable
            val = entry.get('initial_value', 0)
            if isinstance(val, float):
                val_str = f"{val:.6g}"  # Use general format
            else:
                val_str = str(val)
            item_val = QTableWidgetItem(val_str)
            item_val.setData(Qt.UserRole, name)  # Store dict key for lookup
            item_val.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, item_val)
            
            # 2: Units — read-only
            units = entry.get('units', None)
            units_str = str(units) if units is not None else ""
            item_units = QTableWidgetItem(units_str)
            item_units.setFlags(item_units.flags() & ~Qt.ItemIsEditable)
            item_units.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, item_units)
            
            # 3: Min — read-only
            min_val = entry.get('min', None)
            min_str = str(min_val) if min_val is not None else ""
            item_min = QTableWidgetItem(min_str)
            item_min.setFlags(item_min.flags() & ~Qt.ItemIsEditable)
            item_min.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, item_min)
            
            # 4: Max — read-only
            max_val = entry.get('max', None)
            max_str = str(max_val) if max_val is not None else ""
            item_max = QTableWidgetItem(max_str)
            item_max.setFlags(item_max.flags() & ~Qt.ItemIsEditable)
            item_max.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, item_max)
            
        self._is_populating = False

    def on_cell_changed(self, row, column):
        if self._is_populating:
            return
            
        # Only care about Value column (index 1)
        if column != 1:
            return
            
        item = self.table.item(row, column)
        param_name = item.data(Qt.UserRole)
        new_val_str = item.text()
        
        if param_name in self.params:
            entry = self.params[param_name]
            param_type = entry.get('type', 'float')
            try:
                if param_type == 'bool':
                    # Accept common boolean string representations
                    new_val = new_val_str.strip().lower() in ('true', '1', 'yes')
                elif param_type == 'int':
                    new_val = int(float(new_val_str))
                else:
                    new_val = float(new_val_str)

                # Emit signal instead of directly calling param.set_value()
                self.sig_parameter_changed.emit(param_name, new_val)
                
                # Log the change
                gui_name = entry.get('gui_name', param_name)
                if self.logger:
                    self.logger.info(f"Parameter changed: {gui_name} = {new_val}")
                
            except ValueError:
                # Handle invalid input — ignore for now
                pass

    @Slot(str, object)
    def update_parameter(self, param_name, new_val):
        """Updates the value of a specific parameter in the table."""
        if param_name not in self.params:
            return
            
        for row in range(self.table.rowCount()):
            item_val = self.table.item(row, 1)
            if item_val and item_val.data(Qt.UserRole) == param_name:
                self._is_populating = True
                if isinstance(new_val, float):
                    val_str = f"{new_val:.6g}"
                else:
                    val_str = str(new_val)
                item_val.setText(val_str)
                self._is_populating = False
                break

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


class ManualLockPage(SubPageContainer):
    """
    Manual Lock sub-page for setting lock region boundaries.
    """
    sig_region_changed = Signal(float, float)
    sig_start_lock = Signal(float, float)

    def __init__(self, title="Manual Lock"):
        super().__init__(title)
        
        # --- Description Text ---
        self.lbl_desc = QLabel(
            "Choose the boundaries of the lock region. Keep in mid that the lock point "
            "will be determined by the zero-crossing point between a minimum and a maximum "
            "of the error signal inside the lock region."
        )
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("margin-bottom: 10px;")

        # --- Input row ---
        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)

        self.input_x0 = QLineEdit("0.0")
        self.input_x0.setValidator(QDoubleValidator())
        form_layout.addRow("Left boundary:", self.input_x0)

        self.input_x1 = QLineEdit("1.0")
        self.input_x1.setValidator(QDoubleValidator())
        form_layout.addRow("Right boundary:", self.input_x1)

        # --- Start Lock Button ---
        self.btn_start_lock = QPushButton("Start lock")
        
        # Add to layout (insert before the back button/stretch)
        layout = self.layout()
        
        # Remove the default stretch item at index 1
        item = layout.takeAt(1)
        if item:
            del item

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.lbl_desc)
        content_layout.addLayout(form_layout)
        content_layout.addWidget(self.btn_start_lock)
        content_layout.addStretch() # Push everything up
        
        layout.insertWidget(1, content_widget, 1)

        # --- Internal wiring ---
        self.input_x0.textChanged.connect(self._on_inputs_changed)
        self.input_x1.textChanged.connect(self._on_inputs_changed)
        self.btn_start_lock.clicked.connect(self._on_start_lock_clicked)

    def _on_start_lock_clicked(self):
        try:
            x0 = float(self.input_x0.text())
            x1 = float(self.input_x1.text())
            self.sig_start_lock.emit(x0, x1)
        except ValueError:
            pass

    def _on_inputs_changed(self):
        try:
            x0 = float(self.input_x0.text())
            x1 = float(self.input_x1.text())
            self.sig_region_changed.emit(x0, x1)
        except ValueError:
            pass


class OptimizationPage(QWidget):
    """
    Optimization sub-page with demodulation phase optimization controls.
    """
    sig_start = Signal()
    sig_stop = Signal()
    sig_back = Signal()
    sig_set_phase = Signal(float)

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Page Title ---
        lbl_title = QLabel("Optimization page")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # --- Section separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # --- Section Title ---
        lbl_section = QLabel("Demodulation phase optimization")
        lbl_section.setAlignment(Qt.AlignCenter)
        lbl_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 5px; margin-bottom: 5px;")
        layout.addWidget(lbl_section)

        # --- Start / Stop buttons ---
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_start.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.btn_stop.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        layout.addLayout(btn_row)

        # --- Plot: ratio vs phase ---
        self.plot_ratio = pg.PlotWidget(title="Ratio vs Phase")
        self.plot_ratio.setBackground('w')
        self.plot_ratio.showGrid(x=True, y=True)
        self.plot_ratio.setMinimumHeight(200)
        plot_item = self.plot_ratio.getPlotItem()
        plot_item.setLabel('bottom', 'Phase', units='°')
        plot_item.setLabel('left', 'Ratio')
        plot_item.getAxis('bottom').enableAutoSIPrefix(False)
        plot_item.getAxis('left').enableAutoSIPrefix(False)
        self.curve_ratio = plot_item.plot(pen='g', symbol='o', symbolSize=5)
        layout.addWidget(self.plot_ratio)

        self.ratio_x = []  # phases
        self.ratio_y = []  # ratios

        # --- Phase set row ---
        phase_row = QHBoxLayout()
        lbl_set = QLabel("Set demodulation phase to")
        self.input_phase = QLineEdit()
        self.input_phase.setValidator(QDoubleValidator())
        lbl_q = QLabel("?")
        self.btn_plus90 = QPushButton("+90°")
        self.btn_minus90 = QPushButton("-90°")
        self.btn_set = QPushButton("Set")

        phase_row.addWidget(lbl_set)
        phase_row.addWidget(self.input_phase)
        phase_row.addWidget(lbl_q)
        phase_row.addWidget(self.btn_plus90)
        phase_row.addWidget(self.btn_minus90)
        phase_row.addWidget(self.btn_set)
        layout.addLayout(phase_row)

        layout.addStretch()

        # --- Back button ---
        self.btn_back = QPushButton("Back")
        layout.addWidget(self.btn_back)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # --- Internal wiring ---
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_back.clicked.connect(self.sig_back.emit)
        self.btn_plus90.clicked.connect(self._on_plus90)
        self.btn_minus90.clicked.connect(self._on_minus90)
        self.btn_set.clicked.connect(self._on_set_clicked)

    def _on_start_clicked(self):
        self.btn_start.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # Reset plot data
        self.ratio_x = []
        self.ratio_y = []
        self.curve_ratio.setData([], [])

        self.sig_start.emit()

    def _on_stop_clicked(self):
        self.sig_stop.emit()
        self.set_optimization_finished()

    @Slot()
    def set_optimization_finished(self):
        """Re-enable buttons after optimization completes or is stopped."""
        self.btn_start.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_stop.setEnabled(False)

    @Slot(dict)
    def handle_data(self, packet):
        """Process DEMOD_PHASE_OPTIMIZATION packets to update the ratio plot."""
        if packet.get("mode") != "DEMOD_PHASE_OPTIMIZATION":
            return

        step = packet.get("step_index", 0)
        if step == len(self.ratio_x):
            current_phase = packet.get("current_phase", 0.0)
            ratio = packet.get("ratio", 0.0)

            self.ratio_x.append(current_phase)
            self.ratio_y.append(ratio)
            self.curve_ratio.setData(self.ratio_x, self.ratio_y)

            # Update textbox with phase of greatest ratio
            if len(self.ratio_y) > 0:
                max_idx = np.argmax(self.ratio_y)
                self.input_phase.setText(f"{self.ratio_x[max_idx]:.2f}")

    def _on_plus90(self):
        try:
            val = float(self.input_phase.text())
        except ValueError:
            return
        val = (val + 90) % 360
        self.input_phase.setText(f"{val:.2f}")

    def _on_minus90(self):
        try:
            val = float(self.input_phase.text())
        except ValueError:
            return
        val = (val - 90) % 360
        self.input_phase.setText(f"{val:.2f}")

    def _on_set_clicked(self):
        try:
            phase_val = float(self.input_phase.text())
            self.sig_set_phase.emit(phase_val)
        except ValueError:
            pass


class AutoLockPage(QWidget):
    """
    Auto-lock sub-page: selects a reference line, scans a voltage range,
    and triggers the autolock procedure on LaserManager.
    """
    sig_start_autolock = Signal(float, float, dict)
    sig_stop_scan = Signal()
    sig_back = Signal()

    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger
        self.service_manager = None
        self.current_reference_data = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- 1. Title ---
        lbl_title = QLabel("Automatic lock")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # --- 2. Reference Line Selection ---
        ref_row = QHBoxLayout()
        lbl_ref = QLabel("Select the line to lock to")
        self.combo_refline = QComboBox()
        ref_row.addWidget(lbl_ref)
        ref_row.addWidget(self.combo_refline)
        layout.addLayout(ref_row)

        # --- 3. Plot: Reference Line Preview ---
        self.plot_ref = pg.PlotWidget(title="Reference Line")
        self.plot_ref.setBackground('w')
        self.plot_ref.showGrid(x=True, y=True)
        self.plot_ref.setMinimumHeight(200)
        self.plot_ref_item = self.plot_ref.getPlotItem()
        self.plot_ref_item.setLabel('bottom', 'V', units='V')
        self.plot_ref_item.setLabel('left', 'Signal')
        self.plot_ref_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_ref_item.getAxis('left').enableAutoSIPrefix(False)
        self.curve_ref = self.plot_ref_item.plot(pen='b')
        layout.addWidget(self.plot_ref)

        # --- 4. Voltage Range Inputs ---
        lbl_voltage = QLabel("Select the voltage range within which look for the reference line")
        lbl_voltage.setWordWrap(True)
        layout.addWidget(lbl_voltage)

        voltage_form = QFormLayout()
        voltage_form.setHorizontalSpacing(12)
        voltage_form.setVerticalSpacing(8)

        self.input_start_v = QLineEdit("0.05")
        self.input_start_v.setValidator(QDoubleValidator())
        voltage_form.addRow("Start voltage:", self.input_start_v)

        self.input_end_v = QLineEdit("1.75")
        self.input_end_v.setValidator(QDoubleValidator())
        voltage_form.addRow("Stop voltage:", self.input_end_v)

        layout.addLayout(voltage_form)

        # --- 5. Start / Stop Buttons ---
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)

        self.btn_start.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_stop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        layout.addLayout(btn_row)

        # --- 6. Plot: Scan / Correlation Results ---
        self.plot_corr = pg.PlotWidget(title="Correlations")
        self.plot_corr.setBackground('w')
        self.plot_corr.showGrid(x=True, y=True)
        self.plot_corr.setMinimumHeight(200)
        self.plot_corr_item = self.plot_corr.getPlotItem()
        self.plot_corr_item.setLabel('bottom', 'V', units='V')
        self.plot_corr_item.setLabel('left', 'Correlation')
        self.plot_corr_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_corr_item.getAxis('left').enableAutoSIPrefix(False)
        self.curve_corr = self.plot_corr_item.plot(pen='g', symbol='o', symbolSize=5)
        layout.addWidget(self.plot_corr)

        self.corr_x = []
        self.corr_y = []

        layout.addStretch()

        # --- 7. Back Button (full width) ---
        self.btn_back = QPushButton("Back")
        layout.addWidget(self.btn_back)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # --- Wiring ---
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_back.clicked.connect(self.sig_back.emit)
        self.combo_refline.currentIndexChanged.connect(self._on_refline_selected)

    # ---- ServiceManager integration (same pattern as LineCenteringPage) ----

    def set_service_manager(self, sm):
        self.service_manager = sm
        if self.service_manager:
            self.service_manager.sig_reflines_updated.connect(self._update_refline_combo)
            self.service_manager.get_reference_lines()

    @Slot(list)
    def _update_refline_combo(self, data_list):
        self.current_reference_data = data_list
        self.combo_refline.blockSignals(True)
        self.combo_refline.clear()
        self.combo_refline.addItem("None")
        for item in data_list:
            self.combo_refline.addItem(item.get('name', 'Unknown'))
        self.combo_refline.blockSignals(False)

    @Slot(int)
    def _on_refline_selected(self, index):
        if index <= 0 or not self.service_manager:
            self.curve_ref.clear()
            return

        selected_name = self.combo_refline.itemText(index)
        item_data = next((i for i in self.current_reference_data if i['name'] == selected_name), None)

        if item_data:
            filename = item_data.get('file_name', item_data.get('file', item_data.get('name', '')))
            x, y = self.service_manager.get_reference_line_data(filename)
            if x is not None and y is not None:
                self.curve_ref.setData(x, y)
            else:
                self.curve_ref.clear()
        else:
            self.curve_ref.clear()

    # ---- Button handlers ----

    def _on_start_clicked(self):
        try:
            start_v = float(self.input_start_v.text())
            end_v = float(self.input_end_v.text())
        except ValueError:
            return

        index = self.combo_refline.currentIndex()
        if index <= 0 or not self.service_manager:
            return

        selected_name = self.combo_refline.itemText(index)
        item_data = next((i for i in self.current_reference_data if i['name'] == selected_name), None)
        if not item_data:
            return
        filename = item_data.get('file_name', item_data.get('file', item_data.get('name', '')))
        x, y = self.service_manager.get_reference_line_data(filename)
        if x is None or y is None:
            return

        # Disable Start & Back, enable Stop
        self.btn_start.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # Reset correlation plot
        self.corr_x = []
        self.corr_y = []
        self.curve_corr.setData([], [])

        self.sig_start_autolock.emit(start_v, end_v, {'x': x, 'y': y})

    def _on_stop_clicked(self):
        self.sig_stop_scan.emit()
        self.set_autolock_finished()

    @Slot()
    def set_autolock_finished(self):
        """Re-enable buttons after autolock completes or is stopped."""
        self.btn_start.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_stop.setEnabled(False)

    @Slot(dict)
    def handle_data(self, packet):
        """Process SCAN packets with correlations to update the correlation plot."""
        if packet.get("mode") == "SCAN" and "correlations" in packet:
            step = packet.get("step_index", 0)
            if step == len(self.corr_x):
                current_v = packet.get("current_voltage", 0.0)
                corr_val = packet["correlations"][step]

                self.corr_x.append(current_v)
                self.corr_y.append(corr_val)
                self.curve_corr.setData(self.corr_x, self.corr_y)


class LaserControllerPage(QWidget):
    sig_request_setup_manual_lock = Signal()
    sig_request_start_sweep = Signal()
    sig_request_set_state = Signal(str)
    sig_request_start_manual_locking = Signal(int, int, dict)
    sig_request_trace = Signal(float) # for AddReferenceLinePage

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        self.latest_sweep_data = None
        
        # --- LEFT PANEL: Navigation Stack ---
        self.left_stack = QStackedWidget()
        self.left_stack.setMinimumWidth(350) # Increased width for Table
        
        # 1. Main Menu
        self.menu_page = MenuPage()
        self.left_stack.addWidget(self.menu_page)
        
        # 2. Sub Pages
        self.page_parameters = ParametersPage(self.logger) # REAL PAGE
        self.page_advanced = AdvancedSettingsPage(self.logger)
        self.page_reflines = ReferenceLinesPage(self.logger)
        self.page_add_refline = AddReferenceLinePage()
        self.page_scan = ScanPage()
        self.page_centering = LineCenteringPage(self.logger)
        self.page_manual = ManualLockPage()
        self.page_auto = AutoLockPage(self.logger)
        self.page_optimization = OptimizationPage()

        
        self.left_stack.addWidget(self.page_parameters)
        self.left_stack.addWidget(self.page_advanced)
        self.left_stack.addWidget(self.page_reflines)
        self.left_stack.addWidget(self.page_add_refline)
        self.left_stack.addWidget(self.page_scan)
        self.left_stack.addWidget(self.page_centering)
        self.left_stack.addWidget(self.page_manual)
        self.left_stack.addWidget(self.page_auto)
        self.left_stack.addWidget(self.page_optimization)
        
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
        self.menu_page.sig_go_manual.connect(self.on_manual_clicked)
        self.menu_page.sig_go_auto.connect(lambda: self.left_stack.setCurrentWidget(self.page_auto))
        self.menu_page.sig_go_optimization.connect(lambda: self.left_stack.setCurrentWidget(self.page_optimization))

        
        # Reference lines currently does nothing
        self.menu_page.sig_go_reflines.connect(self.on_reflines_clicked)

        # Back Buttons -> Menu
        self.page_parameters.sig_back.connect(self.go_to_menu)
        self.page_advanced.sig_back.connect(self.go_to_menu)
        self.page_scan.sig_back.connect(self.on_scan_back)
        self.page_reflines.sig_request_back.connect(self.go_to_menu)
        
        # Reference Lines -> Add Reference Line
        self.page_reflines.btn_add.clicked.connect(
            lambda: self.left_stack.setCurrentWidget(self.page_add_refline)
        )
        self.page_add_refline.sig_back.connect(
            lambda: self.left_stack.setCurrentWidget(self.page_reflines)
        )
        self.page_add_refline.sig_request_scan_trace.connect(self.sig_request_trace.emit)
        
        self.page_centering.sig_back.connect(self.go_to_menu)
        self.page_manual.sig_back.connect(self.on_manual_back)
        self.page_auto.sig_back.connect(self.on_auto_back)
        self.page_optimization.sig_back.connect(self.on_optimization_back)
        
        # Manual Lock updates
        self.page_manual.sig_region_changed.connect(
            lambda x0, x1: self.plot_panel._handlers["SETUP_MANUAL_LOCK"].set_region(x0, x1)
        )
        self.page_manual.sig_start_lock.connect(self.on_start_lock_clicked)
        
        self.plot_panel.sig_unlock_requested.connect(self.on_unlock_requested)

        
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
        self.menu_page.btn_optimization.setEnabled(enabled)

    @Slot()
    def go_to_menu(self):
        self.left_stack.setCurrentWidget(self.menu_page)
        
    @Slot()
    def on_scan_back(self):
        """Return to menu from scan page. start_sweep is wired via GeneralManager."""
        self.left_stack.setCurrentWidget(self.menu_page)

    def handle_data(self, packet):
        """Pre-processor for data packets before they go to the plot panel."""
        mode = packet.get("mode")
        if mode in ("SWEEP", "SETUP_MANUAL_LOCK"):
            self.latest_sweep_data = packet
        
        # Forward to plot panel
        self.plot_panel.update_plot(packet)

    @Slot()
    def on_reflines_clicked(self):
        self.logger.info("Reference Lines button clicked - opening ReferenceLinesPage.")
        self.left_stack.setCurrentWidget(self.page_reflines)

    @Slot()
    def on_manual_clicked(self):
        """Called when "Manual lock" is clicked in Menu."""
        self.left_stack.setCurrentWidget(self.page_manual)
        self.sig_request_setup_manual_lock.emit()
        # Notify PlotPanel handler of initial values if any
        try:
            x0 = float(self.page_manual.input_x0.text())
            x1 = float(self.page_manual.input_x1.text())
            self.plot_panel._handlers["SETUP_MANUAL_LOCK"].set_region(x0, x1)
        except ValueError:
            pass

    @Slot()
    def on_manual_back(self):
        """Return to menu from manual lock page."""
        self.left_stack.setCurrentWidget(self.menu_page)
        self.sig_request_start_sweep.emit()

    @Slot()
    def on_auto_back(self):
        """Return to menu from auto-lock page."""
        self.left_stack.setCurrentWidget(self.menu_page)
        self.sig_request_start_sweep.emit()

    @Slot()
    def on_optimization_back(self):
        """Return to menu from optimization page."""
        self.left_stack.setCurrentWidget(self.menu_page)
        self.sig_request_start_sweep.emit()

    @Slot(float, float)
    def on_start_lock_clicked(self, x0, x1):
        """Triggered when "Start lock" is clicked in ManualLockPage."""
        if self.latest_sweep_data is None:
            self.logger.warning("Cannot start lock: No sweep data received yet.")
            return
        
        x_data = np.asarray(self.latest_sweep_data['x'])
        # Find closest indices
        idx0 = np.argmin(np.abs(x_data - x0))
        idx1 = np.argmin(np.abs(x_data - x1))
        
        # Ensure idx0 < idx1
        if idx0 > idx1:
            idx0, idx1 = idx1, idx0
            
        self.sig_request_set_state.emit("MANUAL_LOCKING")
        self.sig_request_start_manual_locking.emit(int(idx0), int(idx1), self.latest_sweep_data)
        self.left_stack.setCurrentWidget(self.menu_page)

    @Slot()
    def on_unlock_requested(self):
        """Triggered when "Unlock" is clicked in PlotPanel."""
        self.sig_request_set_state.emit("SWEEP")
