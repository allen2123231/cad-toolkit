"""Run the pinned Inventor server with lazy attachment to an existing CAD session.

Opening the application remains the desktop app's job. A tool call never launches
Inventor through COM, and no document is created or modified by attachment.
"""
import pythoncom
import threading
import win32com.client
from src import server

Base = type(server.inv)
_thread = threading.local()


class ToolkitInventorConnection(Base):
    @property
    def app(self):
        if not getattr(_thread, 'initialized', False):
            pythoncom.CoInitialize()
            _thread.initialized = True
        if self._app is not None:
            try:
                self._app.SoftwareVersion.DisplayVersion
                return self._app
            except Exception:
                self._app = None
        try:
            self._app = win32com.client.GetActiveObject("Inventor.Application")
            self._app.SoftwareVersion.DisplayVersion
            return self._app
        except Exception as exc:
            self._app = None
            raise RuntimeError("請在 MCP Toolkit 按「開啟 Inventor」，完成授權後即可自動連線。") from exc

    def connect(self, visible=True):
        return f"Connected to running Inventor {self.app.SoftwareVersion.DisplayVersion}"

    def is_connected(self):
        try:
            self.app
            return True
        except RuntimeError:
            return False


server.inv.__class__ = ToolkitInventorConnection
if __name__ == "__main__":
    server.mcp.run()
