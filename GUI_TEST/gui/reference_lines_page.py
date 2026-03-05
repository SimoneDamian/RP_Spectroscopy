from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, 
                               QTableWidget, QTableWidgetItem, QPushButton, 
                               QLabel, QHeaderView, QAbstractItemView, QMessageBox)
from PySide6.QtCore import Qt, Signal, Slot
import pyqtgraph as pg
import numpy as np

class ReferenceLinesPage(QWidget):
    sig_request_back = Signal()

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.service_manager = None
        self.is_modifying = False
        self.current_selection_name = None
        
        # Setup UI
        self.init_ui()
        self.logger.info("ReferenceLinesPage initialized.")

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- Header ---
        title = QLabel("Reference Lines")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(title, 0)

        # --- Main Splitter ---
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

        # --- Left Side: List Table ---
        self.table_list = QTableWidget()
        self.table_list.setColumnCount(4)
        self.table_list.setHorizontalHeaderLabels(["Name", "Board", "Created", "Modified"])
        self.table_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.splitter.addWidget(self.table_list)

        # --- Right Side: Plot & Details ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Plot
        self.plot_widget = pg.PlotWidget(title="Reference Line Preview")
        self.plot_widget.setBackground('w') # White background for cleanliness, or 'k' for dark
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.setLabel('bottom', 'V', units='V')
        self.plot_item.setLabel('left', 'Signal')
        
        # Disable scientific notation on axes
        self.plot_item.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_item.getAxis('left').enableAutoSIPrefix(False)
        
        self.current_plot_curve = self.plot_item.plot(pen='b')
        # Red region for lock range
        self.lock_region = pg.LinearRegionItem(values=[0, 1], orientation=pg.LinearRegionItem.Vertical, 
                                               brush=pg.mkBrush(255, 0, 0, 50), movable=False)
        self.plot_item.addItem(self.lock_region)
        
        right_layout.addWidget(self.plot_widget, stretch=2)

        # Details/Properties Table
        self.table_details = QTableWidget()
        self.table_details.setColumnCount(2)
        self.table_details.setHorizontalHeaderLabels(["Property", "Value"])
        self.table_details.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # We will populate rows: Name, Board, Lock Region Min, Lock Region Max
        self.setup_details_table()
        right_layout.addWidget(self.table_details, stretch=1)

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([400, 600]) # Initial ratio

        # --- Buttons Row ---
        btn_layout = QHBoxLayout()
        
        # Back button on the left
        self.btn_back = QPushButton("Back")
        self.btn_back.setStyleSheet("font-size: 14px; padding: 5px 10px;")
        btn_layout.addWidget(self.btn_back)
        
        # Spacer to push action buttons to the right
        btn_layout.addStretch()
        
        # Action buttons on the right
        self.btn_add = QPushButton("Add Reference Line")
        self.btn_add.setEnabled(False) # Default disabled until connected? Or logic TBD
        
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_modify = QPushButton("Modify")
        self.btn_delete = QPushButton("Delete")
        
        self.btn_save = QPushButton("Save")
        self.btn_save.setVisible(False)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_duplicate)
        btn_layout.addWidget(self.btn_modify)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout, 0)

        # --- Connections ---
        self.btn_back.clicked.connect(self.sig_request_back.emit)
        self.table_list.itemSelectionChanged.connect(self.on_selection_changed)
        
        self.btn_delete.clicked.connect(self.on_delete_clicked)
        self.btn_duplicate.clicked.connect(self.on_duplicate_clicked)
        self.btn_modify.clicked.connect(self.on_modify_clicked)
        self.btn_save.clicked.connect(self.on_save_clicked)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        # self.btn_add.clicked.connect(...) # Future implementation

    def setup_details_table(self):
        # Rows: Name (editable), Board (read-only), Scan Center (read-only), Lock Region Min (editable), Lock Region Max (editable), Polarity (read-only)
        rows = ["Name", "Board", "Scan Center", "Lock Region Min", "Lock Region Max", "Polarity"]
        editable_rows = [0, 3, 4]  # Name, Lock Region Min, Lock Region Max
        
        self.table_details.setRowCount(len(rows))
        for i, row_name in enumerate(rows):
            item = QTableWidgetItem(row_name)
            item.setFlags(Qt.ItemIsEnabled) # Read only label
            self.table_details.setItem(i, 0, item)
            
            val_item = QTableWidgetItem("")
            if i in editable_rows:
                # Editable fields
                val_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            else:
                # Read-only fields
                val_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_details.setItem(i, 1, val_item)

    def set_service_manager(self, sm):
        self.service_manager = sm
        if self.service_manager:
            self.service_manager.sig_reflines_updated.connect(self.update_list_table)
            # Initial load
            self.service_manager.get_reference_lines()

    @Slot(list)
    def update_list_table(self, data_list):
        self.logger.info(f"Updating reference lines table with {len(data_list)} items.")
        self.table_list.blockSignals(True)
        self.table_list.setRowCount(0)
        self.current_data_list = data_list # Store for easy access
        
        for row, item in enumerate(data_list):
            self.table_list.insertRow(row)
            self.table_list.setItem(row, 0, QTableWidgetItem(item.get('name', '')))
            self.table_list.setItem(row, 1, QTableWidgetItem(item.get('board', '')))
            self.table_list.setItem(row, 2, QTableWidgetItem(item.get('created', '')))
            self.table_list.setItem(row, 3, QTableWidgetItem(item.get('modified', '')))
            
        self.table_list.blockSignals(False)
        
        # Restore selection if possible
        if self.current_selection_name:
            items = self.table_list.findItems(self.current_selection_name, Qt.MatchExactly)
            if items:
                row = items[0].row()
                self.table_list.selectRow(row)

    def on_selection_changed(self):
        selected_items = self.table_list.selectedItems()
        if not selected_items:
            self.clear_details()
            return

        row = selected_items[0].row()
        name = self.table_list.item(row, 0).text()
        self.current_selection_name = name
        
        # Find data
        item_data = next((i for i in self.current_data_list if i['name'] == name), None)
        if item_data:
            self.populate_details(item_data)
            self.load_plot_data(item_data)

    def populate_details(self, data):
        # Name
        self.table_details.item(0, 1).setText(data.get('name', ''))
        # Board
        self.table_details.item(1, 1).setText(data.get('board', ''))
        # Scan Center
        self.table_details.item(2, 1).setText(str(data.get('scan_center', '')))
        # Lock Region
        region = data.get('lock_region', [0, 0])
        self.table_details.item(3, 1).setText(str(region[0]))
        self.table_details.item(4, 1).setText(str(region[1]))
        # Polarity
        self.table_details.item(5, 1).setText(data.get('polarity', ''))

    def load_plot_data(self, data):
        # Support both 'file_name' (without .npy) and 'file' (with .npy)
        filename = data.get('file_name', data.get('file'))
        if not filename:
            filename = data.get('name', '')  # Fallback to name
            
        if self.service_manager and filename:
            x, y = self.service_manager.get_reference_line_data(filename)
            if x is not None and y is not None:
                self.current_plot_curve.setData(x, y)
                # Update region
                region = data.get('lock_region', [0, 1])
                if len(region) == 2:
                    self.lock_region.setRegion(region)
            else:
                self.current_plot_curve.clear()
        else:
             self.current_plot_curve.clear()

    def clear_details(self):
        for i in range(self.table_details.rowCount()):
            self.table_details.item(i, 1).setText("")
        self.current_plot_curve.clear()

    def set_editing_mode(self, active):
        self.is_modifying = active
        
        # Toggle buttons
        self.btn_modify.setVisible(not active)
        self.btn_delete.setVisible(not active)
        self.btn_duplicate.setVisible(not active)
        self.btn_add.setVisible(False) # Always hide add in edit mode
        self.table_list.setEnabled(not active) # Lock list selection
        
        self.btn_save.setVisible(active)
        self.btn_cancel.setVisible(active)
        
        
        # Enable editing in details table
        # Only Name (0), Lock Region Min (3), and Lock Region Max (4) are editable
        # Board (1), Scan Center (2), and Polarity (5) are always read-only
        editable_rows = [0, 3, 4]
        for i in range(self.table_details.rowCount()):
            item = self.table_details.item(i, 1)
            if item:
                if i in editable_rows:
                    # These fields are always editable when in modify mode
                    if active:
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                    else:
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                else:
                    # Board, Scan Center, and Polarity are always read-only
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
        # Lock Region movable
        self.lock_region.setMovable(active)

    def on_modify_clicked(self):
        if not self.current_selection_name:
             return
        self.set_editing_mode(True)

    def on_save_clicked(self):
        # Gather data
        new_name = self.table_details.item(0, 1).text()
        new_board = self.table_details.item(1, 1).text()
        try:
            # Lock Region Min is now at row 3, Max at row 4 (scan_center is at row 2)
            min_val = float(self.table_details.item(3, 1).text())
            max_val = float(self.table_details.item(4, 1).text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Lock region values must be numbers.")
            return

        # Also get from plot region if it was moved
        region = self.lock_region.getRegion()
        # Prefer values from table if user typed specific numbers? 
        # Or sync them? For now let's trust table if it differs, or maybe plot?
        # Let's align them. If user moved region, plot region is truth.
        # But if user typed in table... 
        # Let's take plot region since it's visual, unless table was the last focus?
        # Simpler: Just take what's in the table, assuming user updated it.
        # BUT wait, the plot region is movable.
        # Let's check if plot region matches table approximately.
        # For simplicity in this step, let's take table values as they are explicit text.
        
        import time
        new_data = {
            'name': new_name,
            'board': new_board,
            'lock_region': [min_val, max_val],
            'modified': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if self.service_manager:
            self.service_manager.modify_reference_line(self.current_selection_name, new_data)
            
        self.current_selection_name = new_name # Update selection tracking
        self.set_editing_mode(False)

    def on_cancel_clicked(self):
        # Revert changes by re-selecting current
        self.set_editing_mode(False)
        self.on_selection_changed()

    def on_delete_clicked(self):
        if not self.current_selection_name: return
        
        reply = QMessageBox.question(self, 'Confirm Delete', 
                                     f"Are you sure you want to delete '{self.current_selection_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if self.service_manager:
                self.service_manager.delete_reference_line(self.current_selection_name)
            self.current_selection_name = None
            self.clear_details()

    def on_duplicate_clicked(self):
        if not self.current_selection_name: return
        if self.service_manager:
            self.service_manager.duplicate_reference_line(self.current_selection_name)
