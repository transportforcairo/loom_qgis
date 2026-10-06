# -*- coding: utf-8 -*-
"""
loom_plugin.py — QGIS plugin entry point.

On first run (or whenever binaries are missing) the DownloadDialog is shown
before the main dialog so the user can fetch pre-built binaries automatically.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui     import QIcon
from qgis.core           import QgsApplication

from .binary_resolver import check_binaries
from .downloader import binaries_present, binaries_outdated


class LoomPlugin:

    def __init__(self, iface):
        self.iface   = iface
        self.action  = None
        self.dialog  = None
        self._update_offered = False

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
        icon = QIcon(icon_path) if os.path.isfile(icon_path) \
               else QgsApplication.getThemeIcon("/mActionAddLayer.svg")

        self.action = QAction(icon, "LOOM Transit Map Generator", self.iface.mainWindow())
        self.action.setToolTip(
            "Generate schematic or geographic transit maps using LOOM\n"
            "(github.com/ad-freiburg/loom) — Windows port by Transport for Cairo"
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&LOOM Transit Maps", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("&LOOM Transit Maps", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()

    def run(self):
        if not binaries_present():
            self._show_download_dialog()
        elif binaries_outdated() and not self._update_offered:
            # Binaries from an older build (e.g. the pre-1.1 macOS/Linux
            # builds that needed Homebrew/apt libraries). Offer the update
            # once per QGIS session; skipping keeps the current binaries.
            self._update_offered = True
            self._show_download_dialog()
        else:
            self._show_main_dialog()

    def _show_download_dialog(self):
        from .download_dialog import DownloadDialog
        dlg = DownloadDialog(parent=self.iface.mainWindow(), auto_start=False)
        dlg.exec()
        # Proceed to main dialog whether they downloaded or skipped
        # (skip case: existing binaries, or LOOM built from source on PATH)
        if dlg.was_successful() or binaries_present() or all(check_binaries().values()):
            self._show_main_dialog()

    def _show_main_dialog(self):
        from .dialog import LoomDialog
        if self.dialog is None:
            self.dialog = LoomDialog(self.iface, parent=self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
