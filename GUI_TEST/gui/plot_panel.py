import pyqtgraph as pg
import numpy as np
from time import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel,
                                QScrollArea, QProgressBar, QPushButton, QSlider)
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
        self._merged = False  # start in separate mode
        self._last_packet = None  # cache last packet for refresh
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Separate plots (default)
        self.plot_error = pg.PlotWidget(title="Error Signal")
        self.setup_plot(self.plot_error, "Error Signal")
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), width=2))
        self.plot_error.addItem(self.zero_line)
        self.zero_line.setZValue(0)
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('c', width=1.5))
        self.curve_error_strength_pos = pg.PlotDataItem()
        self.curve_error_strength_neg = pg.PlotDataItem()
        self.fill_error = pg.FillBetweenItem(self.curve_error_strength_pos, self.curve_error_strength_neg, brush=(0, 255, 255, 60))
        self.plot_error.addItem(self.fill_error)

        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self.setup_plot(self.plot_monitor, "Monitor Signal", "Voltage", "V")
        self.curve_monitor = self.plot_monitor.plot(pen=pg.mkPen(color=(255, 165, 0), width=1.5))
        self.plot_monitor.setXLink(self.plot_error)

        # Merged plot (hidden initially)
        self.plot_merged = pg.PlotWidget(title="Monitor and error signals")
        self.setup_plot(self.plot_merged, "Error Signal", "Voltage", "V")
        # Left axis for error signal (cyan)
        self.plot_merged.getAxis('left').setPen(pg.mkPen('c'))
        self.curve_error_merged = self.plot_merged.plot(pen=pg.mkPen('c', width=1.5))
        # Error strength shading (transparent cyan)
        self.curve_error_strength_pos_merged = pg.PlotDataItem()
        self.curve_error_strength_neg_merged = pg.PlotDataItem()
        self.fill_error_merged = pg.FillBetweenItem(
            self.curve_error_strength_pos_merged,
            self.curve_error_strength_neg_merged,
            brush=(0, 255, 255, 60)
        )
        self.plot_merged.addItem(self.fill_error_merged)
        # Right axis for monitor signal (orange)
        self.plot_merged.showAxis('right')
        self.plot_merged.getPlotItem().setLabel('right', 'Monitor Signal', 'V')
        self.plot_merged.getAxis('right').setPen(pg.mkPen((255, 165, 0)))
        self.monitor_vb = pg.ViewBox()
        self.plot_merged.scene().addItem(self.monitor_vb)
        self.plot_merged.getAxis('right').linkToView(self.monitor_vb)
        self.monitor_vb.setXLink(self.plot_merged.getViewBox())
        self.curve_monitor_merged = pg.PlotDataItem(pen=pg.mkPen(color=(255, 165, 0), width=1.5))
        self.monitor_vb.addItem(self.curve_monitor_merged)
        # Ensure the right axis updates when the view changes
        def updateViewBox():
            self.monitor_vb.setGeometry(self.plot_merged.getViewBox().sceneBoundingRect())
            self.monitor_vb.linkedViewChanged(self.plot_merged.getViewBox(), self.monitor_vb.XAxis)
        self.plot_merged.getViewBox().sigResized.connect(updateViewBox)

        # Add widgets to layout; merged hidden now
        layout.addWidget(self.plot_error)
        layout.addWidget(self.plot_monitor)
        layout.addWidget(self.plot_merged)
        self.plot_merged.setVisible(False)

    def setup_plot(self, widget, left_label, bottom_label=None, units=None):
        widget.setBackground('k')
        widget.showGrid(x=True, y=True, alpha=0.3)
        pi = widget.getPlotItem()
        pi.setLabel('left', left_label)
        if bottom_label:
            pi.setLabel('bottom', bottom_label, units=units)
        pi.getAxis('bottom').enableAutoSIPrefix(False)
        pi.getAxis('left').enableAutoSIPrefix(False)

    def _update_layout(self):
        """Show either separate or merged layout based on self._merged flag."""
        if self._merged:
            # Hide separate plots, show merged
            self.plot_error.setVisible(False)
            self.plot_monitor.setVisible(False)
            self.plot_merged.setVisible(True)
        else:
            # Show separate, hide merged
            self.plot_error.setVisible(True)
            self.plot_monitor.setVisible(True)
            self.plot_merged.setVisible(False)

    def update(self, packet: dict):
        """Update plots based on incoming packet and current mode (separate or merged)."""
        self._last_packet = packet  # cache for refreshes
        x = packet.get("x")
        error = packet.get("error_signal")
        error_strength = packet.get("error_signal_strength")
        monitor = packet.get("monitor_signal")
        if x is None:
            return
        x = np.asarray(x)
        if self._merged:
            # Merged mode: use merged plot curves
            if error is not None:
                self.curve_error_merged.setData(x, np.asarray(error))
            if monitor is not None:
                self.curve_monitor_merged.setData(x, np.asarray(monitor))
            # Add error strength shading if available
            if error_strength is not None:
                self.curve_error_strength_pos_merged.setData(x, np.asarray(error_strength))
                self.curve_error_strength_neg_merged.setData(x, -np.asarray(error_strength))
            else:
                # Clear previous data
                self.curve_error_strength_pos_merged.clear()
                self.curve_error_strength_neg_merged.clear()
        else:
            # Separate mode (original behavior)
            if error is not None:
                err_data = np.asarray(error)
                self.curve_error.setData(x, err_data)
                if error_strength is not None:
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
        self.mon_stats_text, self.mon_mean_line, self.mon_std_upper, self.mon_std_lower = self._add_stats_elements(self.plot_monitor)

        self.expected_mon_line = pg.InfiniteLine(
            angle=0, 
            pen=pg.mkPen(color=(200, 200, 200), style=Qt.DashLine, width=1.5),
            label="expected monitor signal",
            labelOpts={'position': 0.1, 'color': (200, 200, 200), 'fill': (0, 0, 0, 100), 'movable': True}
        )
        self.plot_monitor.addItem(self.expected_mon_line)
        self.expected_mon_line.setVisible(False)

        # --- Middle plot: Fast Control Signal ---
        self.plot_fast = pg.PlotWidget(title="Fast Control Signal")
        self._setup_plot(self.plot_fast, "Fast Control")
        self.curve_fast = self.plot_fast.plot(
            pen=pg.mkPen('c', width=1.5)  # cyan
        )
        self.fast_stats_text, self.fast_mean_line, self.fast_std_upper, self.fast_std_lower = self._add_stats_elements(self.plot_fast)
        
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
        self.slow_stats_text, self.slow_mean_line, self.slow_std_upper, self.slow_std_lower = self._add_stats_elements(self.plot_slow)
        
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

    def _add_stats_elements(self, plot_widget):
        mean_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('y', style=Qt.DashLine, width=1))
        std_upper = pg.InfiniteLine(angle=0, pen=pg.mkPen((255, 255, 0, 100), style=Qt.DotLine))
        std_lower = pg.InfiniteLine(angle=0, pen=pg.mkPen((255, 255, 0, 100), style=Qt.DotLine))
        
        vb = plot_widget.getViewBox()
        vb.addItem(mean_line, ignoreBounds=True)
        vb.addItem(std_upper, ignoreBounds=True)
        vb.addItem(std_lower, ignoreBounds=True)
        
        # anchor=(1,0) means text's top-right corner is at (x,y), so it stays within plot
        stats_text = pg.TextItem("", anchor=(1, 0), color=(255, 255, 0), fill=(0, 0, 0, 150))
        vb.addItem(stats_text, ignoreBounds=True)
        
        return stats_text, mean_line, std_upper, std_lower

    def _update_stats_elements(self, x_arr, vals_arr, stats_text, mean_line, std_upper, std_lower):
        if len(vals_arr) == 0 or len(x_arr) == 0:
            return
        mean_val = np.mean(vals_arr)
        std_val = np.std(vals_arr)
        
        stats_text.setText(f"Mean: {mean_val:.1e}\nStd:  {std_val:.1e}")
        
        # Position at the right edge, top of the current view
        xr, yr = stats_text.getViewBox().viewRange()
        stats_text.setPos(xr[1], yr[1])
        
        mean_line.setValue(mean_val)
        std_upper.setValue(mean_val + std_val)
        std_lower.setValue(mean_val - std_val)

    def update(self, packet: dict):
        now = time()

        # --- Monitor ---
        mon_times = packet.get("monitor_times_unix")
        mon_vals  = packet.get("monitor_values")
        if mon_times is not None and mon_vals is not None and len(mon_times) > 0:
            mon_arr = np.asarray(mon_vals)
            t_rel = np.asarray(mon_times) - now  # negative = seconds ago
            self.curve_monitor.setData(t_rel, mon_arr)
            self._update_stats_elements(t_rel, mon_arr, self.mon_stats_text, self.mon_mean_line, self.mon_std_upper, self.mon_std_lower)

        expected_point = packet.get("expected_lock_monitor_signal_point")
        if expected_point is not None and len(expected_point) >= 2:
            self.expected_mon_line.setValue(expected_point[1])
            self.expected_mon_line.setVisible(True)
        else:
            self.expected_mon_line.setVisible(False)

        # --- Fast Control ---
        fc_times = packet.get("fast_control_times_unix")
        fc_vals  = packet.get("fast_control_values")
        fc_deriv = packet.get("d_fast_control_values")
        show_fast_deriv = packet.get("show_fast_deriv", False)
        
        if fc_times is not None and fc_vals is not None and len(fc_times) > 0:
            fc_arr = np.asarray(fc_vals)
            t_rel = np.asarray(fc_times) - now
            self.curve_fast.setData(t_rel, fc_arr)
            self._update_stats_elements(t_rel, fc_arr, self.fast_stats_text, self.fast_mean_line, self.fast_std_upper, self.fast_std_lower)
            
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
            sc_arr = np.asarray(sc_vals)
            t_rel = np.asarray(sc_times) - now
            self.curve_slow.setData(t_rel, sc_arr)
            self._update_stats_elements(t_rel, sc_arr, self.slow_stats_text, self.slow_mean_line, self.slow_std_upper, self.slow_std_lower)
            
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

        zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), width=2))
        plot_widget.addItem(zero_line)
        zero_line.setZValue(0)

        x = latest_sweep.get("x")
        error = latest_sweep.get("error_signal")
        error_strength = latest_sweep.get("error_signal_strength")
        
        if x is not None:
            x_arr = np.asarray(x)
            if error is not None:
                curve_error = plot_widget.plot(x_arr, np.asarray(error),
                                               pen=pg.mkPen('c', width=1.5))
                curve_error.setZValue(20)
                
            if error_strength is not None:
                s_data = np.asarray(error_strength)
                curve_strength_pos = pg.PlotDataItem(x_arr, s_data)
                curve_strength_neg = pg.PlotDataItem(x_arr, -s_data)
                fill_strength = pg.FillBetweenItem(
                    curve_strength_pos, 
                    curve_strength_neg, 
                    brush=(0, 255, 255, 60)
                )
                plot_widget.addItem(fill_strength)
                fill_strength.setZValue(-10)

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


class PhaseOptimizationPlotHandler(BasePlotHandler):
    """
    Handles the DEMOD_PHASE_OPTIMIZATION mode visualization.
    Shows a scrollable column of plots, one per phase step,
    and a progress bar at the bottom indicating overall progress.
    Behaves like ScanPlotHandler but labels with demodulation phase.
    """
    PLOT_HEIGHT = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Scrollable area for sweep plots ---
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
        self._progress.setFormat("Phase optimization progress: %p%")
        self._progress.setFixedHeight(24)
        layout.addWidget(self._progress)

        self._plot_count = 0

    def clear(self):
        """Remove all existing plots and reset progress bar."""
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
        current_phase = packet.get("current_phase", 0.0)
        latest_sweep = packet.get("latest_sweep", {})
        phases = packet.get("phases", [])
        total_steps = len(phases) if phases is not None and hasattr(phases, '__len__') else 1

        # If this is the first step of a new optimization, clear previous plots
        if step_index == 0:
            self.clear()

        # Only add a new plot if we haven't plotted this index yet
        if step_index < self._plot_count:
            self._progress.setMaximum(total_steps)
            self._progress.setValue(step_index + 1)
            return

        # --- Create new plot widget for this phase step ---
        plot_widget = pg.PlotWidget(title=f"Phase = {current_phase:.2f}°")
        plot_widget.setBackground('k')
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.getPlotItem().setLabel('left', 'Error Signal')
        plot_widget.getPlotItem().setLabel('bottom', 'Voltage', units='V')
        plot_widget.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        plot_widget.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        plot_widget.setFixedHeight(self.PLOT_HEIGHT)

        zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), width=2))
        plot_widget.addItem(zero_line)
        zero_line.setZValue(0)

        x = latest_sweep.get("x")
        error = latest_sweep.get("error_signal")
        error_strength = latest_sweep.get("error_signal_strength")

        if x is not None:
            x_arr = np.asarray(x)
            if error is not None:
                curve_error = plot_widget.plot(x_arr, np.asarray(error),
                                               pen=pg.mkPen('c', width=1.5))
                curve_error.setZValue(20)

            if error_strength is not None:
                s_data = np.asarray(error_strength)
                curve_strength_pos = pg.PlotDataItem(x_arr, s_data)
                curve_strength_neg = pg.PlotDataItem(x_arr, -s_data)
                fill_strength = pg.FillBetweenItem(
                    curve_strength_pos,
                    curve_strength_neg,
                    brush=(0, 255, 255, 60)
                )
                plot_widget.addItem(fill_strength)
                fill_strength.setZValue(-10)

        # Insert before the trailing stretch
        self._scroll_layout.insertWidget(self._scroll_layout.count() - 1,
                                         plot_widget)
        self._plot_count += 1

        # Update progress bar
        self._progress.setMaximum(total_steps)
        self._progress.setValue(step_index + 1)

        # Auto-scroll to bottom
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))


class JitterCheckPlotHandler(BasePlotHandler):
    """
    Handles the JITTER_CHECK mode visualization.
    Shows two vertically-stacked plots:
      - Top:    Sweep signal (cyan) + shifted reference line (dashed orange),
                with x-limits extended by 1.2×linewidth.
                Title shows offset and correlation.
      - Bottom: Shift vs time scatter (cyan dots).
                When stability data is available: mean line (red solid),
                ±jitter_threshold lines (red dashed), std fill (red alpha).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top plot: Sweep + Reference ---
        self.plot_sweep = pg.PlotWidget(title="Sweep Signal")
        self._setup_plot(self.plot_sweep, "Signal")
        self.zero_line = pg.InfiniteLine(pos=0, angle=0,
                                          pen=pg.mkPen(color=(128, 128, 128), width=2))
        self.plot_sweep.addItem(self.zero_line)
        self.zero_line.setZValue(0)

        self.curve_sweep = self.plot_sweep.plot(pen=pg.mkPen('c', width=1.5))
        self.curve_sweep.setZValue(20)
        self.curve_ref = self.plot_sweep.plot(
            pen=pg.mkPen(color=(255, 165, 0), width=1.5, style=Qt.DashLine)
        )
        self.curve_ref.setZValue(10)
        layout.addWidget(self.plot_sweep)

        # --- Bottom plot: Shift vs Time ---
        self.plot_shift = pg.PlotWidget(title="Shift over Time")
        self._setup_plot(self.plot_shift, "Shift [V]", "Time [s]")

        self.scatter_shift = self.plot_shift.plot(
            pen=None, symbol='o', symbolSize=5,
            symbolBrush=pg.mkBrush('c'), symbolPen=None
        )
        # Stability overlay items
        self.mean_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', width=1.5))
        self.thr_upper = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', style=Qt.DashLine, width=1))
        self.thr_lower = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', style=Qt.DashLine, width=1))

        self.plot_shift.addItem(self.mean_line, ignoreBounds=True)
        self.plot_shift.addItem(self.thr_upper, ignoreBounds=True)
        self.plot_shift.addItem(self.thr_lower, ignoreBounds=True)

        self.mean_line.setVisible(False)
        self.thr_upper.setVisible(False)
        self.thr_lower.setVisible(False)

        # Fill for std region
        self.std_fill_upper = pg.PlotDataItem()
        self.std_fill_lower = pg.PlotDataItem()
        self.std_fill = pg.FillBetweenItem(
            self.std_fill_upper, self.std_fill_lower,
            brush=(255, 0, 0, 30)
        )
        self.plot_shift.addItem(self.std_fill)
        self.std_fill.setVisible(False)

        layout.addWidget(self.plot_shift)

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
        sweep_signal = packet.get("sweep_signal", {})
        reference_signal = packet.get("reference_signal", {})
        shift = packet.get("shift", 0.0)
        corr = packet.get("correlation", 0.0)
        len_match = packet.get("len_match", 0.0)
        linewidth = packet.get("linewidth", 0.1)
        offset = packet.get("offset", 0.0)
        times = packet.get("times", [])
        shifts = packet.get("shifts", [])
        jitter_thr = packet.get("jitter_threshold", 0.05)
        avg_shift = packet.get("avg_shift")
        std_shift = packet.get("std_shift")

        # --- Top plot: Sweep + shifted Reference ---
        sweep_x = sweep_signal.get("x")
        sweep_err = sweep_signal.get("error_signal")
        ref_x = reference_signal.get("x")
        ref_y = reference_signal.get("y")

        if sweep_x is not None and sweep_err is not None:
            sx = np.asarray(sweep_x)
            sy = np.asarray(sweep_err)
            self.curve_sweep.setData(sx, sy)

            if ref_x is not None and ref_y is not None:
                rx = np.asarray(ref_x) + shift
                ry = np.asarray(ref_y)
                self.curve_ref.setData(rx, ry)

            # Set x-limits with padding
            #x_min = sx[0] - 1.2 * linewidth
            #x_max = sx[-1] + 1.2 * linewidth
            #self.plot_sweep.setXRange(x_min, x_max)

            # Set y-limits with padding
            # all_y = [sy]
            # if ref_y is not None:
            #     all_y.append(np.asarray(ref_y))
            # y_all = np.concatenate(all_y)
            # y_min, y_max = float(np.min(y_all)), float(np.max(y_all))
            # y_pad = (y_max - y_min) * 0.2
            # self.plot_sweep.setYRange(y_min - y_pad, y_max + y_pad)

            self.plot_sweep.setTitle(
                f"Sweep (Offset = {offset:.2f} V) — Corr = {corr:.2f}, Match = {len_match:.2f} V"
            )

        # --- Bottom plot: Shift vs Time scatter ---
        if len(times) > 0 and len(shifts) > 0:
            t_arr = np.asarray(times)
            s_arr = np.asarray(shifts)
            self.scatter_shift.setData(t_arr, s_arr)

            # X-axis: round up to next minute
            x_max_t = (t_arr[-1] // 60 + 1) * 60
            self.plot_shift.setXRange(0, max(x_max_t, 60))
            self.plot_shift.setYRange(-1.1, 1.1)

            self.plot_shift.setTitle(
                f"Shift over Time (Jitter Threshold = {jitter_thr})"
            )

            # Stability overlay
            if avg_shift is not None and std_shift is not None:
                self.mean_line.setValue(avg_shift)
                self.thr_upper.setValue(avg_shift + jitter_thr)
                self.thr_lower.setValue(avg_shift - jitter_thr)
                self.mean_line.setVisible(True)
                self.thr_upper.setVisible(True)
                self.thr_lower.setVisible(True)

                # Std fill region
                self.std_fill_upper.setData(t_arr, np.full_like(t_arr, avg_shift + std_shift))
                self.std_fill_lower.setData(t_arr, np.full_like(t_arr, avg_shift - std_shift))
                self.std_fill.setVisible(True)
            else:
                self.mean_line.setVisible(False)
                self.thr_upper.setVisible(False)
                self.thr_lower.setVisible(False)
                self.std_fill.setVisible(False)


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
    sig_big_offset_changed = Signal(float)  # emitted when the user moves the big_offset slider
    sig_sweep_amplitude_changed = Signal(float)  # emitted when the user moves the sweep_amplitude slider
    sig_phase_changed = Signal(float)  # emitted when the user moves the demodulation phase slider

    # Big Offset Slider: maps to [0.0 V, +1.8 V]
    _SLIDER_MIN = 0
    _SLIDER_MAX = 18000
    _SLIDER_OFFSET = 0.0      # lower bound in volts
    _SLIDER_SCALE = 10000.0   # integer units per volt

    # Sweep Amplitude Slider: maps to [0.001 Vpp, +1.0 Vpp]
    _SWEEP_AMP_MIN = 1
    _SWEEP_AMP_MAX = 1000
    _SWEEP_AMP_SCALE = 1000.0

    # Demodulation Phase Slider: maps to [0.0 deg, 360.0 deg]
    _PHASE_MIN = 0
    _PHASE_MAX = 36000
    _PHASE_SCALE = 100.0

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
        self.btn_unlock.clicked.connect(self.sig_unlock_requested)
        layout.addWidget(self.btn_unlock)

        # --- Slider Container (visible only in SWEEP mode) ---
        self._slider_container = QWidget()
        container_layout = QVBoxLayout(self._slider_container)
        container_layout.setContentsMargins(8, 4, 8, 4)
        container_layout.setSpacing(6)

        # Common QSlider stylesheet
        slider_stylesheet = """
            QSlider::groove:horizontal {
                height: 6px;
                background: #424242;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #42a5f5;
                border: 1px solid #1565c0;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #64b5f6;
            }
            QSlider::sub-page:horizontal {
                background: #1976d2;
                border-radius: 3px;
            }
        """

        # 1. Big Offset Slider row
        row_offset = QHBoxLayout()
        lbl_offset_title = QLabel("Big Offset:")
        lbl_offset_title.setStyleSheet("color: #ccc; font-size: 12px;")
        lbl_offset_title.setFixedWidth(120)
        row_offset.addWidget(lbl_offset_title)

        self._lbl_slider_min = QLabel("0 V")
        self._lbl_slider_min.setStyleSheet("color: #aaa; font-size: 12px;")
        row_offset.addWidget(self._lbl_slider_min)

        self.slider_big_offset = QSlider(Qt.Horizontal)
        self.slider_big_offset.setMinimum(self._SLIDER_MIN)
        self.slider_big_offset.setMaximum(self._SLIDER_MAX)
        self.slider_big_offset.setValue(0)
        self.slider_big_offset.setTickPosition(QSlider.TicksBelow)
        self.slider_big_offset.setTickInterval(self._SLIDER_MAX // 4)
        self.slider_big_offset.setStyleSheet(slider_stylesheet)
        row_offset.addWidget(self.slider_big_offset, 1)

        self._lbl_slider_max = QLabel("+1.8 V")
        self._lbl_slider_max.setStyleSheet("color: #aaa; font-size: 12px;")
        row_offset.addWidget(self._lbl_slider_max)

        self._lbl_slider_val = QLabel("0.000 V")
        self._lbl_slider_val.setFixedWidth(70)
        self._lbl_slider_val.setAlignment(Qt.AlignCenter)
        self._lbl_slider_val.setStyleSheet("color: #42a5f5; font-size: 13px; font-weight: bold;")
        row_offset.addWidget(self._lbl_slider_val)
        container_layout.addLayout(row_offset)

        # 2. Sweep Amplitude Slider row
        row_amp = QHBoxLayout()
        lbl_amp_title = QLabel("Sweep Amplitude:")
        lbl_amp_title.setStyleSheet("color: #ccc; font-size: 12px;")
        lbl_amp_title.setFixedWidth(120)
        row_amp.addWidget(lbl_amp_title)

        self._lbl_amp_min = QLabel("0.001 Vpp")
        self._lbl_amp_min.setStyleSheet("color: #aaa; font-size: 12px;")
        row_amp.addWidget(self._lbl_amp_min)

        self.slider_sweep_amplitude = QSlider(Qt.Horizontal)
        self.slider_sweep_amplitude.setMinimum(self._SWEEP_AMP_MIN)
        self.slider_sweep_amplitude.setMaximum(self._SWEEP_AMP_MAX)
        self.slider_sweep_amplitude.setValue(1)
        self.slider_sweep_amplitude.setTickPosition(QSlider.TicksBelow)
        self.slider_sweep_amplitude.setTickInterval(self._SWEEP_AMP_MAX // 4)
        self.slider_sweep_amplitude.setStyleSheet(slider_stylesheet)
        row_amp.addWidget(self.slider_sweep_amplitude, 1)

        self._lbl_amp_max = QLabel("1 Vpp")
        self._lbl_amp_max.setStyleSheet("color: #aaa; font-size: 12px;")
        row_amp.addWidget(self._lbl_amp_max)

        self._lbl_amp_val = QLabel("0.001 Vpp")
        self._lbl_amp_val.setFixedWidth(70)
        self._lbl_amp_val.setAlignment(Qt.AlignCenter)
        self._lbl_amp_val.setStyleSheet("color: #42a5f5; font-size: 13px; font-weight: bold;")
        row_amp.addWidget(self._lbl_amp_val)
        container_layout.addLayout(row_amp)

        # 3. Demodulation Phase Slider row
        row_phase = QHBoxLayout()
        lbl_phase_title = QLabel("Demod. Phase:")
        lbl_phase_title.setStyleSheet("color: #ccc; font-size: 12px;")
        lbl_phase_title.setFixedWidth(120)
        row_phase.addWidget(lbl_phase_title)

        self._lbl_phase_min = QLabel("0°")
        self._lbl_phase_min.setStyleSheet("color: #aaa; font-size: 12px;")
        row_phase.addWidget(self._lbl_phase_min)

        self.slider_phase = QSlider(Qt.Horizontal)
        self.slider_phase.setMinimum(self._PHASE_MIN)
        self.slider_phase.setMaximum(self._PHASE_MAX)
        self.slider_phase.setValue(0)
        self.slider_phase.setTickPosition(QSlider.TicksBelow)
        self.slider_phase.setTickInterval(self._PHASE_MAX // 4)
        self.slider_phase.setStyleSheet(slider_stylesheet)
        row_phase.addWidget(self.slider_phase, 1)

        self._lbl_phase_max = QLabel("360°")
        self._lbl_phase_max.setStyleSheet("color: #aaa; font-size: 12px;")
        row_phase.addWidget(self._lbl_phase_max)

        self._lbl_phase_val = QLabel("0.00°")
        self._lbl_phase_val.setFixedWidth(70)
        self._lbl_phase_val.setAlignment(Qt.AlignCenter)
        self._lbl_phase_val.setStyleSheet("color: #42a5f5; font-size: 13px; font-weight: bold;")
        row_phase.addWidget(self._lbl_phase_val)
        container_layout.addLayout(row_phase)

        self._slider_container.setVisible(False)
        layout.addWidget(self._slider_container)

        # Internal flag to prevent feedback loop when updating slider programmatically
        self._slider_updating = False
        self.slider_big_offset.valueChanged.connect(self._on_slider_value_changed)
        self.slider_sweep_amplitude.valueChanged.connect(self._on_sweep_amp_value_changed)
        self.slider_phase.valueChanged.connect(self._on_phase_value_changed)

        # --- Top bar with Sweep mode toggle button (hidden by default) ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addStretch()
        self.btn_toggle_sweep = QPushButton("Merge plots")
        self.btn_toggle_sweep.setFixedHeight(30)
        self.btn_toggle_sweep.setStyleSheet(
            """
            QPushButton {
                background-color: #424242;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            """
        )
        self.btn_toggle_sweep.setVisible(False)
        self.btn_toggle_sweep.clicked.connect(self._toggle_sweep_mode)
        top_bar_layout.addWidget(self.btn_toggle_sweep)
        layout.insertLayout(0, top_bar_layout)



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
        self.register_handler("DEMOD_PHASE_OPTIMIZATION", PhaseOptimizationPlotHandler())
        self.register_handler("JITTER_CHECK", JitterCheckPlotHandler())

    def register_handler(self, mode: str, handler: BasePlotHandler):
        """Register a plot handler for a given FSM mode."""
        self._handlers[mode] = handler
        self._stack.addWidget(handler)

    def _on_slider_value_changed(self, int_val: int):
        """Called when the user drags the big_offset slider."""
        if self._slider_updating:
            return
        volts = self._SLIDER_OFFSET + int_val / self._SLIDER_SCALE
        self._lbl_slider_val.setText(f"{volts:.4f} V")
        self.sig_big_offset_changed.emit(volts)

    def set_big_offset_slider(self, value: float):
        """
        Update the slider position to reflect `value` (in Volts).
        Clamps to [0, +1.8] V. Does NOT emit sig_big_offset_changed.
        """
        self._slider_updating = True
        lo = self._SLIDER_OFFSET
        hi = self._SLIDER_OFFSET + self._SLIDER_MAX / self._SLIDER_SCALE
        clamped = max(lo, min(hi, float(value)))
        int_val = int(round((clamped - self._SLIDER_OFFSET) * self._SLIDER_SCALE))
        self.slider_big_offset.setValue(int_val)
        self._lbl_slider_val.setText(f"{clamped:.4f} V")
        self._slider_updating = False

    def _on_sweep_amp_value_changed(self, int_val: int):
        """Called when the user drags the sweep_amplitude slider."""
        if self._slider_updating:
            return
        vpp = int_val / self._SWEEP_AMP_SCALE
        self._lbl_amp_val.setText(f"{vpp:.3f} Vpp")
        self.sig_sweep_amplitude_changed.emit(vpp)

    def set_sweep_amplitude_slider(self, value: float):
        """
        Update the sweep_amplitude slider position.
        Clamps to [0.001, 1.0] Vpp. Does NOT emit sig_sweep_amplitude_changed.
        """
        self._slider_updating = True
        clamped = max(0.001, min(1.0, float(value)))
        int_val = int(round(clamped * self._SWEEP_AMP_SCALE))
        self.slider_sweep_amplitude.setValue(int_val)
        self._lbl_amp_val.setText(f"{clamped:.3f} Vpp")
        self._slider_updating = False

    def _on_phase_value_changed(self, int_val: int):
        """Called when the user drags the phase slider."""
        if self._slider_updating:
            return
        deg = int_val / self._PHASE_SCALE
        self._lbl_phase_val.setText(f"{deg:.2f}°")
        self.sig_phase_changed.emit(deg)

    def set_phase_slider(self, value: float):
        """
        Update the phase slider position.
        Clamps to [0.0, 360.0] degrees. Does NOT emit sig_phase_changed.
        """
        self._slider_updating = True
        clamped = max(0.0, min(360.0, float(value)))
        int_val = int(round(clamped * self._PHASE_SCALE))
        self.slider_phase.setValue(int_val)
        self._lbl_phase_val.setText(f"{clamped:.2f}°")
        self._slider_updating = False

    @Slot(dict)
    def update_plot(self, packet: dict):
        """Route a data packet to the appropriate handler."""
        mode = packet.get("mode")
        handler = self._handlers.get(mode)
        
        # Toggle Unlock button visibility
        self.btn_unlock.setVisible(mode == "LOCKED")
        # Toggle Sweep merge/separate button visibility (only in SWEEP mode)
        self.btn_toggle_sweep.setVisible(mode == "SWEEP")
        # Toggle big_offset slider (only in SWEEP mode)
        self._slider_container.setVisible(mode == "SWEEP")
        
        if handler:
            self._stack.setCurrentWidget(handler)
            handler.update(packet)

    def _toggle_sweep_mode(self):
        """Toggle between separate and merged sweep visualizations."""
        sweep_handler = self._handlers.get("SWEEP")
        if isinstance(sweep_handler, SweepPlotHandler):
            sweep_handler._merged = not sweep_handler._merged
            # Update button label to reflect the *next* action
            if sweep_handler._merged:
                self.btn_toggle_sweep.setText("Separate plots")
            else:
                self.btn_toggle_sweep.setText("Merge plots")
            sweep_handler._update_layout()
            # Refresh with last packet if available
            if hasattr(sweep_handler, "_last_packet"):
                sweep_handler.update(sweep_handler._last_packet)
        else:
            # No sweep handler registered – do nothing
            pass
