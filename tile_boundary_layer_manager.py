import math

from PyQt5.QtGui import QColor, QFont
from qgis.PyQt.QtCore import QVariant, QObject

from qgis.core import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFillSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)

# Web Mercator definitions
ORIGIN_SHIFT = 20037508.342789244
TILE_SIZE_XYZ = 256
TILE_SIZE_VECTOR = 512

def resolution(z, tile_size=TILE_SIZE_XYZ):
    return (2 * ORIGIN_SHIFT) / (tile_size * 2 ** z)

def mercator_to_tile(mx, my, z, tile_size=TILE_SIZE_XYZ):
    """EPSG:3857 -> tile x, y"""
    res = resolution(z, tile_size)
    px = (mx + ORIGIN_SHIFT) / res
    py = (ORIGIN_SHIFT - my) / res
    tx = int(px / tile_size)
    ty = int(py / tile_size)
    return tx, ty

def tile_bounds(tx, ty, z, tile_size=TILE_SIZE_XYZ):
    """Tile x, y, z -> EPSG:3857 bounding box (minx, miny, maxx, maxy)"""
    res = resolution(z, tile_size)
    minx = tx * tile_size * res - ORIGIN_SHIFT
    maxx = (tx + 1) * tile_size * res - ORIGIN_SHIFT
    maxy = ORIGIN_SHIFT - ty * tile_size * res
    miny = ORIGIN_SHIFT - (ty + 1) * tile_size * res
    return (minx, miny, maxx, maxy)

def is_valid_tile(tx, ty, z):
    """Check if the specified tile coordinates are within valid Web Mercator range"""
    # Valid tile range at zoom level z is 0 <= x,y < 2^z
    max_tile = 2 ** z
    return 0 <= tx < max_tile and 0 <= ty < max_tile

def get_canvas_zoom(iface, tile_size=TILE_SIZE_XYZ) -> int:
    """Estimate Web Mercator z from canvas display state"""
    canvas = iface.mapCanvas()
    
    # More accurate method: Use QGIS scale and DPI
    scale = canvas.scale()
    
    # Get DPI (use logical DPI - always 96 even on HiDPI displays)
    # QGIS tile rendering is based on logical DPI, so use logical DPI not physical DPI
    try:
        dpi = iface.mainWindow().logicalDpiX()
    except:
        dpi = 96  # Fallback value
    
    # Calculate meters/pixel
    # 1 meter = 39.37 inches, 1 inch = dpi pixels
    meters_per_pixel = scale / (39.37 * dpi)
    
    # Calculate zoom level (Web Mercator tile method)
    z_float = math.log2((2 * ORIGIN_SHIFT) / (tile_size * meters_per_pixel))
    z_int = int(round(z_float))
    
    return z_int


class TileBoundaryLayerManager(QObject):
    """Manager that automatically updates tile boundary layer according to map changes"""
    
    def __init__(self, iface, zoom_setting=None, is_vector_tile=False):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.current_layer = None
        self.zoom_setting = zoom_setting  # Auto-estimate if None
        self.is_vector_tile = is_vector_tile  # Whether in vector tile mode
        self.tile_size = TILE_SIZE_VECTOR if is_vector_tile else TILE_SIZE_XYZ
        
        # Connect to map change events
        self.canvas.extentsChanged.connect(self.update_tile_layer)
        self.canvas.scaleChanged.connect(self.update_tile_layer)
        
        # Initial creation
        self.update_tile_layer()
        
    def disconnect_signals(self):
        """Disconnect signals (for cleanup when plugin unloads)"""
        try:
            self.canvas.extentsChanged.disconnect(self.update_tile_layer)
            self.canvas.scaleChanged.disconnect(self.update_tile_layer)
        except:
            pass
    
    def remove_current_layer(self):
        """Remove current tile boundary layer"""
        if self.current_layer is not None:
            try:
                # Safely check if layer is still valid
                if self.current_layer.isValid():
                    QgsProject.instance().removeMapLayer(self.current_layer)
            except RuntimeError:
                # C++ object already deleted
                pass
            finally:
                self.current_layer = None
    
    def _calculate_font_size(self, zoom_level):
        """Calculate font size according to zoom level"""
        # Base font size (at zoom level 10)
        base_font_size = 8
        base_zoom = 10
        
        # Smaller font as zoom level increases, larger as it decreases
        # Approximately 20% size change per zoom level difference
        size_factor = 0.8 ** (zoom_level - base_zoom)
        calculated_size = base_font_size * size_factor
        
        # Limit to minimum 4pt, maximum 16pt
        font_size = max(4, min(16, int(calculated_size)))
        
        return font_size
    
    def create_tile_layer(self, zoom_level):
        """Create tile boundary layer at specified zoom level"""
        # ==== Get display extent ==== #
        extent = self.canvas.extent()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        epsg3857 = QgsCoordinateReferenceSystem("EPSG:3857")

        # ---- Transform canvas extent to EPSG:3857 ----
        if canvas_crs != epsg3857:
            xfm = QgsCoordinateTransform(canvas_crs, epsg3857, QgsProject.instance())
            ext = xfm.transformBoundingBox(extent)
        else:
            ext = extent

        minx, maxx = ext.xMinimum(), ext.xMaximum()
        miny, maxy = ext.yMinimum(), ext.yMaximum()

        # ---- Tile range covering the display extent ----
        min_tx, max_ty = mercator_to_tile(minx, miny, zoom_level, self.tile_size)
        max_tx, min_ty = mercator_to_tile(maxx, maxy, zoom_level, self.tile_size)
        tx0, tx1 = sorted([min_tx, max_tx])
        ty0, ty1 = sorted([min_ty, max_ty])

        # ==== Create layer ==== #
        layer_name = f"tile_boundary"
        vl = QgsVectorLayer("Polygon?crs=EPSG:3857", layer_name, "memory")
        pr = vl.dataProvider()

        pr.addAttributes([
            QgsField("z", QVariant.Int),
            QgsField("x", QVariant.Int),
            QgsField("y", QVariant.Int),
        ])
        vl.updateFields()

        # ==== Generate tile boundary polygons ==== #
        features = []
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                # Generate only tiles within valid Web Mercator range
                if not is_valid_tile(tx, ty, zoom_level):
                    continue
                    
                minx, miny, maxx, maxy = tile_bounds(tx, ty, zoom_level, self.tile_size)
                pts = [
                    QgsPointXY(minx, miny),
                    QgsPointXY(maxx, miny),
                    QgsPointXY(maxx, maxy),
                    QgsPointXY(minx, maxy),
                    QgsPointXY(minx, miny),
                ]
                feat = QgsFeature(vl.fields())
                feat.setGeometry(QgsGeometry.fromPolygonXY([pts]))
                feat["z"] = zoom_level
                feat["x"] = tx
                feat["y"] = ty
                features.append(feat)

        pr.addFeatures(features)
        vl.updateExtents()

        # Style settings
        symbol = QgsFillSymbol.createSimple({
            'style': 'no',                  # No fill
            'outline_color': '255,0,0',       # Line color (red)
            'outline_width': '0.3',         # Line width (mm)
        })
        vl.setRenderer(QgsSingleSymbolRenderer(symbol))

        # ---- Label settings: display (z/ x/ y) at center ----
        pal = QgsPalLayerSettings()
        pal.enabled = True

        pal.fieldName = 'concat("z", \'/ \', "x", \'/ \', "y")'
        pal.isExpression = True
        pal.centroidInside = True
        pal.dist = 0

        # Adjust font size according to zoom level
        # Smaller as zoom level increases
        font_size = self._calculate_font_size(zoom_level)
        
        text_format = QgsTextFormat()
        font = QFont()
        font.setPointSize(font_size)
        text_format.setFont(font)
        text_format.setColor(QColor(0, 0, 0))
        buffer = text_format.buffer()
        buffer.setEnabled(True)
        buffer.setSize(1)  # Size (px or mm conversion)
        buffer.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer)
        pal.setFormat(text_format)

        labeling = QgsVectorLayerSimpleLabeling(pal)
        vl.setLabeling(labeling)
        vl.setLabelsEnabled(True)

        return vl
    
    def update_tile_layer(self):
        """Update tile boundary layer according to map changes"""
        # Get current zoom level
        if self.zoom_setting is None:
            current_zoom = get_canvas_zoom(self.iface, self.tile_size)
        else:
            current_zoom = self.zoom_setting
        
        # Remove existing layer
        self.remove_current_layer()
        
        # Create new layer
        self.current_layer = self.create_tile_layer(current_zoom)
        
        # Add to project
        QgsProject.instance().addMapLayer(self.current_layer)