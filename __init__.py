def classFactory(iface):
    from .tile_boundary_layer_plugin import TileBoundaryLayerPlugin
    return TileBoundaryLayerPlugin(iface)
