"""Window titles must be classified correctly, including Edge's zero-width space."""
from agent.perception import ABSENT, NEW_TAB, PRIVACY_ERROR, READY, UNREACHABLE, Perception, normalise

EDGE = "msedge.exe"
P = Perception()


def test_normalise_strips_zero_width_and_nonbreaking_characters():
    assert normalise("Apple -​ Microsoft​ Edge") == "apple - microsoft edge"


def test_ordinary_page_is_ready():
    assert P.page_state("Apple and 2 more pages - Personal - Microsoft​ Edge", EDGE) == READY


def test_expired_certificate_interstitial_is_detected():
    for title in ("Privacy error - Microsoft Edge", "Your connection isn't private - Microsoft Edge",
                  "Clock error - Microsoft\u200b Edge", "Clock error and 1 more page - Personal - Microsoft Edge"):
        assert P.page_state(title, EDGE) == PRIVACY_ERROR, title


def test_dead_host_is_detected():
    for title in ("www.dell.com can't be reached - Microsoft Edge", "This page isn't working - Microsoft Edge"):
        assert P.page_state(title, EDGE) == UNREACHABLE, title


def test_new_tab_and_absent_states():
    assert P.page_state("New tab - Microsoft Edge", EDGE) == NEW_TAB
    assert P.page_state("Program Manager", "explorer.exe") == ABSENT
    assert P.page_state("", "") == ABSENT


def test_process_name_wins_over_title():
    """A window titled like Edge but belonging to another process is not the browser."""
    assert P.page_state("Microsoft Edge setup - Notepad", "notepad.exe") == ABSENT
    assert P.is_app("browser", "anything at all", EDGE)


def test_title_markers_are_the_fallback_when_there_is_no_process_name():
    assert P.is_app("browser", "Apple - Microsoft Edge", "")
    assert not P.is_app("browser", "Document1 - Word", "")


def test_config_can_override_the_browser_process():
    custom = Perception.from_config({"apps": {"browser": {"process": "chrome.exe"}}})
    assert custom.is_app("browser", "x", "chrome.exe") and not custom.is_app("browser", "x", EDGE)


def test_page_name_is_the_leading_segment():
    assert P.page_name("Apple - Personal - Microsoft​ Edge") == "apple"


def test_process_lookups_are_cached_per_window_so_processaccess_events_stay_rare():
    """A verbose Sysmon config logs OpenProcess as Event ID 10; one per poll would look like recon."""
    import ctypes
    from agent.win.desktop import WindowsDesktop

    class FakeUser32:
        def GetForegroundWindow(self): return 4242
        def GetWindowTextW(self, handle, buffer, size): return 0
        def GetWindowThreadProcessId(self, handle, pid_ref): return 1

    class FakeKernel32:
        def __init__(self): self.opens = 0
        def OpenProcess(self, access, inherit, pid): self.opens += 1; return 7
        def QueryFullProcessImageNameW(self, proc, flags, buffer, size):
            buffer.value = r"C:\Program Files\Edge\msedge.exe"; return 1
        def CloseHandle(self, handle): return 1

    kernel = FakeKernel32()
    desktop = WindowsDesktop(FakeUser32(), kernel, kernel)
    assert [desktop.foreground_process() for _ in range(50)] == ["msedge.exe"] * 50
    assert kernel.opens == 1 and desktop.lookups == 1


def test_process_lookup_can_be_switched_off_entirely():
    from agent.win.desktop import WindowsDesktop

    class Boom:
        def __getattr__(self, name): raise AssertionError("no API call should happen")

    desktop = WindowsDesktop(Boom(), Boom(), Boom(), use_process_lookup=False)
    assert desktop.foreground_process() == ""
