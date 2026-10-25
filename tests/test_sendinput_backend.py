"""The stdlib backend is testable on any OS by injecting a fake user32."""
import ctypes
from agent.input.sendinput_backend import SendInputBackend, VK, INPUT_KEYBOARD, INPUT_MOUSE


class FakeUser32:
    def __init__(self): self.inputs = []
    def SendInput(self, n, ptr, size):
        inp = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_byte * size)).contents
        self.inputs.append(bytes(inp)); return n
    def GetSystemMetrics(self, i): return 1920 if i == 0 else 1080
    def GetCursorPos(self, ptr): return 1


def test_press_sends_down_and_up():
    u = FakeUser32(); SendInputBackend(u).press("enter")
    assert len(u.inputs) == 2 and u.inputs[0][0] == INPUT_KEYBOARD


def test_hotkey_sends_all_downs_then_ups_in_reverse():
    u = FakeUser32(); SendInputBackend(u).hotkey("ctrl", "l")
    assert len(u.inputs) == 4


def test_write_uses_unicode_events():
    u = FakeUser32(); SendInputBackend(u).write("ab")
    assert len(u.inputs) == 4


def test_move_and_click_are_mouse_inputs():
    u = FakeUser32(); b = SendInputBackend(u); b.move_to(100, 100); b.click(); b.scroll(-1)
    assert all(i[0] == INPUT_MOUSE for i in u.inputs) and len(u.inputs) == 4
    assert b.screen_size() == (1920, 1080)


def test_vk_table_covers_keys_the_skills_use():
    for k in ("win", "enter", "escape", "tab", "backspace", "ctrl", "alt", "f4", "l", "w", "s", "r", "f", "left", "1", "2"):
        assert k in VK


def _flags(raw: bytes) -> int:
    from agent.input.sendinput_backend import _INPUT, _KEYBDINPUT
    off = _INPUT.u.offset + _KEYBDINPUT.dwFlags.offset
    return int.from_bytes(raw[off: off + _KEYBDINPUT.dwFlags.size], "little")


def test_arrow_keys_carry_the_extended_flag_letters_do_not():
    """Shift + arrow only selects text when arrows are sent as extended keys (VM bug 25 Oct)."""
    u = FakeUser32(); b = SendInputBackend(u)
    b.key_event("right", True); b.key_event("a", True); b.key_event("delete", True)
    assert _flags(u.inputs[0]) & 0x1 and _flags(u.inputs[2]) & 0x1
    assert not _flags(u.inputs[1]) & 0x1
