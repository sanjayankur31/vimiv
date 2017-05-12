# vim: ft=python fileencoding=utf-8 sw=4 et sts=4
"""Gtk.ScrolledWindow class which is usually the main window of vimiv.

The ScrolledWindow can either include a Gtk.Image in IMAGE mode or a
Gtk.IconView in THUMBNAIL mode.
"""

from gi.repository import Gtk
from vimiv.image import Image
from vimiv.thumbnail import Thumbnail


class MainWindow(Gtk.ScrolledWindow):
    """Main window of vimiv containing either an Image or an IconView.

    Attributes:
        image: Vimiv Image class which may be displayed.
        thumbnail: Vimiv Thumbnail class which may be displayed.

        _app: The main vimiv class to interact with.
    """

    def __init__(self, app, settings):
        """Initialize image and thumbnail attributes and configure self."""
        super(MainWindow, self).__init__()
        self._app = app
        self.image = Image(app, settings)
        self.thumbnail = Thumbnail(app, settings)

        self.set_hexpand(True)
        self.set_vexpand(True)
        # Image is default
        self.add(self.image)
        self.connect("key_press_event", self._app["eventhandler"].key_pressed,
                     "IMAGE")

    def switch_to_child(self, new_child):
        """Switch the widget displayed in the main window.

        Args:
            new_child: The child to switch to.
        """
        self.remove(self.get_child())
        self.add(new_child)

    def center_window(self):
        """Center the widget in the current window."""
        h_adj = self.get_hadjustment()
        size = self.get_allocated_size()[0]
        h_middle = (h_adj.get_upper() - h_adj.get_lower() - size.width) / 2
        h_adj.set_value(h_middle)
        v_adj = self.get_vadjustment()
        v_middle = (v_adj.get_upper() - v_adj.get_lower() - size.height) / 2
        v_adj.set_value(v_middle)
        self.set_hadjustment(h_adj)
        self.set_vadjustment(v_adj)

    def scroll(self, direction):
        """Scroll the correct object.

        Args:
            direction: Scroll direction to emit.
        """
        if direction not in "hjklHJKL":
            self._app["statusbar"].message(
                "Invalid scroll direction " + direction, "error")
        elif self.thumbnail.toggled:
            self.thumbnail.move_direction(direction)
        else:
            self._scroll(direction)
        return True  # Deactivates default bindings (here for Arrows)

    def _scroll(self, direction):
        """Scroll the widget.

        Args:
            direction: Direction to scroll in.
        """
        steps = self._app["eventhandler"].num_receive()
        scale = self.image.get_scroll_scale()
        h_adj = self.get_hadjustment()
        size = self.get_allocated_size()[0]
        h_size = h_adj.get_upper() - h_adj.get_lower() - size.width
        h_step = h_size / scale * steps
        v_adj = self.get_vadjustment()
        v_size = v_adj.get_upper() - v_adj.get_lower() - size.height
        v_step = v_size / scale * steps
        # To the ends
        if direction == "H":
            h_adj.set_value(0)
        elif direction == "J":
            v_adj.set_value(v_size)
        elif direction == "K":
            v_adj.set_value(0)
        elif direction == "L":
            h_adj.set_value(h_size)
        # By step
        elif direction == "h":
            h_adj.set_value(h_adj.get_value() - h_step)
        elif direction == "j":
            v_adj.set_value(v_adj.get_value() + v_step)
        elif direction == "k":
            v_adj.set_value(v_adj.get_value() - v_step)
        elif direction == "l":
            h_adj.set_value(h_adj.get_value() + h_step)
        self.set_hadjustment(h_adj)
        self.set_vadjustment(v_adj)
