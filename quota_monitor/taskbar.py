from __future__ import annotations

import ctypes
import ctypes.wintypes as w
from dataclasses import dataclass
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QWindow


class DockError(Exception):
    pass


class WindowsTaskbar:
    """Taskbar child window plus an explicitly reserved Windows 10 task-button gap.

    All foreign geometry changes are restored on detach. No shell process is
    injected and no persistent Windows taskbar setting is changed.
    """
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        u = self.user
        u.FindWindowW.argtypes=[w.LPCWSTR,w.LPCWSTR];u.FindWindowW.restype=w.HWND
        u.FindWindowExW.argtypes=[w.HWND,w.HWND,w.LPCWSTR,w.LPCWSTR];u.FindWindowExW.restype=w.HWND
        u.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)];u.GetWindowRect.restype=w.BOOL
        u.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)];u.GetClientRect.restype=w.BOOL
        u.MapWindowPoints.argtypes=[w.HWND,w.HWND,ctypes.POINTER(w.POINT),w.UINT];u.MapWindowPoints.restype=ctypes.c_int
        u.GetParent.argtypes=[w.HWND];u.GetParent.restype=w.HWND
        u.IsWindow.argtypes=[w.HWND];u.IsWindow.restype=w.BOOL
        u.IsWindowVisible.argtypes=[w.HWND];u.IsWindowVisible.restype=w.BOOL
        u.GetDpiForWindow.argtypes=[w.HWND];u.GetDpiForWindow.restype=w.UINT
        u.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        u.SetWindowPos.restype=w.BOOL
        self.host = self.rebar = self.notify = None
        self.baseline = self.reserved = None

    def rect(self, hwnd, parent=None):
        r = w.RECT()
        if not self.user.GetWindowRect(hwnd,ctypes.byref(r)):
            raise DockError('无法读取任务栏位置')
        if parent:
            points=(w.POINT*2)(w.POINT(r.left,r.top),w.POINT(r.right,r.bottom))
            self.user.MapWindowPoints(None,parent,points,2)
            return points[0].x,points[0].y,points[1].x-points[0].x,points[1].y-points[0].y
        return r.left,r.top,r.right-r.left,r.bottom-r.top

    def find(self):
        host=self.user.FindWindowW('Shell_TrayWnd',None)
        if not host:
            raise DockError('Windows 任务栏尚未就绪')
        rebar=self.user.FindWindowExW(host,None,'ReBarWindow32',None)
        notify=self.user.FindWindowExW(host,None,'TrayNotifyWnd',None)
        if not rebar or not notify:
            raise DockError('当前任务栏布局不支持直接显示额度')
        x,y,width,height=self.rect(host)
        if height>width:
            raise DockError('请将任务栏放在屏幕上方或下方')
        if self.host != host:
            self.host,self.rebar,self.notify=host,rebar,notify
            self.baseline=self.reserved=None
        return host

    def reserve(self, widget_hwnd, logical_width):
        self.find()
        _,_,host_width,host_height=self.rect(self.host)
        rx,ry,rw,rh=self.rect(self.rebar,self.host)
        nx,ny,nw,nh=self.rect(self.notify,self.host)
        dpi=self.user.GetDpiForWindow(self.host) or 96
        scale=dpi/96
        width=round(logical_width*scale)
        height=min(round(34*scale),host_height-round(6*scale))
        gap=round(8*scale)
        if nx-rx < width+gap+round(160*scale):
            raise DockError('任务栏空间不足，请减少任务栏工具栏')
        target_width=nx-rx-width-gap
        if self.reserved is None or rw != self.reserved:
            self.baseline=(rx,ry,rw,rh)
        if rw != target_width:
            if not self.user.SetWindowPos(self.rebar,None,rx,ry,target_width,rh,0x0014):
                raise DockError('无法为任务栏额度预留空间')
        self.reserved=target_width
        x=nx-width-gap//2
        y=max(0,(host_height-height)//2)
        if not self.user.SetWindowPos(widget_hwnd,None,x,y,width,height,0x0050):
            raise DockError('无法放置任务栏额度')
        return {'host':int(self.host),'dpi':dpi,'slot':[x,y,width,height]}

    def restore(self):
        if self.rebar and self.baseline and self.user.IsWindow(self.rebar):
            try:
                rx,ry,rw,rh=self.rect(self.rebar,self.host)
                if rw == self.reserved:
                    _,_,original_width,_=self.baseline
                    self.user.SetWindowPos(self.rebar,None,rx,ry,original_width,rh,0x0014)
            except DockError:
                pass
        self.reserved=self.baseline=None


class TaskbarDock(QObject):
    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget=widget
        self.native=WindowsTaskbar()
        self.foreign=None
        self.attached=False
        self.error=None
        self.last_info={}
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def attach(self):
        if self.attached:
            return self.refresh()
        try:
            host=self.native.find()
            self.widget.winId()
            self.foreign=QWindow.fromWinId(int(host))
            if self.foreign is None:
                raise DockError('无法连接 Windows 任务栏')
            self.widget.windowHandle().setParent(self.foreign)
            if self.native.user.GetParent(int(self.widget.winId())) != host:
                raise DockError('任务栏额度嵌入失败')
            self.widget.show()
            self.attached=True
            if not self.refresh():
                return False
            self.timer.start(1000)
            return True
        except (DockError,OSError) as error:
            self.error=str(error)
            self.detach()
            return False

    def refresh(self):
        if not self.attached:
            return False
        try:
            if not self.native.user.IsWindow(self.native.host):
                raise DockError('任务栏正在重新启动')
            self.last_info=self.native.reserve(int(self.widget.winId()),104)
            self.error=None
            return True
        except (DockError,OSError) as error:
            self.error=str(error)
            self.detach()
            return False

    def detach(self):
        self.timer.stop()
        self.widget.hide()
        self.native.restore()
        if self.widget.windowHandle() and self.foreign:
            self.widget.windowHandle().setParent(None)
        self.foreign=None
        self.attached=False

    def diagnostic(self):
        info=dict(self.last_info)
        if self.attached:
            hwnd=int(self.widget.winId())
            parent=self.native.user.GetParent(hwnd)
            wr=self.native.rect(hwnd)
            hr=self.native.rect(self.native.host)
            rr=self.native.rect(self.native.rebar)
            nr=self.native.rect(self.native.notify)
            info.update(parent=int(parent or 0),window_rect=wr,host_rect=hr,
                task_buttons_rect=rr,notification_rect=nr,
                inside_taskbar=wr[0]>=hr[0] and wr[1]>=hr[1] and wr[0]+wr[2]<=hr[0]+hr[2] and wr[1]+wr[3]<=hr[1]+hr[3],
                no_overlap=rr[0]+rr[2]<=wr[0] and wr[0]+wr[2]<=nr[0],
                native_visible=bool(self.native.user.IsWindowVisible(hwnd)))
        info['attached']=self.attached
        info['error']=self.error
        return info
