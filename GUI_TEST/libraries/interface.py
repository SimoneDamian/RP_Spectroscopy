from .logging_config import setup_logging
import os
import logging
import sys
import pickle
import numpy as np
from time import sleep, time

from linien_client.device import Device
from linien_client.connection import LinienClient
from linien_common.common import AutolockMode

from linien_common.common import ANALOG_OUT_V, Vpp
from scipy.ndimage import gaussian_filter1d
import matplotlib.dates as mdates
from datetime import datetime

class HardwareInterface():
    """
    This class is the interface between the user and the Red Pitaya.
    It contains all the low level methods to communicate with the device.
    """

    def __init__(self, config, board):
        self.config = config
        self.board = board

        # Setup Logging
        log_path = self.config.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'interface.log')
        self.logger = logging.getLogger('HardwareInterface')
        setup_logging(self.logger, log_file)

        self.device = None
        self.client = None
        self._connect()
        self._basic_configure()

        self.logger.info("HardwareInterface initialized.")

    def _connect(self):
        """
        Connects to the RedPitaya
        """

        try:
            self.logger.info(f"Attempting connection via {self.board['name']} address ({self.board['ip']}:{self.board['linien_port']})")
            self.device = Device(host=self.board['ip'], username=self.board['username'], password=self.board['password'])
            self.client = LinienClient(self.device)
            self.client.connect(autostart_server=True, use_parameter_cache=True)
            self.logger.info(f"Connected to device {self.board['name']}")
            return
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.board['name']}: {e}")
            raise ConnectionError(f"Failed to connect to {self.board['name']}.")

    def _basic_configure(self):
        """
        Configures the RedPitaya with the basic configuration.
        Note: Parameter loading is no longer done here — it happens when
        the ServiceManager sends the parameters dict via signal chain.
        """
        self.logger.info("Basic configuration complete. Waiting for parameters from ServiceManager...")
        self.writeable_params = {}
        self.readable_params = {}

    def load_parameters_from_dict(self, params_dict):
        """
        Load writeable and readable parameters from an already-parsed dict
        (provided by ServiceManager) and create corresponding parameter objects.
        Writes initial values to the device at the end.
        
        Args:
            params_dict: dict with 'writeable_parameters' and 'readable_parameters' keys,
                         each containing the parameter definitions from YAML.
        """
        self.logger.info("Loading parameters from dict...")

        self.writeable_params = {}
        for name, entry in params_dict.get("writeable_parameters", {}).items():
            self.logger.debug(f"Loading writeable parameter {name} with hardware name {entry['hardware_name']}, initial value {entry['initial_value']}, scaling {entry['scaling']}")
            self.writeable_params[name] = WriteableParameter(
                name=entry["hardware_name"],
                initial_value=entry["initial_value"],
                scaling=entry["scaling"],
                client=self.client
            )

        self.readable_params = {}
        for name, entry in params_dict.get("readable_parameters", {}).items():
            self.readable_params[name] = ReadableParameter(
                name=entry['hardware_name'],
                client=self.client
            )

        self.write_registers()
        self.logger.info(f"Parameters loaded: {len(self.writeable_params)} writeable, {len(self.readable_params)} readable.")

    def write_registers(self):
        self.client.connection.root.write_registers()

    def stop_lock(self):
        """
        Properly stop the lock and return to sweep mode.
        Mirrors linien GUI's on_stop_lock: first stop the autolock task,
        then call exposed_start_sweep() which sets lock=False and restarts acquisition.
        """
        # 1. Stop the autolock task (same as linien GUI's on_stop_lock)
        try:
            task = self.client.parameters.task.value
            if task is not None:
                task.stop()
                self.client.parameters.task.value = None
                self.logger.info("Autolock task stopped.")
        except Exception as e:
            self.logger.warning(f"Could not stop autolock task: {e}")

        # 2. Start sweep (sets lock=False, resets combined_offset, restarts acquisition)
        self.client.connection.root.exposed_start_sweep()
        self.logger.info("Lock stopped, sweep restarted.")

    def start_sweep(self):
        self.client.connection.root.exposed_start_sweep()

    def check_for_changed_parameters(self):
        self.client.parameters.check_for_changed_parameters()

    def get_sweep(self):
        """
        Neglecting the mixing channel for simplicity.
        """
        self.check_for_changed_parameters()
        to_plot = pickle.loads(self.readable_params["sweep_signal"].get_remote_value())
        #self.logger.info(f"Entries of the sweep: {list(to_plot.keys())}")
        try:
            error_signal = np.array(to_plot["error_signal_1"]/(2*Vpp))
            error_signal_quadrature = np.array(to_plot['error_signal_1_quadrature'])/(2*Vpp)
            error_signal_strength = np.sqrt(error_signal**2 + error_signal_quadrature**2)
            monitor_signal = np.array(to_plot["monitor_signal"]/(2*Vpp))
            sweep_signal = {}
            sweep_center = self.writeable_params["sweep_center"].get_remote_value()
            sweep_range = self.writeable_params["sweep_amplitude"].get_remote_value()
            sweep_scan = np.linspace(sweep_center - sweep_range, sweep_center + sweep_range, len(error_signal))
            sweep_signal['x'] = sweep_scan
            sweep_signal['error_signal'] = error_signal
            sweep_signal['error_signal_strength'] = error_signal_strength
            sweep_signal['monitor_signal'] = monitor_signal
            return sweep_signal
        except Exception as e:
            self.logger.warning(f"Failed to get sweep: {e}")
            return None

    def set_value(self, param_name, value):
        """
        Sets the value of a writeable parameter.
        """
        if param_name in self.writeable_params:
            self.writeable_params[param_name].set_value(value)
            self.write_registers() #actually it already does this in the other set_value
            self.logger.debug(f"Set parameter {param_name} to value {value}")
        else:
            self.logger.error(f"Parameter {param_name} not found among writeable parameters.")
            raise KeyError(f"Parameter {param_name} not found among writeable parameters. Possible writeable parameters are: {list(self.writeable_params.keys())}")

    def set_advanced_settings(self, advanced_settings):
        """
        Sets the advanced settings for the autolock.
        """

        mode_map = {
            "SIMPLE": AutolockMode.SIMPLE,
            "ROBUST": AutolockMode.ROBUST
        }

        autolock = advanced_settings.get("autolock_settings", {})
        
        # Access nested value/enabled fields
        mode_str = autolock.get("mode", {}).get("value", "ROBUST")
        determine_offset = autolock.get("determine_offset", {}).get("enabled", False)

        self.client.parameters.autolock_mode_preference.value = mode_map.get(mode_str, AutolockMode.ROBUST)
        self.client.parameters.autolock_determine_offset.value = determine_offset
        self.client.connection.root.write_registers()
        self.logger.info(f"Autolock mode set to {mode_str} and determine offset set to {determine_offset}")

    def wait_for_lock_status(self, should_be_locked):
        """
        Wait until the laser reaches the desired lock state.
        """
        counter = 0
        while True:
            #print("checking lock status...")
            self.logger.info("checking lock status...")
            to_plot = pickle.loads(self.client.parameters.to_plot.value)
            self.logger.info(f"to_plot keys: {list(to_plot.keys())}")

            is_locked = "error_signal" in to_plot

            if is_locked == should_be_locked:
                break

            counter += 1
            if counter > 10:
                raise Exception("waited too long")

            sleep(1)

    def init_history_buffers(self, fast_length_s, slow_length_s):
        """
        Initializes local circular buffers for accumulating history data
        beyond the Red Pitaya's fixed-length buffer.

        Args:
            fast_length_s: max age (seconds) for monitor & fast-control buffers.
            slow_length_s: max age (seconds) for slow-control buffers.
        """
        self._fast_length_s = fast_length_s
        self._slow_length_s = slow_length_s

        # Fast-window buffers (monitor + fast control)
        self._buf_fast_control_times = []   # unix timestamps
        self._buf_fast_control_values = []  # scaled values
        self._buf_monitor_times = []        # unix timestamps
        self._buf_monitor_values = []       # scaled values

        # Slow-window buffers
        self._buf_slow_control_times = []   # unix timestamps
        self._buf_slow_control_values = []  # scaled values

        self.logger.info(
            f"History buffers initialized: fast={fast_length_s}s, slow={slow_length_s}s"
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers for the circular-buffer logic                     #
    # ------------------------------------------------------------------ #
    def _append_new(self, buf_times, buf_values, new_times, new_values):
        """
        Append only data points whose timestamps are strictly newer
        than the latest entry already in the buffer.
        """
        if len(buf_times) == 0:
            buf_times.extend(new_times.tolist())
            buf_values.extend(new_values.tolist())
        else:
            last_t = buf_times[-1]
            mask = new_times > last_t
            if mask.any():
                buf_times.extend(new_times[mask].tolist())
                buf_values.extend(new_values[mask].tolist())

    @staticmethod
    def _trim_buffer(buf_times, buf_values, max_age_s):
        """
        Remove entries older than *max_age_s* seconds from the current time.
        Operates in-place on the two parallel lists.
        """
        if len(buf_times) == 0:
            return
        cutoff = time() - max_age_s
        # Find first index that is >= cutoff
        idx = 0
        for i, t in enumerate(buf_times):
            if t >= cutoff:
                idx = i
                break
        else:
            # All entries are older than cutoff
            idx = len(buf_times)
        if idx > 0:
            del buf_times[:idx]
            del buf_values[:idx]

    def get_history(self):
        """
        Fetches new history data from the Red Pitaya, appends it to the
        local circular buffers, trims to the configured time windows, and
        returns the buffered data as numpy arrays.
        """
        control_signal_history = self.readable_params["control_signal_history"].get_remote_value()
        monitor_signal_history = self.readable_params["monitor_signal_history"].get_remote_value()

        # --- Raw RP data → numpy ---
        raw_fc_times  = np.array(control_signal_history["times"])
        raw_fc_values = np.array(control_signal_history["values"]) / (2 * Vpp)
        raw_sc_times  = np.array(control_signal_history["slow_times"])
        raw_sc_values = np.array(control_signal_history["slow_values"]) * ANALOG_OUT_V
        raw_mon_times = np.array(monitor_signal_history["times"])
        raw_mon_values = np.array(monitor_signal_history["values"]) / (2 * Vpp)

        # --- Append only new points to local buffers ---
        self._append_new(self._buf_fast_control_times,  self._buf_fast_control_values,  raw_fc_times,  raw_fc_values)
        self._append_new(self._buf_monitor_times,       self._buf_monitor_values,       raw_mon_times, raw_mon_values)
        self._append_new(self._buf_slow_control_times,  self._buf_slow_control_values,  raw_sc_times,  raw_sc_values)

        # --- Trim to configured window ---
        self._trim_buffer(self._buf_fast_control_times, self._buf_fast_control_values, self._fast_length_s)
        self._trim_buffer(self._buf_monitor_times,      self._buf_monitor_values,      self._fast_length_s)
        self._trim_buffer(self._buf_slow_control_times, self._buf_slow_control_values, self._slow_length_s)

        # --- Build output dict (numpy arrays) ---
        temp_dict = {}

        fc_times = np.array(self._buf_fast_control_times)
        fc_values = np.array(self._buf_fast_control_values)
        temp_dict['fast_control_values'] = fc_values
        temp_dict['fast_control_times_unix'] = fc_times

        # Derivative of fast control
        sigma = 5
        if len(fc_times) >= 2:
            dt = fc_times[-1] - fc_times[-2]
            if dt > 0:
                d_control = np.diff(gaussian_filter1d(fc_values, sigma=sigma)) / dt
            else:
                d_control = np.zeros(max(len(fc_values) - 1, 0))
        else:
            d_control = np.array([])
        temp_dict['d_fast_control_values'] = d_control

        sc_times = np.array(self._buf_slow_control_times)
        sc_values = np.array(self._buf_slow_control_values)
        temp_dict['slow_control_values'] = sc_values
        temp_dict['slow_control_times_unix'] = sc_times

        # Derivative of slow control
        if len(sc_times) >= 2:
            dt_slow = sc_times[-1] - sc_times[-2]
            if dt_slow > 0:
                d_slow = np.diff(gaussian_filter1d(sc_values, sigma=sigma)) / dt_slow
            else:
                d_slow = np.zeros(max(len(sc_values) - 1, 0))
        else:
            d_slow = np.array([])
        temp_dict['d_slow_control_values'] = d_slow

        mon_times = np.array(self._buf_monitor_times)
        mon_values = np.array(self._buf_monitor_values)
        temp_dict['monitor_values'] = mon_values
        temp_dict['monitor_times_unix'] = mon_times

        self.history = temp_dict
        return temp_dict

class ReadableParameter:
    def __init__(self, name, client):
        self.name = name
        self.remote_value = None
        self.client = client

    def get_attribute(self):
        attribute = getattr(self.client.parameters, self.name)
        return attribute
    
    def get_remote_value(self):
        self.client.parameters.check_for_changed_parameters()
        value = self.get_attribute().value
        self.value = value
        return value

class WriteableParameter(ReadableParameter):
    def __init__(self, name, initial_value, scaling, client):
        super().__init__(name, client) #Writeable parameters are also readable parameters so they inherits all the attributes of the parent class
        self.value = initial_value
        self.scaling = scaling
        self.initialize_parameter()

    def initialize_parameter(self):
        '''
        The initialization is faster then using set_value for each parameter because it runs
        only at the end the write_registers().
        '''
        if self.scaling is not None:
            if self.scaling == 1:
                self.get_attribute().value = self.value
            else:
                self.get_attribute().value = self.value * self.scaling
        else:
            self.get_attribute().value = self.value

    def set_value(self, value):
        # Convert numpy scalars to native Python types
        if hasattr(value, 'item'):
            value = value.item()
        self.value = value
        if self.scaling is not None:
            if self.scaling == 1:
                self.get_attribute().value = value
            else:
                self.get_attribute().value = self.value * self.scaling
        else:
            self.get_attribute().value = self.value

        self.client.connection.root.write_registers()

    def get_remote_value(self):
        self.client.parameters.check_for_changed_parameters()
        if self.scaling is not None:
            value = self.get_attribute().value / self.scaling
        else:
            value = self.get_attribute().value
        self.value = value
        return value