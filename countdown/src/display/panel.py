from abc import ABC, abstractmethod

from PIL import Image


class Panel(ABC):
    @abstractmethod
    def render(self, image_width: int, image_height: int) -> Image.Image:
        raise NotImplementedError("Subclasses must implement the render method.")
