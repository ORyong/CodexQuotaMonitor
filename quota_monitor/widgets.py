from __future__ import annotations
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor,QIntValidator
from PySide6.QtWidgets import (QAbstractSpinBox,QComboBox,QDialog,QFrame,QGridLayout,
 QHBoxLayout,QLabel,QLineEdit,QListView,QPushButton,QSlider,QSpinBox,QVBoxLayout)


def component_style(assets, family="Noto Sans SC"):
    sheet="""
    QWidget { font-family: '@FAMILY@'; font-size: 12px; color: #3E4753; }
    QDialog { background: #F5F6F8; }
    QToolTip { background: #FFFFFF; color: #43516A; border: 1px solid #DDE4EE; padding: 6px 9px; border-radius: 6px; }
    QFrame#stepper { background: #FAFBFD; border: 1px solid #DDE4EE; border-radius: 8px; }
    QFrame#stepper:hover { border-color: #BDCBDD; }
    QSpinBox#spinEditor { border: 0; background: transparent; padding: 0; min-height: 24px; selection-background-color: #DEE8F5; color: #435773; }
    QPushButton#stepButton { border: 0; background: transparent; color: #677C98; border-radius: 5px; font-size: 17px; font-weight: 500; padding: 0; }
    QPushButton#stepButton:hover { background: #E9EFF7; color: #344F73; }
    QPushButton#stepButton:pressed { background: #DCE6F3; }
    QPushButton#stepButton:disabled { color: #C6CFDB; }
    QComboBox { background: #FAFBFD; border: 1px solid #DDE4EE; border-radius: 8px; padding: 5px 27px 5px 9px; min-height: 20px; }
    QComboBox:hover { border-color: #BDCBDD; }
    QComboBox:focus { border-color: #7C98BF; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 26px; border: 0; background: transparent; }
    QComboBox::down-arrow { image: url('@DOWN@'); width: 14px; height: 14px; }
    QComboBox QAbstractItemView { background: white; border: 1px solid #DDE4EE; outline: 0; padding: 5px; selection-background-color: #EAF0F8; selection-color: #344F73; }
    QListView::item { padding: 7px 9px; border-radius: 5px; min-height: 18px; }
    QListView::item:hover { background: #F0F4FA; }
    QCheckBox { spacing: 7px; }
    QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #C6D1E0; border-radius: 4px; background: white; }
    QCheckBox::indicator:hover { border-color: #7E98BB; }
    QCheckBox::indicator:checked { background: #526D92; border-color: #526D92; image: url('@CHECK@'); }
    QMenu { background: #FFFFFF; color: #43516A; border: 1px solid #DDE4EE; border-radius: 9px; padding: 5px; }
    QMenu::item { padding: 7px 22px 7px 12px; border-radius: 5px; }
    QMenu::item:selected { background: #EAF0F8; color: #344F73; }
    QMenu::item:disabled { color: #ADB7C4; }
    QMenu::separator { height: 1px; background: #E9EDF3; margin: 5px 8px; }
    QMenu::indicator { width: 15px; height: 15px; }
    QMenu::indicator:checked { image: url('@CHECKBLUE@'); }
    QLineEdit { background: white; border: 1px solid #DDE4EE; border-radius: 7px; padding: 6px 9px; selection-background-color: #DEE8F5; }
    QLineEdit:focus { border-color: #7C98BF; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: #C6D1E0; border-radius: 3px; min-height: 25px; }
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background: transparent; }
    QSlider::groove:horizontal { height: 4px; background: #E2E8F1; border-radius: 2px; }
    QSlider::sub-page:horizontal { background: #7791B5; border-radius: 2px; }
    QSlider::handle:horizontal { background: #526D92; border: 2px solid white; width: 12px; margin: -6px 0; border-radius: 8px; }
    QPushButton#saveButton { background: #4C6382; color: white; border: 0; border-radius: 7px; padding: 7px 20px; font-weight: 600; }
    QPushButton#saveButton:hover { background: #3D5371; }
    QPushButton#saveButton:disabled { background: #ABB9CB; }
    QPushButton#cancelButton { background: transparent; color: #67727F; border: 1px solid #D7DFEC; border-radius: 7px; padding: 7px 16px; }
    QPushButton#cancelButton:hover { background: #E8EDF5; }
    """
    return sheet.replace('@FAMILY@', family).replace('@DOWN@',(assets/'chevron-down.svg').as_posix()).replace('@CHECK@',(assets/'check-white.svg').as_posix()).replace('@CHECKBLUE@',(assets/'check-blue.svg').as_posix())


class Stepper(QFrame):
    valueChanged=Signal(int)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('stepper')
        self.setFixedHeight(32)
        layout=QHBoxLayout(self);layout.setContentsMargins(3,2,3,2);layout.setSpacing(0)
        self.minus=QPushButton('−');self.minus.setObjectName('stepButton');self.minus.setFixedSize(24,26)
        self.minus.setToolTip('减小');self.minus.setAccessibleName('减小')
        self.editor=QSpinBox();self.editor.setObjectName('spinEditor')
        self.editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.editor.setMinimumWidth(48)
        self.plus=QPushButton('+');self.plus.setObjectName('stepButton');self.plus.setFixedSize(24,26)
        self.plus.setToolTip('增加');self.plus.setAccessibleName('增加')
        for button in (self.minus,self.plus):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAutoDefault(False)
        layout.addWidget(self.minus);layout.addWidget(self.editor,1);layout.addWidget(self.plus)
        self.minus.clicked.connect(self.editor.stepDown);self.plus.clicked.connect(self.editor.stepUp)
        self.editor.valueChanged.connect(self.changed)
    def changed(self,value):
        self.minus.setEnabled(value>self.editor.minimum());self.plus.setEnabled(value<self.editor.maximum())
        self.valueChanged.emit(value)
    def setRange(self,a,b):self.editor.setRange(a,b);self.changed(self.value())
    def setValue(self,value):self.editor.setValue(value);self.changed(self.value())
    def value(self):return self.editor.value()
    def setSuffix(self,value):self.editor.setSuffix(value)
    def setSingleStep(self,value):self.editor.setSingleStep(value)


class ModernComboBox(QComboBox):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ColorPicker(QDialog):
    def __init__(self,color,parent=None,title='选择颜色'):
        super().__init__(parent);self.setWindowTitle(title);self.setFixedWidth(312)
        self.color=QColor(color);self.syncing=False
        root=QVBoxLayout(self);root.setContentsMargins(20,18,20,18);root.setSpacing(14)
        heading=QLabel(title);heading.setStyleSheet('font-size:16px;font-weight:600;color:#34445D;');root.addWidget(heading)
        self.preview=QLabel();self.preview.setFixedHeight(52);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);root.addWidget(self.preview)
        colors=['#485F87','#252932','#24594E','#665078','#E6ECF5','#FFFFFF','#E9EDF7','#405779']
        swatches=QHBoxLayout();swatches.setSpacing(6)
        for color in colors:
            button=QPushButton();button.setFixedSize(27,27);button.setToolTip(color)
            button.setStyleSheet(f'background:{color};border:1px solid #D7DFEA;border-radius:7px;')
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False,c=color:self.set_color(QColor(c)))
            swatches.addWidget(button)
        root.addLayout(swatches)
        self.sliders=[];self.values=[]
        for name in ('R','G','B'):
            row=QHBoxLayout();row.setSpacing(10);label=QLabel(name);label.setFixedWidth(14);row.addWidget(label)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,255);slider.valueChanged.connect(self.slider_changed)
            value=QLabel();value.setFixedWidth(26);value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            self.sliders.append(slider);self.values.append(value);row.addWidget(slider,1);row.addWidget(value);root.addLayout(row)
        self.hex=QLineEdit();self.hex.setPlaceholderText('#485F87');self.hex.textChanged.connect(self.hex_changed)
        root.addWidget(self.hex)
        footer=QHBoxLayout();footer.addStretch()
        cancel=QPushButton('取消');cancel.setObjectName('cancelButton');cancel.clicked.connect(self.reject)
        self.apply=QPushButton('应用');self.apply.setObjectName('saveButton');self.apply.clicked.connect(self.accept)
        footer.addWidget(cancel);footer.addWidget(self.apply);root.addLayout(footer)
        self.set_color(self.color)
    def set_color(self,color):
        self.syncing=True;self.color=QColor(color)
        for slider,value,channel in zip(self.sliders,self.values,(color.red(),color.green(),color.blue())):
            slider.setValue(channel);value.setText(str(channel))
        self.hex.setText(color.name().upper())
        text='#28384F' if color.lightness()>155 else '#FFFFFF'
        self.preview.setText(color.name().upper());self.preview.setStyleSheet(f'background:{color.name()};color:{text};border:1px solid #DDE4EE;border-radius:9px;font-size:15px;')
        self.apply.setEnabled(True);self.syncing=False
    def slider_changed(self,*args):
        if not self.syncing:self.set_color(QColor(*(s.value() for s in self.sliders)))
    def hex_changed(self,text):
        if self.syncing:return
        if len(text)==7 and text.startswith('#') and QColor(text).isValid():self.set_color(QColor(text))
        else:self.apply.setEnabled(False)
