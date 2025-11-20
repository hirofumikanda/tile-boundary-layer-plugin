import os
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMessageBox

from .tile_boundary_layer_manager import TileBoundaryLayerManager

class TileBoundaryLayerPlugin:
    """QGISプラグインのメインクラス"""
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.manager = None
        
        # Plugin actions
        self.actions = []
        self.menu = '&Tile Boundary Layer'
    
    def tr(self, message):
        """Translation method"""
        return QCoreApplication.translate('TileBoundaryLayerPlugin', message)
    
    def initGui(self):
        """Initialize plugin GUI"""
        # Icon path
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        
        # Toggle tile boundary layer action
        self.toggle_action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            self.tr('Toggle Tile Boundary Layer'),
            self.iface.mainWindow()
        )
        self.toggle_action.triggered.connect(self.toggle_tile_layer)
        self.toggle_action.setCheckable(True)
        self.toggle_action.setStatusTip(self.tr('Toggle tile boundary layer display'))
        self.toggle_action.setWhatsThis(self.tr('Show/hide tile boundaries and coordinates on the map'))
        
        # Add to menu and toolbar
        self.iface.addToolBarIcon(self.toggle_action)
        self.iface.addPluginToMenu(self.menu, self.toggle_action)
        
        self.actions.append(self.toggle_action)
    
    def unload(self):
        """Unload plugin"""
        # Cleanup manager
        if self.manager is not None:
            try:
                self.manager.disconnect_signals()
                self.manager.remove_current_layer()
            except Exception as e:
                print(f"Manager cleanup error: {e}")
            finally:
                self.manager = None
        
        # Remove GUI elements
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        
        self.actions = []
    
    def toggle_tile_layer(self):
        """Toggle tile boundary layer display"""
        if self.manager is None:
            # Show tile type selection dialog
            msg_box = QMessageBox(self.iface.mainWindow())
            msg_box.setWindowTitle('Select Tile Type')
            msg_box.setText('Please select the tile type to use')
            msg_box.setIcon(QMessageBox.Question)
            
            xyz_button = msg_box.addButton('XYZ Tile (256px)', QMessageBox.AcceptRole)
            vector_button = msg_box.addButton('Vector Tile (512px)', QMessageBox.AcceptRole)
            cancel_button = msg_box.addButton('Cancel', QMessageBox.RejectRole)
            msg_box.setDefaultButton(xyz_button)
            
            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == cancel_button:
                # Uncheck and exit if cancelled
                self.toggle_action.setChecked(False)
                return
            
            is_vector_tile = (clicked_button == vector_button)
            tile_type_name = 'Vector Tile (512px)' if is_vector_tile else 'XYZ Tile (256px)'
            
            # Create manager and start display
            self.manager = TileBoundaryLayerManager(self.iface, is_vector_tile=is_vector_tile)
            self.toggle_action.setChecked(True)
            self.iface.messageBar().pushMessage(
                'Tile Boundary Layer',
                f'Tile boundary layer display started ({tile_type_name})',
                level=0,  # INFO level
                duration=3
            )
        else:
            # Remove manager and stop display
            try:
                self.manager.disconnect_signals()
                self.manager.remove_current_layer()
            except Exception as e:
                print(f"Manager stop error: {e}")
            finally:
                self.manager = None
                self.toggle_action.setChecked(False)
            self.iface.messageBar().pushMessage(
                'Tile Boundary Layer',
                'Tile boundary layer display stopped',
                level=0,  # INFO level
                duration=3
            )