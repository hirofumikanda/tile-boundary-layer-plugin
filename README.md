# Tile Boundary Layer Plugin

A QGIS plugin for displaying tile boundaries in real-time. This plugin automatically displays Web Mercator tile boundaries as you pan and zoom the map.

## Features

- **Tile Type Menu**: Choose between XYZ tiles (256px) and Vector tiles (512px) from the toolbar button menu
- **Type-specific Icons**: The toolbar button shows the icon of the selected grid type
- **Grid Color Menu**: Choose Red, Black, or White line rendering
- **Persistent Color Choice**: The selected line mode is restored from the QGIS profile
- **Real-time Updates**: Tile boundaries are automatically updated when you move or zoom the map
- **Automatic Zoom Detection**: Automatically calculates the appropriate tile zoom level from the current map scale
- **Tile Coordinate Display**: Shows z/x/y format coordinate labels for each tile
- **Adaptive Font Sizing**: Label font size automatically adjusts based on zoom level
- **Hidden Overlay Layer**: The internal grid layer is not shown in the Layers panel
- **Always on Top**: The grid is kept above project layers, including custom layer order
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
2. Open the side arrow menu on the toolbar button and select a grid type:
   - **XYZ Tile (256px)**: Standard web map tiles (default, red grid icon)
   - **Vector Tile (512px)**: High-resolution vector map tiles (blue vector grid icon)
3. After the separator, select a grid line mode:
   - **Red** (default), **Black**, or **White** for a fixed line color
4. Selecting a type displays its grid and replaces the toolbar button icon with the selected type icon
5. Click the main part of the toolbar button to show or hide the selected grid
6. Labels remain black with a white buffer in every line color mode; boundaries update automatically when you pan or zoom the map

The color selection is stored in the QGIS profile. Changing it while the grid is hidden does not enable the grid; the selection is applied the next time it is shown.

## Technical Specifications

- **QGIS Compatibility**: QGIS 3.x (Qt5) and QGIS 4.x (Qt6)
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
- `256_icon.svg`: Raster grid icon
- `512_icon.svg`: Vector grid icon

## License

MIT License
