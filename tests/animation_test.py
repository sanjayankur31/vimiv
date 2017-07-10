# vim: ft=python fileencoding=utf-8 sw=4 et sts=4
"""Test animations in image mode for vimiv's testsuite."""

from unittest import main

from vimiv_testcase import VimivTestCase, refresh_gui, compare_pixbufs


class AnimationTest(VimivTestCase):
    """Test animations in image mode."""

    @classmethod
    def setUpClass(cls):
        cls.init_test(cls, ["vimiv/testimages/animation/animation.gif"])
        cls.image = cls.vimiv["image"]

    def test_toggle_animation(self):
        """Pause and play an animated gif."""
        self._update_gif(True)
        # Frames should be updated
        first_pb = self.image.pixbuf_original.copy()
        delay = self.image.pixbuf_iter.get_delay_time()
        refresh_gui((delay + 50) / 1000)
        second_pb = self.image.pixbuf_original.copy()
        self.assertFalse(compare_pixbufs(first_pb, second_pb))
        # Frames should no longer be updated
        self._update_gif(False)
        first_pb = self.image.pixbuf_original.copy()
        delay = self.image.pixbuf_iter.get_delay_time()
        refresh_gui((delay + 50) / 1000)
        second_pb = self.image.pixbuf_original.copy()
        self.assertTrue(compare_pixbufs(first_pb, second_pb))
        # Back to standard state
        self._update_gif(True)

    def test_fail_transform_animation(self):
        """Fail transforming an animation."""
        self.vimiv["transform"].rotate(3)
        self.check_statusbar("WARNING: Animations cannot be rotated")
        self.vimiv["transform"].flip(True)
        self.check_statusbar("WARNING: Animations cannot be flipped")

    def test_zoom_animation(self):
        """Zoom an animation."""
        start = self.image.get_zoom_percent()
        self.image.zoom_delta()
        self.assertGreater(self.image.get_zoom_percent(), start)
        self.image.zoom_delta(zoom_in=False)
        self.assertEqual(self.image.get_zoom_percent(), start)

    def test_overzoom(self):
        """Test overzoom at opening and fit afterwards for animations."""
        # Overzoom is respected
        self.assertEqual(self.image.get_zoom_percent(), 100)
        # But not for a direct call to fit
        self.image.zoom_to(0, "fit")
        self.assertGreater(self.image.get_zoom_percent(), 100)
        self.image.move_pos(forward=False)

    def _update_gif(self, assertion):
        self.run_command("set play_animations %s" % (str(assertion)))
        refresh_gui(0.1)
        self.assertEqual(self.settings["play_animations"].get_value(),
                         assertion)


if __name__ == "__main__":
    main()