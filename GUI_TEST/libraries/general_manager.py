from .service_manager import ServiceManager
from .laser_manager import LaserManager
from PySide6.QtCore import QThread, Slot
from gui.main_window import MainWindow
import logging
import os
from .logging_config import setup_logging
from ruamel.yaml import YAML
import warnings


class GeneralManager:
    def __init__(self, config=None):
        # Load config robustly
        self.cfg = config
        if not self.cfg:
             # Fallback: Assume board_list is in the script folder if config fails
            print("WARNING: Using default config fallback.", flush=True)
            self.cfg = {'paths': {'hardware': './', 'logs': './logs'}}

        # Setup Logging
        log_path = self.cfg.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'general_manager.log')
        self.logger = logging.getLogger('GeneralManager')
        setup_logging(self.logger, log_file)
        self.logger.info("GeneralManager starting up...")

        self.advanced_settings = {}
        self.current_board = None

        self.services = ServiceManager(self.cfg)
        self.logger.info("ServiceManager initialized.")
        self.svc_thread = QThread()
        self.services.moveToThread(self.svc_thread)
        self.logger.info("ServiceManager moved to thread.")

        self.window = MainWindow()
        self.logger.info("MainWindow initialized.")

        # Wiring
        self.window.page_connect.sig_request_add_page.connect(self.window.go_to_add)
        self.window.page_add.sig_request_back.connect(self.window.go_to_connection)
        self.window.page_add.sig_submit_board.connect(self.services.add_board)
        self.window.page_add.sig_submit_board.connect(self.window.go_to_connection)
        self.window.page_connect.sig_request_remove.connect(self.services.remove_board)
        self.window.page_connect.sig_request_refresh.connect(self.services.load_boards)
        self.window.page_connect.sig_request_connect.connect(self.connect_to_board)
        self.services.sig_board_list_updated.connect(self.window.page_connect.update_table)
        
        # New Navigation Wiring
        self.window.page_initial.sig_request_reference_lines.connect(self.window.go_to_reference_lines)
        self.window.page_initial.sig_request_connection.connect(self.window.go_to_connection)
        self.window.page_reflines.sig_request_back.connect(self.window.go_to_initial_page)

        self.window.page_connect.sig_request_back.connect(self.window.go_to_initial_page)
        
        # Inject ServiceManager into ReferenceLinesPage
        self.window.page_reflines.set_service_manager(self.services)
        self.logger.info("ServiceManager injected into ReferenceLinesPage.")

        self.svc_thread.start()
        self.logger.info("ServiceManager thread started.")
        
        # Trigger initial load via signal (Thread safe practice)
        # We need a temporary signal or just call it directly since loop hasn't started yet
        self.services.load_boards() 
        
        self.window.show()

    def _safe_disconnect(self, signal):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                signal.disconnect()
        except (TypeError, RuntimeError):
            pass

    def connect_to_board(self, board):
        board_name = board.get('name', 'Unknown')
        self.logger.info(f"Connecting to {board_name}...")

        self.laser = LaserManager(self.cfg, board)
        self.logger.info("LaserManager initialized.")
        self.lsr_thread = QThread()
        self.laser.moveToThread(self.lsr_thread)
        self.logger.info("LaserManager moved to thread.")
        
        # Connect started signal to setup method to ensure it runs in the thread
        self.lsr_thread.started.connect(self.laser.setup)
        
        # Connect connection signal to GUI update
        # We need Qt.QueuedConnection because signal is from thread, slot is in GUI thread
        # In PySide/Qt, default connection type is AutoConnection which handles this automatically
        self.laser.sig_connected.connect(self.window.page_laser.set_connected_state)
        self.laser.sig_connected.connect(self.on_laser_connected)
        
        # Connection for Default Settings Button
        # Disconnect previous backend connections to avoid duplicates (safeguard)
        self._safe_disconnect(self.window.page_laser.page_parameters.sig_restore_defaults)
            
        self.window.page_laser.page_parameters.sig_restore_defaults.connect(self.laser.restore_default_parameters)
        self.laser.sig_parameters_updated.connect(self.on_parameters_updated)

        # Connection for live data plotting
        self.laser.sig_data_ready.connect(self.window.page_laser.plot_panel.update_plot)
        self.laser.sig_data_ready.connect(self.on_data_ready)

        # Scan page signals
        self.window.page_laser.page_scan.sig_start_scan.connect(self.laser.start_scan)
        self.window.page_laser.page_scan.sig_stop_scan.connect(self.laser.stop_scan)
        self.window.page_laser.page_scan.sig_back.connect(self.laser.start_sweep)

        # Connection for advanced settings
        #  - Direct to QWidget slot for GUI (auto-connection ensures GUI thread)
        self.services.sig_advanced_settings_loaded.connect(
            self.window.page_laser.page_advanced.load_advanced_settings
        )
        #  - Direct to LaserManager slot (auto-connection ensures laser thread)
        self.services.sig_advanced_settings_loaded.connect(self.laser.set_advanced_settings)
        #  - Non-QObject storage (runs in emitter's thread, but only stores a dict)
        self.services.sig_advanced_settings_loaded.connect(self.on_advanced_settings_loaded)
        #  - GUI edits -> forward to laser + local storage
        self.window.page_laser.page_advanced.sig_advanced_setting_changed.connect(
            self.on_advanced_setting_changed
        )
        self.window.page_laser.page_advanced.sig_advanced_setting_changed.connect(
            self.laser.set_advanced_settings
        )
        
        # Connection for Default Advanced Settings Button
        self._safe_disconnect(self.window.page_laser.page_advanced.sig_restore_defaults)
        self.window.page_laser.page_advanced.sig_restore_defaults.connect(
            lambda: self.services.load_default_advanced_settings(self.current_board)
        )
        
        self.lsr_thread.start()
        self.logger.info("LaserManager thread started.")
        
        # Switch to Laser Controller Page and set to connecting state
        self.window.page_laser.set_connecting_state()
        self.window.go_to_laser_controller()

        # Trigger loading advanced settings from YAML (via ServiceManager)
        self.current_board = board
        self.services.load_advanced_settings(board)

    @Slot()
    def on_laser_connected(self):
        """
        Called when laser manager is fully connected.
        Populate the parameters table.
        """
        # We access the interface params. 
        # Note: self.laser.interface might be in use by the thread.
        # But reading the dict of params structure is likely fine once setup is done.
        
        if self.laser.interface and hasattr(self.laser.interface, 'writeable_params'):
            params = self.laser.interface.writeable_params
            self.window.page_laser.page_parameters.load_parameters(params)
            self.logger.info("Parameters loaded into GUI.")
        else:
            self.logger.warning("Could not load parameters: Interface not ready or no params.")

    @Slot()
    def on_parameters_updated(self):
        """
        Called when parameters are updated (e.g. defaults restored).
        Refreshes the GUI table.
        """
        if self.laser.interface and hasattr(self.laser.interface, 'writeable_params'):
            params = self.laser.interface.writeable_params
            self.window.page_laser.page_parameters.load_parameters(params)
            self.logger.info("Parameters refreshed from defaults.")
        else:
            self.logger.warning("Could not refresh parameters: Interface not ready.")

    @Slot(dict)
    def on_advanced_settings_loaded(self, settings):
        """
        Stores the advanced settings dict locally.
        GUI population and LaserManager delivery are handled by
        direct signal connections (thread-safe via Qt auto-connection).
        """
        self.advanced_settings = settings
        self.logger.info("Advanced settings stored in GeneralManager.")

    @Slot(dict)
    def on_advanced_setting_changed(self, settings):
        """
        Called when the user edits a value in the AdvancedSettingsPage.
        Updates the stored copy. LaserManager receives settings via
        a direct signal connection.
        """
        self.advanced_settings = settings
        self.logger.info("Advanced settings updated from GUI.")

    @Slot(dict)
    def on_data_ready(self, packet):
        """
        Listens to every data packet. When a SCAN packet indicates
        the last step, re-enable the ScanPage buttons.
        """
        if packet.get("mode") == "SCAN":
            step = packet.get("step_index", 0)
            total = packet.get("total_steps", 1)
            if step + 1 >= total:
                self.window.page_laser.page_scan.set_scan_finished()

    def save_advanced_settings(self):
        """
        Saves the current advanced_settings back into the board YAML file,
        preserving comments and structure using ruamel.yaml.
        """
        if not self.current_board or not self.advanced_settings:
            return

        board_name = self.current_board.get('name', '')
        hardware_path = self.cfg.get('paths', {}).get('hardware', './boards')
        param_file = os.path.join(hardware_path, f"{board_name}_parameters.yaml")

        if not os.path.exists(param_file):
            self.logger.error(f"Cannot save advanced settings: {param_file} not found.")
            return

        try:
            yml = YAML()
            yml.preserve_quotes = True

            with open(param_file, 'r') as f:
                full_config = yml.load(f)

            # Deep-update the advanced_settings section
            self._deep_update(full_config['advanced_settings'], self.advanced_settings)

            with open(param_file, 'w') as f:
                yml.dump(full_config, f)

            self.logger.info(f"Advanced settings saved to {param_file}")
        except Exception as e:
            self.logger.error(f"Failed to save advanced settings: {e}")

    @staticmethod
    def _deep_update(target, source):
        """
        Recursively update `target` dict with values from `source`,
        preserving ruamel.yaml comment structure.
        """
        for key, val in source.items():
            if isinstance(val, dict) and key in target and isinstance(target[key], dict):
                GeneralManager._deep_update(target[key], val)
            else:
                target[key] = val

    def cleanup(self):
        self.logger.info("GeneralManager shutting down...")
        self.svc_thread.quit()
        self.svc_thread.wait()
        
        if hasattr(self, 'lsr_thread') and self.lsr_thread.isRunning():
            # Stop the timer before quitting the thread
            # We use QMetaObject.invokeMethod to call the slot in the thread context
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            
            # 1. Save parameters to YAML
            QMetaObject.invokeMethod(self.laser, "save_parameters", Qt.BlockingQueuedConnection)
            
            # 2. Stop the control loop timer
            QMetaObject.invokeMethod(self.laser, "stop", Qt.BlockingQueuedConnection)
            
            self.lsr_thread.quit()
            self.lsr_thread.wait()

        # 3. Save advanced settings (runs in GUI thread, no thread issues)
        self.save_advanced_settings()
            
        self.logger.info("GeneralManager shut down.")