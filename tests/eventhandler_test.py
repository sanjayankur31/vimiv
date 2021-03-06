# vim: ft=python fileencoding=utf-8 sw=4 et sts=4
"""Tests eventhandler.py for vimiv's test suite."""

from unittest import main

from gi import require_version
require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from vimiv_testcase import VimivTestCase, refresh_gui


class KeyHandlerTest(VimivTestCase):
    """KeyHandler Tests."""

    @classmethod
    def setUpClass(cls):
        cls.init_test(cls, ["vimiv/testimages/"])

    def test_key_press(self):
        """Press key."""
        self.vimiv["library"].file_select(None, Gtk.TreePath(1), None, True)
        image_before = self.vimiv.get_path()
        event = Gdk.Event().new(Gdk.EventType.KEY_PRESS)
        event.keyval = Gdk.keyval_from_name("n")
        self.vimiv["main_window"].emit("key_press_event", event)
        image_after = self.vimiv.get_path()
        self.assertNotEqual(image_before, image_after)
        event.keyval = Gdk.keyval_from_name("O")
        self.vimiv["main_window"].emit("key_press_event", event)
        self.assertTrue(self.vimiv["library"].is_focus())

    def test_button_click(self):
        """Click mouse button."""
        self.vimiv["library"].file_select(None, Gtk.TreePath(1), None, True)
        image_before = self.vimiv.get_path()
        event = Gdk.Event().new(Gdk.EventType.BUTTON_PRESS)
        event.button = 1
        self.vimiv["window"].emit("button_press_event", event)
        image_after = self.vimiv.get_path()
        self.assertNotEqual(image_before, image_after)
        # Double click should not work
        event = Gdk.Event().new(Gdk.EventType.DOUBLE_BUTTON_PRESS)
        event.button = 1
        self.vimiv["window"].emit("button_press_event", event)
        self.assertEqual(image_after, self.vimiv.get_path())
        # Focus library via mouse click
        event = Gdk.Event().new(Gdk.EventType.BUTTON_PRESS)
        event.button = 2
        self.vimiv["window"].emit("button_press_event", event)
        self.assertTrue(self.vimiv["library"].is_focus())

    def test_add_number(self):
        """Add number to the numstr and clear it."""
        self.assertFalse(self.vimiv["eventhandler"].get_num_str())
        # Add a number
        self.vimiv["eventhandler"].num_append("2")
        self.assertEqual(self.vimiv["eventhandler"].get_num_str(), "2")
        # Add another number, should change the timer_id
        self.vimiv["eventhandler"].num_append("3")
        self.assertEqual(self.vimiv["eventhandler"].get_num_str(), "23")
        # Clear manually, GLib timeout should definitely work as well if the
        # code runs without errors
        self.vimiv["eventhandler"].num_clear()
        self.assertFalse(self.vimiv["eventhandler"].get_num_str())

    def test_receive_number(self):
        """Get a number from numstr and clear it."""
        # Integer
        self.vimiv["eventhandler"].num_append("3")
        num = self.vimiv["eventhandler"].num_receive()
        self.assertEqual(num, 3)
        self.assertFalse(self.vimiv["eventhandler"].get_num_str())
        # Float
        self.vimiv["eventhandler"].num_append("03")
        num = self.vimiv["eventhandler"].num_receive(to_float=True)
        self.assertEqual(num, 0.3)
        self.assertFalse(self.vimiv["eventhandler"].get_num_str())
        # Empty should give default
        num = self.vimiv["eventhandler"].num_receive()
        self.assertEqual(num, 1)
        num = self.vimiv["eventhandler"].num_receive(5)
        self.assertEqual(num, 5)

    def test_add_number_via_keypress(self):
        """Add a number to the numstr by keypress."""
        self.assertFalse(self.vimiv["eventhandler"].get_num_str())
        event = Gdk.Event().new(Gdk.EventType.KEY_PRESS)
        event.keyval = Gdk.keyval_from_name("2")
        self.vimiv["library"].emit("key_press_event", event)
        self.assertEqual(self.vimiv["eventhandler"].get_num_str(), "2")
        # Clear as it might interfere
        self.vimiv["eventhandler"].num_clear()

    def test_key_press_modifier(self):
        """Press key with modifier."""
        before = self.settings["show_hidden"].get_value()
        event = Gdk.Event().new(Gdk.EventType.KEY_PRESS)
        event.keyval = Gdk.keyval_from_name("h")
        event.state = Gdk.ModifierType.CONTROL_MASK
        self.vimiv["library"].emit("key_press_event", event)
        after = self.settings["show_hidden"].get_value()
        self.assertNotEqual(before, after)

    def test_touch(self):
        """Touch event."""
        self.vimiv["library"].file_select(None, Gtk.TreePath(1), None, True)
        image_before = self.vimiv.get_path()
        event = Gdk.Event().new(Gdk.EventType.TOUCH_BEGIN)
        # Twice to check for exception
        self.vimiv["window"].emit("touch-event", event)
        self.vimiv["window"].emit("touch-event", event)
        image_after = self.vimiv.get_path()
        self.assertEqual(image_before, image_after)  # Touch only disables
        self.vimiv["library"].toggle()
        self.assertTrue(self.vimiv["library"].is_focus())
        refresh_gui()
        # Test again to see if it was re-activated properly
        self.test_button_click()


if __name__ == "__main__":
    main()
