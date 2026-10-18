#!/usr/bin/env python3
"""Measure the agent's resource footprint during a run — the Resource Efficiency evidence.

Samples CPU% and working-set memory of the agent process over time and writes a CSV plus a
peak/mean summary, so the report can show a flat, low footprint (no screenshots, no OCR, no
busy-waiting) next to a hard number. This is the numeric counterpart to a Process Explorer
graph. Standard library only (ctypes + Win32); it reads process counters, never the screen.

  python tools/resource_monitor.py --name DeskAssist.exe --duration 180 --interval 1 --csv usage.csv
  python tools/resource_monitor.py --pid 1234 --duration 60

Windows only (it queries Win32 process counters). On other platforms it explains and exits.
This is an operator tool, run alongside the agent — it is not part of the agent package.
"""
import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _filetime_to_100ns(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def find_pids_by_name(name: str) -> list:
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return []
    entry = PROCESSENTRY32W(); entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pids, ok = [], k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        if entry.szExeFile.lower() == name.lower():
            pids.append(entry.th32ProcessID)
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return pids


def _cpu_times(k32, handle) -> int:
    creation, exit_, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    if not k32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_),
                               ctypes.byref(kernel), ctypes.byref(user)):
        return 0
    return _filetime_to_100ns(kernel) + _filetime_to_100ns(user)


def _working_set_mb(k32, handle) -> float:
    pmc = PROCESS_MEMORY_COUNTERS(); pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    if not k32.K32GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return 0.0
    return pmc.WorkingSetSize / (1024 * 1024)


def _cpu_count() -> int:
    class SYSTEM_INFO(ctypes.Structure):
        _fields_ = [("wProcessorArchitecture", wintypes.WORD), ("wReserved", wintypes.WORD),
                    ("dwPageSize", wintypes.DWORD), ("lpMinimumApplicationAddress", ctypes.c_void_p),
                    ("lpMaximumApplicationAddress", ctypes.c_void_p), ("dwActiveProcessorMask", ctypes.POINTER(ctypes.c_ulong)),
                    ("dwNumberOfProcessors", wintypes.DWORD), ("dwProcessorType", wintypes.DWORD),
                    ("dwAllocationGranularity", wintypes.DWORD), ("wProcessorLevel", wintypes.WORD),
                    ("wProcessorRevision", wintypes.WORD)]
    info = SYSTEM_INFO(); ctypes.windll.kernel32.GetSystemInfo(ctypes.byref(info))
    return max(1, int(info.dwNumberOfProcessors))


def _sparkline(values: list) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    hi = max(values) or 1.0
    return "".join(blocks[min(len(blocks) - 1, int(v / hi * (len(blocks) - 1)))] for v in values)


def monitor(pids: list, duration: float, interval: float) -> list:
    k32 = ctypes.windll.kernel32
    ncpu = _cpu_count()
    handles = {pid: k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid) for pid in pids}
    handles = {pid: h for pid, h in handles.items() if h}
    if not handles:
        return []
    last_cpu = {pid: _cpu_times(k32, h) for pid, h in handles.items()}
    last_wall = time.perf_counter()
    rows, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < duration:
        time.sleep(interval)
        now = time.perf_counter()
        dt = now - last_wall
        cpu_pct, rss = 0.0, 0.0
        for pid, h in handles.items():
            cur = _cpu_times(k32, h)
            busy_s = (cur - last_cpu[pid]) / 1e7      # 100ns ticks -> seconds
            cpu_pct += 100.0 * busy_s / (dt * ncpu) if dt > 0 else 0.0
            last_cpu[pid] = cur
            rss += _working_set_mb(k32, h)
        last_wall = now
        rows.append((round(now - t0, 1), round(cpu_pct, 2), round(rss, 1)))
    for h in handles.values():
        k32.CloseHandle(h)
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", default="DeskAssist.exe", help="process image name to sample (default DeskAssist.exe)")
    p.add_argument("--pid", type=int, help="sample this PID instead of resolving --name")
    p.add_argument("--duration", type=float, default=120.0, help="seconds to sample (default 120)")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between samples (default 1)")
    p.add_argument("--csv", type=Path, help="write per-sample t,cpu_percent,rss_mb here")
    a = p.parse_args()

    if not sys.platform.startswith("win"):
        print("resource_monitor.py queries Win32 process counters and runs on the Windows VM only.\n"
              "On the VM: python tools\\resource_monitor.py --name DeskAssist.exe --duration 180 --csv usage.csv")
        sys.exit(2)

    pids = [a.pid] if a.pid else find_pids_by_name(a.name)
    if not pids:
        print(f"No process found matching {'PID ' + str(a.pid) if a.pid else a.name!r}. Is the agent running?")
        sys.exit(1)
    print(f"sampling {len(pids)} process(es) {pids} every {a.interval}s for {a.duration}s ...")
    rows = monitor(pids, a.duration, a.interval)
    if not rows:
        print("Could not open the process for counters (try running as the same user).")
        sys.exit(1)

    cpu = [r[1] for r in rows]; rss = [r[2] for r in rows]
    print(f"\nsamples: {len(rows)}")
    print(f"CPU %   peak {max(cpu):.1f}   mean {sum(cpu) / len(cpu):.1f}   {_sparkline(cpu)}")
    print(f"RSS MB  peak {max(rss):.1f}   mean {sum(rss) / len(rss):.1f}   {_sparkline(rss)}")
    if a.csv:
        a.csv.write_text("t_seconds,cpu_percent,rss_mb\n" + "\n".join(f"{t},{c},{m}" for t, c, m in rows), encoding="utf-8")
        print(f"wrote {len(rows)} samples to {a.csv}")


if __name__ == "__main__":
    main()
