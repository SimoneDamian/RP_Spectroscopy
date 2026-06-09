import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QPushButton, QLabel, QComboBox, QScrollArea)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator

class LineCenteringPage(QWidget):
    sig_start_scan = Signal(float, float, int, bool, dict)
    sig_stop_scan = Signal()
    sig_center = Signal(float)
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

        # --- Title ---
        lbl_title = QLabel("Line centering")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # --- Description Text ---
        self.lbl_desc = QLabel(
            "This feature allows you to look for a specific reference line across a "
            "voltage scan range using a correlation based algorithm."
        )
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("margin-bottom: 10px;")
        layout.addWidget(self.lbl_desc)

        # --- Scan Input settings ---
        scan_group = QWidget()
        scan_layout = QVBoxLayout(scan_group)
        scan_layout.setContentsMargins(0, 0, 0, 0)
        
        scan_form = QFormLayout()
        self.input_start_v = QLineEdit("0.05")
        self.input_start_v.setValidator(QDoubleValidator())
        scan_form.addRow("Start voltage:", self.input_start_v)

        self.input_end_v = QLineEdit("1.75")
        self.input_end_v.setValidator(QDoubleValidator())
        scan_form.addRow("Stop voltage:", self.input_end_v)
        scan_layout.addLayout(scan_form)

        layout.addWidget(scan_group)

        # --- Reference Line Selection ---
        ref_row = QHBoxLayout()
        lbl_ref = QLabel("Select the reference line:")
        self.combo_refline = QComboBox()
        ref_row.addWidget(lbl_ref)
        ref_row.addWidget(self.combo_refline)
        layout.addLayout(ref_row)

        # --- Plot 1: Reference Line Preview ---
        self.plot_ref = pg.PlotWidget(title="Reference Line")
        self.plot_ref.setBackground('w')
        self.plot_ref.showGrid(x=True, y=True)
        self.plot_ref.setMaximumHeight(200)
        self.plot_ref_item = self.plot_ref.getPlotItem()
        self.plot_ref_item.setLabel('bottom', 'V', units='V')
        self.plot_ref_item.setLabel('left', 'Signal')
        self.plot_ref_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_ref_item.getAxis('left').enableAutoSIPrefix(False)
        
        self.curve_ref = self.plot_ref_item.plot(pen='b')
        layout.addWidget(self.plot_ref)

        # --- Start/Stop Scan Buttons ---
        btn_row = QHBoxLayout()
        self.btn_start_scan = QPushButton("Start scan")
        self.btn_stop_scan = QPushButton("Stop scan")
        self.btn_stop_scan.setEnabled(False)
        
        # Buttons share equal width
        self.btn_start_scan.setSizePolicy(self.btn_start_scan.sizePolicy().horizontalPolicy().Expanding, self.btn_start_scan.sizePolicy().verticalPolicy().Fixed)
        self.btn_stop_scan.setSizePolicy(self.btn_stop_scan.sizePolicy().horizontalPolicy().Expanding, self.btn_stop_scan.sizePolicy().verticalPolicy().Fixed)
        
        btn_row.addWidget(self.btn_start_scan)
        btn_row.addWidget(self.btn_stop_scan)
        layout.addLayout(btn_row)

        # --- Plot 2: Correlations ---
        self.plot_corr = pg.PlotWidget(title="Correlations")
        self.plot_corr.setBackground('w')
        self.plot_corr.showGrid(x=True, y=True)
        self.plot_corr.setMaximumHeight(200)
        self.plot_corr_item = self.plot_corr.getPlotItem()
        self.plot_corr_item.setLabel('bottom', 'V', units='V')
        self.plot_corr_item.setLabel('left', 'Correlation')
        self.plot_corr_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_corr_item.getAxis('left').enableAutoSIPrefix(False)
        self.curve_corr = self.plot_corr_item.plot(pen='g', symbol='o', symbolSize=5)
        layout.addWidget(self.plot_corr)
        
        self.corr_x = []
        self.corr_y = []

        # --- Center Here Row ---
        center_row = QHBoxLayout()
        lbl_center = QLabel("Center here:")
        self.input_center = QLineEdit()
        self.input_center.setValidator(QDoubleValidator())
        lbl_q = QLabel("?")
        self.btn_center = QPushButton("Center")
        
        center_row.addWidget(lbl_center)
        center_row.addWidget(self.input_center)
        center_row.addWidget(lbl_q)
        center_row.addWidget(self.btn_center)
        layout.addLayout(center_row)

        layout.addStretch()
        
        # --- Back button ---
        self.btn_back = QPushButton("Back")
        layout.addWidget(self.btn_back)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # --- Wiring ---
        self.btn_start_scan.clicked.connect(self._on_start_scan)
        self.btn_stop_scan.clicked.connect(self._on_stop_scan)
        self.btn_center.clicked.connect(self._on_center_clicked)
        self.btn_back.clicked.connect(self.sig_back.emit)
        self.combo_refline.currentIndexChanged.connect(self._on_refline_selected)

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

    def _on_start_scan(self):
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
        if not item_data: return
        filename = item_data.get('file_name', item_data.get('file', item_data.get('name', '')))
        x, y = self.service_manager.get_reference_line_data(filename)
        if x is None or y is None: return

        self.btn_start_scan.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_stop_scan.setEnabled(True)
        
        self.corr_x = []
        self.corr_y = []
        self.curve_corr.setData([], [])

        self.sig_start_scan.emit(start_v, end_v, 40, True, {'x': x, 'y': y})

    @Slot(dict)
    def handle_data(self, packet):
        if packet.get("mode") == "SCAN" and "correlations" in packet:
            step = packet.get("step_index", 0)
            if step == len(self.corr_x):
                current_v = packet.get("current_voltage", 0.0)
                corr_val = packet["correlations"][step]
                
                self.corr_x.append(current_v)
                self.corr_y.append(corr_val)
                self.curve_corr.setData(self.corr_x, self.corr_y)
                
                if len(self.corr_y) > 0:
                    max_idx = np.argmax(self.corr_y)
                    self.input_center.setText(f"{self.corr_x[max_idx]:.4f}")

    def _on_stop_scan(self):
        self.sig_stop_scan.emit()
        self.set_scan_finished()

    @Slot()
    def set_scan_finished(self):
        self.btn_start_scan.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_stop_scan.setEnabled(False)

    def _on_center_clicked(self):
        try:
            center_v = float(self.input_center.text())
            self.sig_center.emit(center_v)
        except ValueError:
            pass
