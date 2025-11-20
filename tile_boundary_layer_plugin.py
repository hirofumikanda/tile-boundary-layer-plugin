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
        
        # プラグイン用のアクション
        self.actions = []
        self.menu = '&Tile Boundary Layer'
    
    def tr(self, message):
        """翻訳用メソッド"""
        return QCoreApplication.translate('TileBoundaryLayerPlugin', message)
    
    def initGui(self):
        """プラグインのGUI初期化"""
        # アイコンパス
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        
        # タイル境界レイヤ表示の切り替えアクション
        self.toggle_action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            self.tr('タイル境界レイヤ表示切り替え'),
            self.iface.mainWindow()
        )
        self.toggle_action.triggered.connect(self.toggle_tile_layer)
        self.toggle_action.setCheckable(True)
        self.toggle_action.setStatusTip(self.tr('タイル境界レイヤの表示を切り替えます'))
        self.toggle_action.setWhatsThis(self.tr('地図上にタイル境界と座標を表示/非表示します'))
        
        # メニューとツールバーに追加
        self.iface.addToolBarIcon(self.toggle_action)
        self.iface.addPluginToMenu(self.menu, self.toggle_action)
        
        self.actions.append(self.toggle_action)
    
    def unload(self):
        """プラグインのアンロード処理"""
        # マネージャーをクリーンアップ
        if self.manager is not None:
            try:
                self.manager.disconnect_signals()
                self.manager.remove_current_layer()
            except Exception as e:
                print(f"マネージャークリーンアップエラー: {e}")
            finally:
                self.manager = None
        
        # GUI要素を削除
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        
        self.actions = []
    
    def toggle_tile_layer(self):
        """タイル境界レイヤ表示の切り替え"""
        if self.manager is None:
            # タイルタイプの選択ダイアログを表示
            msg_box = QMessageBox(self.iface.mainWindow())
            msg_box.setWindowTitle('タイルタイプの選択')
            msg_box.setText('使用するタイルタイプを選択してください')
            msg_box.setIcon(QMessageBox.Question)
            
            xyz_button = msg_box.addButton('XYZタイル (256px)', QMessageBox.AcceptRole)
            vector_button = msg_box.addButton('ベクタタイル (512px)', QMessageBox.AcceptRole)
            cancel_button = msg_box.addButton('キャンセル', QMessageBox.RejectRole)
            msg_box.setDefaultButton(xyz_button)
            
            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == cancel_button:
                # キャンセルされた場合はチェックを外して終了
                self.toggle_action.setChecked(False)
                return
            
            is_vector_tile = (clicked_button == vector_button)
            tile_type_name = 'ベクタタイル (512px)' if is_vector_tile else 'XYZタイル (256px)'
            
            # マネージャーを作成して表示開始
            self.manager = TileBoundaryLayerManager(self.iface, is_vector_tile=is_vector_tile)
            self.toggle_action.setChecked(True)
            self.iface.messageBar().pushMessage(
                'Tile Boundary Layer',
                f'タイル境界レイヤの表示を開始しました ({tile_type_name})',
                level=0,  # INFO level
                duration=3
            )
        else:
            # マネージャーを削除して表示停止
            try:
                self.manager.disconnect_signals()
                self.manager.remove_current_layer()
            except Exception as e:
                print(f"マネージャー停止エラー: {e}")
            finally:
                self.manager = None
                self.toggle_action.setChecked(False)
            self.iface.messageBar().pushMessage(
                'Tile Boundary Layer',
                'タイル境界レイヤの表示を停止しました',
                level=0,  # INFO level
                duration=3
            )