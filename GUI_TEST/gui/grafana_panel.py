from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView


class GrafanaPanel(QWidget):
    """
    Reusable widget that embeds a Grafana dashboard panel via QWebEngineView.
    """

    def __init__(self, url: str = "", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        if url:
            self.set_url(url)

    def set_url(self, url: str):
        """Load (or reload) the given Grafana URL."""
        self.web_view.setUrl(QUrl(url))
