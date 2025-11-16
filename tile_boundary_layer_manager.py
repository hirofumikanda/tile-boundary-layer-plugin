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
TILE_SIZE = 256

def resolution(z):
    return (2 * ORIGIN_SHIFT) / (TILE_SIZE * 2 ** z)

def mercator_to_tile(mx, my, z):
    """EPSG:3857 -> タイル x, y"""
    res = resolution(z)
    px = (mx + ORIGIN_SHIFT) / res
    py = (ORIGIN_SHIFT - my) / res
    tx = int(px / TILE_SIZE)
    ty = int(py / TILE_SIZE)
    return tx, ty

def tile_bounds(tx, ty, z):
    """タイル x, y, z -> EPSG:3857 のバウンディングボックス (minx, miny, maxx, maxy)"""
    res = resolution(z)
    minx = tx * TILE_SIZE * res - ORIGIN_SHIFT
    maxx = (tx + 1) * TILE_SIZE * res - ORIGIN_SHIFT
    maxy = ORIGIN_SHIFT - ty * TILE_SIZE * res
    miny = ORIGIN_SHIFT - (ty + 1) * TILE_SIZE * res
    return (minx, miny, maxx, maxy)

def get_canvas_zoom(iface) -> int:
    """キャンバスの表示状態から Webメルカトルの z を推定"""
    canvas = iface.mapCanvas()
    
    # より正確な方法：QGISのスケールとDPIを使用
    scale = canvas.scale()
    
    # DPIを取得（通常は96だが、実際の値を使用）
    try:
        dpi = iface.mainWindow().physicalDpiX()
    except:
        dpi = 96  # フォールバック値
    
    # メートル/ピクセルを計算
    # 1インチ = 39.37メートル、1インチ = dpi ピクセル
    meters_per_pixel = scale / (39.37 * dpi)
    
    # ズームレベルを計算（Web Mercatorタイル方式）
    z_float = math.log2((2 * ORIGIN_SHIFT) / (TILE_SIZE * meters_per_pixel))
    z_int = int(round(z_float))
    
    return z_int


class TileBoundaryLayerManager(QObject):
    """地図の変更に応じてタイル境界レイヤを自動更新するマネージャー"""
    
    def __init__(self, iface, zoom_setting=None):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.current_layer = None
        self.zoom_setting = zoom_setting  # None の場合自動推定
        
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
        min_tx, max_ty = mercator_to_tile(minx, miny, zoom_level)
        max_tx, min_ty = mercator_to_tile(maxx, maxy, zoom_level)
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
                minx, miny, maxx, maxy = tile_bounds(tx, ty, zoom_level)
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

        text_format = QgsTextFormat()
        font = QFont()
        font.setPointSize(8)
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
            current_zoom = get_canvas_zoom(self.iface)
        else:
            current_zoom = self.zoom_setting
        
        # 既存のレイヤを削除
        self.remove_current_layer()
        
        # 新しいレイヤを作成
        self.current_layer = self.create_tile_layer(current_zoom)
        
        # プロジェクトに追加
        QgsProject.instance().addMapLayer(self.current_layer)