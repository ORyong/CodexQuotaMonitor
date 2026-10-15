"""Read-only diagnostics of our application's Windows notification icon."""
import ctypes
import ctypes.wintypes as w
import json
import pathlib
import psutil
import winreg

root=pathlib.Path(__file__).resolve().parents[1]
own=[]
for p in psutil.process_iter(['pid','name']):
 if p.info['name']=='CodexQuotaMonitor.exe':
  try:
   if pathlib.Path(p.exe()).resolve().is_relative_to(root):own.append(p.pid)
  except (psutil.AccessDenied,psutil.NoSuchProcess):pass
user=ctypes.WinDLL('user32',use_last_error=True)
callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
user.EnumWindows.argtypes=[callback_type,w.LPARAM]
user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
class GUID(ctypes.Structure):
 _fields_=[('d1',w.DWORD),('d2',w.WORD),('d3',w.WORD),('d4',ctypes.c_ubyte*8)]
class Identifier(ctypes.Structure):
 _fields_=[('cbSize',w.DWORD),('hWnd',w.HWND),('uID',w.UINT),('guidItem',GUID)]
shell=ctypes.WinDLL('shell32')
shell.Shell_NotifyIconGetRect.argtypes=[ctypes.POINTER(Identifier),ctypes.POINTER(w.RECT)]
shell.Shell_NotifyIconGetRect.restype=ctypes.c_long
rows=[]
user.EnumChildWindows.argtypes=[w.HWND,callback_type,w.LPARAM]
children=[]
@callback_type
def child_callback(hwnd,param):
 cls=ctypes.create_unicode_buffer(256);user.GetClassNameW(hwnd,cls,256)
 rect=w.RECT();user.GetWindowRect(hwnd,ctypes.byref(rect))
 children.append({'hwnd':int(hwnd),'class':cls.value,'visible':bool(user.IsWindowVisible(hwnd)),'rect':[rect.left,rect.top,rect.right,rect.bottom]})
 return True
@callback_type
def callback(hwnd,param):
 pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
 cls=ctypes.create_unicode_buffer(256);user.GetClassNameW(hwnd,cls,256)
 if pid.value not in own and cls.value not in ('Shell_TrayWnd','NotifyIconOverflowWindow'):return True
 rect=w.RECT();user.GetWindowRect(hwnd,ctypes.byref(rect))
 row={'pid':pid.value,'hwnd':int(hwnd),'class':cls.value,'visible':bool(user.IsWindowVisible(hwnd)),'rect':[rect.left,rect.top,rect.right,rect.bottom]}
 if pid.value in own:
  title=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,title,256);row['title']=title.value
  if 'Tray' in cls.value or 'tray' in cls.value:
   row['notification_probes']=[]
   for uid in (0,1):
    identity=Identifier(ctypes.sizeof(Identifier),hwnd,uid,GUID());iconrect=w.RECT()
    result=shell.Shell_NotifyIconGetRect(ctypes.byref(identity),ctypes.byref(iconrect))
    row['notification_probes'].append({'id':uid,'hresult':result,'rect':[iconrect.left,iconrect.top,iconrect.right,iconrect.bottom]})
 if cls.value=='Shell_TrayWnd':user.EnumChildWindows(hwnd,child_callback,0)
 rows.append(row)
 return True
user.EnumWindows(callback,0)
report={'pids':own,'windows':rows,'taskbar_children':children,'theme':{}}
try:
 with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
  for name in ['SystemUsesLightTheme','AppsUseLightTheme']:
   try:report['theme'][name]=winreg.QueryValueEx(key,name)[0]
   except OSError:pass
except OSError:pass
print(json.dumps(report,ensure_ascii=False,indent=2))
