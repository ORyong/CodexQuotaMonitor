"""Bundled font choices; registering fonts never installs them in Windows."""
from __future__ import annotations

FONT_OPTIONS = {
    'noto': ('默认 · Noto', 'NotoSansSC-VF.ttf'),
    'source_han_sans': ('思源黑体', 'SourceHanSansCN-Regular.otf'),
    'source_han_serif': ('思源宋体', 'SourceHanSerifCN-Regular.otf'),
    'lxgw_wenkai': ('霞鹜文楷', 'LXGWWenKai-Regular.ttf'),
    'smiley_sans': ('得意黑', 'SmileySans-Oblique.ttf'),
    'zcool_kuaile': ('站酷快乐体', 'ZCOOLKuaiLe-Regular.ttf'),
    'zcool_xiaowei': ('站酷小薇体', 'ZCOOLXiaoWei-Regular.ttf'),
}
FAMILIES = {}
FONT_IDS = {}


def register_fonts(directory):
    from PySide6.QtGui import QFontDatabase
    for key, (_, filename) in FONT_OPTIONS.items():
        font_id = QFontDatabase.addApplicationFont(str(directory / filename))
        FONT_IDS[key] = font_id
        families = QFontDatabase.applicationFontFamilies(font_id)
        FAMILIES[key] = families[0] if families else 'Microsoft YaHei UI'
    medium = directory / 'SourceHanSansCN-Medium.otf'
    if medium.exists():
        FONT_IDS['source_han_sans_medium'] = QFontDatabase.addApplicationFont(str(medium))
    return FONT_IDS.copy()


def family(key):
    return FAMILIES.get(key, 'Microsoft YaHei UI')


def make_font(key, pixels=12, weight=400):
    from PySide6.QtGui import QFont
    font = QFont(family(key))
    font.setPixelSize(pixels)
    font.setWeight(QFont.Weight(weight))
    if key == 'noto':
        font.setVariableAxis(QFont.Tag.fromString('wght'), weight)
    return font
