from .logging_config import setup_logging
import os
import logging
import sys
import pickle
import numpy as np
from time import sleep

from linien_client.device import Device
from linien_client.connection import LinienClient
from linien_common.common import AutolockMode

from linien_common.common import ANALOG_OUT_V, Vpp


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

    def start_sweep(self):
        self.client.connection.root.start_sweep()

    def check_for_changed_parameters(self):
        self.client.parameters.check_for_changed_parameters()

    def get_sweep(self):
        """
        Neglectiing the mixing channel for simplicity.
        """
        self.start_sweep()
        #print("Sweep_speed ", self.writeable_params["sweep_speed"].get_remote_value())
        sleep(5.0 * ((2.0**self.writeable_params["sweep_speed"].get_remote_value())/(3.8e3))) #wait 3 sweep periods
        self.check_for_changed_parameters()
        to_plot = pickle.loads(self.readable_params["sweep_signal"].get_remote_value())
        error_signal = np.array(to_plot["error_signal_1"]/(2*Vpp))
        monitor_signal = np.array(to_plot["monitor_signal"]/(2*Vpp))
        sweep_signal = {}
        sweep_center = self.writeable_params["sweep_center"].get_remote_value()
        sweep_range = self.writeable_params["sweep_amplitude"].get_remote_value()
        sweep_scan = np.linspace(sweep_center - sweep_range, sweep_center + sweep_range, len(error_signal))
        sweep_signal['x'] = sweep_scan
        sweep_signal['error_signal'] = error_signal
        sweep_signal['monitor_signal'] = monitor_signal
        return sweep_signal

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
            raise KeyError(f"Parameter {param_name} not found among writeable parameters.")

    def set_advanced_settings(self, advanced_settings):
        """
        Sets the advanced settings for the autolock.
        """

        mode_map = {
            "SIMPLE": AutolockMode.SIMPLE,
            "ROBUST": AutolockMode.ROBUST
        }

        self.client.parameters.autolock_mode_preference.value = mode_map[advanced_settings["mode"]]
        self.client.parameters.autolock_determine_offset.value = advanced_settings["determine_offset"]
        self.client.connection.root.write_registers()
        self.logger.info(f"Autolock mode set to {advanced_settings['mode']} and determine offset set to {advanced_settings['determine_offset']}")

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