# vim: ft=python fileencoding=utf-8 sw=4 et sts=4
"""Switching between modes tests for vimiv's test suite."""

import os
from unittest import main

from gi import require_version
require_version("Gtk", "3.0")
from gi.repository import Gtk

from vimiv_testcase import VimivTestCase


class ModeSwitchTestImage(VimivTestCase):
    """Mode Switching Tests starting from image mode."""

    @classmethod
    def setUpClass(cls):
        cls.init_test(cls, ["vimiv/testimages/arch-logo.png"])

    def setUp(self):
        self.test_directory = os.getcwd()

    def test_image_library(self):
        """Switch between image and library mode."""
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertFalse(self.vimiv["library"].is_visible())

        self.vimiv["library"].toggle()
        self.assertFalse(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["library"].is_visible())
        self.assertTrue(self.vimiv["library"].is_focus())

        self.vimiv["library"].toggle()
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertFalse(self.vimiv["library"].is_visible())

    def test_image_thumbnail(self):
        """Switch between image and thumbnail mode."""
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertEqual(type(self.vimiv["main_window"].get_child()),
                         Gtk.Viewport)  # We do not know the exact viewport

        self.vimiv["thumbnail"].toggle()
        self.assertTrue(self.vimiv["thumbnail"].is_focus())
        self.assertEqual(self.vimiv["main_window"].get_child(),
                         self.vimiv["thumbnail"])
        self.assertEqual(self.vimiv["thumbnail"].last_focused, "im")
        # Quick insert of thumbnail <-> manipulate as it would be to expensive
        # to write an extra thumbnail class for this
        self.vimiv["manipulate"].toggle()
        self.assertTrue(self.vimiv["thumbnail"].is_focus())
        self.assertFalse(self.vimiv["manipulate"].is_visible())
        self.check_statusbar(
            "WARNING: Manipulate not supported in thumbnail mode")

        self.vimiv["thumbnail"].toggle()
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertEqual(type(self.vimiv["main_window"].get_child()),
                         Gtk.Viewport)

    def test_image_manipulate(self):
        """Switch between image and manipulate mode."""
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertFalse(self.vimiv["manipulate"].is_visible())

        self.vimiv["manipulate"].toggle()
        self.assertTrue(self.vimiv["manipulate"].is_visible())
        self.assertTrue(self.vimiv["manipulate"].sliders["bri"].is_focus())

        self.vimiv["manipulate"].toggle()
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertFalse(self.vimiv["manipulate"].is_visible())

    def tearDown(self):
        os.chdir(self.test_directory)


class ModeSwitchTestLibrary(VimivTestCase):
    """Mode Switching Tests starting from library mode."""

    @classmethod
    def setUpClass(cls):
        cls.init_test(cls, ["vimiv/testimages/"])

    def setUp(self):
        self.test_directory = os.getcwd()

    def test_library_image(self):
        """Switch between library and image mode."""
        self.assertTrue(self.vimiv["library"].is_focus())
        path = Gtk.TreePath(
            [self.vimiv["library"].files.index("arch-logo.png")])
        self.vimiv["library"].file_select(None, path, None, True)
        self.assertTrue(self.vimiv["main_window"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertFalse(self.vimiv["library"].is_visible())

        self.vimiv["library"].toggle()
        self.assertTrue(self.vimiv["library"].is_focus())
        self.assertTrue(self.vimiv["library"].is_visible())

    def test_library_thumbnail(self):
        """Switch between library and thumbnail mode."""
        self.assertTrue(self.vimiv["library"].is_focus())
        self.vimiv["thumbnail"].toggle()
        self.assertTrue(self.vimiv["thumbnail"].is_focus())
        self.assertTrue(self.vimiv["main_window"].is_visible())
        self.assertEqual(self.vimiv["main_window"].get_child(),
                         self.vimiv["thumbnail"])
        self.assertEqual(self.vimiv["thumbnail"].last_focused, "lib")

        self.vimiv["thumbnail"].toggle()
        self.assertTrue(self.vimiv["library"].is_focus())
        self.assertNotEqual(self.vimiv["main_window"].get_child(),
                            self.vimiv["thumbnail"])

    def test_library_manipulate(self):
        """Switch between library and manipulate mode should fail."""
        self.assertTrue(self.vimiv["library"].is_focus())
        self.vimiv["manipulate"].toggle()
        self.assertTrue(self.vimiv["library"].is_focus())
        self.assertFalse(self.vimiv["manipulate"].is_visible())
        self.check_statusbar("WARNING: Manipulate not supported in library")

    def tearDown(self):
        os.chdir(self.test_directory)
        self.vimiv["library"].reload(os.getcwd())


if __name__ == "__main__":
    main()
