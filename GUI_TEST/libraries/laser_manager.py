from .logging_config import setup_logging
from .interface import HardwareInterface
from .controller import LockController
from PySide6.QtCore import QObject, Signal, Slot, QTimer
import os
import logging
import numpy as np
from linien_common.common import ANALOG_OUT_V, Vpp
import pickle

class LaserManager(QObject):
    sig_connected = Signal()
    sig_parameters_ready = Signal()
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
            self.get_and_send_sweep("SWEEP")
        elif self.state == "SCAN":
            self.handle_scan_step()
        elif self.state == "SETUP_MANUAL_LOCK":
            self.get_and_send_sweep("SETUP_MANUAL_LOCK")
        else:
            self.logger.warning(f"Unknown state: {self.state}")

    @Slot(str)
    def get_and_send_sweep(self, mode):

        sweep_signal = self.interface.get_sweep()

        packet = {
            "mode": mode,
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

        # 0. If it is the first scan, save the initial center of the sweep, in order to return to that one at the end of the sweep
        if self.scan_index == 0:
            self.initial_center = self.interface.writeable_params['big_offset'].value

        # 1. Check if we are done
        if self.scan_index >= len(self.scan_voltages):
            self.logger.info("Scan completed successfully.")
            self.state = "IDLE"
            self.interface.set_value('big_offset', self.initial_center)
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
            if self.initial_center is not None:
                self.interface.set_value('big_offset', self.initial_center)
            self.state = "IDLE"
            self.logger.info("Scan aborted by user.")

    @Slot()
    def start_sweep(self):
        self.state = "SWEEP"
        self.logger.info("Sweep started by user.")

    @Slot(dict)
    def load_parameters(self, params_dict):
        """
        Receives the parameters dict from ServiceManager (via GeneralManager)
        and forwards it to the Interface to create hardware parameter objects.
        """
        if self.interface:
            try:
                self.interface.load_parameters_from_dict(params_dict)
                self.logger.info("Parameters loaded into Interface.")
                self.sig_parameters_ready.emit()
            except Exception as e:
                self.logger.error(f"Failed to load parameters into Interface: {e}")
        else:
            self.logger.warning("Cannot load parameters: Interface not initialized.")

    @Slot(dict)
    def load_advanced_settings(self, settings_dict):
        """
        Receives the advanced settings dict from ServiceManager (via GeneralManager)
        and forwards come of them to the Interface to initialize it correctly.
        """
        self.advanced_settings = settings_dict
        
        if self.interface:
            try:
                self.interface.set_advanced_settings(settings_dict)
                self.logger.info("Advanced settings loaded into Interface.")
            except Exception as e:
                self.logger.error(f"Failed to load advanced settings into Interface: {e}")
        else:
            self.logger.warning("Cannot load advanced settings: Interface not initialized.")

    @Slot(str, object)
    def set_parameter_value(self, param_name, value):
        """
        Sets a single parameter value on the hardware (called when user edits GUI).
        """
        if self.interface:
            try:
                self.interface.set_value(param_name, value)
                self.logger.debug(f"Set parameter {param_name} to {value}")
            except Exception as e:
                self.logger.error(f"Failed to set parameter {param_name}: {e}")

    def get_current_parameter_values(self):
        """
        Returns a dict of {param_name: current_value} for all writeable parameters.
        Used by GeneralManager when saving parameters on app close.
        """
        if self.interface and hasattr(self.interface, 'writeable_params'):
            return {name: param.value for name, param in self.interface.writeable_params.items()}
        return {}

    @Slot(dict)
    def set_advanced_settings(self, settings):
        """
        Receives and stores the advanced settings dictionary.
        """
        self.advanced_settings = settings
        self.logger.info("Advanced settings updated.")

    @Slot(float, float, dict)
    def start_manual_locking(self, x0, x1, sweep_data):
        self.interface.wait_for_lock_status(False) #wait until the laser is unlocked

        expected_lock_monitor_signal_point = self.find_monitor_signal_peak(sweep_data['error_signal'], sweep_data['monitor_signal'], x0, x1)
        self.expected_lock_monitor_signal_point = expected_lock_monitor_signal_point
        #print("Expected lock monitor signal point:", expected_lock_monitor_signal_point)

        self.interface.client.connection.root.start_autolock(x0, x1, pickle.dumps(sweep_data['error_signal']*2*Vpp))

        try:
            self.interface.wait_for_lock_status(True)
            self.logger.info("Locking the laser worked! \\o/")
        except Exception:
            self.logger.warning("Locking the laser failed :(")
            return

    def find_monitor_signal_peak(self, error_signal, monitor_signal, x0, x1):
        error_signal_selected_region = error_signal[x0:x1]
        monitor_signal_selected_region = monitor_signal[x0:x1]

        maximum_error_index = np.argmax(error_signal_selected_region)
        minimum_error_index = np.argmin(error_signal_selected_region)

        if minimum_error_index < maximum_error_index:
            #slope is positive so I have to look for a minimum in the monitor signal
            return [x0 + np.argmin(monitor_signal_selected_region), monitor_signal_selected_region[np.argmin(monitor_signal_selected_region)]]
        else:
            return [x0 + np.argmax(monitor_signal_selected_region), monitor_signal_selected_region[np.argmax(monitor_signal_selected_region)]]
