import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMenu, QToolButton
from qgis.core import Qgis, QgsSettings

try:
    # QAction moved from QtWidgets in Qt5 to QtGui in Qt6.
    from qgis.PyQt.QtGui import QAction, QActionGroup
except ImportError:
    from qgis.PyQt.QtWidgets import QAction, QActionGroup

from .tile_boundary_layer_manager import (
    DEFAULT_GRID_COLOR_MODE,
    TileBoundaryLayerManager,
    normalize_grid_color_mode,
)


TILE_TYPES = {
    "xyz": {
        "label": "XYZ Tile (256px)",
        "icon": "256_icon.png",
        "is_vector_tile": False,
    },
    "vector": {
        "label": "Vector Tile (512px)",
        "icon": "512_icon.png",
        "is_vector_tile": True,
    },
}
DEFAULT_TILE_TYPE = "xyz"
GRID_COLOR_SETTING_KEY = "tile_boundary_layer/grid_color_mode"
GRID_COLOR_OPTIONS = {
    "red": "Red",
    "black": "Black",
    "white": "White",
}


class TileBoundaryLayerPlugin:
    """QGIS plugin entry point and toolbar controls."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.manager = None

        self.actions = []
        self.menu = "&Tile Boundary Layer"
        self.selected_tile_type = DEFAULT_TILE_TYPE
        self.tile_type_icons = {}
        self.tile_type_actions = {}
        self.tile_type_menu = None
        self.tile_type_action_group = None
        self.grid_color_actions = {}
        self.grid_color_action_group = None
        self.selected_grid_color_mode = DEFAULT_GRID_COLOR_MODE
        self.toggle_action = None
        self.toolbar_button = None
        self.toolbar_widget_action = None

    def tr(self, message):
        """Translate a user-facing string."""
        return QCoreApplication.translate("TileBoundaryLayerPlugin", message)

    def _load_icon(self, filename):
        icon_path = os.path.join(self.plugin_dir, filename)
        return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

    def initGui(self):
        """Initialize the split toggle button and grid type menu."""
        self.selected_grid_color_mode = normalize_grid_color_mode(
            QgsSettings().value(
                GRID_COLOR_SETTING_KEY, DEFAULT_GRID_COLOR_MODE
            )
        )
        self.tile_type_icons = {
            key: self._load_icon(config["icon"])
            for key, config in TILE_TYPES.items()
        }

        self.toggle_action = QAction(
            self.tile_type_icons[self.selected_tile_type],
            self.tr("Toggle Tile Boundary Layer"),
            self.iface.mainWindow(),
        )
        self.toggle_action.setCheckable(True)
        self.toggle_action.triggered.connect(self.toggle_tile_layer)
        self.toggle_action.setStatusTip(
            self.tr("Show or hide the selected tile grid")
        )
        self.toggle_action.setWhatsThis(
            self.tr("Show or hide the currently selected tile grid")
        )

        self.tile_type_menu = QMenu(self.iface.mainWindow())
        self.tile_type_action_group = QActionGroup(self.tile_type_menu)
        self.tile_type_action_group.setExclusive(True)

        for key, config in TILE_TYPES.items():
            action = QAction(
                self.tile_type_icons[key],
                self.tr(config["label"]),
                self.tile_type_action_group,
            )
            action.setCheckable(True)
            action.setData(key)
            action.setStatusTip(
                self.tr(f"Display the {config['label']} grid")
            )
            self.tile_type_action_group.addAction(action)
            self.tile_type_menu.addAction(action)
            self.tile_type_actions[key] = action

        self.tile_type_actions[self.selected_tile_type].setChecked(True)
        self.tile_type_action_group.triggered.connect(self.select_tile_type)

        self.tile_type_menu.addSeparator()
        self.grid_color_action_group = QActionGroup(self.tile_type_menu)
        self.grid_color_action_group.setExclusive(True)
        for mode, label in GRID_COLOR_OPTIONS.items():
            action = QAction(
                self.tr(label), self.grid_color_action_group
            )
            action.setCheckable(True)
            action.setData(mode)
            action.setStatusTip(self.tr(f"Use {label} grid lines"))
            self.grid_color_action_group.addAction(action)
            self.tile_type_menu.addAction(action)
            self.grid_color_actions[mode] = action

        self.grid_color_actions[
            self.selected_grid_color_mode
        ].setChecked(True)
        self.grid_color_action_group.triggered.connect(
            self.select_grid_color_mode
        )

        # Split button: the main area toggles the current grid, while the
        # separate arrow area opens the grid type menu.
        self.toolbar_button = QToolButton(self.iface.mainWindow())
        self.toolbar_button.setObjectName("TileBoundaryLayerToolButton")
        self.toolbar_button.setAutoRaise(True)
        self.toolbar_button.setDefaultAction(self.toggle_action)
        self.toolbar_button.setMenu(self.tile_type_menu)
        self.toolbar_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.MenuButtonPopup
        )
        self.toolbar_widget_action = self.iface.addToolBarWidget(
            self.toolbar_button
        )

        # Keep the Plugins menu entry as a plain toggle without a side submenu.
        self.iface.addPluginToMenu(self.menu, self.toggle_action)
        self.actions.append(self.toggle_action)

    def unload(self):
        """Unload the plugin and release its GUI objects."""
        self._stop_tile_layer(show_message=False)

        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
        self.actions = []

        if self.toolbar_widget_action is not None:
            self.iface.removeToolBarIcon(self.toolbar_widget_action)
        self.toolbar_widget_action = None
        self.toolbar_button = None

        if self.tile_type_menu is not None:
            self.tile_type_menu.deleteLater()
        self.tile_type_menu = None
        self.tile_type_action_group = None
        self.tile_type_actions = {}
        self.grid_color_action_group = None
        self.grid_color_actions = {}
        self.tile_type_icons = {}
        self.toggle_action = None

    def _set_selected_tile_type(self, tile_type):
        self.selected_tile_type = tile_type
        if tile_type in self.tile_type_actions:
            self.tile_type_actions[tile_type].setChecked(True)
        if self.toggle_action is not None:
            self.toggle_action.setIcon(self.tile_type_icons[tile_type])
        if self.toolbar_button is not None:
            self.toolbar_button.setIcon(self.tile_type_icons[tile_type])

    def select_tile_type(self, action):
        """Select a grid type, update the button icon, and display it."""
        tile_type = action.data()
        if tile_type not in TILE_TYPES:
            return

        type_changed = tile_type != self.selected_tile_type
        was_active = self.manager is not None

        if was_active and type_changed:
            self._stop_tile_layer(show_message=False)

        self._set_selected_tile_type(tile_type)

        if not was_active or type_changed:
            message_template = (
                "Tile grid changed to {name}"
                if was_active
                else "Tile boundary layer display started ({name})"
            )
            self._start_tile_layer(message_template=message_template)

    def select_grid_color_mode(self, action):
        """Persist and apply a mutually exclusive grid line color mode."""
        mode = normalize_grid_color_mode(action.data())
        self.selected_grid_color_mode = mode
        if mode in self.grid_color_actions:
            self.grid_color_actions[mode].setChecked(True)
        QgsSettings().setValue(GRID_COLOR_SETTING_KEY, mode)

        if self.manager is not None:
            self.manager.set_grid_color_mode(mode)

    def _start_tile_layer(self, message_template=None):
        if self.manager is not None:
            if self.toggle_action is not None:
                self.toggle_action.setChecked(True)
            return

        config = TILE_TYPES[self.selected_tile_type]
        self.manager = TileBoundaryLayerManager(
            self.iface,
            is_vector_tile=config["is_vector_tile"],
            grid_color_mode=self.selected_grid_color_mode,
        )
        if self.toggle_action is not None:
            self.toggle_action.setChecked(True)

        if message_template is None:
            message_template = "Tile boundary layer display started ({name})"
        self.iface.messageBar().pushMessage(
            "Tile Boundary Layer",
            message_template.format(name=config["label"]),
            level=Qgis.MessageLevel.Info,
            duration=3,
        )

    def _stop_tile_layer(self, show_message=True):
        if self.manager is not None:
            try:
                self.manager.disconnect_signals()
                self.manager.remove_current_layer()
            except Exception as error:
                print(f"Manager stop error: {error}")
            finally:
                self.manager = None

        if self.toggle_action is not None:
            self.toggle_action.setChecked(False)

        if show_message:
            self.iface.messageBar().pushMessage(
                "Tile Boundary Layer",
                "Tile boundary layer display stopped",
                level=Qgis.MessageLevel.Info,
                duration=3,
            )

    def toggle_tile_layer(self, checked=None):
        """Toggle the currently selected tile grid without opening a dialog."""
        if checked is None:
            checked = self.manager is None

        if checked:
            self._start_tile_layer()
        else:
            self._stop_tile_layer()
