# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
from pathlib import Path


DEFAULT_MUTEX_NAME = "OrderSystem_OrderCollectorAgent"
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 128
WAIT_TIMEOUT = 258


class SingleInstance:
    def __init__(self, name: str = DEFAULT_MUTEX_NAME):
        self.name = name
        self.acquired = False
        self._handle = None
        self._lock_fd: int | None = None
        self._lock_path: Path | None = None

    def acquire(self) -> bool:
        if os.name == "nt":
            return self._acquire_windows()
        return self._acquire_lock_file()

    def release(self) -> None:
        if os.name == "nt":
            self._release_windows()
        else:
            self._release_lock_file()

    def __enter__(self) -> "SingleInstance":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def _acquire_windows(self) -> bool:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        self.acquired = wait_result in (WAIT_OBJECT_0, WAIT_ABANDONED)
        if self.acquired:
            self._handle = handle
        else:
            kernel32.CloseHandle(handle)
            self._handle = None
        return self.acquired

    def _release_windows(self) -> None:
        if not self._handle:
            return
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        if self.acquired:
            kernel32.ReleaseMutex(self._handle)
        kernel32.CloseHandle(self._handle)
        self._handle = None
        self.acquired = False

    def _acquire_lock_file(self) -> bool:
        path = Path(tempfile.gettempdir()) / f"{self.name}.lock"
        try:
            self._lock_fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            self._lock_path = path
            self.acquired = False
            return False
        self._lock_path = path
        self.acquired = True
        return True

    def _release_lock_file(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self.acquired and self._lock_path and self._lock_path.exists():
            try:
                self._lock_path.unlink()
            except OSError:
                pass
        self.acquired = False
