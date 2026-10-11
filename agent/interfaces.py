"""Small abstractions shared by the agent components."""
from abc import ABC, abstractmethod
from typing import Any, Protocol


class InputBackend(ABC):
    """Defines platform-independent desktop input operations."""

    @abstractmethod
    def press(self, key: str) -> None: ...

    @abstractmethod
    def hotkey(self, *keys: str) -> None: ...

    @abstractmethod
    def write(self, text: str) -> None: ...

    @abstractmethod
    def move_to(self, x: float, y: float) -> None: ...

    @abstractmethod
    def click(self, x: float | None = None, y: float | None = None) -> None: ...

    @abstractmethod
    def scroll(self, amount: int) -> None: ...

    @abstractmethod
    def position(self) -> tuple[int, int]: ...

    @abstractmethod
    def screen_size(self) -> tuple[int, int]: ...

    # Separate down/up events, so key holds, rollover and mouse-button holds can be timed.
    @abstractmethod
    def key_event(self, key: str, down: bool) -> None: ...

    @abstractmethod
    def char_event(self, char: str, down: bool) -> None: ...

    @abstractmethod
    def button_event(self, down: bool) -> None: ...


class DelayDistribution(ABC):
    """Defines a strategy for sampling nonnegative wait durations."""

    @abstractmethod
    def sample(self, rng: Any) -> float: ...


class Skill(ABC):
    """Defines one reusable, injectable desktop action."""

    @abstractmethod
    def run(self, context: Any, args: dict[str, Any]) -> Any: ...


class Objective(ABC):
    """Defines a named ordered sequence of skill calls."""

    @abstractmethod
    def run(self, context: Any) -> None: ...


class ActionLogger(Protocol):
    """Defines the action event sink used by skills and the runner."""

    def log(self, event: dict[str, Any]) -> None: ...
