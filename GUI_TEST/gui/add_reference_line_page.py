import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QPushButton, QLabel, QScrollArea)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator, QIntValidator


class AddReferenceLinePage(QWidget):
    sig_start_scan = Signal(float, float, int)
    sig_stop_scan = Signal()
    sig_request_scan_trace = Signal(float)  # Ask backend for sweep at center V
    sig_save = Signal(dict)
    sig_back = Signal()

    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # We need a scroll area because the form + plot can be tall
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Title ---
        lbl_title = QLabel("Add Reference Line")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # --- Scan Controls (Copied from ScanPage) ---
        scan_group = QWidget()
        scan_layout = QVBoxLayout(scan_group)
        scan_layout.setContentsMargins(0, 0, 0, 0)
        
        scan_form = QFormLayout()
        self.input_start_v = QLineEdit("0.05")
        self.input_start_v.setValidator(QDoubleValidator())
        scan_form.addRow("Start voltage:", self.input_start_v)

        self.input_end_v = QLineEdit("1.75")
        self.input_end_v.setValidator(QDoubleValidator())
        scan_form.addRow("End voltage:", self.input_end_v)

        self.input_num_pts = QLineEdit("40")
        self.input_num_pts.setValidator(QIntValidator(1, 100000))
        scan_form.addRow("Number of points:", self.input_num_pts)
        scan_layout.addLayout(scan_form)

        btn_row = QHBoxLayout()
        self.btn_start_scan = QPushButton("Start scan")
        self.btn_stop_scan = QPushButton("Stop scan")
        self.btn_stop_scan.setEnabled(False)
        btn_row.addWidget(self.btn_start_scan)
        btn_row.addWidget(self.btn_stop_scan)
        scan_layout.addLayout(btn_row)
        
        layout.addWidget(scan_group)

        # --- Save Reference Line Section ---
        lbl_save_title = QLabel("Save reference line")
        lbl_save_title.setAlignment(Qt.AlignCenter)
        lbl_save_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px; margin-bottom: 10px;")
        layout.addWidget(lbl_save_title)

        form_layout = QFormLayout()
        
        self.input_name = QLineEdit()
        form_layout.addRow("Name:", self.input_name)
        
        self.lbl_board = QLabel("N/A")  # Display only
        form_layout.addRow("Board:", self.lbl_board)

        self.input_scan_center = QLineEdit("0.0")
        self.input_scan_center.setValidator(QDoubleValidator())
        form_layout.addRow("Scan center:", self.input_scan_center)

        self.input_ref_left = QLineEdit("-1.0")
        self.input_ref_left.setValidator(QDoubleValidator())
        form_layout.addRow("Reference line left side:", self.input_ref_left)

        self.input_ref_right = QLineEdit("1.0")
        self.input_ref_right.setValidator(QDoubleValidator())
        form_layout.addRow("Reference line right side:", self.input_ref_right)

        self.input_lock_min = QLineEdit("-0.5")
        self.input_lock_min.setValidator(QDoubleValidator())
        form_layout.addRow("Lock Region Min:", self.input_lock_min)

        self.input_lock_max = QLineEdit("0.5")
        self.input_lock_max.setValidator(QDoubleValidator())
        form_layout.addRow("Lock Region Max:", self.input_lock_max)

        self.input_polarity = QLineEdit()
        form_layout.addRow("Polarity:", self.input_polarity)
        
        layout.addLayout(form_layout)

        # --- Plot Panel ---
        self.plot_widget = pg.PlotWidget(title="Preview")
        self.plot_widget.setBackground('k')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setMinimumHeight(250)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.setLabel('bottom', 'V', units='V')
        self.plot_item.setLabel('left', 'Signal')
        self.plot_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_item.getAxis('left').enableAutoSIPrefix(False)

        # 1. The sweep signal
        self.curve_signal = self.plot_item.plot(pen=pg.mkPen('c', width=1.5))
        
        # 2. Vertical red dashed lines (Reference Left/Right)
        pen_dashed = pg.mkPen('r', style=Qt.DashLine, width=1.5)
        self.v_line_left = pg.InfiniteLine(pos=-1.0, angle=90, pen=pen_dashed, movable=False)
        self.v_line_right = pg.InfiniteLine(pos=1.0, angle=90, pen=pen_dashed, movable=False)
        self.plot_item.addItem(self.v_line_left)
        self.plot_item.addItem(self.v_line_right)
        
        # 3. Two vertical red lines (Lock Region) with semi-transparent red region between
        # pg.LinearRegionItem gives us the lines and the fill together
        self.lock_region = pg.LinearRegionItem(values=[-0.5, 0.5], 
                                               orientation=pg.LinearRegionItem.Vertical, 
                                               brush=pg.mkBrush(255, 0, 0, 60),
                                               pen=pg.mkPen('r', width=1.5),
                                               movable=False)
        self.plot_item.addItem(self.lock_region)

        layout.addWidget(self.plot_widget)

        # --- Bottom Buttons ---
        btn_bottom_row = QVBoxLayout()
        self.btn_save = QPushButton("Save reference line")
        self.btn_back = QPushButton("Back")
        
        # Initially disabled until scan is done and trace is loaded
        # self.btn_save.setEnabled(False) 
        
        btn_bottom_row.addWidget(self.btn_save)
        btn_bottom_row.addWidget(self.btn_back)
        layout.addLayout(btn_bottom_row)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # --- Wiring ---
        self.btn_start_scan.clicked.connect(self._on_start_scan)
        self.btn_stop_scan.clicked.connect(self._on_stop_scan)
        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_back.clicked.connect(self.sig_back.emit)

        # Update lines on text change
        self.input_ref_left.textChanged.connect(self._update_plot_lines)
        self.input_ref_right.textChanged.connect(self._update_plot_lines)
        self.input_lock_min.textChanged.connect(self._update_plot_lines)
        self.input_lock_max.textChanged.connect(self._update_plot_lines)
        
        # Update trace when scan center changes
        self.input_scan_center.editingFinished.connect(self._on_scan_center_changed)


    def _on_start_scan(self):
        try:
            start_v = float(self.input_start_v.text())
            end_v = float(self.input_end_v.text())
            num_pts = int(self.input_num_pts.text())
        except ValueError:
            return

        self.btn_start_scan.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_stop_scan.setEnabled(True)

        self.sig_start_scan.emit(start_v, end_v, num_pts)

    def _on_stop_scan(self):
        self.sig_stop_scan.emit()
        self.set_scan_finished()

    @Slot()
    def set_scan_finished(self):
        self.btn_start_scan.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_stop_scan.setEnabled(False)
        # Automatically load the trace for the current scan center
        self._on_scan_center_changed()

    def _on_scan_center_changed(self):
        try:
            v_center = float(self.input_scan_center.text())
            self.sig_request_scan_trace.emit(v_center)
        except ValueError:
            pass

    def _update_plot_lines(self):
        try:
            l_ref = float(self.input_ref_left.text())
            self.v_line_left.setValue(l_ref)
        except ValueError:
            pass
            
        try:
            r_ref = float(self.input_ref_right.text())
            self.v_line_right.setValue(r_ref)
        except ValueError:
            pass
            
        try:
            l_min = float(self.input_lock_min.text())
            l_max = float(self.input_lock_max.text())
            self.lock_region.setRegion([l_min, l_max])
        except ValueError:
            pass

    @Slot(dict)
    def update_trace(self, trace_data):
        """Called by the backend to plot the requested trace."""
        x = trace_data.get("x")
        y = trace_data.get("error_signal")
        if x is not None and y is not None:
            self.curve_signal.setData(np.asarray(x), np.asarray(y))
        else:
            self.curve_signal.clear()

    def _on_save_clicked(self):
        # Gather info and emit
        data = {
            "name": self.input_name.text(),
            "board": self.lbl_board.text(),
            "scan_center": self.input_scan_center.text(),
            "ref_left": self.input_ref_left.text(),
            "ref_right": self.input_ref_right.text(),
            "lock_min": self.input_lock_min.text(),
            "lock_max": self.input_lock_max.text(),
            "polarity": self.input_polarity.text()
        }
        self.sig_save.emit(data)

    @Slot(str)
    def set_board_name(self, board_name):
        """Sets the board name displayed on the form."""
        self.lbl_board.setText(board_name)
