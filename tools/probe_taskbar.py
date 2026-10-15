import pathlib,sys,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtCore import Qt,QTimer
from quota_monitor.taskbar import TaskbarDock
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
widget=QLabel('任务栏测试')
widget.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint)
widget.setStyleSheet('QLabel{background:#485F87;color:white;border-radius:12px;font-size:13px;font-weight:600;}')
widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
widget.resize(104,34)
dock=TaskbarDock(widget)
print('attach',dock.attach(),flush=True)
def finish():
 report=dock.diagnostic();dock.detach();report['restored']=dock.native.reserved is None
 pathlib.Path('validation/taskbar-probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report),flush=True);app.quit()
QTimer.singleShot(3000,finish)
app.exec()

