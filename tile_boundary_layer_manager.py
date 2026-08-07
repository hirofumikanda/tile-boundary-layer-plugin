import math

from qgis.PyQt.QtCore import QVariant, QObject, QTimer
from qgis.PyQt.QtGui import QColor, QFont

from qgis.core import (
    Qgis,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
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
MIN_ZOOM = 0
MAX_ZOOM = 30
MAX_TILE_COUNT = 1000
UPDATE_DEBOUNCE_MS = 120
DEFAULT_GRID_COLOR_MODE = "red"
GRID_COLOR_VALUES = {
    "red": "#ff0000",
    "black": "#000000",
    "white": "#ffffff",
}


def normalize_grid_color_mode(mode):
    normalized = str(mode or "").strip().lower()
    if normalized not in GRID_COLOR_VALUES:
        return DEFAULT_GRID_COLOR_MODE
    return normalized


def resolution(z, tile_size=TILE_SIZE_XYZ):
    return (2 * ORIGIN_SHIFT) / (tile_size * 2 ** z)


def mercator_to_tile(mx, my, z, tile_size=TILE_SIZE_XYZ):
    """EPSG:3857 -> tile x, y."""
    res = resolution(z, tile_size)
    px = (mx + ORIGIN_SHIFT) / res
    py = (ORIGIN_SHIFT - my) / res
    # floor is important for coordinates just outside the Web Mercator world.
    tx = math.floor(px / tile_size)
    ty = math.floor(py / tile_size)
    return tx, ty


def tile_bounds(tx, ty, z, tile_size=TILE_SIZE_XYZ):
    """Tile x, y, z -> EPSG:3857 bounding box."""
    res = resolution(z, tile_size)
    minx = tx * tile_size * res - ORIGIN_SHIFT
    maxx = (tx + 1) * tile_size * res - ORIGIN_SHIFT
    maxy = ORIGIN_SHIFT - ty * tile_size * res
    miny = ORIGIN_SHIFT - (ty + 1) * tile_size * res
    return minx, miny, maxx, maxy


def is_valid_tile(tx, ty, z):
    """Check whether tile coordinates are in the Web Mercator tile matrix."""
    max_tile = 2 ** z
    return 0 <= tx < max_tile and 0 <= ty < max_tile


def get_canvas_zoom(iface, tile_size=TILE_SIZE_XYZ) -> int:
    """Estimate and validate a Web Mercator zoom from the canvas state."""
    canvas = iface.mapCanvas()
    scale = float(canvas.scale())
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Canvas scale must be a positive finite number")

    try:
        dpi = float(iface.mainWindow().logicalDpiX())
    except (AttributeError, TypeError, ValueError):
        dpi = 96.0
    if not math.isfinite(dpi) or dpi <= 0:
        dpi = 96.0

    meters_per_pixel = scale / (39.37 * dpi)
    if not math.isfinite(meters_per_pixel) or meters_per_pixel <= 0:
        raise ValueError("Canvas resolution must be a positive finite number")

    z_float = math.log2(
        (2 * ORIGIN_SHIFT) / (tile_size * meters_per_pixel)
    )
    if not math.isfinite(z_float):
        raise ValueError("Calculated zoom must be finite")

    return max(MIN_ZOOM, min(MAX_ZOOM, int(round(z_float))))


class TileBoundaryLayerManager(QObject):
    """Maintain a debounced, persistent tile boundary memory layer."""

    def __init__(
        self,
        iface,
        zoom_setting=None,
        is_vector_tile=False,
        grid_color_mode=DEFAULT_GRID_COLOR_MODE,
    ):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.current_layer = None
        self.zoom_setting = zoom_setting
        self.is_vector_tile = is_vector_tile
        self.tile_size = TILE_SIZE_VECTOR if is_vector_tile else TILE_SIZE_XYZ
        self.grid_color_mode = normalize_grid_color_mode(grid_color_mode)

        self._last_tile_key = None
        self._last_label_zoom = None
        self._limit_warning_shown = False
        self._invalid_state_reported = False
        self._disposed = False
        self._layer_tree_root = None
        self._layer_node = None
        self._layer_tree_signals_connected = False
        self._positioning_layer = False

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(UPDATE_DEBOUNCE_MS)
        self._update_timer.timeout.connect(self.update_tile_layer)

        # The layer is registered exactly once for each activation cycle.
        self.current_layer = self._create_tile_layer()
        self._register_hidden_top_layer()

        # Populate immediately, then debounce subsequent canvas events.
        self.update_tile_layer()
        self.canvas.extentsChanged.connect(self.schedule_update)
        self.canvas.scaleChanged.connect(self.schedule_update)

    def schedule_update(self, *_args):
        """Coalesce rapid canvas events into one update."""
        if not self._disposed:
            self._update_timer.start()

    def disconnect_signals(self):
        """Stop pending work and disconnect canvas signals."""
        self._disposed = True
        self._update_timer.stop()

        try:
            self.canvas.extentsChanged.disconnect(self.schedule_update)
        except (TypeError, RuntimeError):
            pass
        try:
            self.canvas.scaleChanged.disconnect(self.schedule_update)
        except (TypeError, RuntimeError):
            pass
        self._disconnect_layer_tree_signals()

    def _register_hidden_top_layer(self):
        """Register the grid, render it first, and hide its legend row."""
        project = QgsProject.instance()
        root_getter = getattr(project, "layerTreeRoot", None)
        if not callable(root_getter):
            # Lightweight fallback for standalone/test environments.
            project.addMapLayer(self.current_layer)
            return

        self._layer_tree_root = root_getter()
        project.addMapLayer(self.current_layer, False)
        self._layer_node = self._layer_tree_root.insertLayer(
            0, self.current_layer
        )
        self._layer_node.setCustomProperty(
            "tile_boundary_layer/internal", True
        )
        self._layer_node.setItemVisibilityChecked(True)

        try:
            self._layer_tree_root.addedChildren.connect(
                self._schedule_layer_tree_sync
            )
            self._layer_tree_root.customLayerOrderChanged.connect(
                self._schedule_layer_tree_sync
            )
            self._layer_tree_signals_connected = True
        except (AttributeError, TypeError, RuntimeError):
            self._layer_tree_signals_connected = False

        self._ensure_hidden_layer_on_top()

    def _disconnect_layer_tree_signals(self):
        if not self._layer_tree_signals_connected:
            return

        self._layer_tree_signals_connected = False
        try:
            self._layer_tree_root.addedChildren.disconnect(
                self._schedule_layer_tree_sync
            )
        except (AttributeError, TypeError, RuntimeError):
            pass
        try:
            self._layer_tree_root.customLayerOrderChanged.disconnect(
                self._schedule_layer_tree_sync
            )
        except (AttributeError, TypeError, RuntimeError):
            pass

    def _schedule_layer_tree_sync(self, *_args):
        if self._disposed or self._positioning_layer:
            return
        QTimer.singleShot(0, self._ensure_hidden_layer_on_top)

    def _set_layer_node_hidden(self, hidden, node=None):
        node = node or self._layer_node
        if node is None:
            return

        view_getter = getattr(self.iface, "layerTreeView", None)
        if not callable(view_getter):
            return

        try:
            view = view_getter()
            model = view.layerTreeModel()
            index = model.node2index(node)
            if index.isValid():
                view.setRowHidden(index.row(), index.parent(), hidden)
        except (AttributeError, RuntimeError):
            pass

    def _ensure_hidden_layer_on_top(self):
        """Keep the hidden grid first in tree and custom render order."""
        if (
            self._disposed
            or self._positioning_layer
            or self.current_layer is None
            or self._layer_tree_root is None
        ):
            return

        self._positioning_layer = True
        try:
            layer_id = self.current_layer.id()
            node = self._layer_tree_root.findLayer(layer_id)
            if node is None:
                return

            root_children = list(self._layer_tree_root.children())
            node_is_first = (
                node.parent() == self._layer_tree_root
                and root_children
                and root_children[0] == node
            )
            if not node_is_first:
                self._set_layer_node_hidden(False, node)
                new_node = node.clone()
                self._layer_tree_root.insertChildNode(0, new_node)
                node.parent().removeChildNode(node)
                node = new_node

            node.setItemVisibilityChecked(True)
            node.setCustomProperty("tile_boundary_layer/internal", True)
            self._layer_node = node

            if self._layer_tree_root.hasCustomLayerOrder():
                custom_order = list(
                    self._layer_tree_root.customLayerOrder()
                )
                if not custom_order:
                    custom_order = list(self._layer_tree_root.layerOrder())
                custom_order = [
                    layer
                    for layer in custom_order
                    if layer.id() != layer_id
                ]
                custom_order.insert(0, self.current_layer)
                self._layer_tree_root.setCustomLayerOrder(custom_order)

            self._set_layer_node_hidden(True, node)
        except RuntimeError:
            pass
        finally:
            self._positioning_layer = False

    def remove_current_layer(self):
        """Remove the persistent layer once during plugin cleanup."""
        layer = self.current_layer
        self.current_layer = None
        self._last_tile_key = None
        if layer is None:
            return

        self._disconnect_layer_tree_signals()
        self._set_layer_node_hidden(False)
        self._layer_node = None
        self._layer_tree_root = None

        try:
            layer_id = layer.id()
            if QgsProject.instance().mapLayer(layer_id) is not None:
                QgsProject.instance().removeMapLayer(layer_id)
        except RuntimeError:
            # The project may already own and have deleted the C++ object.
            pass
        finally:
            # Removing a layer invalidates the project state, but some QGIS
            # versions keep the previous rendered frame until another canvas
            # event occurs. Force a new render so the grid disappears now.
            try:
                self.canvas.refresh()
            except RuntimeError:
                pass

    def _calculate_font_size(self, zoom_level):
        """Calculate font size according to zoom level."""
        base_font_size = 8
        base_zoom = 10
        size_factor = 0.8 ** (zoom_level - base_zoom)
        calculated_size = base_font_size * size_factor
        return max(4, min(16, int(calculated_size)))

    def _create_tile_layer(self):
        """Create and configure the persistent empty memory layer."""
        layer = QgsVectorLayer(
            "Polygon?crs=EPSG:3857", "tile_boundary", "memory"
        )
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("z", QVariant.Int),
            QgsField("x", QVariant.Int),
            QgsField("y", QVariant.Int),
        ])
        layer.updateFields()

        self._set_grid_renderer(layer, self.grid_color_mode)
        self._set_labeling(layer, 10)
        return layer

    def _set_grid_renderer(self, layer, mode):
        mode = normalize_grid_color_mode(mode)
        symbol = QgsFillSymbol.createSimple(
            {
                "style": "no",
                "outline_color": GRID_COLOR_VALUES[mode],
                "outline_width": "0.3",
            }
        )
        renderer = QgsSingleSymbolRenderer(symbol)
        renderer.setPaintEffect(None)

        layer.setRenderer(renderer)

    def set_grid_color_mode(self, mode):
        """Change line color/blending without rebuilding tile features."""
        normalized = normalize_grid_color_mode(mode)
        if normalized == self.grid_color_mode:
            return

        self.grid_color_mode = normalized
        if self.current_layer is None:
            return

        self._set_grid_renderer(self.current_layer, normalized)
        self.current_layer.triggerRepaint()
        try:
            self.canvas.refresh()
        except RuntimeError:
            pass

    def _set_labeling(self, layer, zoom_level):
        """Configure labels, updating them only when tile zoom changes."""
        pal = QgsPalLayerSettings()
        pal.enabled = True
        pal.fieldName = 'concat("z", \'/ \', "x", \'/ \', "y")'
        pal.isExpression = True
        pal.centroidInside = True
        pal.dist = 0

        text_format = QgsTextFormat()
        font = QFont()
        font.setPointSize(self._calculate_font_size(zoom_level))
        text_format.setFont(font)
        text_format.setColor(QColor(0, 0, 0))
        buffer = text_format.buffer()
        buffer.setEnabled(True)
        buffer.setSize(1)
        buffer.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer)
        pal.setFormat(text_format)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
        self._last_label_zoom = zoom_level

    def _current_zoom(self):
        if self.zoom_setting is None:
            return get_canvas_zoom(self.iface, self.tile_size)

        zoom = int(self.zoom_setting)
        return max(MIN_ZOOM, min(MAX_ZOOM, zoom))

    def _calculate_tile_range(self, zoom_level):
        """Return a clipped visible tile range, or None outside EPSG:3857."""
        extent = self.canvas.extent()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        epsg3857 = QgsCoordinateReferenceSystem("EPSG:3857")

        if canvas_crs != epsg3857:
            transform = QgsCoordinateTransform(
                canvas_crs, epsg3857, QgsProject.instance()
            )
            extent = transform.transformBoundingBox(extent)

        coordinates = (
            float(extent.xMinimum()),
            float(extent.yMinimum()),
            float(extent.xMaximum()),
            float(extent.yMaximum()),
        )
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("Transformed canvas extent must be finite")

        minx = max(coordinates[0], -ORIGIN_SHIFT)
        miny = max(coordinates[1], -ORIGIN_SHIFT)
        maxx = min(coordinates[2], ORIGIN_SHIFT)
        maxy = min(coordinates[3], ORIGIN_SHIFT)
        if minx > maxx or miny > maxy:
            return None

        min_tx, max_ty = mercator_to_tile(
            minx, miny, zoom_level, self.tile_size
        )
        max_tx, min_ty = mercator_to_tile(
            maxx, maxy, zoom_level, self.tile_size
        )
        tx0, tx1 = sorted((min_tx, max_tx))
        ty0, ty1 = sorted((min_ty, max_ty))

        max_tile_index = (2 ** zoom_level) - 1
        tx0 = max(0, min(tx0, max_tile_index))
        tx1 = max(0, min(tx1, max_tile_index))
        ty0 = max(0, min(ty0, max_tile_index))
        ty1 = max(0, min(ty1, max_tile_index))
        return tx0, tx1, ty0, ty1

    def _build_features(self, zoom_level, tile_range):
        """Build at most MAX_TILE_COUNT features for an already-clipped range."""
        tx0, tx1, ty0, ty1 = tile_range
        fields = self.current_layer.fields()
        features = []

        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                minx, miny, maxx, maxy = tile_bounds(
                    tx, ty, zoom_level, self.tile_size
                )
                points = [
                    QgsPointXY(minx, miny),
                    QgsPointXY(maxx, miny),
                    QgsPointXY(maxx, maxy),
                    QgsPointXY(minx, maxy),
                    QgsPointXY(minx, miny),
                ]
                feature = QgsFeature(fields)
                feature.setGeometry(QgsGeometry.fromPolygonXY([points]))
                feature["z"] = zoom_level
                feature["x"] = tx
                feature["y"] = ty
                features.append(feature)

        return features

    def _replace_features(self, features):
        """Bulk-replace features without replacing the registered layer."""
        if self.current_layer is None:
            return

        provider = self.current_layer.dataProvider()
        existing_ids = self.current_layer.allFeatureIds()
        if existing_ids:
            provider.deleteFeatures(existing_ids)
        if features:
            provider.addFeatures(features)
        self.current_layer.updateExtents()
        self.current_layer.triggerRepaint()

    def _show_tile_limit_warning(self, tile_count):
        if self._limit_warning_shown:
            return

        self._limit_warning_shown = True
        self.iface.messageBar().pushMessage(
            "Tile Boundary Layer",
            (
                f"Grid hidden: visible extent covers {tile_count} tiles "
                f"(limit: {MAX_TILE_COUNT})."
            ),
            level=Qgis.MessageLevel.Warning,
            duration=6,
        )

    def _handle_invalid_state(self, error):
        invalid_key = ("invalid",)
        if self._last_tile_key != invalid_key:
            self._replace_features([])
            self._last_tile_key = invalid_key
        if not self._invalid_state_reported:
            self._invalid_state_reported = True
            print(f"Tile Boundary Layer update skipped: {error}")

    def update_tile_layer(self):
        """Refresh features only when the visible tile set changes."""
        if self._disposed or self.current_layer is None:
            return

        try:
            current_zoom = self._current_zoom()
            tile_range = self._calculate_tile_range(current_zoom)
        except (
            ArithmeticError,
            QgsCsException,
            TypeError,
            ValueError,
            RuntimeError,
        ) as error:
            self._handle_invalid_state(error)
            return

        self._invalid_state_reported = False
        if tile_range is None:
            tile_key = (current_zoom, "empty")
            if tile_key != self._last_tile_key:
                self._replace_features([])
                self._last_tile_key = tile_key
            return

        tile_key = (current_zoom,) + tile_range
        if tile_key == self._last_tile_key:
            return

        tx0, tx1, ty0, ty1 = tile_range
        tile_count = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
        if tile_count > MAX_TILE_COUNT:
            self._replace_features([])
            self._last_tile_key = tile_key
            self._show_tile_limit_warning(tile_count)
            return

        if self._last_label_zoom != current_zoom:
            self._set_labeling(self.current_layer, current_zoom)

        features = self._build_features(current_zoom, tile_range)
        self._replace_features(features)
        self._last_tile_key = tile_key
