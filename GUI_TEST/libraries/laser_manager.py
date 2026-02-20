from .logging_config import setup_logging
from .interface import HardwareInterface
from .controller import LockController
from PySide6.QtCore import QObject, Signal, Slot, QTimer
import os
import logging
import numpy as np

class LaserManager(QObject):
    sig_connected = Signal()
    sig_parameters_updated = Signal()
    sig_data_ready = Signal(dict)

    def __init__(self, config, board):
        super().__init__()
        # ... (rest of init)


        self.cfg = config
        self.board = board

        self.interface = None 
        self.controller = None 
        self.timer = None

        self.state = "SWEEP"
        self.advanced_settings = {}
        
        # Setup Logging
        log_path = self.cfg.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'laser_manager.log')
        self.logger = logging.getLogger('LaserManager')
        setup_logging(self.logger, log_file)

        self.logger.info("LaserManager initialized.")

    @Slot()
    def stop(self):
        """
        Stops the control loop timer
        """
        if self.timer and self.timer.isActive():
            self.timer.stop()
            self.logger.info("Control loop timer stopped.")

    @Slot()
    def setup(self):
        """
        Sets up the HardwareInterface and the Controller
        """
        try:
            self.interface = HardwareInterface(self.cfg, self.board)
            self.controller = LockController(self.interface)

            #Setup internal Timer for the control loop
            self.timer = QTimer()
            self.timer.timeout.connect(self.control_loop)
            self.timer.start(self.cfg['app']['update_interval_ms'])
            
            self.logger.info("LaserManager setup complete. Control loop started.")
            self.sig_connected.emit()

        except Exception as e:
            self.logger.error(f"Failed to initialize HardwareInterface and Controller: {e}")

    @Slot()
    def control_loop(self):
        """
        Runs every x seconds and decides what to do
        based on the current state of the Finite State Machine.
        """
        if self.state == "IDLE":
            pass
        elif self.state == "SWEEP":
            self.get_and_send_sweep()
        elif self.state == "SCAN":
            self.handle_scan_step()
        else:
            self.logger.warning(f"Unknown state: {self.state}")

    @Slot()
    def get_and_send_sweep(self):

        sweep_signal = self.interface.get_sweep()

        packet = {
            "mode": "SWEEP",
            "x": sweep_signal["x"],
            "error_signal": sweep_signal["error_signal"],
            "monitor_signal": sweep_signal["monitor_signal"]
        }

        self.sig_data_ready.emit(packet)

    @Slot(float, float, int)
    def start_scan(self, start_voltage=0.05, stop_voltage=1.75, num_points=40):
        """
        Initializes the scan variables and enters the SCAN state.
        This function returns immediately (Non-blocking).
        """
        self.logger.info(f"Initiating scan: {start_voltage}V -> {stop_voltage}V ({num_points} pts)")
        
        # 1. Pre-calculate the voltage array
        self.scan_voltages = np.linspace(start_voltage, stop_voltage, num_points)
        self.scan_index = 0
        self.scan_results = [] # Buffer to store accumulated results
        
        # 2. Change State -> The control_loop will take over from here
        self.state = "SCAN"

    def handle_scan_step(self):
        """
        Performs exactly ONE step of the scan.
        """
        # 1. Check if we are done
        if self.scan_index >= len(self.scan_voltages):
            self.logger.info("Scan completed successfully.")
            self.state = "IDLE"
            return

        # 2. Get the target voltage for this step
        target_v = self.scan_voltages[self.scan_index]
        
        # 3. Hardware Interaction (Blocking only for this small step)
        # self.logger.debug(f"Scanning point {self.scan_index}: {target_v:.3f}V")
        self.interface.set_value('big_offset', target_v)
        
        current_sweep = self.interface.get_sweep()
        
        # 4. Store Data
        self.scan_results.append(current_sweep)
        
        # 5. Emit Partial Result (The "Old + New" requirement)
        # We send the specific index so the GUI knows where to plot it
        packet = {
            "mode": "SCAN",
            "step_index": self.scan_index,
            "total_steps": len(self.scan_voltages),
            "current_voltage": target_v,
            "scan_data": self.scan_results, # Sends all accumulated data
            "latest_sweep": current_sweep   # Sends just the newest trace
        }
        self.sig_data_ready.emit(packet)

        # 6. Increment for the next loop tick
        self.scan_index += 1

    @Slot()
    def stop_scan(self):
        if self.state == "SCAN":
            self.state = "IDLE"
            self.logger.info("Scan aborted by user.")

    @Slot()
    def start_sweep(self):
        self.state = "SWEEP"
        self.logger.info("Sweep started by user.")

    @Slot()
    def restore_default_parameters(self):
        """
        Reloads the default parameters from the config file and updates the interface.
        """
        if self.interface:
            try:
                self.interface.load_default_RedPitaya_parameters()
                self.logger.info("Default parameters restored.")
                self.sig_parameters_updated.emit()
            except Exception as e:
                self.logger.error(f"Failed to restore default parameters: {e}")

    @Slot()
    def save_parameters(self):
        """
        Saves current parameters back to the YAML file.
        """
        if self.interface:
            try:
                self.interface.save_RedPitaya_parameters_before_closing()
            except Exception as e:
                self.logger.error(f"Failed to save parameters: {e}")

    @Slot(dict)
    def set_advanced_settings(self, settings):
        """
        Receives and stores the advanced settings dictionary.
        """
        self.advanced_settings = settings
        self.logger.info("Advanced settings updated.")