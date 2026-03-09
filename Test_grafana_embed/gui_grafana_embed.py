import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

class GrafanaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 Grafana Integration")
        self.resize(1000, 600)

        # 1. Create the central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Set margins to 0 if you want the panel to sit flush against the window edges
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0) 

        # 2. Create the WebEngine View
        self.web_view = QWebEngineView()
        
        # 3. Your specific Grafana Embed URL
        # Port updated to 3001, time range set to live (last 1 hour), refresh every 5s
        grafana_url = (
            "http://localhost:3001/d-solo/ads9vgq/lockingapp?"
            "orgId=1&"
            "from=now-3h&to=now&refresh=10s&"
            "timezone=browser&"
            "showCategory=State%20timeline&"
            "kiosk=true&"
            "theme=dark&"
            "panelId=panel-3&"
            "__feature.dashboardSceneSolo=true"
        )
        
        # 4. Load the URL into the view
        self.web_view.setUrl(QUrl(grafana_url))

        # Add the web view to the layout
        layout.addWidget(self.web_view)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GrafanaApp()
    window.show()
    sys.exit(app.exec())