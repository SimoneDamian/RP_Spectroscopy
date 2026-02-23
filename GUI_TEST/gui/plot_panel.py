import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QStackedWidget, QLabel,
                                QScrollArea, QProgressBar)
from PySide6.QtCore import Qt, Slot, QTimer


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
        self.plot_error.setBackground('k')
        self.plot_error.showGrid(x=True, y=True, alpha=0.3)
        self.plot_error.getPlotItem().setLabel('left', 'Error Signal')
        self.plot_error.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_error.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('c', width=1.5))

        # --- Bottom plot: Monitor Signal ---
        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self.plot_monitor.setBackground('k')
        self.plot_monitor.showGrid(x=True, y=True, alpha=0.3)
        self.plot_monitor.getPlotItem().setLabel('left', 'Monitor Signal')
        self.plot_monitor.getPlotItem().setLabel('bottom', 'Voltage', units='V')
        self.plot_monitor.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_monitor.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        self.curve_monitor = self.plot_monitor.plot(pen=pg.mkPen(color=(255, 165, 0), width=1.5))

        # Link x-axes so zooming/panning is synchronised
        self.plot_monitor.setXLink(self.plot_error)

        # Hide the x-axis label on the top plot (shared axis)
        self.plot_error.getPlotItem().setLabel('bottom', '')

        layout.addWidget(self.plot_error)
        layout.addWidget(self.plot_monitor)

    def update(self, packet: dict):
        x = packet.get("x")
        error = packet.get("error_signal")
        monitor = packet.get("monitor_signal")

        if x is None:
            return

        # Convert to numpy arrays if they aren't already
        x = np.asarray(x)
        if error is not None:
            self.curve_error.setData(x, np.asarray(error))
        if monitor is not None:
            self.curve_monitor.setData(x, np.asarray(monitor))

class ManualLockingPlotHandler(BasePlotHandler):
    """
    Handles the MANUAL_LOCKING mode visualization.
    Shows two vertically-stacked plots sharing the same x-axis:
      - Top:    error_signal   (blue)
      - Bottom: monitor_signal (orange)
      - In addition it shows the vertical lines associated with the lock region selected by the user.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top plot: Error Signal ---
        self.plot_error = pg.PlotWidget(title="Error Signal")
        self.plot_error.setBackground('k')
        self.plot_error.showGrid(x=True, y=True, alpha=0.3)
        self.plot_error.getPlotItem().setLabel('left', 'Error Signal')
        self.plot_error.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_error.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('c', width=1.5))

        # --- Bottom plot: Monitor Signal ---
        self.plot_monitor = pg.PlotWidget(title="Monitor Signal")
        self.plot_monitor.setBackground('k')
        self.plot_monitor.showGrid(x=True, y=True, alpha=0.3)
        self.plot_monitor.getPlotItem().setLabel('left', 'Monitor Signal')
        self.plot_monitor.getPlotItem().setLabel('bottom', 'Voltage', units='V')
        self.plot_monitor.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_monitor.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        self.curve_monitor = self.plot_monitor.plot(pen=pg.mkPen(color=(255, 165, 0), width=1.5))

        # Link x-axes so zooming/panning is synchronised
        self.plot_monitor.setXLink(self.plot_error)

        # Hide the x-axis label on the top plot (shared axis)
        self.plot_error.getPlotItem().setLabel('bottom', '')

        layout.addWidget(self.plot_error)
        layout.addWidget(self.plot_monitor)

    def update(self, packet: dict):
        x = packet.get("x")
        error = packet.get("error_signal")
        monitor = packet.get("monitor_signal")

        if x is None:
            return

        # Convert to numpy arrays if they aren't already
        x = np.asarray(x)
        if error is not None:
            self.curve_error.setData(x, np.asarray(error))
        if monitor is not None:
            self.curve_monitor.setData(x, np.asarray(monitor))


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
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

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

    def register_handler(self, mode: str, handler: BasePlotHandler):
        """Register a plot handler for a given FSM mode."""
        self._handlers[mode] = handler
        self._stack.addWidget(handler)

    @Slot(dict)
    def update_plot(self, packet: dict):
        """Route a data packet to the appropriate handler."""
        mode = packet.get("mode")
        handler = self._handlers.get(mode)
        if handler:
            self._stack.setCurrentWidget(handler)
            handler.update(packet)
