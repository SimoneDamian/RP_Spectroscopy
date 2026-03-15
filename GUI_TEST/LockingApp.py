import sys
import yaml
import os
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from libraries.general_manager import GeneralManager

# =============================================================================
# CONFIGURATION LOADER
# =============================================================================

def load_config(filename="config.yaml"):
    """
    Reads the YAML config file safely by looking in the script's own directory.
    """
    # 1. Get the folder where this python script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Create the full path to config.yaml
    config_path = os.path.join(base_dir, filename)
    
    print(f"DEBUG: Attempting to load config from: {config_path}", flush=True)

    if not os.path.exists(config_path):
        print(f"CRITICAL ERROR: Config file NOT found at {config_path}", flush=True)
        return None
        
    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            print("DEBUG: Config loaded successfully.", flush=True)
            return data
    except Exception as e:
        print(f"CRITICAL ERROR: Could not parse YAML: {e}", flush=True)
        return None

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "images/closed_lock.png")
    app.setWindowIcon(QIcon(icon_path))
    cfg = load_config()
    gm = GeneralManager(cfg)
    exit_code = app.exec()
    gm.cleanup()
    sys.exit(exit_code)