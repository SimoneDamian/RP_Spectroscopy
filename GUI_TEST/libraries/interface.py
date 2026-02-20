from .logging_config import setup_logging
import os
import logging
import yaml
from ruamel.yaml import YAML
import sys
import pickle
import numpy as np
from time import sleep

from linien_client.device import Device
from linien_client.connection import LinienClient

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
        Configures the RedPitaya with the basic configuration (this will get updated each time the
        program is turned off) and loads the other fundamental parameters.
        """

        self.logger.info("Loading RedPitaya initial configurationparameters...")

        self.load_RedPitaya_parameters()

        #self.load_advanced_settings()

        #self.load_additional_hardware_parameters()

        # setup the autolock mode
        #self.client.parameters.autolock_mode_preference.value = AutolockMode.ROBUST # use robust autolock mode
        #self.client.parameters.autolock_determine_offset.value = False # do not determine offset automatically
        #self.client.connection.root.write_registers()

    def load_RedPitaya_parameters(self):
        """
        Load writeable and readable parameters from a YAML config file and create corresponding parameter objects. It also
        writes the initial values of the writeable parameters to the device only once at the end of the loading procedure.   
        """
        
        board_config_file_path = self.config.get('paths', {}).get('hardware', './boards')
        board_config_file = os.path.join(board_config_file_path, f"{self.board['name']}_parameters.yaml")

        if not os.path.exists(board_config_file):
            raise FileNotFoundError(f"Parameter config file not found: {board_config_file}")

        with open(board_config_file, 'r') as f:
            config = yaml.safe_load(f)

        self.writeable_params = {}
        for name, entry in config.get("writeable_parameters", {}).items():
            self.logger.debug(f"Loading writeable parameter {name} with hardware name {entry['hardware_name']}, initial value {entry['initial_value']}, scaling {entry['scaling']}")
            self.writeable_params[name] = WriteableParameter(
                name=entry["hardware_name"],
                initial_value=entry["initial_value"],
                scaling=entry["scaling"],
                client = self.client
            )

        self.readable_params = {}
        for name,entry in config.get("readable_parameters", {}).items():
            self.readable_params[name] = ReadableParameter(
                name=entry['hardware_name'],
                client = self.client
            )

        self.write_registers()

    def load_default_RedPitaya_parameters(self):
        """
        Load writeable and readable parameters from a YAML config file and create corresponding parameter objects. It also
        writes the initial values of the writeable parameters to the device only once at the end of the loading procedure.   
        """
        
        board_config_file_path = self.config.get('paths', {}).get('hardware', './boards')
        board_config_file = os.path.join(board_config_file_path, f"{self.board['name']}_parameters_default.yaml")

        if not os.path.exists(board_config_file):
            raise FileNotFoundError(f"Parameter config file not found: {board_config_file}")

        with open(board_config_file, 'r') as f:
            config = yaml.safe_load(f)

        self.writeable_params = {}
        for name, entry in config.get("writeable_parameters", {}).items():
            self.logger.debug(f"Loading writeable parameter {name} with hardware name {entry['hardware_name']}, initial value {entry['initial_value']}, scaling {entry['scaling']}")
            self.writeable_params[name] = WriteableParameter(
                name=entry["hardware_name"],
                initial_value=entry["initial_value"],
                scaling=entry["scaling"],
                client = self.client
            )

        self.readable_params = {}
        for name,entry in config.get("readable_parameters", {}).items():
            self.readable_params[name] = ReadableParameter(
                name=entry['hardware_name'],
                client = self.client
            )

        self.write_registers()

    def write_registers(self):
        self.client.connection.root.write_registers()

    def start_sweep(self):
        self.client.connection.root.start_sweep()

    def check_for_changed_parameters(self):
        self.client.parameters.check_for_changed_parameters()
        
    def save_RedPitaya_parameters_before_closing(self):
        """
        Reads the original YAML, updates the writeable parameters 
        with their current values, and saves it back preserving comments
        and other parameters.
        """

        yaml = YAML()
        yaml.preserve_quotes = True
        
        # 1. Read the full existing file structure
        # We read the file again to ensure we have the full tree with comments
        board_config_file_path = self.config.get('paths', {}).get('hardware', './boards')
        board_config_file = os.path.join(board_config_file_path, f"{self.board['name']}_parameters.yaml")

        if not os.path.exists(board_config_file):
            raise FileNotFoundError(f"Parameter config file not found: {board_config_file}")

        with open(board_config_file, 'r') as f:
            full_config = yaml.load(f)

        # 2. Update ONLY the writeable parameters
        # We iterate through your active python objects and update the YAML structure
        if 'writeable_parameters' in full_config:
            for name, param_obj in self.writeable_params.items():
                
                # Check if this parameter exists in the file structure
                if name in full_config['writeable_parameters']:
                    
                    # Update the 'initial_value' in the YAML to match the current state
                    current_val = self.writeable_params[name].value

                    # Convert numpy types to native Python for YAML serialization
                    if hasattr(current_val, 'item'):
                        current_val = current_val.item()
                    
                    full_config['writeable_parameters'][name]['initial_value'] = current_val
                    
                    self.logger.info(f"Updated {name} to {current_val} in config.")

        # 3. Write to a temporary file first, then rename to avoid
        #    data loss if the dump fails partway through.
        tmp_file = board_config_file + '.tmp'
        with open(tmp_file, 'w') as f:
            yaml.dump(full_config, f)
        os.replace(tmp_file, board_config_file)
            
        self.logger.info(f"Configuration saved successfully to {board_config_file}")

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