from abc import ABC, abstractmethod

from PIL import Image

class Panel(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def render(self) -> Image.Image:
        raise NotImplementedError("Subclasses must implement the render method.")