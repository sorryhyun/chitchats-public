"""Windows-specific compatibility shims: hide console windows, kill children on exit."""

import sys

_job_handle = None


def patch_subprocess_no_window():
    """Patch subprocess.Popen to hide console windows on Windows.

    When running as a windowed exe (console=False), any subprocess spawned
    without CREATE_NO_WINDOW will flash a visible console window. This patches
    subprocess.Popen to automatically inject the flag for all subprocesses,
    hiding the Claude CLI terminal that would otherwise appear.
    """
    import subprocess

    CREATE_NO_WINDOW = 0x08000000
    _original_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):
        if "creationflags" not in kwargs or kwargs["creationflags"] == 0:
            kwargs["creationflags"] = CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init


def setup_job_kill_on_close():
    """Create a Windows Job Object that kills all child processes on exit.

    When the main process exits (including via os._exit), the OS closes all
    handles. With KILL_ON_JOB_CLOSE, closing the Job Object handle automatically
    terminates all child processes (Claude SDK, Codex servers, etc.), preventing
    stale processes after quitting from the system tray.
    """
    global _job_handle

    if sys.platform != "win32":
        return

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFO(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return

        info = JOBOBJECT_EXTENDED_LIMIT_INFO()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if not kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(job)
            return

        current_process = kernel32.GetCurrentProcess()
        if not kernel32.AssignProcessToJobObject(job, current_process):
            kernel32.CloseHandle(job)
            return

        # Store globally so the handle stays open until process exits
        _job_handle = job

    except Exception:
        pass
