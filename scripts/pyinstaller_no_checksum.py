# -*- coding: utf-8 -*-
"""Run PyInstaller while skipping Windows PE timestamp/checksum rewrites.

Some Windows machines lock newly created one-file EXEs while antivirus or
indexing scans them. PyInstaller's final timestamp/checksum rewrite is optional
for our local packages, and skipping it makes the build repeatable here.
"""
from PyInstaller.utils.win32 import winutils
import PyInstaller.__main__


def _noop(*args, **kwargs):
    return None


winutils.set_exe_build_timestamp = _noop
winutils.update_exe_pe_checksum = _noop


if __name__ == "__main__":
    PyInstaller.__main__.run()
