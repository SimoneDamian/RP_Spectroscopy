from PySide6.QtCore import QObject, Signal, Slot
import os
import yaml
from ruamel.yaml import YAML
import logging
import numpy as np
import influxdb_client
from influxdb_client import Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import time

from .logging_config import setup_logging

class ServiceManager(QObject):
    sig_board_list_updated = Signal(list) 
    sig_reflines_updated = Signal(list)
    sig_advanced_settings_loaded = Signal(dict)
    sig_parameters_loaded = Signal(dict)
    sig_error = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

        # Setup Logging
        log_path = self.config.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'service_manager.log')
        self.logger = logging.getLogger('ServiceManager')
        setup_logging(self.logger, log_file)
        self.logger.info("ServiceManager initializing...")
        
        # --- PATH LOGIC ---
        # 1. Try the path defined in config.yaml
        hardware_path = self.config.get('paths', {}).get('hardware', '')
        
        # 2. If config path is absolute, use it. If relative, join with script dir.
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        self.board_list_path = os.path.join(hardware_path, "board_list.yaml")

        self.logger.info(f"ServiceManager looking for board list at: {self.board_list_path}")
        
        # Reference Lines Path from Config
        reflines_dir = self.config.get('paths', {}).get('reference_lines', hardware_path)
        if not os.path.isabs(reflines_dir):
             base_dir = os.path.dirname(os.path.abspath(__file__))
             reflines_dir = os.path.join(base_dir, reflines_dir)
             
        self.reflines_list_path = os.path.join(reflines_dir, "reference_lines_inventory.yaml")
        
        self.logger.info(f"ServiceManager looking for reference lines at: {self.reflines_list_path}")

        # Grafana configuration
        self.grafana_config = self.config['services']['grafana']
        self.grafana_client = influxdb_client.InfluxDBClient(
            url=self.grafana_config['url'],
            token=self.grafana_config['token'],
            org=self.grafana_config['org']
        )

        self.write_grafana_api = self.grafana_client.write_api(write_options=SYNCHRONOUS)

        self.logger.info(f"Grafana client initialized.")

        self.logger.info("ServiceManager initialization completed.")


    # -------------------------------------------------------------------------
    # YAML FILES METHODS
    # -------------------------------------------------------------------------

    # ---- Red Pitaya boards ----

    def _read_boards_yaml(self):
        if not os.path.exists(self.board_list_path):
            self.logger.info(f"board_list.yaml not found at {self.board_list_path}")
            return {'devices': []}
        
        try:
            with open(self.board_list_path, 'r') as f:
                data = yaml.safe_load(f)
                if data is None: return {'devices': []}
                return data
        except Exception as e:
            err = f"Failed to read board list: {e}"
            self.logger.error(f"{err}")
            self.sig_error.emit(err)
            return {'devices': []}

    def _save_boards_yaml(self, data):
        try:
            # Ensure directory exists before writing
            os.makedirs(os.path.dirname(self.board_list_path), exist_ok=True)
            
            with open(self.board_list_path, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False)
            self.logger.info("board_list.yaml saved.")
        except Exception as e:
            err = f"Failed to save board list: {e}"
            self.logger.error(f"{err}")
            self.sig_error.emit(err)

    @Slot()
    def load_boards(self):
        """Triggered on startup or refresh."""
        self.logger.info("Loading boards...")
        data = self._read_boards_yaml()
        device_list = data.get('devices', [])
        self.logger.info(f"Found {len(device_list)} devices.")
        self.sig_board_list_updated.emit(device_list)

    @Slot(str, str, str, str)
    def add_board(self, name, ip, linien_port, ssh_port):
        self.logger.info(f"Adding board '{name}'...")
        data = self._read_boards_yaml()
        if 'devices' not in data or data['devices'] is None:
            data['devices'] = []

        new_device = {
            'name': name,
            'ip': ip,
            'linien_port': int(linien_port) if linien_port.isdigit() else 18862,
            'ssh_port': int(ssh_port) if ssh_port.isdigit() else 22,
            'username': 'root',
            'password': 'root'
        }

        data['devices'].append(new_device)
        self._save_boards_yaml(data)
        self.sig_board_list_updated.emit(data['devices'])
        self.logger.info(f"Board '{name}' added.")

    @Slot(str)
    def remove_board(self, board_name):
        self.logger.info(f"Removing board '{board_name}'...")
        data = self._read_boards_yaml()
        current_list = data.get('devices', [])
        new_list = [d for d in current_list if d.get('name') != board_name]
        data['devices'] = new_list
        self._save_boards_yaml(data)
        self.sig_board_list_updated.emit(new_list)
        self.logger.info(f"Board '{board_name}' removed.")

    # ---- Reference lines ----

    def _read_reflines_yaml(self):
        if not os.path.exists(self.reflines_list_path):
            self.logger.info(f"reference_lines_inventory.yaml not found at {self.reflines_list_path}")
            return {'lines': []}
        
        try:
            with open(self.reflines_list_path, 'r') as f:
                data = yaml.safe_load(f)
                if data is None: return {'lines': []}
                return data
        except Exception as e:
            err = f"Failed to read reference lines list: {e}"
            self.logger.error(f"{err}")
            self.sig_error.emit(err)
            return {'lines': []}

    def _save_reflines_yaml(self, data):
        try:
            os.makedirs(os.path.dirname(self.reflines_list_path), exist_ok=True)
            with open(self.reflines_list_path, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False)
            self.logger.info("reference_lines_inventory.yaml saved.")
        except Exception as e:
            err = f"Failed to save reference lines list: {e}"
            self.logger.error(f"{err}")
            self.sig_error.emit(err)

    @Slot()
    def get_reference_lines(self):
        """Triggered to get list or refresh."""
        data = self._read_reflines_yaml()
        lines_list = data.get('lines', [])
        # Emit signal so GUI can update
        self.sig_reflines_updated.emit(lines_list)
        return lines_list

    @Slot(str)
    def delete_reference_line(self, name):
        self.logger.info(f"Deleting reference line '{name}'...")
        data = self._read_reflines_yaml()
        current_list = data.get('lines', [])
        
        # Find entry to get filename
        to_delete = next((item for item in current_list if item["name"] == name), None)
        
        # Remove from YAML list
        new_list = [d for d in current_list if d.get('name') != name]
        data['lines'] = new_list
        self._save_reflines_yaml(data)
        
        # Delete the .npy file
        if to_delete:
            file_name = to_delete.get('file_name', to_delete.get('file', name))
            if not file_name.endswith('.npy'):
                file_name += '.npy'
            npy_path = os.path.join(os.path.dirname(self.reflines_list_path), file_name)
            if os.path.exists(npy_path):
                try:
                    os.remove(npy_path)
                    self.logger.info(f"Deleted file {npy_path}")
                except Exception as e:
                     self.logger.error(f"Failed to delete {npy_path}: {e}")

        # Update GUI
        self.sig_reflines_updated.emit(new_list)

    @Slot(str, dict)
    def modify_reference_line(self, old_name, new_data):
        self.logger.info(f"Modifying reference line '{old_name}'...")
        data = self._read_reflines_yaml()
        current_list = data.get('lines', [])
        
        found = False
        for item in current_list:
            if item.get('name') == old_name:
                # If name changed, rename .npy file
                if old_name != new_data['name']:
                    from datetime import datetime
                    import time
                    
                    old_file_name = item.get('file_name', item.get('file', old_name))
                    if not old_file_name.endswith('.npy'):
                        old_file_name += '.npy'
                    
                    # Generate new filename following pattern: name_board_YYYYMMDD_HHMMSS
                    # Use the CREATION date (not modification date)
                    created_date = item.get('created', time.strftime("%Y-%m-%d %H:%M:%S"))
                    try:
                        created_dt = datetime.strptime(created_date, "%Y-%m-%d %H:%M:%S")
                        timestamp = created_dt.strftime("%Y%m%d_%H%M%S")
                    except:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                    
                    board = new_data.get('board', item.get('board', 'Unknown'))
                    new_file_name_base = f"{new_data['name']}_{board}_{timestamp}"
                    new_file_name = new_file_name_base + '.npy'
                    
                    old_path = os.path.join(os.path.dirname(self.reflines_list_path), old_file_name)
                    new_path = os.path.join(os.path.dirname(self.reflines_list_path), new_file_name)
                    
                    if os.path.exists(old_path):
                        try:
                            os.rename(old_path, new_path)
                            self.logger.info(f"Renamed {old_path} to {new_path}")
                            item['file_name'] = new_file_name_base.replace('.npy', '')
                        except Exception as e:
                            self.logger.error(f"Failed to rename {old_path}: {e}")
                
                # Update other fields
                item['name'] = new_data['name']
                item['board'] = new_data['board']
                item['lock_region'] = new_data['lock_region'] 
                item['modified'] = new_data['modified']
                
                found = True
                break
        
        if found:
            self._save_reflines_yaml(data)
            self.sig_reflines_updated.emit(current_list)
        else:
            self.logger.warning(f"Reference line '{old_name}' not found for modification.")

    @Slot(dict)
    def add_reference_line(self, data):
        self.logger.info(f"Adding new reference line '{data.get('name', 'Unnamed')}'...")
        inventory = self._read_reflines_yaml()
        current_list = inventory.get('lines', [])

        import time
        from datetime import datetime

        trace = data.get('trace_data')
        if not trace or 'x' not in trace or 'error_signal' not in trace:
            self.logger.error("No trace data provided to save.")
            self.sig_error.emit("Cannot save: No scan trace loaded.")
            return

        x_arr = np.array(trace['x'])
        y_arr = np.array(trace['error_signal'])

        try:
            ref_left = float(data['ref_left'])
            ref_right = float(data['ref_right'])
            lock_min = float(data['lock_min'])
            lock_max = float(data['lock_max'])
            scan_center = float(data['scan_center'])
        except ValueError:
            self.logger.error("Invalid numerical limits provided.")
            self.sig_error.emit("Cannot save: Invalid numerical values.")
            return

        start_idx = np.argmin(np.abs(x_arr - ref_left))
        stop_idx = np.argmin(np.abs(x_arr - ref_right))
        
        if start_idx > stop_idx:
            start_idx, stop_idx = stop_idx, start_idx
            
        x_cut = x_arr[start_idx:stop_idx]
        y_cut = y_arr[start_idx:stop_idx]

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        created_date = time.strftime("%Y-%m-%d %H:%M:%S")

        board = data.get('board', 'Unknown')
        name = data.get('name', 'Unnamed_Line')
        
        file_name_base = f"{name}_{board}_{timestamp}"
        file_name_full = file_name_base + '.npy'
        
        npy_path = os.path.join(os.path.dirname(self.reflines_list_path), file_name_full)
        
        try:
            np.savetxt(npy_path, np.column_stack((x_cut, y_cut)))
            self.logger.info(f"Saved numpy data to {npy_path}")
        except Exception as e:
            self.logger.error(f"Failed to save {npy_path}: {e}")
            self.sig_error.emit(f"Failed to save data file: {e}")
            return
            
        new_item = {
            'name': name,
            'board': board,
            'file_name': file_name_base,
            'lock_region': [lock_min, lock_max],
            'scan_center': scan_center,
            'created': created_date,
            'modified': created_date,
            'polarity': data.get('polarity', '')
        }
        
        current_list.append(new_item)
        inventory['lines'] = current_list
        self._save_reflines_yaml(inventory)
        
        self.sig_reflines_updated.emit(current_list)

    @Slot(str)
    def duplicate_reference_line(self, name_to_copy):
        self.logger.info(f"Duplicating reference line '{name_to_copy}'...")
        data = self._read_reflines_yaml()
        current_list = data.get('lines', [])
        
        original_item = next((item for item in current_list if item["name"] == name_to_copy), None)
        if not original_item:
            self.logger.error(f"Cannot duplicate: '{name_to_copy}' not found.")
            return

        import time
        from copy import deepcopy
        from datetime import datetime
        
        new_item = deepcopy(original_item)
        new_name = original_item['name'] + "_COPY"
        new_item['name'] = new_name
        # Keep the original created date (same experimental data)
        # Only update the modified date to current time
        new_item['modified'] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Copy file
        old_file_name = original_item.get('file_name', original_item.get('file', name_to_copy))
        if not old_file_name.endswith('.npy'):
            old_file_name += '.npy'
        
        # Generate new filename following pattern: name_board_YYYYMMDD_HHMMSS
        # Use the CREATION date (same as original since it's the same experimental data)
        created_date = original_item.get('created', time.strftime("%Y-%m-%d %H:%M:%S"))
        # Parse and format the creation date
        try:
            created_dt = datetime.strptime(created_date, "%Y-%m-%d %H:%M:%S")
            timestamp = created_dt.strftime("%Y%m%d_%H%M%S")
        except:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        board = original_item.get('board', 'Unknown')
        new_file_name_base = f"{new_name}_{board}_{timestamp}"
        new_file_name = new_file_name_base + '.npy'
        
        old_path = os.path.join(os.path.dirname(self.reflines_list_path), old_file_name)
        new_path = os.path.join(os.path.dirname(self.reflines_list_path), new_file_name)
        
        if os.path.exists(old_path):
             try:
                import shutil
                shutil.copy2(old_path, new_path)
                new_item['file_name'] = new_file_name_base
                self.logger.info(f"Copied {old_path} to {new_path}")
             except Exception as e:
                self.logger.error(f"Failed to copy file: {e}")
                pass
        else:
            self.logger.warning(f"Original file {old_path} not found.")

        current_list.append(new_item)
        data['lines'] = current_list
        self._save_reflines_yaml(data)
        self.sig_reflines_updated.emit(current_list)

    @Slot(str)
    def get_reference_line_data(self, filename):
        """Loads .npy file returning (x, y) arrays."""
        # Handle both 'file_name' (without .npy) and 'file' (with .npy)
        if not filename.endswith('.npy'):
            filename += '.npy'
        path = os.path.join(os.path.dirname(self.reflines_list_path), filename)
        if not os.path.exists(path):
             self.logger.error(f"File not found: {path}")
             return None, None
        try:
            # The .npy files are actually ASCII text files with x, y columns
            data = np.loadtxt(path)
            # Data should be shape (N, 2) where N is number of points
            if len(data.shape) == 2 and data.shape[1] == 2:
                # Return x and y as separate arrays
                return data[:, 0], data[:, 1]
            elif len(data.shape) == 1 and len(data) == 2:
                # Single point case
                return np.array([data[0]]), np.array([data[1]])
            else:
                # Unexpected format
                self.logger.warning(f"Unexpected data shape: {data.shape}")
                return None, None
        except Exception as e:
             self.logger.error(f"Failed to load .npy: {e}")
             return None, None

    # ---- Redpitaya parameters configuration ----

    @Slot(dict)
    def load_parameters(self, board):
        """Read writeable_parameters and readable_parameters from the board's parameter YAML."""
        board_name = board.get('name', '')
        hardware_path = self.config.get('paths', {}).get('hardware', './boards')
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        param_file = os.path.join(hardware_path, f"{board_name}_parameters.yaml")
        if not os.path.exists(param_file):
            self.logger.error(f"Parameter file not found: {param_file}")
            return

        try:
            with open(param_file, 'r') as f:
                data = yaml.safe_load(f)
            params = {
                'writeable_parameters': data.get('writeable_parameters', {}),
                'readable_parameters': data.get('readable_parameters', {})
            }
            self.logger.info(f"Loaded parameters for '{board_name}' "
                            f"({len(params['writeable_parameters'])} writeable, "
                            f"{len(params['readable_parameters'])} readable).")
            self.sig_parameters_loaded.emit(params)
        except Exception as e:
            self.logger.error(f"Failed to load parameters: {e}")

    @Slot(dict)
    def load_default_parameters(self, board):
        """Read parameters from the board's default parameter YAML."""
        board_name = board.get('name', '')
        hardware_path = self.config.get('paths', {}).get('hardware', './boards')
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        param_file = os.path.join(hardware_path, f"{board_name}_parameters_default.yaml")
        if not os.path.exists(param_file):
            self.logger.error(f"Default parameter file not found: {param_file}")
            return

        try:
            with open(param_file, 'r') as f:
                data = yaml.safe_load(f)
            params = {
                'writeable_parameters': data.get('writeable_parameters', {}),
                'readable_parameters': data.get('readable_parameters', {})
            }
            self.logger.info(f"Loaded default parameters for '{board_name}' "
                            f"({len(params['writeable_parameters'])} writeable, "
                            f"{len(params['readable_parameters'])} readable).")
            self.sig_parameters_loaded.emit(params)
        except Exception as e:
            self.logger.error(f"Failed to load default parameters: {e}")

    def save_parameters(self, board, current_values):
        """
        Save the current writeable parameter values back into the board's YAML,
        preserving comments and structure using ruamel.yaml.
        
        Args:
            board: dict with at least 'name' key
            current_values: dict of {param_name: current_value}
        """
        board_name = board.get('name', '')
        hardware_path = self.config.get('paths', {}).get('hardware', './boards')
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        param_file = os.path.join(hardware_path, f"{board_name}_parameters.yaml")
        if not os.path.exists(param_file):
            self.logger.error(f"Cannot save parameters: {param_file} not found.")
            return

        try:
            yml = YAML()
            yml.preserve_quotes = True

            with open(param_file, 'r') as f:
                full_config = yml.load(f)

            # Update ONLY the writeable parameters' initial_value fields
            if 'writeable_parameters' in full_config:
                for name, current_val in current_values.items():
                    if name in full_config['writeable_parameters']:
                        # Convert numpy types to native Python for YAML serialization
                        if hasattr(current_val, 'item'):
                            current_val = current_val.item()
                        full_config['writeable_parameters'][name]['initial_value'] = current_val
                        self.logger.info(f"Updated {name} to {current_val} in config.")

            # Write to a temporary file first, then rename
            tmp_file = param_file + '.tmp'
            with open(tmp_file, 'w') as f:
                yml.dump(full_config, f)
            os.replace(tmp_file, param_file)

            self.logger.info(f"Parameters saved successfully to {param_file}")
        except Exception as e:
            self.logger.error(f"Failed to save parameters: {e}")

    # ---- Redpitaya advanced settings configuration ----

    @Slot(dict)
    def load_advanced_settings(self, board):
        """Read the advanced_settings section from the board's parameter YAML."""
        board_name = board.get('name', '')
        hardware_path = self.config.get('paths', {}).get('hardware', './boards')
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        param_file = os.path.join(hardware_path, f"{board_name}_parameters.yaml")
        if not os.path.exists(param_file):
            self.logger.error(f"Parameter file not found: {param_file}")
            return

        try:
            with open(param_file, 'r') as f:
                data = yaml.safe_load(f)
            advanced = data.get('advanced_settings', {})
            self.logger.info(f"Loaded advanced settings for '{board_name}' ({len(advanced)} groups).")
            self.sig_advanced_settings_loaded.emit(advanced)
        except Exception as e:
            self.logger.error(f"Failed to load advanced settings: {e}")

    @Slot(dict)
    def load_default_advanced_settings(self, board):
        """Read the advanced_settings section from the board's default parameter YAML."""
        board_name = board.get('name', '')
        hardware_path = self.config.get('paths', {}).get('hardware', './boards')
        if not os.path.isabs(hardware_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            hardware_path = os.path.join(base_dir, hardware_path)

        param_file = os.path.join(hardware_path, f"{board_name}_parameters_default.yaml")
        if not os.path.exists(param_file):
            self.logger.error(f"Default parameter file not found: {param_file}")
            return

        try:
            with open(param_file, 'r') as f:
                data = yaml.safe_load(f)
            advanced = data.get('advanced_settings', {})
            self.logger.info(f"Loaded default advanced settings for '{board_name}' ({len(advanced)} groups).")
            self.sig_advanced_settings_loaded.emit(advanced)
        except Exception as e:
            self.logger.error(f"Failed to load default advanced settings: {e}")


    # ---- Circuits parameters ----

    # -------------------------------------------------------------------------
    # ZERORPC METHODS
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # GRAFANA METHODS
    # -------------------------------------------------------------------------

    @Slot(dict)
    def send_point_to_grafana(self, packet):

        p = Point("Locking_data") \
            .tag("board", packet["board_name"]) \
            .time(time.time_ns(), WritePrecision.NS)
        
        mode = packet.get("mode")
        
        if mode == "Send_FSM_state":

            if packet["FSM_state"] == "IDLE":
                p.field("FSM_state", 0)
                p.tag("FSM_state", "IDLE")
            elif packet["FSM_state"] == "SWEEP":
                p.field("FSM_state", 1)
                p.tag("FSM_state", "SWEEP")
            elif packet["FSM_state"] == "SCAN":
                p.field("FSM_state", 2)
                p.tag("FSM_state", "SCAN")
            elif packet["FSM_state"] == "SETUP_MANUAL_LOCK":
                p.field("FSM_state", 3)
                p.tag("FSM_state", "SETUP_MANUAL_LOCK")
            elif packet["FSM_state"] == "MANUAL_LOCKING":
                p.field("FSM_state", 4)
                p.tag("FSM_state", "MANUAL_LOCKING")
            elif packet["FSM_state"] == "LOCKED":
                p.field("FSM_state", 5)
                p.tag("FSM_state", "LOCKED")
            elif packet["FSM_state"] == "OFF":
                p.field("FSM_state", 6)
                p.tag("FSM_state", "OFF")

        try:
            self.write_grafana_api.write(bucket=self.grafana_config['bucket'], org=self.grafana_config['org'], record=p)
        except Exception as e:
            self.logger.error(f"Failed to send data to Grafana: {e}")

    def close_grafana_client(self):
        self.grafana_client.close()
        self.logger.info("Grafana client closed.")