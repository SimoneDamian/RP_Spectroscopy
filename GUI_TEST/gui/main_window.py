from PySide6.QtWidgets import QMainWindow, QStackedWidget, QSplitter
from PySide6.QtCore import Qt
from .connection_page import ConnectionPage
from .add_board_page import AddBoardPage
from .initial_page import InitialPage
from .reference_lines_page import ReferenceLinesPage
from .laser_controller_page import LaserControllerPage
from .grafana_panel import GrafanaPanel
import logging
import os
from libraries.logging_config import setup_logging

class MainWindow(QMainWindow):
    def __init__(self, grafana_url=""):
        super().__init__()
        self.setWindowTitle("LaserLock Application")
        self.resize(800, 600)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._grafana_url = grafana_url
        self._grafana_panels = []

        # Setup Logging
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, 'logs')
        log_file = os.path.join(log_dir, 'gui.log')
        
        self.logger = logging.getLogger('GUI')
        setup_logging(self.logger, log_file)
        self.logger.info("GUI MainWindow initialized.")

        self.page_initial = InitialPage(self.logger)
        self.page_connect = ConnectionPage(self.logger)
        self.page_add = AddBoardPage(self.logger)
        self.page_reflines = ReferenceLinesPage(self.logger)
        self.page_laser = LaserControllerPage(self.logger)

        # Wrap each page inside a vertical QSplitter with a GrafanaPanel at the bottom
        self._splitter_initial = self._wrap_with_grafana(self.page_initial)
        self._splitter_connect = self._wrap_with_grafana(self.page_connect)
        self._splitter_add = self._wrap_with_grafana(self.page_add)
        self._splitter_reflines = self._wrap_with_grafana(self.page_reflines)
        self._splitter_laser = self._wrap_with_grafana(self.page_laser)

        self.stack.addWidget(self._splitter_initial)
        self.stack.addWidget(self._splitter_connect)
        self.stack.addWidget(self._splitter_add)
        self.stack.addWidget(self._splitter_reflines)
        self.stack.addWidget(self._splitter_laser)
        
        # Set initial page
        self.stack.setCurrentWidget(self._splitter_initial)

    def _wrap_with_grafana(self, page_widget):
        """Wrap a page widget in a vertical QSplitter with a GrafanaPanel at the bottom."""
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(page_widget)

        grafana = GrafanaPanel(self._grafana_url)
        self._grafana_panels.append(grafana)
        splitter.addWidget(grafana)

        # Page content gets ~80% of height, Grafana panel ~20%
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        return splitter

    def set_grafana_url(self, url):
        """Update the Grafana URL on all embedded panels."""
        self._grafana_url = url
        for panel in self._grafana_panels:
            panel.set_url(url)

    def go_to_connection(self):
        self.stack.setCurrentWidget(self._splitter_connect)

    def go_to_add(self):
        self.stack.setCurrentWidget(self._splitter_add)

    def go_to_initial_page(self):
        self.stack.setCurrentWidget(self._splitter_initial)
        self.page_initial.reset_state()

    def go_to_reference_lines(self):
        self.stack.setCurrentWidget(self._splitter_reflines)

    def go_to_laser_controller(self):
        self.stack.setCurrentWidget(self._splitter_laser)