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

# Webメルカトル定義
ORIGIN_SHIFT = 20037508.342789244
TILE_SIZE_XYZ = 256
TILE_SIZE_VECTOR = 512

def resolution(z, tile_size=TILE_SIZE_XYZ):
    return (2 * ORIGIN_SHIFT) / (tile_size * 2 ** z)

def mercator_to_tile(mx, my, z, tile_size=TILE_SIZE_XYZ):
    """EPSG:3857 -> タイル x, y"""
    res = resolution(z, tile_size)
    px = (mx + ORIGIN_SHIFT) / res
    py = (ORIGIN_SHIFT - my) / res
    tx = int(px / tile_size)
    ty = int(py / tile_size)
    return tx, ty

def tile_bounds(tx, ty, z, tile_size=TILE_SIZE_XYZ):
    """タイル x, y, z -> EPSG:3857 のバウンディングボックス (minx, miny, maxx, maxy)"""
    res = resolution(z, tile_size)
    minx = tx * tile_size * res - ORIGIN_SHIFT
    maxx = (tx + 1) * tile_size * res - ORIGIN_SHIFT
    maxy = ORIGIN_SHIFT - ty * tile_size * res
    miny = ORIGIN_SHIFT - (ty + 1) * tile_size * res
    return (minx, miny, maxx, maxy)

def is_valid_tile(tx, ty, z):
    """指定されたタイル座標がWebメルカトルの有効範囲内かチェック"""
    # ズームレベルzにおける有効なタイル範囲は 0 <= x,y < 2^z
    max_tile = 2 ** z
    return 0 <= tx < max_tile and 0 <= ty < max_tile

def get_canvas_zoom(iface, tile_size=TILE_SIZE_XYZ) -> int:
    """キャンバスの表示状態から Webメルカトルの z を推定"""
    canvas = iface.mapCanvas()
    
    # より正確な方法：QGISのスケールとDPIを使用
    scale = canvas.scale()
    
    # DPIを取得（論理DPIを使用 - HiDPIディスプレイでも常に96）
    # QGISのタイルレンダリングは論理DPIを基準とするため、物理DPIではなく論理DPIを使用
    try:
        dpi = iface.mainWindow().logicalDpiX()
    except:
        dpi = 96  # フォールバック値
    
    # メートル/ピクセルを計算
    # 1メートル = 39.37インチ、1インチ = dpi ピクセル
    meters_per_pixel = scale / (39.37 * dpi)
    
    # ズームレベルを計算（Web Mercatorタイル方式）
    z_float = math.log2((2 * ORIGIN_SHIFT) / (tile_size * meters_per_pixel))
    z_int = int(round(z_float))
    
    return z_int


class TileBoundaryLayerManager(QObject):
    """地図の変更に応じてタイル境界レイヤを自動更新するマネージャー"""
    
    def __init__(self, iface, zoom_setting=None, is_vector_tile=False):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.current_layer = None
        self.zoom_setting = zoom_setting  # None の場合自動推定
        self.is_vector_tile = is_vector_tile  # ベクタタイルモードかどうか
        self.tile_size = TILE_SIZE_VECTOR if is_vector_tile else TILE_SIZE_XYZ
        
        # 地図の変更イベントに接続
        self.canvas.extentsChanged.connect(self.update_tile_layer)
        self.canvas.scaleChanged.connect(self.update_tile_layer)
        
        # 初回作成
        self.update_tile_layer()
        
    def disconnect_signals(self):
        """シグナルを切断（プラグインアンロード時のクリーンアップ用）"""
        try:
            self.canvas.extentsChanged.disconnect(self.update_tile_layer)
            self.canvas.scaleChanged.disconnect(self.update_tile_layer)
        except:
            pass
    
    def remove_current_layer(self):
        """現在のタイル境界レイヤを削除"""
        if self.current_layer is not None:
            try:
                # レイヤーがまだ有効かどうかを安全にチェック
                if self.current_layer.isValid():
                    QgsProject.instance().removeMapLayer(self.current_layer)
            except RuntimeError:
                # C++オブジェクトが既に削除されている場合
                pass
            finally:
                self.current_layer = None
    
    def _calculate_font_size(self, zoom_level):
        """ズームレベルに応じてフォントサイズを計算"""
        # ベースフォントサイズ（ズームレベル10の場合）
        base_font_size = 8
        base_zoom = 10
        
        # ズームレベルが高くなるほどフォントを小さく、低くなるほど大きく
        # ズームレベル差1につき約20%サイズ変更
        size_factor = 0.8 ** (zoom_level - base_zoom)
        calculated_size = base_font_size * size_factor
        
        # 最小サイズ4pt、最大サイズ16ptに制限
        font_size = max(4, min(16, int(calculated_size)))
        
        return font_size
    
    def create_tile_layer(self, zoom_level):
        """指定されたズームレベルでタイル境界レイヤを作成"""
        # ==== 表示範囲取得 ==== #
        extent = self.canvas.extent()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        epsg3857 = QgsCoordinateReferenceSystem("EPSG:3857")

        # ---- キャンバス範囲を EPSG:3857 に変換 ----
        if canvas_crs != epsg3857:
            xfm = QgsCoordinateTransform(canvas_crs, epsg3857, QgsProject.instance())
            ext = xfm.transformBoundingBox(extent)
        else:
            ext = extent

        minx, maxx = ext.xMinimum(), ext.xMaximum()
        miny, maxy = ext.yMinimum(), ext.yMaximum()

        # ---- 表示範囲にかかるタイル範囲 ----
        min_tx, max_ty = mercator_to_tile(minx, miny, zoom_level, self.tile_size)
        max_tx, min_ty = mercator_to_tile(maxx, maxy, zoom_level, self.tile_size)
        tx0, tx1 = sorted([min_tx, max_tx])
        ty0, ty1 = sorted([min_ty, max_ty])

        # ==== レイヤ作成 ==== #
        layer_name = f"tile_boundary"
        vl = QgsVectorLayer("Polygon?crs=EPSG:3857", layer_name, "memory")
        pr = vl.dataProvider()

        pr.addAttributes([
            QgsField("z", QVariant.Int),
            QgsField("x", QVariant.Int),
            QgsField("y", QVariant.Int),
        ])
        vl.updateFields()

        # ==== タイル境界ポリゴン生成 ==== #
        features = []
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                # Webメルカトルの有効範囲内のタイルのみ生成
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

        # スタイル設定
        symbol = QgsFillSymbol.createSimple({
            'style': 'no',                  # 塗りつぶしなし
            'outline_color': '255,0,0',       # 線色（赤）
            'outline_width': '0.3',         # 線の太さ（mm）
        })
        vl.setRenderer(QgsSingleSymbolRenderer(symbol))

        # ---- ラベル設定: (z/ x/ y) を中央に表示 ----
        pal = QgsPalLayerSettings()
        pal.enabled = True

        pal.fieldName = 'concat("z", \'/ \', "x", \'/ \', "y")'
        pal.isExpression = True
        pal.centroidInside = True
        pal.dist = 0

        # ズームレベルに応じてフォントサイズを調整
        # ズームレベルが高くなるほど小さくする
        font_size = self._calculate_font_size(zoom_level)
        
        text_format = QgsTextFormat()
        font = QFont()
        font.setPointSize(font_size)
        text_format.setFont(font)
        text_format.setColor(QColor(0, 0, 0))
        buffer = text_format.buffer()
        buffer.setEnabled(True)
        buffer.setSize(1)  # 太さ（pxまたはmm換算）
        buffer.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer)
        pal.setFormat(text_format)

        labeling = QgsVectorLayerSimpleLabeling(pal)
        vl.setLabeling(labeling)
        vl.setLabelsEnabled(True)

        return vl
    
    def update_tile_layer(self):
        """地図の変更に応じてタイル境界レイヤを更新"""
        # 現在のズームレベルを取得
        if self.zoom_setting is None:
            current_zoom = get_canvas_zoom(self.iface, self.tile_size)
        else:
            current_zoom = self.zoom_setting
        
        # 既存のレイヤを削除
        self.remove_current_layer()
        
        # 新しいレイヤを作成
        self.current_layer = self.create_tile_layer(current_zoom)
        
        # プロジェクトに追加
        QgsProject.instance().addMapLayer(self.current_layer)