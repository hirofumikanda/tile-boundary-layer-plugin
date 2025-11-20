# Tile Boundary Layer Plugin

A QGIS plugin for displaying tile boundaries in real-time. This plugin automatically displays Web Mercator tile boundaries as you pan and zoom the map.

## Features

- **Tile Type Selection**: Choose between XYZ tiles (256px) or Vector tiles (512px) when activating the plugin
- **Real-time Updates**: Tile boundaries are automatically updated when you move or zoom the map
- **Automatic Zoom Detection**: Automatically calculates the appropriate tile zoom level from the current map scale
- **Tile Coordinate Display**: Shows z/x/y format coordinate labels for each tile
- **Adaptive Font Sizing**: Label font size automatically adjusts based on zoom level
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
3. A dialog will appear asking you to select the tile type:
   - **XYZ Tile (256px)**: Standard web map tiles (default)
   - **Vector Tile (512px)**: High-resolution vector map tiles
   - **Cancel**: Cancel the operation
4. After selecting a tile type, tile boundaries will be displayed as red lines with coordinate labels (z/x/y format) at the center of each tile
5. Tile boundaries will automatically update when you pan or zoom the map
6. Click the icon again or select the menu option to stop the display

## Technical Specifications

- **QGIS Compatibility**: 3.0 and above
- **Coordinate System**: EPSG:3857 (Web Mercator)
- **Tile Sizes**: 
  - XYZ Tiles: 256 x 256 pixels
  - Vector Tiles: 512 x 512 pixels
- **Font Size Range**: 4pt to 16pt (automatically adjusted based on zoom level)

## Developer Information

Plugin structure:
- `__init__.py`: Plugin entry point
- `tile_boundary_layer_plugin.py`: Main plugin class
- `tile_boundary_layer_manager.py`: Tile layer management logic
- `metadata.txt`: Plugin metadata
- `icon.png`: Plugin icon

## License

MIT License
