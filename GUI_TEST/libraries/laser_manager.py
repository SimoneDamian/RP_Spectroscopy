from .logging_config import setup_logging
from .interface import HardwareInterface
from .controller import LockController
from .signal_analysis import SignalAnalysis
from PySide6.QtCore import QObject, Signal, Slot, QTimer
import os
import logging
import numpy as np
from linien_common.common import ANALOG_OUT_V, Vpp
import pickle
import time
from time import sleep

class LaserManager(QObject):
    sig_connected = Signal()
    sig_parameters_ready = Signal()
    sig_data_ready = Signal(dict)
    sig_grafana_data_ready = Signal(dict)
    sig_trace_ready = Signal(dict)

    def __init__(self, config, board):
        super().__init__()
        # ... (rest of init)


        self.cfg = config
        self.board = board

        self.interface = None 
        self.controller = None 
        self.timer = None
        self.signal_analysis = SignalAnalysis(config)

        self.state = "SWEEP"
        self.advanced_settings = {}
        self.old_state = "OFF"
        
        # Setup Logging
        log_path = self.cfg.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'laser_manager.log')
        self.logger = logging.getLogger('LaserManager')
        setup_logging(self.logger, log_file)

        self.logger.info("LaserManager initialized.")

    @Slot()
    def send_grafana_state(self):
        self.logger.info(f"Sending FSM state: {self.state}")
        packet = {
            "mode": "Send_FSM_state",
            "board_name": self.board['name'],
            "FSM_state": self.state
        }

        self.sig_grafana_data_ready.emit(packet)

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
            #self.interface.start_sweep()
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

        if self.state != self.old_state:
            self.logger.info(f"State changed from {self.old_state} to {self.state}")
            
            packet = {
                "mode": "Send_FSM_state",
                "board_name": self.board['name'],
                "FSM_state": self.old_state
            }

            self.sig_grafana_data_ready.emit(packet)

            packet = {
                "mode": "Send_FSM_state",
                "board_name": self.board['name'],
                "FSM_state": self.state
            }

            self.sig_grafana_data_ready.emit(packet)

        self.old_state = self.state

        if self.state == "IDLE":
            pass
        elif self.state == "SWEEP":
            self.get_and_send_sweep("SWEEP")
        elif self.state == "SCAN":
            self.handle_scan_step()
        elif self.state == "SETUP_MANUAL_LOCK":
            self.get_and_send_sweep("SETUP_MANUAL_LOCK")
        elif self.state == "MANUAL_LOCKING":
            self.handle_manual_locking()
        elif self.state == "LOCKED":
            self.handle_locked_state()
        elif self.state == "DEMOD_PHASE_OPTIMIZATION":
            self.handle_demod_phase_optimization_step()
        elif self.state == "JITTER_CHECK":
            self.handle_center_for_jitter_step()
        else:
            self.logger.warning(f"Unknown state: {self.state}")

    @Slot(str)
    def set_state(self, state):
        self.state = state
        if state == "SWEEP":
            self.interface.stop_lock()
            #self.interface.wait_for_lock_status(False)

    @Slot(str)
    def get_and_send_sweep(self, mode):

        sweep_signal = self.interface.get_sweep()

        if sweep_signal is None:
            packet = {
                "mode": "TEXT",
                "text": "Starting the sweep..."
            }
        else:
            packet = {
                "mode": mode,
                "x": sweep_signal["x"],
                "error_signal": sweep_signal["error_signal"],
                "error_signal_strength": sweep_signal["error_signal_strength"],
                "monitor_signal": sweep_signal["monitor_signal"]
            }

        #self.logger.info(f"first error_signal data: {sweep_signal['error_signal'][0:20]}")

        self.sig_data_ready.emit(packet)


    @Slot(float, float, int)
    def start_scan(self, start_voltage=0.05, stop_voltage=1.75, num_points=40, calculate_correlation=False, reference_signal=None, autolock=False):
        """
        Initializes the scan variables and enters the SCAN state.
        This function returns immediately (Non-blocking).
        """
        self.reference_signal = reference_signal
        self.calculate_correlation = calculate_correlation
        self.autolock = autolock
        if self.calculate_correlation:
            num_points = int((stop_voltage - start_voltage) / 0.02) #maybe sweep_amplitude/(ref_line_width*100)
            self.scan_voltages = np.linspace(start_voltage, stop_voltage, num_points)
            self.correlations = np.zeros(num_points)
            self.amplitudes = np.zeros(num_points)
            self.len_matches = np.zeros(num_points)
            self.offsets = np.zeros(num_points)
        else:
            self.scan_voltages = np.linspace(start_voltage, stop_voltage, num_points)


        self.logger.info(f"Initiating scan: {start_voltage}V -> {stop_voltage}V ({num_points} pts)")
        
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
            if self.autolock:
                self.set_optimal_scan_center()
                self.start_center_for_jitter()
                return
            else:
                self.logger.info("Scan completed successfully.")
                self.state = "IDLE"
                self.interface.set_value('big_offset', self.initial_center)
                return

        # 2. Get the target voltage for this step
        target_v = self.scan_voltages[self.scan_index]
        
        # 3. Hardware Interaction (Blocking only for this small step)
        # self.logger.debug(f"Scanning point {self.scan_index}: {target_v:.3f}V")
        self.interface.set_value('big_offset', target_v)

        waiting_time = ((2.0**self.interface.writeable_params["sweep_speed"].get_remote_value())/(3.8e3))
        sleep(waiting_time)

        if self.scan_index == 0:
            # Sometimes the last sweep remains in the buffer
            current_sweep = self.interface.get_sweep()
        
        current_sweep = self.interface.get_sweep()
        
        # 4. Store Data
        self.scan_results.append(current_sweep)
        
        packet = {
            "mode": "SCAN",
            "step_index": self.scan_index,
            "total_steps": len(self.scan_voltages),
            "current_voltage": target_v,
            "scan_data": self.scan_results, # Sends all accumulated data
            "latest_sweep": current_sweep   # Sends just the newest trace
        }

        if self.calculate_correlation:
            r_coeff, len_window, offset, amplitude = self.signal_analysis.find_correlation({'x': current_sweep['x'], 'y': current_sweep['error_signal']}, self.reference_signal)
            self.correlations[self.scan_index] = r_coeff
            self.amplitudes[self.scan_index] = amplitude
            self.len_matches[self.scan_index] = len_window
            self.offsets[self.scan_index] = offset
            self.logger.info(f"Correlation at {target_v}V: {r_coeff}, Length of match: {len_window}, offset with respect to the reference signal: {offset}")
            packet.update({
                "correlations": self.correlations
            })
        # 5. Emit Partial Result (The "Old + New" requirement)
        # We send the specific index so the GUI knows where to plot it
        
        self.sig_data_ready.emit(packet)

        # 6. Increment for the next loop tick
        self.scan_index += 1

    @Slot()
    def start_demod_phase_optimization(self):
        """
        Initializes the phase scan variables and enters the DEMOD_PHASE_OPTIMIZATION state.
        This function returns immediately (Non-blocking).
        """

        self.logger.info(f"Initiating demod phase optimization...")
        
        self.phase_scan_index = 0
        self.scan_phases = np.linspace(0, 180, 30)
        self.phase_scan_results = [] # Buffer to store accumulated results
        #self.scan_phases = []
        self.phase_right_extreme = 180
        self.ratio_right_extreme = 0
        self.phase_left_extreme = 0
        self.ratio_left_extreme = 0
        self.ratio_results = []
        
        # 2. Change State -> The control_loop will take over from here
        self.state = "DEMOD_PHASE_OPTIMIZATION"

    def handle_demod_phase_optimization_step(self):
        """
        Performs exactly ONE phase optimization step of the scan.
        """

        # 0. If it is the first scan, save the initial phase value, in order to return to that one if the optimization does not work
        if self.phase_scan_index == 0:
            current_params = self.get_current_parameter_values()
            self.initial_phase = current_params.get('phase', 0.0)
            #calculate the initial ratios for 0 and 180
            # for target_phase in [0, 180]:
            #     self.scan_phases.append(target_phase)
            #     self.interface.set_value('demodulation_phase_a', target_phase)
            #     waiting_time = ((2.0**self.interface.writeable_params["sweep_speed"].get_remote_value())/(3.8e3))
            #     sleep(waiting_time)
            #     current_sweep = self.interface.get_sweep()
            #     self.phase_scan_results.append(current_sweep)
            #     ratio = self.calculate_ratio(current_sweep)
            #     self.ratio_results.append(ratio)
            #     packet = {
            #         "mode": "DEMOD_PHASE_OPTIMIZATION",
            #         "step_index": self.phase_scan_index,
            #         "current_phase": target_phase,
            #         "phases": self.scan_phases,
            #         "scan_data": self.phase_scan_results, # Sends all accumulated data
            #         "latest_sweep": current_sweep,   # Sends just the newest trace
            #         "ratio": ratio,
            #         "ratio_data": self.ratio_results
            #     }
        
            #     self.sig_data_ready.emit(packet)

            # self.ratio_right_extreme = self.ratio_results[-1]
            # self.ratio_left_extreme = self.ratio_results[0]

        # 1. Check if we are done
        # if (self.phase_right_extreme - self.phase_left_extreme < 1):
        #     self.logger.info("Phase scan completed successfully.")
        #     self.state = "IDLE"
        #     self.interface.set_value('demodulation_phase_a', self.initial_phase)
        #     return
        if self.phase_scan_index >= len(self.scan_phases):
            self.logger.info("Phase scan completed successfully.")
            self.state = "IDLE"
            self.set_parameter_value('phase', self.initial_phase)
            return

        # 2. Get the target voltage for this step
        target_phase = self.scan_phases[self.phase_scan_index]
        
        # 3. Hardware Interaction (Blocking only for this small step)
        self.set_parameter_value('phase', target_phase)

        waiting_time = ((2.0**self.interface.writeable_params["sweep_speed"].get_remote_value())/(3.8e3))
        sleep(waiting_time)

        if self.phase_scan_index == 0:
            # Sometimes the last sweep remains in the buffer
            current_sweep = self.interface.get_sweep()
        
        current_sweep = self.interface.get_sweep()
        
        # 4. Store Data
        self.phase_scan_results.append(current_sweep)

        ratio = self.calculate_ratio(current_sweep)
        self.ratio_results.append(ratio)
        # 5. Emit Partial Result (The "Old + New" requirement)
        # We send the specific index so the GUI knows where to plot it
        packet = {
            "mode": "DEMOD_PHASE_OPTIMIZATION",
            "step_index": self.phase_scan_index,
            "current_phase": target_phase,
            "phases": self.scan_phases,
            "scan_data": self.phase_scan_results, # Sends all accumulated data
            "latest_sweep": current_sweep,   # Sends just the newest trace
            "ratio": ratio,
            "ratio_data": self.ratio_results
        }
        
        self.sig_data_ready.emit(packet)

        # 6. Increment for the next loop tick and substitute the new extreme
        self.phase_scan_index += 1


    def calculate_ratio(self, sweep):
        """
        Calculates the ratio between the maximum amplitudes of the signal and its strength
        in order to find the optimal phase for the demodulation.
        """
        
        signal_amplitude = np.max(sweep['error_signal']) - np.min(sweep['error_signal'])
        signal_strength = np.max(sweep['error_signal_strength']) - np.min(sweep['error_signal_strength'])
        ratio = np.abs(signal_amplitude / signal_strength)

        return ratio

    @Slot(float, float, dict)
    def start_autolock(self, start_voltage=0.05, stop_voltage=1.75, reference_signal=None):
        self.logger.info("Starting autolock, scan for the line...")

        #init of the variables
        self.reference_line_width = reference_signal['x'][-1] - reference_signal['x'][0]
        self.index_sweep_center_try = 0
        self.correlations = []
        self.shifts = []
        self.times = []
        self.amplitudes = []
        self.line_outside_arr = []
        self.line_outside = True 
        self.frequence_stable = False
        self.cnt = 0

        #call of a scan with the autolock option
        self.start_scan(start_voltage=start_voltage, stop_voltage=stop_voltage, reference_signal=reference_signal, calculate_correlation=True, autolock=True)

    def set_optimal_scan_center(self):
        self.logger.info("Setting the optimal scan center...")
        best_idx = np.argmax(self.correlations)
        self.optimal_scan_center = self.scan_voltages[best_idx]
        self.set_parameter_value('big_offset', self.optimal_scan_center)

        # Set vertical offset to align zero-crossing with the reference line
        vertical_offset = -self.offsets[best_idx] + self.interface.writeable_params['offset_a'].value
        self.set_parameter_value('offset_a', vertical_offset)
        self.logger.info(f"Set vertical offset (offset_a) to {vertical_offset}")

        sleep(1)
        return

    def start_center_for_jitter(self):
        self.logger.info("Starting the jitter check loop...")

        # Init variables from advanced settings
        self.jitter_threshold = self.advanced_settings['autocenter_settings']['jitter_threshold']['value']
        self.threshold_count = self.advanced_settings['autocenter_settings']['threshold_count']['value']
        self.offset_big_jump = self.advanced_settings['autocenter_settings']['offset_big_jump']['value']
        self.offset_small_jump = self.advanced_settings['autocenter_settings']['offset_small_jump']['value']
        self.offset_try_list = self.advanced_settings['autocenter_settings']['offset_try_list']['value']
        self.correlation_minimum = self.advanced_settings['autocenter_settings']['correlation_minimum']['value']
        self.length_match_minimum = self.advanced_settings['autocenter_settings']['length_match_minimum']['value']
        self.proportion_free_space_left = self.advanced_settings['autocenter_settings']['proportion_free_space_left']['value']

        # Init loop variables
        self.jitter_time_0 = time.time()
        self.jitter_time_last_retry = 0
        self.jitter_offset = self.interface.writeable_params['big_offset'].value
        self.jitter_offset_0 = self.jitter_offset
        self.jitter_offset_try = np.array(self.offset_try_list) * self.offset_big_jump
        self.jitter_ind_off_try = 0

        # Reset accumulated lists (already initialised in start_autolock, but reset here for safety)
        self.correlations = []
        self.shifts = []
        self.times = []
        self.amplitudes = []
        self.line_outside_arr = []
        self.line_outside = True
        self.frequence_stable = False
        self.cnt = 0

        self.state = "JITTER_CHECK"

    def handle_center_for_jitter_step(self):
        """
        Performs ONE iteration of the jitter/centering feedback loop.
        Adapted from the notebook's center_and_lock_v1 while loop.
        """
        # 1. Acquire signal and compute correlation and shift
        sweep_signal = self.interface.get_sweep()
        if sweep_signal is None:
            return

        shift = SignalAnalysis.find_shift(
            {'x': sweep_signal['x'], 'y': sweep_signal['error_signal']},
            self.reference_signal
        )
        corr, len_match, vertical_offset, amplitude = SignalAnalysis.find_correlation(
            {'x': sweep_signal['x'], 'y': sweep_signal['error_signal']},
            self.reference_signal
        )

        current_time = time.time() - self.jitter_time_0
        self.times.append(current_time)
        self.shifts.append(shift)
        self.correlations.append(corr)
        self.amplitudes.append(amplitude)

        linewidth = self.reference_line_width

        # 2. Detect if line is inside or outside
        line_now_outside = (corr < self.correlation_minimum) or (len_match < self.length_match_minimum * linewidth)
        self.line_outside_arr.append(line_now_outside)

        if line_now_outside and not self.line_outside:
            self.logger.info("Line has escaped")
        elif not line_now_outside and self.line_outside:
            self.logger.info("Line is now inside")

        self.line_outside = line_now_outside
        self.cnt = self.cnt + 1 if not self.line_outside else 0

        # Prepare packet data for GUI
        avg_shift = None
        std_shift = None

        # 3. If recent history suggests line is unstable, try different offset
        recent_history = np.array(self.line_outside_arr[-self.threshold_count-1:])
        if len(recent_history) >= self.threshold_count+1 and np.sum(recent_history) > 3 and (current_time - self.jitter_time_last_retry > 30):
            self.jitter_ind_off_try += 1
            if self.jitter_ind_off_try >= len(self.jitter_offset_try):
                self.logger.info(f"Could not find good offset starting from {self.jitter_offset_0}. Giving up.")
                self.state = "IDLE"
                self._emit_jitter_packet(sweep_signal, shift, corr, len_match, avg_shift, std_shift)
                return
            self.jitter_offset = self.jitter_offset_0 + self.jitter_offset_try[self.jitter_ind_off_try]
            self.jitter_time_last_retry = current_time
            self.logger.info(f"Trying new offset = {self.jitter_offset}")
            self.interface.set_value('big_offset', self.jitter_offset)
            self._emit_jitter_packet(sweep_signal, shift, corr, len_match, avg_shift, std_shift)
            return

        # 4. When enough points collected, check stability and try to center
        if self.cnt > self.threshold_count:
            recent_shifts = self.shifts[-(self.threshold_count - 1):]
            avg_shift = float(np.mean(recent_shifts))
            std_shift = float(np.std(recent_shifts))
            self.frequence_stable = std_shift < self.jitter_threshold

            if self.frequence_stable:
                self.logger.info("Frequency stable enough")
                space_left = shift - sweep_signal['x'][0]
                len_sweep_signal = sweep_signal['x'][-1] - sweep_signal['x'][0]
                space_right = len_sweep_signal - linewidth - space_left
                free_space = len_sweep_signal - linewidth
                edge_space_thr = free_space / 3

                self.logger.info(f"Shift: {shift}, space left: {space_left}, space right: {space_right}, free space: {free_space}, edge space threshold: {edge_space_thr}")

                if space_left > free_space / 3 and space_right > edge_space_thr:
                    # Line is centered and stable
                    self.logger.info(f"Line is centered at offset {self.jitter_offset}. Jitter check complete.")
                    self._emit_jitter_packet(sweep_signal, shift, corr, len_match, avg_shift, std_shift)
                    self.state = "IDLE"
                    return
                elif space_left < free_space / 2:
                    self.logger.info("Too far left: increase offset to decrease frequency")
                    self.jitter_offset -= self.offset_small_jump
                else:
                    self.logger.info("Too far right: decrease offset to increase frequency")
                    self.jitter_offset += self.offset_small_jump

                self.interface.set_value('big_offset', self.jitter_offset)
                self.cnt = 0
                self.line_outside = True
                self.frequence_stable = False
            else:
                self.logger.info("Frequency not stable enough")

        # 5. Emit packet for GUI update
        self._emit_jitter_packet(sweep_signal, shift, corr, len_match, avg_shift, std_shift)

    def _emit_jitter_packet(self, sweep_signal, shift, corr, len_match, avg_shift, std_shift):
        """Build and emit a JITTER_CHECK data packet for the GUI."""
        packet = {
            "mode": "JITTER_CHECK",
            "sweep_signal": sweep_signal,
            "reference_signal": self.reference_signal,
            "shift": shift,
            "correlation": corr,
            "len_match": len_match,
            "linewidth": self.reference_line_width,
            "offset": self.jitter_offset,
            "times": list(self.times),
            "shifts": list(self.shifts),
            "line_outside": self.line_outside,
            "jitter_threshold": self.jitter_threshold,
            "avg_shift": avg_shift,
            "std_shift": std_shift,
        }
        self.sig_data_ready.emit(packet)
        

    @Slot(float)
    def get_sweep_from_scan(self, v_center):
        """
        Gets the trace from the existing scan results that matches `v_center` closest,
        and emits it so the GUI can plot it.
        """
        if not hasattr(self, 'scan_voltages') or not hasattr(self, 'scan_results') or len(self.scan_results) == 0:
            self.logger.warning("No scan data available to get trace from.")
            return

        # Handle the case where the scan is still running or finished early (results length < voltages length)
        available_pts = len(self.scan_results)
        available_volts = self.scan_voltages[:available_pts]

        idx = (np.abs(available_volts - v_center)).argmin()
        matching_trace = self.scan_results[idx]
        
        self.sig_trace_ready.emit(matching_trace)

    @Slot()
    def stop_scan(self):
        if self.state == "SCAN" or self.state == "JITTER_CHECK":
            if self.initial_center is not None:
                self.interface.set_value('big_offset', self.initial_center)
            self.state = "IDLE"
            self.logger.info("Scan aborted by user.")
        if self.state == "DEMOD_PHASE_OPTIMIZATION":
            if self.initial_phase is not None:
                self.set_parameter_value('phase', self.initial_phase)
            self.state = "IDLE"
            self.logger.info("Demod phase optimization aborted by user.")

    @Slot()
    def start_sweep(self):
        self.state = "SWEEP"
        self.logger.info("Sweep started by user.")

    @Slot()
    def setup_manual_lock(self):
        self.state = "SETUP_MANUAL_LOCK"
        self.logger.info("FSM switched to SETUP_MANUAL_LOCK.")

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
                self.logger.info(f"Set parameter {param_name} to {value}")
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

    def handle_manual_locking(self):
        """
        Handles what to send to the GUI while the system tries to lock manually.
        """
        self.logger.info("Handling manual locking...")
        packet = {
            "mode": self.state,
            "text": "Trying to lock the laser..."
        }

        self.sig_data_ready.emit(packet)

    def handle_locked_state(self):
        """
        Handles the locked state of the laser sending the History to the GUI and detecting unlock events if required.
        """
        try:
            history = self.interface.get_history()
            
            gui_vis = self.advanced_settings.get("gui_visualization", {})
            show_fast_deriv = gui_vis.get("fast_control_signal_derivative", {}).get("enabled", False)
            show_slow_deriv = gui_vis.get("slow_control_signal_derivative", {}).get("enabled", False)

            packet = {
                "mode": self.state,
                "show_fast_deriv": show_fast_deriv,
                "show_slow_deriv": show_slow_deriv,
                **history
            }
            self.sig_data_ready.emit(packet)
        except Exception as e:
            self.logger.error(f"Failed to get history: {e}")
            packet = {
                "mode": self.state,
                "text": "Laser is locked! (history unavailable)"
            }
            self.sig_data_ready.emit(packet)

    @Slot(int, int, dict)
    def start_manual_locking(self, x0, x1, sweep_data):
        self.logger.info("Starting manual locking...")
        self.interface.wait_for_lock_status(False)

        expected_lock_monitor_signal_point = self.find_monitor_signal_peak(sweep_data['error_signal'], sweep_data['monitor_signal'], x0, x1)
        self.expected_lock_monitor_signal_point = expected_lock_monitor_signal_point

        self.interface.client.connection.root.start_autolock(x0, x1, pickle.dumps(sweep_data['error_signal']*2*Vpp))

        try:
            self.interface.wait_for_lock_status(True)
            self.logger.info("Locking the laser worked! \\o/")

            # Initialize history buffers from advanced settings
            gui_vis = self.advanced_settings.get("gui_visualization", {})
            hist_cfg = gui_vis.get("history_length", {})
            fast_s = hist_cfg.get("fast", 600)
            slow_s = hist_cfg.get("slow", 3600)
            self.interface.init_history_buffers(fast_s, slow_s)

            self.state = "LOCKED"
        except Exception:
            self.logger.warning("Locking the laser failed :(")
            self.set_state("SWEEP")
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
