# Tile Boundary Layer Plugin

A QGIS plugin for displaying tile boundaries in real-time. This plugin automatically displays Web Mercator tile boundaries as you pan and zoom the map.

## Features

- **Real-time Updates**: Tile boundaries are automatically updated when you move or zoom the map
- **Automatic Zoom Detection**: Automatically calculates the appropriate tile zoom level from the current map scale
- **Tile Coordinate Display**: Shows z/x/y format coordinate labels for each tile
- **Easy Operation**: Simple on/off toggle via toolbar button or menu

## Installation

1. Download `tile-boundary-layer-plugin-main.zip` from this repository (Code → Download ZIP)
2. Launch QGIS
3. Go to **Plugins** → **Manage and Install Plugins**
4. Select the **Install from ZIP** tab
5. Choose the `tile-boundary-layer-plugin-main.zip` file and install
6. Enable "Tile Boundary Layer" in the **Installed** tab

## Usage

1. After enabling the plugin, a tile grid icon will appear in the toolbar
2. Click the icon or select **Plugins** → **Tile Boundary Layer** → **Toggle Tile Boundary Layer**
3. Tile boundaries will be displayed as red lines with coordinate labels at the center of each tile
4. Tile boundaries will automatically update when you pan or zoom the map
5. Click the icon again or select the menu option to stop the display

## Technical Specifications

- **QGIS Compatibility**: 3.0 and above
- **Coordinate System**: EPSG:3857 (Web Mercator)
- **Tile Size**: 256 x 256 pixels

## Developer Information

Plugin structure:
- `__init__.py`: Plugin entry point
- `tile_boundary_layer_plugin.py`: Main plugin class
- `tile_boundary_layer_manager.py`: Tile layer management logic
- `metadata.txt`: Plugin metadata
- `icon.png`: Plugin icon

## License

MIT License
