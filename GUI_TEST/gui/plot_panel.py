import pyqtgraph as pg
import numpy as np
from time import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QStackedWidget, QLabel,
                                QScrollArea, QProgressBar, QPushButton)
from PySide6.QtCore import Qt, Slot, QTimer, Signal


class BasePlotHandler(QWidget):
    """
    Abstract base class for mode-specific plot handlers.
    Subclass this and implement update() to add a new FSM visualization mode.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def update(self, packet: dict):
        raise NotImplementedError("Subclasses must implement update()")
    
class SweepPlotHandler(BasePlotHandler):
    """
    Handles the SWEEP mode visualization.
    Shows two vertically-stacked plots sharing the same x-axis:
      - Top:    error_signal   (blue)
      - Bottom: monitor_signal (orange)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top plot: Error Signal ---
        self.plot_error = pg.PlotWidget(title="Error Signal")
        self.setup_plot(self.plot_error, "Error Signal")

        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), width=2))
        self.plot_error.addItem(self.zero_line)
        self.zero_line.setZValue(0) # Keep it above the fill but below the signal line
        
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('c', width=1.5))
        
        self.curve_error_strength_pos = pg.PlotDataItem() 
        self.curve_error_strength_neg = pg.PlotDataItem() 

        # 3. Create the Fill between (+) and (-)
        self.fill_error = pg.FillBetweenItem(
            self.curve_error_strength_pos, 
            self.curve_error_strength_neg, 
            brush=(0, 255, 255, 60) # Semi-transparent Cyan
        )
        self.plot_error.addItem(self.fill_error)

        # --- Bottom plot: Monitor Signal (Remains standard) ---
        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self.setup_plot(self.plot_monitor, "Monitor Signal", "Voltage", "V")
        self.curve_monitor = self.plot_monitor.plot(pen=pg.mkPen(color=(255, 165, 0), width=1.5))

        self.plot_monitor.setXLink(self.plot_error)
        layout.addWidget(self.plot_error)
        layout.addWidget(self.plot_monitor)

    def setup_plot(self, widget, left_label, bottom_label=None, units=None):
        widget.setBackground('k')
        widget.showGrid(x=True, y=True, alpha=0.3)
        pi = widget.getPlotItem()
        pi.setLabel('left', left_label)
        if bottom_label:
            pi.setLabel('bottom', bottom_label, units=units)
        pi.getAxis('bottom').enableAutoSIPrefix(False)
        pi.getAxis('left').enableAutoSIPrefix(False)

    def update(self, packet: dict):
        x = packet.get("x")
        error = packet.get("error_signal")
        error_strength = packet.get("error_signal_strength")
        monitor = packet.get("monitor_signal")

        if x is None:
            return

        x = np.asarray(x)

        if error is not None:
            err_data = np.asarray(error)
            self.curve_error.setData(x, err_data)
            self.curve_error_strength_pos.setData(x, error_strength)
            self.curve_error_strength_neg.setData(x, -error_strength)

        if monitor is not None:
            self.curve_monitor.setData(x, np.asarray(monitor))

class ManualLockingPlotHandler(BasePlotHandler):
    """
    Handles the MANUAL_LOCKING mode visualization.
    Shows two vertically-stacked plots sharing the same x-axis:
      - Top:    error_signal (cyan line) + strength (red fill)
      - Bottom: monitor_signal (orange)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top plot: Error Signal ---
        self.plot_error = pg.PlotWidget(title="Error Signal")
        self.setup_plot_style(self.plot_error, left_label='Error Signal')

        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), width=2))
        self.plot_error.addItem(self.zero_line)
        self.zero_line.setZValue(0) # Keep it above the fill but below the signal line
        
        # 1. Main Error Signal Line
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('c', width=1.5))
        self.curve_error.setZValue(20) # Keep line on top

        # 2. Strength boundaries (invisible data containers)
        self.curve_strength_pos = pg.PlotDataItem() 
        self.curve_strength_neg = pg.PlotDataItem() 

        # 3. Strength Fill (Semi-transparent Red)
        self.fill_strength = pg.FillBetweenItem(
            self.curve_strength_pos, 
            self.curve_strength_neg, 
            brush=(0, 255, 255, 60)
        )
        self.plot_error.addItem(self.fill_strength)
        self.fill_strength.setZValue(-10) # Keep fill behind grid/lines

        # --- Bottom plot: Monitor Signal ---
        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self.setup_plot_style(self.plot_monitor, left_label='Monitor Signal', 
                              bottom_label='Voltage', units='V')
        self.curve_monitor = self.plot_monitor.plot(pen=pg.mkPen(color=(255, 165, 0), width=1.5))

        # --- Region Selection (already red, stays as is) ---
        self.region = pg.LinearRegionItem(brush=pg.mkBrush(255, 0, 0, 40), pen=pg.mkPen('r', width=1))
        self.region.setZValue(5)
        self.plot_error.addItem(self.region)
        self.region.setMovable(False)

        # Link x-axes
        self.plot_monitor.setXLink(self.plot_error)
        self.plot_error.getPlotItem().setLabel('bottom', '')

        layout.addWidget(self.plot_error)
        layout.addWidget(self.plot_monitor)

    def setup_plot_style(self, widget, left_label, bottom_label=None, units=None):
        """Helper to standardize plot appearance"""
        widget.setBackground('k')
        widget.showGrid(x=True, y=True, alpha=0.3)
        pi = widget.getPlotItem()
        pi.setLabel('left', left_label)
        if bottom_label:
            pi.setLabel('bottom', bottom_label, units=units)
        pi.getAxis('bottom').enableAutoSIPrefix(False)
        pi.getAxis('left').enableAutoSIPrefix(False)

    def set_region(self, x0, x1):
        self.region.setRegion([x0, x1])

    def update(self, packet: dict):
        x = packet.get("x")
        error = packet.get("error_signal")
        strength = packet.get("error_signal_strength")
        monitor = packet.get("monitor_signal")

        if x is None:
            return

        x = np.asarray(x)
        
        if error is not None:
            self.curve_error.setData(x, np.asarray(error))
            
        if strength is not None:
            s_data = np.asarray(strength)
            # Update the fill boundaries
            self.curve_strength_pos.setData(x, s_data)
            self.curve_strength_neg.setData(x, -s_data)

        if monitor is not None:
            self.curve_monitor.setData(x, np.asarray(monitor))


class MessagePlotHandler(BasePlotHandler):
    """
    Handles modes that only display a status message (e.g., MANUAL_LOCKING, LOCKED).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.lbl_message = QLabel("Message")
        self.lbl_message.setAlignment(Qt.AlignCenter)
        self.lbl_message.setStyleSheet("font-size: 24px; font-weight: bold; color: #aaa;")
        layout.addWidget(self.lbl_message)

    def update(self, packet: dict):
        text = packet.get("text", "")
        self.lbl_message.setText(text)


class LockingMonitorPlotHandler(BasePlotHandler):
    """
    Handles the LOCKED mode visualization.
    Shows three vertically-stacked real-time plots (oscilloscope roll mode):
      - Top:    Monitor Signal
      - Middle: Fast Control Signal
      - Bottom: Slow Control Signal
    X-axis displays relative time (seconds ago).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top plot: Monitor Signal ---
        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self._setup_plot(self.plot_monitor, "Monitor Signal")
        self.curve_monitor = self.plot_monitor.plot(
            pen=pg.mkPen(color=(255, 165, 0), width=1.5)  # orange
        )

        # --- Middle plot: Fast Control Signal ---
        self.plot_fast = pg.PlotWidget(title="Fast Control Signal")
        self._setup_plot(self.plot_fast, "Fast Control")
        self.curve_fast = self.plot_fast.plot(
            pen=pg.mkPen('c', width=1.5)  # cyan
        )
        
        # Derivative for fast control
        self.plot_fast.showAxis('right')
        axis_right_fast = self.plot_fast.getAxis('right')
        axis_right_fast.setLabel('Derivative', color='r')
        axis_right_fast.setPen(color='r')
        axis_right_fast.setTextPen('r')
        self.fast_deriv_vb = pg.ViewBox()
        self.plot_fast.scene().addItem(self.fast_deriv_vb)
        self.plot_fast.getAxis('right').linkToView(self.fast_deriv_vb)
        p_fast_vb = self.plot_fast.getViewBox()
        self.fast_deriv_vb.setXLink(p_fast_vb)
        self.curve_fast_deriv = pg.PlotCurveItem(pen=pg.mkPen('r', width=1.0, style=Qt.DashLine))
        self.fast_deriv_vb.addItem(self.curve_fast_deriv)

        def update_fast_vb():
            self.fast_deriv_vb.setGeometry(p_fast_vb.sceneBoundingRect())
            self.fast_deriv_vb.linkedViewChanged(p_fast_vb, self.fast_deriv_vb.XAxis)
        p_fast_vb.sigResized.connect(update_fast_vb)

        # --- Bottom plot: Slow Control Signal ---
        self.plot_slow = pg.PlotWidget(title="Slow Control Signal")
        self._setup_plot(self.plot_slow, "Slow Control", bottom_label="Time", units="s")
        self.curve_slow = self.plot_slow.plot(
            pen=pg.mkPen(color=(0, 200, 83), width=1.5)  # green
        )
        
        # Derivative for slow control
        self.plot_slow.showAxis('right')
        axis_right_slow = self.plot_slow.getAxis('right')
        axis_right_slow.setLabel('Derivative', color='r')
        axis_right_slow.setPen(color='r')
        axis_right_slow.setTextPen('r')
        self.slow_deriv_vb = pg.ViewBox()
        self.plot_slow.scene().addItem(self.slow_deriv_vb)
        self.plot_slow.getAxis('right').linkToView(self.slow_deriv_vb)
        p_slow_vb = self.plot_slow.getViewBox()
        self.slow_deriv_vb.setXLink(p_slow_vb)
        self.curve_slow_deriv = pg.PlotCurveItem(pen=pg.mkPen('r', width=1.0, style=Qt.DashLine))
        self.slow_deriv_vb.addItem(self.curve_slow_deriv)

        def update_slow_vb():
            self.slow_deriv_vb.setGeometry(p_slow_vb.sceneBoundingRect())
            self.slow_deriv_vb.linkedViewChanged(p_slow_vb, self.slow_deriv_vb.XAxis)
        p_slow_vb.sigResized.connect(update_slow_vb)

        layout.addWidget(self.plot_monitor)
        layout.addWidget(self.plot_fast)
        layout.addWidget(self.plot_slow)

    @staticmethod
    def _setup_plot(widget, left_label, bottom_label=None, units=None):
        widget.setBackground('k')
        widget.showGrid(x=True, y=True, alpha=0.3)
        pi = widget.getPlotItem()
        pi.setLabel('left', left_label)
        if bottom_label:
            pi.setLabel('bottom', bottom_label, units=units)
        pi.getAxis('bottom').enableAutoSIPrefix(False)
        pi.getAxis('left').enableAutoSIPrefix(False)

    def update(self, packet: dict):
        now = time()

        # --- Monitor ---
        mon_times = packet.get("monitor_times_unix")
        mon_vals  = packet.get("monitor_values")
        if mon_times is not None and mon_vals is not None and len(mon_times) > 0:
            t_rel = np.asarray(mon_times) - now  # negative = seconds ago
            self.curve_monitor.setData(t_rel, np.asarray(mon_vals))

        # --- Fast Control ---
        fc_times = packet.get("fast_control_times_unix")
        fc_vals  = packet.get("fast_control_values")
        fc_deriv = packet.get("d_fast_control_values")
        show_fast_deriv = packet.get("show_fast_deriv", False)
        
        if fc_times is not None and fc_vals is not None and len(fc_times) > 0:
            t_rel = np.asarray(fc_times) - now
            self.curve_fast.setData(t_rel, np.asarray(fc_vals))
            
            if show_fast_deriv and fc_deriv is not None and len(fc_deriv) > 0 and len(t_rel) > 1:
                self.curve_fast_deriv.setData(t_rel[1:], np.asarray(fc_deriv))
                self.curve_fast_deriv.setVisible(True)
                self.plot_fast.showAxis('right')
            else:
                self.curve_fast_deriv.setVisible(False)
                self.plot_fast.hideAxis('right')

        # --- Slow Control ---
        sc_times = packet.get("slow_control_times_unix")
        sc_vals  = packet.get("slow_control_values")
        sc_deriv = packet.get("d_slow_control_values")
        show_slow_deriv = packet.get("show_slow_deriv", False)
        
        if sc_times is not None and sc_vals is not None and len(sc_times) > 0:
            t_rel = np.asarray(sc_times) - now
            self.curve_slow.setData(t_rel, np.asarray(sc_vals))
            
            if show_slow_deriv and sc_deriv is not None and len(sc_deriv) > 0 and len(t_rel) > 1:
                self.curve_slow_deriv.setData(t_rel[1:], np.asarray(sc_deriv))
                self.curve_slow_deriv.setVisible(True)
                self.plot_slow.showAxis('right')
            else:
                self.curve_slow_deriv.setVisible(False)
                self.plot_slow.hideAxis('right')


class ScanPlotHandler(BasePlotHandler):
    """
    Handles the SCAN mode visualization.
    Shows a scrollable column of plots, one per scan voltage step,
    and a progress bar at the bottom indicating overall scan progress.
    """
    PLOT_HEIGHT = 200  # Fixed height per individual plot widget

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Scrollable area for scan plots ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.addStretch()  # Keeps plots pushed to the top
        self._scroll.setWidget(self._scroll_content)
        layout.addWidget(self._scroll, 1)

        # --- Progress bar ---
        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._progress.setFormat("Scan progress: %p%")
        self._progress.setFixedHeight(24)
        layout.addWidget(self._progress)

        # Track how many plots we've added so far
        self._plot_count = 0

    def clear(self):
        """Remove all existing plots and reset progress bar."""
        # Remove all widgets except the trailing stretch
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._plot_count = 0
        self._progress.setValue(0)
        self._progress.setMaximum(1)

    def update(self, packet: dict):
        step_index = packet.get("step_index", 0)
        total_steps = packet.get("total_steps", 1)
        current_voltage = packet.get("current_voltage", 0.0)
        latest_sweep = packet.get("latest_sweep", {})

        # If this is the first step of a new scan, clear previous plots
        if step_index == 0:
            self.clear()

        # Only add a new plot if we haven't plotted this index yet
        if step_index < self._plot_count:
            # Already plotted — just update progress
            self._progress.setMaximum(total_steps)
            self._progress.setValue(step_index + 1)
            return

        # --- Create new plot widget for this voltage step ---
        plot_widget = pg.PlotWidget(title=f"V = {current_voltage:.4f} V")
        plot_widget.setBackground('k')
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.getPlotItem().setLabel('left', 'Error Signal')
        plot_widget.getPlotItem().setLabel('bottom', 'Voltage', units='V')
        plot_widget.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        plot_widget.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        plot_widget.setFixedHeight(self.PLOT_HEIGHT)

        x = latest_sweep.get("x")
        error = latest_sweep.get("error_signal")
        if x is not None and error is not None:
            plot_widget.plot(np.asarray(x), np.asarray(error),
                            pen=pg.mkPen('c', width=1.5))

        # Insert before the trailing stretch
        self._scroll_layout.insertWidget(self._scroll_layout.count() - 1,
                                         plot_widget)
        self._plot_count += 1

        # Update progress bar
        self._progress.setMaximum(total_steps)
        self._progress.setValue(step_index + 1)

        # Auto-scroll to bottom after a brief delay so layout settles
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))


class PlotPanel(QWidget):
    """
    Mode-aware plot container.
    Routes incoming data packets to the correct handler based on packet['mode'].

    Usage:
        panel = PlotPanel()
        panel.register_handler("SWEEP", SweepPlotHandler())
        panel.update_plot({"mode": "SWEEP", "x": ..., "error_signal": ..., "monitor_signal": ...})

    To add a new mode, create a BasePlotHandler subclass and register it.
    """
    sig_unlock_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # --- Unlock Button (Hidden by default) ---
        self.btn_unlock = QPushButton("Unlock")
        self.btn_unlock.setFixedHeight(40)
        self.btn_unlock.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
        """)
        self.btn_unlock.setVisible(False)
        self.btn_unlock.clicked.connect(self.sig_unlock_requested.emit)
        layout.addWidget(self.btn_unlock)

        self._handlers: dict[str, BasePlotHandler] = {}

        # Placeholder shown before first data arrives
        self._placeholder = QLabel("Waiting for data...")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 16px;")
        self._stack.addWidget(self._placeholder)

        # Register default handlers
        self.register_handler("SWEEP", SweepPlotHandler())
        self.register_handler("SCAN", ScanPlotHandler())
        self.register_handler("SETUP_MANUAL_LOCK", ManualLockingPlotHandler())
        
        self.register_handler("MANUAL_LOCKING", MessagePlotHandler())
        self.register_handler("TEXT", MessagePlotHandler())
        self.register_handler("LOCKED", LockingMonitorPlotHandler())

    def register_handler(self, mode: str, handler: BasePlotHandler):
        """Register a plot handler for a given FSM mode."""
        self._handlers[mode] = handler
        self._stack.addWidget(handler)

    @Slot(dict)
    def update_plot(self, packet: dict):
        """Route a data packet to the appropriate handler."""
        mode = packet.get("mode")
        handler = self._handlers.get(mode)
        
        # Toggle Unlock button visibility
        self.btn_unlock.setVisible(mode == "LOCKED")

        if handler:
            self._stack.setCurrentWidget(handler)
            handler.update(packet)
