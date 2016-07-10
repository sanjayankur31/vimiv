#!/usr/bin/env python3
# encoding: utf-8

import mimetypes
import os
import re
import shutil
from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk, Gdk, GdkPixbuf, Pango
from random import shuffle
from subprocess import Popen, PIPE
from threading import Thread
from PIL import Image
from vimiv.helpers import read_file
from vimiv.variables import types, scrolltypes
from vimiv.fileactions import populate, delete
from vimiv.parser import parse_keys
from vimiv import imageactions
from vimiv.completions import Completion
from vimiv.toggle import FullscreenToggler, VariableToggler
from vimiv.commands import Commands
from vimiv.commandline import CommandLine

# Directories
vimivdir = os.path.join(os.path.expanduser("~"), ".vimiv")
trashdir = os.path.join(vimivdir, "Trash")
thumbdir = os.path.join(vimivdir, "Thumbnails")
tagdir = os.path.join(vimivdir, "Tags")


class Vimiv(Gtk.Window):
    """ Actual vimiv class as a Gtk Window """

    def __init__(self, settings, paths, index):

        self.paths = paths
        self.index = index

        # Default values
        self.animation_toggled = False
        self.thumbnail_toggled = False
        self.marked = []
        self.marked_bak = []  # saves marked images after marked toggle
        self.manipulate_toggled = False
        self.user_zoomed = False  # checks if the user manually zoomed the
        #                          image, necessary for the auto_resize function
        self.library_focused = False
        self.num_str = ""  # used to prepend actions with numbers
        self.dir_pos = {}  # Remembers positions in the library browser
        self.error = []
        self.search_names = []
        self.search_positions = []
        # Dictionary for all the possible editing
        self.manipulations = [1, 1, 1, False]
        # The configruations from vimivrc
        general = settings["GENERAL"]
        library = settings["LIBRARY"]
        # General
        self.slideshow = general["start_slideshow"]
        self.slideshow_delay = general["slideshow_delay"]
        self.shuffle = general["shuffle"]
        self.sbar = general["display_bar"]
        self.winsize = general["geometry"]
        self.recursive = general["recursive"]
        self.thumbsize = general["thumbsize"]
        # Library
        self.library_toggled = library["show_library"]
        self.library_default_width = library["library_width"]
        self.library_width = self.library_default_width
        self.expand_lib = library["expand_lib"]
        self.border_width = library["border_width"]
        self.search_case = general["search_case_insensitive"]
        self.border_color = library["border_color"]
        self.markup = library["markup"]
        self.show_hidden = library["show_hidden"]
        self.desktop_start_dir = library["desktop_start_dir"]

        # Keybindings
        self.keys = parse_keys()

        # Cmd history from file
        self.cmd_history = read_file(os.path.expanduser("~/.vimiv/history"))
        self.cmd_pos = 0

        Gtk.Window.__init__(self)
        self.toggle_fullscreen = FullscreenToggler(self, settings)
        self.toggle_vars = VariableToggler(self, settings)
        Commands(self)
        self.commandline = CommandLine(self)

    def delete(self):
        """ Delete all marked images or the current one """
        # Get all images
        images = self.manipulated_images("Deleted")
        self.marked = []
        # TODO name overridden?
        if delete(images):
            self.err_message("Deleting directories is not supported")
        else:
            self.reload_changes(os.path.abspath("."))

    def quit(self, force=False):
        """ Quit the main loop, printing marked files and saving history """
        for image in self.marked:
            print(image)
        # Check if image has been edited
        if self.check_for_edit(force):
            return
        # Save the history
        histfile = os.path.expanduser("~/.vimiv/history")
        histfile = open(histfile, 'w')
        for cmd in self.cmd_history:
            cmd += "\n"
            histfile.write(cmd)
        histfile.close()

        Gtk.main_quit()

    def check_for_edit(self, force):
        """ Checks if an image was edited before moving """
        if self.paths:
            if "EDIT" in self.paths[self.index]:
                if force:
                    self.button_clicked(False)
                    return 0
                else:
                    self.err_message("Image has been edited, add ! to force")
                    return 1

    def scroll(self, direction):
        """ Scroll the correct object """
        if self.thumbnail_toggled:
            self.thumbnail_move(direction)
        else:
            self.scrolled_win.emit('scroll-child',
                                   scrolltypes[direction][0],
                                   scrolltypes[direction][1])
        return True  # Deactivates default bindings (here for Arrows)

    def scroll_lib(self, direction):
        """ Scroll the library viewer and select if necessary """
        # Handle the specific keys
        if direction == "h":  # Behave like ranger
            self.remember_pos(os.path.abspath("."), self.treepos)
            self.move_up()
        elif direction == "l":
            self.file_select("a", Gtk.TreePath(self.treepos), "b", False)
        else:
            # Scroll the tree checking for a user step
            if self.num_str:
                step = int(self.num_str)
            else:
                step = 1
            if direction == "j":
                self.treepos = (self.treepos + step) % len(self.filelist)
            else:
                self.treepos = (self.treepos - step) % len(self.filelist)

            self.treeview.set_cursor(Gtk.TreePath(self.treepos), None, False)
            # Clear the user prefixed step
            self.num_clear()
        return True  # Deactivates default bindings (here for Arrows)

    def thumbnail_move(self, direction):
        """ Select thumbnails correctly and scroll """
        # Check for a user prefixed step
        if self.num_str:
            step = int(self.num_str)
        else:
            step = 1
        # Check for the specified thumbnail and handle exceptons
        if direction == "h":
            self.thumbpos -= step
        elif direction == "k":
            self.thumbpos -= self.columns*step
        elif direction == "l":
            self.thumbpos += step
        else:
            self.thumbpos += self.columns*step
        # Do not scroll to self.paths that don't exist
        if self.thumbpos < 0:
            self.thumbpos = 0
        elif self.thumbpos > (len(self.files)-len(self.errorpos)-1):
            self.thumbpos = len(self.files)-len(self.errorpos)-1
        # Move
        path = Gtk.TreePath.new_from_string(str(self.thumbpos))
        self.iconview.select_path(path)
        curthing = self.iconview.get_cells()[0]
        self.iconview.set_cursor(path, curthing, False)
        # Actual scrolling TODO
        self.thumbnail_scroll(direction, step, self.thumbpos)
        # Clear the user prefixed step
        self.num_clear()

    def thumbnail_scroll(self, direction, step, target):
        """ Handles the actual scrolling """
        # TODO
        if step == 0:
            step += 1
        # Vertical
        if direction == "k" or direction == "j":
            Gtk.Adjustment.set_step_increment(
                self.viewport.get_vadjustment(), (self.thumbsize[1]+30)*step)
            self.scrolled_win.emit('scroll-child',
                                   scrolltypes[direction][0], False)
        # Horizontal (tricky because one might reach a new column)
        else:
            start = target - step
            startcol = int(start / self.columns)
            endcol = int(target / self.columns)
            toscroll = endcol - startcol
            Gtk.Adjustment.set_step_increment(self.viewport.get_vadjustment(),
                                              (self.thumbsize[1]+30)*toscroll)
            self.scrolled_win.emit('scroll-child',
                                   scrolltypes[direction][0], False)

    def toggle_slideshow(self):
        """ Toggles the slideshow or updates the delay """
        if not self.paths:
            self.err_message("No valid paths, starting slideshow failed")
            return
        if self.thumbnail_toggled:
            self.err_message("Slideshow makes no sense in thumbnail mode")
            return
        # Delay changed via num_str?
        if self.num_str:
            self.set_slideshow_delay(float(self.num_str))
        # If the delay wasn't changed in any way just toggle the slideshow
        else:
            self.slideshow = not self.slideshow
            if self.slideshow:
                self.timer_id_s = GLib.timeout_add(1000*self.slideshow_delay,
                                                   self.move_index, True,
                                                   False, 1)
            else:
                GLib.source_remove(self.timer_id_s)
        self.update_info()

    def set_slideshow_delay(self, val, key=""):
        """ Sets slideshow delay to val or inc/dec depending on key """
        if key == "-":
            if self.slideshow_delay >= 0.8:
                self.slideshow_delay -= 0.2
        elif key == "+":
            self.slideshow_delay += 0.2
        elif val:
            self.slideshow_delay = float(val)
            self.num_str = ""
        # If slideshow was running reload it
        if self.slideshow:
            GLib.source_remove(self.timer_id_s)
            self.timer_id_s = GLib.timeout_add(1000*self.slideshow_delay,
                                               self.move_index, True, False, 1)
            self.update_info()

    def err_message(self, mes):
        """ Pushes an error message to the statusbar """
        self.error.append(1)
        mes = "<b>" + mes + "</b>"
        self.timer_id = GLib.timeout_add_seconds(5, self.error_false)
        if not self.sbar:
            self.left_label.set_markup(mes)
        else:  # Show bar if it isn't there
            self.toggle_statusbar()
            self.left_label.set_markup(mes)
            self.timer_id = GLib.timeout_add_seconds(5, self.toggle_statusbar)

    def error_false(self):
        """ Strip one error and update the statusbar if no more errors remain"""
        self.error = self.error[0:-1]
        if not self.error:
            self.update_info()

    def toggle_statusbar(self):
        if not self.sbar and not self.cmd_line.is_visible():
            self.leftbox.hide()
        else:
            self.leftbox.show()
        self.sbar = not self.sbar
        # Resize the image if necessary
        if not self.user_zoomed and self.paths and not self.thumbnail_toggled:
            self.zoom_to(0)

    def manipulated_images(self, message):
        """ Returns the images which should be manipulated - either the
            currently focused one or all marked images """
        images = []
        # Add the image shown
        if not self.marked and not self.thumbnail_toggled:
            if self.library_focused:
                images.append(os.path.abspath(self.files[self.treepos]))
            else:
                images.append(self.paths[self.index])
        # Add all marked images
        else:
            images = self.marked
            if len(images) == 1:
                err = "%s %d marked image" % (message, len(images))
            else:
                err = "%s %d marked images" % (message, len(images))
            self.err_message(err)
        # Delete all thumbnails of manipulated images
        thumbdir = os.path.expanduser("~/.vimiv/Thumbnails")
        thumbnails = os.listdir(thumbdir)
        for im in images:
            thumb = ".".join(im.split(".")[:-1]) + ".thumbnail" + ".png"
            thumb = os.path.basename(thumb)
            if thumb in thumbnails:
                thumb = os.path.join(thumbdir, thumb)
                shutil.os.remove(thumb)

        return images

    def rotate(self, cwise):
        try:
            cwise = int(cwise)
            images = self.manipulated_images("Rotated")
            cwise = cwise % 4
            # Rotate the image shown
            if self.paths[self.index] in images:
                self.pixbufOriginal = self.pixbufOriginal.rotate_simple(
                    (90 * cwise))
                self.update_image(False)
            # Rotate all files in external thread
            rotate_thread = Thread(target=self.thread_for_rotate, args=(images,
                                                                        cwise))
            rotate_thread.start()
        except:
            self.err_message("Warning: Object cannot be rotated")

    def thread_for_rotate(self, images, cwise):
        """ Rotate all image files in an extra thread """
        try:
            imageactions.rotate_file(images, cwise)
            if self.thumbnail_toggled:
                for image in images:
                    self.thumb_reload(image, self.paths.index(image))
        except:
            self.err_message("Error: Rotation of file failed")

    def flip(self, dir):
        try:
            dir = int(dir)
            images = self.manipulated_images("Flipped")
            # Flip the image shown
            if self.paths[self.index] in images:
                self.pixbufOriginal = self.pixbufOriginal.flip(dir)
                self.update_image(False)
            # Flip all files in an extra thread
            flip_thread = Thread(target=self.thread_for_flip, args=(images,
                                                                    dir))
            flip_thread.start()
        except:
            self.err_message("Warning: Object cannot be flipped")

    def thread_for_flip(self, images, horizontal):
        """ Flip all image files in an extra thread """
        try:
            imageactions.flip_file(images, horizontal)
            if self.thumbnail_toggled:
                for image in images:
                    self.thumb_reload(image, self.paths.index(image))
        except:
            self.err_message("Error: Flipping of file failed")

    def rotate_auto(self):
        """ This function autorotates all pictures in the current pathlist """
        amount, method = imageactions.autorotate(self.paths)
        if amount:
            self.move_index(True, False, 0)
            message = "Autorotated %d image(s) using %s." % (amount, method)
        else:
            message = "No image rotated. Tried using %s." % (method)
        self.err_message(message)


    def manipulate(self):
        """ Starts a toolbar with basic image manipulation """
        # A vbox in which everything gets packed
        self.hboxman = Gtk.HBox(spacing=5)
        self.hboxman.connect("key_press_event", self.handle_key_press,
                             "MANIPULATE")

        # A list to save the changes being done
        self.manipulations = [1, 1, 1, False]

        # Sliders
        self.scale_bri = Gtk.HScale()
        self.scale_bri.connect("value-changed", self.value_slider, "bri")
        self.scale_con = Gtk.HScale()
        self.scale_con.connect("value-changed", self.value_slider, "con")
        self.scale_sha = Gtk.HScale()
        self.scale_sha.connect("value-changed", self.value_slider, "sha")

        # Set some properties
        for scale in [self.scale_bri, self.scale_con, self.scale_sha]:
            scale.set_range(-127, 127)
            scale.set_size_request(120, 20)
            scale.set_value(0)
            scale.set_digits(0)

        # Labels
        bri_label = Gtk.Label()
        bri_label.set_markup("\n<b>Bri</b>")
        con_label = Gtk.Label()
        con_label.set_markup("\n<b>Con</b>")
        sha_label = Gtk.Label()
        sha_label.set_markup("\n<b>Sha</b>")

        # Buttons
        button_yes = Gtk.Button(label="Accept")
        button_yes.connect("clicked", self.button_clicked, True)
        button_yes.set_size_request(80, 20)
        button_no = Gtk.Button(label="Cancel")
        button_no.connect("clicked", self.button_clicked, False)
        button_no.set_size_request(80, 20)
        button_opt = Gtk.Button(label="Optimize")
        button_opt.connect("clicked", self.button_opt_clicked)
        button_opt.set_size_request(80, 20)

        # Pack everything into the box
        for item in [bri_label, self.scale_bri, con_label, self.scale_con,
                     sha_label, self.scale_sha, button_opt, button_yes,
                     button_no]:
            self.hboxman.add(item)

    def toggle_manipulate(self):
        if self.manipulate_toggled:
            self.manipulate_toggled = False
            self.hboxman.hide()
            self.scrolled_win.grab_focus()
            self.update_info()
        elif self.paths and not(self.thumbnail_toggled or self.library_focused):
            try:
                self.pixbufOriginal.is_static_image()
                self.err_message("Manipulating Gifs is not supported")
            except:
                self.manipulate_toggled = True
                self.hboxman.show()
                self.scale_bri.grab_focus()
                self.update_info()
        else:
            if self.thumbnail_toggled:
                self.err_message("Manipulate not supported in thumbnail mode")
            elif self.library_focused:
                self.err_message("Manipulate not supported in library")
            else:
                self.err_message("No image open to edit")

    def manipulate_image(self, real=""):
        """ Apply the actual changes defined by the following actions """
        if real:  # To the actual image?
            orig, out = real, real
        # A thumbnail for higher responsiveness
        elif "-EDIT" not in self.paths[self.index]:
            im = Image.open(self.paths[self.index])
            out = "-EDIT.".join(self.paths[self.index].rsplit(".", 1))
            orig = out.replace("EDIT", "EDIT-ORIG")
            im.thumbnail(self.imsize, Image.ANTIALIAS)
            imageactions.save_image(im, out)
            self.paths[self.index] = out
            # Save the original to work with
            imageactions.save_image(im, orig)
        else:
            out = self.paths[self.index]
            orig = out.replace("EDIT", "EDIT-ORIG")
        # Apply all manipulations
        if imageactions.manipulate_all(orig, out, self.manipulations):
            self.err_message("Optimize failed. Is imagemagick installed?")
        # Reset optimize so it isn't repeated all the time
        self.manipulations[3] = False

        # Show the edited image
        self.image.clear()
        self.pixbufOriginal = GdkPixbuf.PixbufAnimation.new_from_file(out)
        self.pixbufOriginal = self.pixbufOriginal.get_static_image()
        if not self.toggle_fullscreen.window_is_fullscreen:
            self.imsize = self.image_size()
        self.zoom_percent = self.get_zoom_percent()
        self.update_image()

    def value_slider(self, slider, name):
        """ Function for the brightness/contrast sliders """
        val = slider.get_value()
        val = (val + 127) / 127
        # Change brightness, contrast or sharpness
        if name == "bri":
            self.manipulations[0] = val
        elif name == "con":
            self.manipulations[1] = val
        else:
            self.manipulations[2] = val
        # Run the manipulation function
        self.manipulate_image()

    def focus_slider(self, man):
        """ Focuses one of the three sliders """
        if man == "bri":
            self.scale_bri.grab_focus()
        elif man == "con":
            self.scale_con.grab_focus()
        else:
            self.scale_sha.grab_focus()

    def change_slider(self, dec, large):
        """ Changes the value of the currently focused slider """
        for scale in [self.scale_bri, self.scale_con, self.scale_sha]:
            if scale.is_focus():
                val = scale.get_value()
                if self.num_str:
                    step = int(self.num_str)
                    self.num_str = ""
                elif large:
                    step = 10
                else:
                    step = 1
                if dec:
                    val -= step
                else:
                    val += step
                scale.set_value(val)

    def button_clicked(self, widget, accept=False):
        """ Finishes manipulate mode """
        # Reload the real images if changes were made
        if "EDIT" in self.paths[self.index]:
            out = self.paths[self.index]             # manipulated thumbnail
            orig = out.replace("EDIT", "EDIT-ORIG")  # original thumbnail
            path = out.replace("-EDIT", "")          # real file
            # Edit the actual file if yes
            if accept:
                self.manipulate_image(path)
            # Reset all the manipulations
            self.manipulations = [1, 1, 1, False]
            for scale in [self.scale_bri, self.scale_con, self.scale_sha]:
                scale.set_value(0)
            # Remove the thumbnail files used
            os.remove(out)
            os.remove(orig)
            # Show the original image
            self.image.clear()
            self.pixbufOriginal = GdkPixbuf.PixbufAnimation.new_from_file(path)
            self.pixbufOriginal = self.pixbufOriginal.get_static_image()
            self.paths[self.index] = path
            if not self.toggle_fullscreen.window_is_fullscreen:
                self.imsize = self.image_size()
            self.zoom_percent = self.get_zoom_percent()
            self.update_image()
        # Done
        self.toggle_manipulate()
        self.update_info()

    def button_opt_clicked(self, widget):
        """ Sets optimize to True and runs the manipulation """
        self.manipulations[3] = True
        self.manipulate_image()

    def toggle_animation(self):
        if self.paths and not self.thumbnail_toggled:
            self.animation_toggled = not self.animation_toggled
            self.update_image()

    def thumbnails(self):
        """ Creates the Gtk elements necessary for thumbnail mode, fills them
        and focuses the iconview """
        thumblist, errtuple = imageactions.thumbnails_create(self.paths,
                                                             self.thumbsize)
        self.errorpos = errtuple[0]
        if self.errorpos:
            failed_files = ", ".join(errtuple[1])
            self.err_message("Thumbnail creation for %s failed" %(failed_files))

        # Create the liststore and iconview
        self.liststore = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        self.iconview = Gtk.IconView.new()
        self.iconview.connect("item-activated", self.iconview_clicked)
        self.iconview.connect("key_press_event", self.handle_key_press,
                              "THUMBNAIL")
        self.iconview.set_model(self.liststore)
        self.columns = int(self.imsize[0]/(self.thumbsize[0]+30))
        self.iconview.set_spacing(0)
        self.iconview.set_columns(self.columns)
        self.iconview.set_item_width(5)
        self.iconview.set_item_padding(10)
        self.iconview.set_pixbuf_column(0)
        self.iconview.set_border_width(1)
        self.iconview.set_markup_column(1)

        # Add all thumbnails to the liststore
        for i, thumb in enumerate(thumblist):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(thumb)
            name = os.path.basename(thumb).split(".")[0]
            if self.paths[i] in self.marked:
                name = name + " [*]"
            self.liststore.append([pixbuf, name])

        # Draw the icon view instead of the image
        self.viewport.remove(self.image)
        self.viewport.add(self.iconview)
        # Show the window
        self.iconview.show()
        self.thumbnail_toggled = True
        # Focus the current immage
        self.iconview.grab_focus()
        self.thumbpos = (self.index) % len(self.paths)
        for i in self.errorpos:
            if self.thumbpos > i:
                self.thumbpos -= 1
        curpath = Gtk.TreePath.new_from_string(str(self.thumbpos))
        self.iconview.select_path(curpath)
        curthing = self.iconview.get_cells()[0]
        self.iconview.set_cursor(curpath, curthing, False)

    def iconview_clicked(self, w, count):
        # Move to the current position if the iconview is clicked
        self.toggle_thumbnail()
        count = count.get_indices()[0] + 1
        self.num_clear()
        for i in self.errorpos:
            if count > i:
                count += 1
        self.num_str = str(count)
        self.move_pos()

    def toggle_thumbnail(self):
        if self.thumbnail_toggled:
            self.viewport.remove(self.iconview)
            self.viewport.add(self.image)
            self.update_image()
            self.scrolled_win.grab_focus()
            self.thumbnail_toggled = False
        elif self.paths:
            self.thumbnails()
            self.timer_id = GLib.timeout_add(1, self.scroll_to_thumb)
            if self.library_focused:
                self.treeview.grab_focus()
            if self.manipulate_toggled:
                self.toggle_manipulate()
        else:
            self.err_message("No open image")
        # Update info for the current mode
        if not self.errorpos:
            self.update_info()

    def thumb_reload(self, thumb, index, reload_image=True):
        """ Reloads the thumbnail of manipulated images """
        for i in self.errorpos:
            if index > i:
                index -= 1
        iter = self.liststore.get_iter(index)
        self.liststore.remove(iter)
        try:
            if reload_image:
                thumblist, errlist = imageactions.thumbnails_create([thumb])
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(thumblist[0])
            name = os.path.basename(thumblist[0]).split(".")[0]
            if thumb in self.marked:
                name = name + " [*]"
            self.liststore.insert(index, [pixbuf, name])
            path = Gtk.TreePath.new_from_string(str(self.thumbpos))
            self.iconview.select_path(path)
            curthing = self.iconview.get_cells()[0]
            self.iconview.set_cursor(path, curthing, False)
        except:
            self.err_message("Reload of manipulated thumbnails failed ")

    def scroll_to_thumb(self):
        """ Function which scrolls to the currently selected thumbnail """
        # TODO
        scrollamount = int(self.thumbpos / self.columns) * self.thumbsize[1]
        Gtk.Adjustment.set_step_increment(
            self.viewport.get_vadjustment(), scrollamount)
        self.scrolled_win.emit('scroll-child',
                               Gtk.ScrollType.STEP_FORWARD, False)

    def get_zoom_percent(self, zWidth=False, zHeight=False):
        """ returns the current zoom factor """
        # Size of the file
        pboWidth = self.pixbufOriginal.get_width()
        pboHeight = self.pixbufOriginal.get_height()
        pboScale = pboWidth / pboHeight
        # Size of the image to be shown
        wScale = self.imsize[0] / self.imsize[1]
        stickout = zWidth | zHeight

        # Image is completely shown and user doesn't want overzoom
        if (pboWidth < self.imsize[0] and pboHeight < self.imsize[1] and
                not (stickout or self.toggle_vars.overzoom)):
            return 1
        # "Portrait" image
        elif (pboScale < wScale and not stickout) or zHeight:
            return self.imsize[1] / pboHeight
        # "Panorama/landscape" image
        else:
            return self.imsize[0] / pboWidth

    def update_image(self, update_info=True, update_gif=True):
        """ Show the final image """
        if not self.paths:
            return
        pboWidth = self.pixbufOriginal.get_width()
        pboHeight = self.pixbufOriginal.get_height()

        try:  # If possible scale the image
            pbfWidth = int(pboWidth * self.zoom_percent)
            pbfHeight = int(pboHeight * self.zoom_percent)
            # Rescaling of svg
            ending = os.path.basename(self.paths[self.index]).split(".")[-1]
            if ending == "svg" and self.toggle_vars.rescale_svg:
                pixbufFinal = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    self.paths[self.index], -1, pbfHeight, True)
            else:
                pixbufFinal = self.pixbufOriginal.scale_simple(
                    pbfWidth, pbfHeight, GdkPixbuf.InterpType.BILINEAR)
            self.image.set_from_pixbuf(pixbufFinal)
        except:  # If not it must me an animation
            # TODO actual pause and play of Gifs
            self.zoom_percent = 1
            if update_gif:
                if not self.animation_toggled:
                    self.image.set_from_animation(self.pixbufOriginal)
                else:
                    pixbufFinal = self.pixbufOriginal.get_static_image()
                    self.image.set_from_pixbuf(pixbufFinal)
        # Update the statusbar if required
        if update_info:
            self.update_info()

    def update_info(self):
        """ Update the statusbar and the window title """
        # Left side
        try:
            # Directory if library is focused
            if self.library_focused:
                self.left_label.set_text(os.path.abspath("."))
            # Position, name and thumbnail size in thumb mode
            elif self.thumbnail_toggled:
                name = os.path.basename(self.paths[self.thumbpos])
                message = "{0}/{1}  {2}  {3}".format(self.thumbpos+1,
                    len(self.paths), name, self.thumbsize)
                self.left_label.set_text(message)
            # Image info in image mode
            else:
                name = os.path.basename(self.paths[self.index])
                message = "{0}/{1}  {2}  [{3:.0f}%]".format(self.index+1,
                    len(self.paths), name, self.zoom_percent*100)
                self.left_label.set_text(message)
        except:
            self.left_label.set_text("No open images")
        # Center
        if not (self.thumbnail_toggled or self.library_focused) and self.paths:
            mark = "[*]" if self.paths[self.index] in self.marked else ""
        else:
            mark = ""
        if self.slideshow:
            slideshow = "[slideshow - {0:.1f}s]".format(self.slideshow_delay)
        else:
            slideshow = ""
        message = "{0}  {1}".format(mark, slideshow)
        self.center_label.set_text(message)
        # Right side
        mode = self.get_mode()
        message = "{0:15}  {1:4}".format(mode, self.num_str)
        self.right_label.set_markup(message)
        # Window title
        try:
            name = os.path.basename(self.paths[self.index])
            self.set_title("vimiv - "+name)
        except:
            self.set_title("vimiv")
        # Size of statusbar for resizing image
        self.statusbar_size = self.labelbox.get_allocated_height()

    def get_mode(self):
        """ Returns which widget is currently focused """
        if self.library_focused:
            return "<b>-- LIBRARY --</b>"
        elif self.manipulate_toggled:
            return "<b>-- MANIPULATE --</b>"
        elif self.thumbnail_toggled:
            return "<b>-- THUMBNAIL --</b>"
        else:
            return "<b>-- IMAGE --</b>"

    def image_size(self):
        """ Returns the size of the image depending on what other widgets
        are visible and if fullscreen or not """
        if self.toggle_fullscreen.window_is_fullscreen:
            size = self.screensize
        else:
            size = self.get_size()
        if self.library_toggled:
            size = (size[0] - self.library_width, size[1])
        if not self.sbar:
            size = (size[0], size[1] - self.statusbar_size - 24)
        return size

    def zoom_delta(self, delta):
        """ Zooms the image by delta percent """
        if self.thumbnail_toggled:
            return
        try:
            self.zoom_percent = self.zoom_percent * (1 + delta)
            # Catch some unreasonable zooms
            if (self.pixbufOriginal.get_height()*self.zoom_percent < 5 or
                    self.pixbufOriginal.get_height()*self.zoom_percent >
                    self.screensize[0]*5):
                raise ValueError
            self.user_zoomed = True
            self.update_image(update_gif=False)
        except:
            self.zoom_percent = self.zoom_percent / (1 + delta)
            self.err_message("Warning: Object cannot be zoomed (further)")

    def zoom_to(self, percent, zWidth=False, zHeight=False):
        """ Zooms to a given percentage """
        if self.thumbnail_toggled:
            return
        before = self.zoom_percent
        self.user_zoomed = False
        # Catch user zooms
        if self.num_str:
            self.user_zoomed = True
            percent = self.num_str
            # If prefixed with a zero invert value
            try:
                if percent[0] == "0":
                    percent = 1/float(percent[1:])
                else:
                    percent = float(percent)
            except:
                self.err_message("Error: Zoom percentage not parseable")
                return
            self.num_str = ""
        try:
            self.imsize = self.image_size()
            self.zoom_percent = (percent if percent
                                 else self.get_zoom_percent(zWidth, zHeight))
            # Catch some unreasonable zooms
            if (self.pixbufOriginal.get_height()*self.zoom_percent < 5 or
                    self.pixbufOriginal.get_height()*self.zoom_percent >
                    self.screensize[0]*5):
                self.zoom_percent = before
                raise ValueError
            self.update_image(update_gif=False)
        except:
            self.err_message("Warning: Object cannot be zoomed (further)")

    def center_window(self):
        """ Centers the image in the current window """
        # Don't do anything if no images are open
        if not self.paths or self.thumbnail_toggled:
            return
        # Vertical
        pboHeight = self.pixbufOriginal.get_height()
        vadj = self.viewport.get_vadjustment().get_value()
        vact = self.zoom_percent * pboHeight
        diff = vact - self.imsize[1]
        if diff > 0:
            toscroll = (diff - 2*vadj) / 2
            Gtk.Adjustment.set_step_increment(
                self.viewport.get_vadjustment(), toscroll)
            self.scrolled_win.emit('scroll-child',
                                   Gtk.ScrollType.STEP_FORWARD, False)
            # Reset scrolling
            Gtk.Adjustment.set_step_increment(self.viewport.get_vadjustment(),
                                              100)
        # Horizontal
        pboWidth = self.pixbufOriginal.get_width()
        hadj = self.viewport.get_hadjustment().get_value()
        hact = self.zoom_percent * pboWidth
        if diff > 0:
            diff = hact - self.imsize[0]
            toscroll = (diff - 2*hadj) / 2
            Gtk.Adjustment.set_step_increment(
                self.viewport.get_hadjustment(), toscroll)
            self.scrolled_win.emit('scroll-child',
                                   Gtk.ScrollType.STEP_FORWARD, True)
            # Reset scrolling
            Gtk.Adjustment.set_step_increment(self.viewport.get_hadjustment(),
                                              100)

    def move_index(self, forward=True, key=False, delta=1, force=False):
        """ Move by delta in the path """
        # Check if an image is opened
        if not self.paths or self.thumbnail_toggled:
            return
        # Check if image has been edited
        if self.check_for_edit(force):
            return
        # Check for prepended numbers
        if key and self.num_str:
            delta *= int(self.num_str)
        # Forward or backward
        if not forward:
            delta *= -1
        self.index = (self.index + delta) % len(self.paths)
        self.user_zoomed = False

        # Reshuffle on wrap-around
        if self.shuffle and self.index is 0 and delta > 0:
            shuffle(self.paths)

        path = self.paths[self.index]
        try:
            if not os.path.exists(path):
                self.delete()
                return
            else:
                self.pixbufOriginal = GdkPixbuf.PixbufAnimation.new_from_file(
                    path)
            if self.pixbufOriginal.is_static_image():
                self.pixbufOriginal = self.pixbufOriginal.get_static_image()
                self.imsize = self.image_size()
                self.zoom_percent = self.get_zoom_percent()
            else:
                self.zoom_percent = 1
            # If one simply reloads the file the info shouldn't be updated
            if delta:
                self.update_image()
            else:
                self.update_image(False)

        except GLib.Error:  # File not accessible
            self.paths.remove(path)
            self.err_message("Error: file not accessible")
            self.move_pos(False)

        self.num_clear()
        return True  # for the slideshow

    def move_pos(self, forward=True, force=False):
        """ Move to pos in path """
        # Check if image has been edited (might be gone by now -> try)
        try:
            if self.check_for_edit(force):
                raise ValueError
        except:
            return
        max = len(self.paths)
        if self.thumbnail_toggled:
            current = self.thumbpos % len(self.paths)
            max = max - len(self.errorpos)
        else:
            current = (self.index) % len(self.paths)
        # Move to definition by keys or end/beg
        if self.num_str:
            pos = int(self.num_str)
        elif forward:
            pos = max
        else:
            pos = 1
        # Catch exceptions
        try:
            current = int(current)
            max = int(max)
            if pos < 0 or pos > max:
                raise ValueError
        except:
            self.err_message("Warning: Unsupported index")
            return False
        # Do the math and move
        dif = pos - current - 1
        if self.thumbnail_toggled:
            pos -= 1
            self.thumbpos = pos
            path = Gtk.TreePath.new_from_string(str(pos))
            self.iconview.select_path(path)
            curthing = self.iconview.get_cells()[0]
            self.iconview.set_cursor(path, curthing, False)
            if forward:
                self.scrolled_win.emit('scroll-child',
                                       Gtk.ScrollType.END, False)
            else:
                self.scrolled_win.emit('scroll-child',
                                       Gtk.ScrollType.START, False)
        else:
            self.move_index(True, False, dif)
            self.user_zoomed = False

        self.num_clear()
        return True

    def num_append(self, num):
        """ Adds a new char to the num_str """
        self.num_str += num
        self.timer_id = GLib.timeout_add_seconds(1, self.num_clear)
        self.update_info()

    def num_clear(self):
        """ Clears the num_str """
        self.num_str = ""
        self.update_info()

    def recursive_search(self, dir):
        """ Searchs a given directory recursively for images """
        self.paths = self.filelist_create(dir)
        for path in self.paths:
            path = os.path.join(dir, path)
            if os.path.isfile(path):
                self.paths.append(path)
            else:
                self.recursive_search(path)

    def mark(self):
        """ Marks the current image """
        # Check which image
        if self.library_focused:
            current = os.path.abspath(self.files[self.treepos])
        elif self.thumbnail_toggled:
            index = self.thumbpos
            pathindex = index
            # Remove errors and reload the thumb_name
            for i in self.errorpos:
                if pathindex >= i:
                    pathindex += 1
            current = self.paths[pathindex]
        else:
            current = self.paths[self.index]
        # Toggle the mark
        if os.path.isfile(current):
            if current in self.marked:
                self.marked.remove(current)
            else:
                self.marked.append(current)
            self.mark_reload(False, [current])
        else:
            self.err_message("Marking directories is not supported")

    def toggle_mark(self):
        if self.marked:
            self.marked_bak = self.marked
            self.marked = []
        else:
            self.marked, self.marked_bak = self.marked_bak, self.marked
        to_reload = self.marked + self.marked_bak
        self.mark_reload(False, to_reload)

    def mark_all(self):
        """ Marks all images """
        # Get the correct filelist
        if self.library_focused:
            files = []
            for fil in self.files:
                files.append(os.path.abspath(fil))
        elif self.paths:
            files = self.paths
        else:
            self.err_message("No image to mark")
        # Add all to the marks
        for fil in files:
            if os.path.isfile(fil) and fil not in self.marked:
                self.marked.append(fil)
        self.mark_reload()

    def mark_between(self):
        """ Marks all images between the two last selections """
        # Check if there are enough marks
        if len(self.marked) < 2:
            self.err_message("Not enough marks")
            return
        start = self.marked[-2]
        end = self.marked[-1]
        # Get the correct filelist
        if self.library_focused:
            files = []
            for fil in self.files:
                files.append(os.path.abspath(fil))
        elif self.paths:
            files = self.paths
        else:
            self.err_message("No image to mark")
        # Find the images to mark
        for i, image in enumerate(files):
            if image == start:
                start = i
            elif image == end:
                end = i
        for i in range(start+1, end):
            self.marked.insert(-1, files[i])
        self.mark_reload()

    def mark_reload(self, all=True, current=None):
        self.update_info()
        # Update lib
        if self.library_toggled:
            self.remember_pos(".", self.treepos)
            self.reload(".")
            self.update_info()
        if self.thumbnail_toggled:
            for i, image in enumerate(self.paths):
                if all or image in current:
                    self.thumb_reload(image, i, False)

    def library(self):
        """ Starts the library browser """
        # Librarybox
        self.boxlib = Gtk.HBox()
        # Set up the self.grid in which the file info will be positioned
        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        if self.paths or not self.expand_lib:
            self.grid.set_size_request(self.library_width-self.border_width, 10)
        else:
            self.grid.set_size_request(self.winsize[0], 10)
        # A simple border
        if self.border_width:
            border = Gtk.Box()
            border.set_size_request(self.border_width, 0)
            border.modify_bg(Gtk.StateType.NORMAL, self.border_color)
            self.boxlib.pack_end(border, False, False, 0)
        # Entering content
        self.scrollable_treelist = Gtk.ScrolledWindow()
        self.scrollable_treelist.set_vexpand(True)
        self.grid.attach(self.scrollable_treelist, 0, 0, 4, 10)
        # Pack everything
        self.boxlib.pack_start(self.grid, True, True, 0)
        # Call the function to create the treeview
        self.treeview_create()
        self.scrollable_treelist.add(self.treeview)

    def toggle_library(self):
        """ Toggles the library """
        if self.library_toggled:
            self.remember_pos(os.path.abspath("."), self.treepos)
            self.boxlib.hide()
            self.animation_toggled = False  # Now play Gifs
            self.library_toggled = not self.library_toggled
            self.focus_library(False)
        else:
            self.boxlib.show()
            if not self.paths:
                self.scrolled_win.hide()
            else:  # Try to focus the current image in the library
                path = os.path.dirname(self.paths[self.index])
                if path == os.path.abspath("."):
                    self.treeview.set_cursor(Gtk.TreePath([self.index]),
                                             None, False)
                    self.treepos = self.index
            self.animation_toggled = True  # Do not play Gifs with the lib
            self.library_toggled = not self.library_toggled
            self.focus_library(True)
            # Markings and other stuff might have changed
            self.reload(os.path.abspath("."))
        if not self.user_zoomed and self.paths:
            self.zoom_to(0)  # Always rezoom the image
        #  Change the toggle state of animation
        self.update_image()

    def focus_library(self, library=True):
        if library:
            if not self.library_toggled:
                self.toggle_library()
            self.treeview.grab_focus()
            self.library_focused = True
        else:
            self.scrolled_win.grab_focus()
            self.library_focused = False
        # Update info for the current mode
        self.update_info()

    def treeview_create(self, search=False):
        # The search parameter is necessary to highlight searches after a search
        # and to delete search items if a new directory is entered
        if not search:
            self.reset_search()
        # Tree View
        current_file_filter = self.filestore(self.datalist_create())
        self.treeview = Gtk.TreeView.new_with_model(current_file_filter)
        # Needed for the movement keys
        self.treepos = 0
        self.treeview.set_enable_search(False)
        # Select file when row activated
        self.treeview.connect("row-activated", self.file_select, True)
        # Handle key events
        self.treeview.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.treeview.connect("key_press_event", self.handle_key_press,
                              "LIBRARY")
        # Add the columns
        for i, name in enumerate(["Num", "Name", "Size", "M"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(name, renderer, markup=i)
            if name == "Name":
                column.set_expand(True)
                column.set_max_width(20)
            self.treeview.append_column(column)

    def filestore(self, datalist):
        """ Returns the file_filter for the tree view """
        # Filelist in a liststore model
        self.filelist = Gtk.ListStore(int, str, str, str)
        # Numerate each filename
        count = 0
        for data in datalist:
            count += 1
            data.insert(0, count)
            # The data into the filelist
            self.filelist.append(data)

        current_file_filter = self.filelist.filter_new()
        return current_file_filter

    def datalist_create(self):
        """ Returns the list of data for the file_filter model """
        self.datalist = list()
        self.files = self.filelist_create()
        # Remove unsupported files if one isn't in the tagdir
        if os.path.abspath(".") != tagdir:
            self.files = [
                possible_file
                for possible_file in self.files
                if (mimetypes.guess_type(possible_file)[0] in types or
                    os.path.isdir(possible_file))]
        # Add all the supported files
        for fil in self.files:
            markup_string = fil
            size = self.filesize[fil]
            marked = ""
            if os.path.abspath(fil) in self.marked:
                marked = "[*]"
            if os.path.isdir(fil):
                markup_string = "<b>" + markup_string + "</b>"
            if fil in self.search_names:
                markup_string = self.markup + markup_string + '</span>'
            self.datalist.append([markup_string, size, marked])

        return self.datalist

    def filelist_create(self, dir="."):
        """ Create a filelist from all files in dir """
        # Get data from ls -lh and parse it correctly
        if self.show_hidden:
            p = Popen(['ls', '-lAh', dir], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        else:
            p = Popen(['ls', '-lh', dir], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        data, err = p.communicate()
        data = data.decode(encoding='UTF-8').split("\n")[1:-1]
        files = []
        self.filesize = {}
        for fil in data:
            fil = fil.split()
            # Catch stupid filenames with whitespaces
            filename = " ".join(fil[8:])
            files.append(filename)
            # Number of images in dir as filesize
            if os.path.isdir(filename):
                try:
                    subfiles = os.listdir(filename)
                    subfiles = [
                        possible_file
                        for possible_file in subfiles
                        if mimetypes.guess_type(possible_file)[0] in types]
                    self.filesize[filename] = str(len(subfiles))
                except:
                    self.filesize[filename] = "N/A"
            else:
                self.filesize[filename] = fil[4]

        return files

    def file_select(self, alternative, count, b, close):
        """ Focus image or open dir for activated file in library """
        if isinstance(count, str):
            fil = count
        else:
            count = count.get_indices()[0]
            fil = self.files[count]
            self.remember_pos(os.path.abspath("."), count)
        # Catch symbolic links
        if "->" in fil:
            fil = "".join(fil.split(">")[:-1]).split(" ")[:-1]
            fil = "".join(fil)
            fil = os.path.realpath(fil)
            self.move_up(os.path.dirname(fil))
        # Tags
        if os.path.abspath(".") == tagdir:
            self.tag_handler.tag_load(fil)
            return
        # Rest
        if os.path.isdir(fil):  # Open the directory
            self.move_up(fil)
        else:  # Focus the image and populate a new list from the dir
            if self.paths and fil in self.paths[self.index]:
                close = True  # Close if file selected twice
            path = 0  # Reload the path, could have changed (symlinks)
            for f in self.files:
                if f == fil:
                    break
                else:
                    path += 1
            self.treeview.set_cursor(Gtk.TreePath(path), None, False)
            self.treepos = path
            self.paths, self.index = populate(self.files)
            if self.paths:
                self.grid.set_size_request(self.library_width-self.border_width, 10)
                self.scrolled_win.show()
            # Show the selected file, if thumbnail toggled go out
            if self.thumbnail_toggled:
                self.toggle_thumbnail()
                self.treeview.grab_focus()
            self.move_index(delta=count)
            # Close the library depending on key and repeat
            if close:
                self.toggle_library()
                self.update_image()

    def move_up(self, dir="..", start=False):
        """ move (up/to) dir in the library """
        try:
            curdir = os.path.abspath(".")
            os.chdir(dir)
            if not start:
                self.reload(os.path.abspath("."), curdir)
        except:
            self.err_message("Error: directory not accessible")

    def remember_pos(self, dir, count):
        """ Write the current position in dir to the dir_pos dictionary """
        self.dir_pos[dir] = count

    def reload(self, dir, curdir="", search=False):
        """ Reloads the treeview """
        self.scrollable_treelist.remove(self.treeview)
        self.treeview_create(search)
        self.scrollable_treelist.add(self.treeview)
        self.focus_library(True)
        # Check if there is a saved position
        if dir in self.dir_pos.keys():
            self.treeview.set_cursor(Gtk.TreePath(self.dir_pos[dir]),
                                     None, False)
            self.treepos = self.dir_pos[dir]
        # Check if the last directory is in the current one
        else:
            curdir = os.path.basename(curdir)
            for i, fil in enumerate(self.files):
                if curdir == fil:
                    self.treeview.set_cursor(Gtk.TreePath([i]), None, False)
                    self.treepos = i
                    break
        self.boxlib.show_all()

    def move_pos_lib(self, forward=True):
        """ Move to pos in lib """
        max = len(self.files) - 1
        if self.num_str:
            pos = int(self.num_str) - 1
            if pos < 0 or pos > max:
                self.err_message("Warning: Unsupported index")
                return False
        elif forward:
            pos = max
        else:
            pos = 0
        try:
            self.treepos = pos
            self.treeview.set_cursor(Gtk.TreePath(self.treepos), None, False)
        except:
            self.err_message("Warning: Unsupported index")
            return False

        self.num_clear()
        return True

    def resize_lib(self, val=None, inc=True):
        """ Resize the library and update the image if necessary """
        if isinstance(val, int):
            # The default 0 passed by arguments
            if not val:
                val = 300
            self.library_width = self.library_default_width
        elif val:  # A non int was given as library width
            self.err_message("Library width must be an integer")
            return
        elif inc:
            self.library_width += 20
        else:
            self.library_width -= 20
        # Set some reasonable limits to the library size
        if self.library_width > self.winsize[0]-200:
            self.library_width = self.winsize[0]-200
        elif self.library_width < 100:
            self.library_width = 100
        self.grid.set_size_request(self.library_width-self.border_width, 10)
        # Rezoom image
        if not self.user_zoomed and self.paths:
            self.zoom_to(0)

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self.reload('.')

    def auto_resize(self, w):
        """ Automatically resize image when window is resized """
        if self.get_size() != self.winsize:
            self.winsize = self.get_size()
            if self.paths and not self.user_zoomed:
                self.zoom_to(0)
            elif not self.paths and self.expand_lib:
                self.grid.set_size_request(self.winsize[0], 10)
            self.cmd_line_info.set_max_width_chars(self.winsize[0]/16)

    def reload_changes(self, dir, reload_path=True, pipe=False, input=None):
        """ Reload everything, meaning filelist in library and image """
        if (dir == os.path.abspath(".") and dir != tagdir and
                self.library_toggled):
            if self.treepos >= 0 and self.treepos <= len(self.files):
                self.remember_pos(dir, self.treepos)
            self.reload(dir)
        if self.paths and reload_path:
            pathdir = os.path.dirname(self.paths[self.index])
            files = sorted(os.listdir(pathdir))
            for i, fil in enumerate(files):
                files[i] = os.path.join(pathdir, fil)
            self.num_str = str(self.index + 1)  # Remember current pos
            self.paths = []
            self.paths, self.index = populate(files)
            self.move_pos()
            if self.expand_lib and not self.paths:
                self.grid.set_size_request(self.winsize[0], 10)
            if self.thumbnail_toggled:
                for i, image in self.paths:
                    self.thumb_reload(image, i, False)
        # Run the pipe
        if pipe:
            self.commandline.pipe(input)
        return False  # To stop the timer

    def history(self, down):
        """ Update the cmd_handler text with history """
        # Shortly disconnect the change signal
        self.cmd_line.disconnect_by_func(self.cmd_check_close)
        # Only parts of the history that match the entered text
        if not self.sub_history:
            substring = self.cmd_line.get_text()
            matchstr = '^(' + substring + ')'
            self.sub_history = [substring]
            for cmd in self.cmd_history:
                if re.match(matchstr, cmd):
                    self.sub_history.append(cmd)
        # Move and set the text
        if down:
            self.cmd_pos -= 1
        else:
            self.cmd_pos += 1
        self.cmd_pos = self.cmd_pos % (len(self.sub_history))
        self.cmd_line.set_text(self.sub_history[self.cmd_pos])
        self.cmd_line.set_position(-1)
        # Reconnect when done
        self.cmd_line.connect("changed", self.cmd_check_close)

    def focus_cmd_line(self):
        """ Open and focus the command line """
        # Colon for text
        self.cmd_line.set_text(":")
        # Show the statusbar
        if self.sbar:
            self.leftbox.show()
        # Remove old error messages
        self.update_info()
        # Show/hide the relevant stuff
        self.cmd_line_box.show()
        self.labelbox.hide()
        self.leftbox.set_border_width(10)
        # Remember what widget was focused before
        if self.library_focused:
            self.last_focused = "lib"
        elif self.manipulate_toggled:
            self.last_focused = "man"
        elif self.thumbnail_toggled:
            self.last_focused = "thu"
        else:
            self.last_focused = "im"
        self.cmd_line.grab_focus()
        self.cmd_line.set_position(-1)

    def cmd_line_leave(self):
        """ Close the command line """
        self.cmd_line_box.hide()
        self.labelbox.show()
        self.leftbox.set_border_width(12)
        # Remove all completions shown and the text currently inserted
        self.cmd_line_info.set_text("")
        self.cmd_line.set_text("")
        # Refocus the remembered widget
        if self.last_focused == "lib":
            self.focus_library(True)
        elif self.last_focused == "man":
            self.scale_bri.grab_focus()
        elif self.last_focused == "thu":
            self.iconview.grab_focus()
        else:
            self.scrolled_win.grab_focus()
        # Rehide the command line
        if self.sbar:
            self.leftbox.hide()

    def cmd_check_close(self, entry):
        """ Close the entry if the colon/slash is deleted """
        self.sub_history = []
        self.cmd_pos = 0
        text = entry.get_text()
        if not text or text[0] not in ":/":
            self.cmd_line_leave()

    def cmd_complete(self):
        """ Simple autocompletion for the command line """
        command = self.cmd_line.get_text()
        command = command.lstrip(":")
        # Strip prepending numbers
        numstr = ""
        while True:
            try:
                num = int(command[0])
                numstr += str(num)
                command = command[1:]
            except:
                break
        # Generate completion class and get completions
        commandlist = sorted(list(self.commands.keys()))
        completion = Completion(command, commandlist)
        output, compstr = completion.complete()

        # Set text
        self.cmd_line.set_text(output)
        self.cmd_line_info.set_text(compstr)
        self.cmd_line.set_position(-1)

        return True  # Deactivates default bindings (here for Tab)

    def clear(self, dir):
        """ Remove all files in dir (Trash or Thumbnails) """
        trashdir = os.path.join(os.path.expanduser("~/.vimiv"), dir)
        for fil in os.listdir(trashdir):
            fil = os.path.join(trashdir, fil)
            os.remove(fil)

    def cmd_edit(self, man, num="0"):
        """ Run the specified edit command """
        if not self.manipulate_toggled:
            if not self.paths:
                self.err_message("No image to manipulate")
                return
            else:
                self.toggle_manipulate()
        if man == "opt":
            self.button_opt_clicked("button_widget")
        else:
            self.focus_slider(man)
            self.num_str = num
            execstr = "self.scale_" + man + ".set_value(int(self.num_str))"
            exec(execstr)
        self.num_str = ""

    def cmd_search(self):
        """ Prepend search to the cmd_line and open it """
        self.focus_cmd_line()
        self.cmd_line.set_text("/")
        self.cmd_line.set_position(-1)

    def search(self, searchstr):
        """ Run a search on the appropriate filelist """
        if self.library_focused:
            paths = self.files
        else:
            paths = self.paths
        self.search_names = []
        self.search_positions = []
        self.search_pos = 0

        if self.search_case:
            for i, fil in enumerate(paths):
                if searchstr in fil:
                    self.search_names.append(fil)
                    self.search_positions.append(i)
        else:
            for i, fil in enumerate(paths):
                if searchstr.lower() in fil.lower():
                    self.search_names.append(fil)
                    self.search_positions.append(i)

        if self.library_focused:
            self.reload(".", search=True)

        # Move to first result or throw an error
        if self.search_names:
            self.search_move()
        else:
            self.err_message("No matching file")

    def search_move(self, index=0, forward=True):
        """ Move to the next/previous search """
        # Correct handling of index
        if self.num_str:
            index = int(self.num_str)
            self.num_str = ""
        if forward:
            self.search_pos += index
        else:
            self.search_pos -= index
        self.search_pos = self.search_pos % len(self.search_names)

        # Select file depending on library
        if self.library_toggled:
            if len(self.search_names) == 1:
                self.file_select("alt", self.search_names[self.search_pos],
                                "b", False)
            else:
                path = self.search_positions[self.search_pos]
                self.treeview.set_cursor(Gtk.TreePath(path), None, False)
                self.treepos = path
        else:
            self.num_str = str(self.search_positions[self.search_pos]+1)
            self.move_pos()

    def reset_search(self):
        """ Simply resets all search parameters to null """
        self.search_names = []
        self.search_positions = []
        self.search_pos = 0
        return

    def listdir_nohidden(self, path):
        """ Reimplementation of os.listdir which doesn't show hidden files """
        files = os.listdir(os.path.expanduser(path))
        for fil in files:
            if not fil.startswith("."):
                yield fil

    def format_files(self, string):
        """ Format the image names in the filelist according to a formatstring
            nicely numbering them """
        if not self.paths:
            self.err_message("No files in path")
            return

        # Check if exifdata is available and needed
        tofind = ("%" in string)
        if tofind:
            try:
                for fil in self.paths:
                    im = Image.open(fil)
                    exif = im._getexif()
                    if not (exif and 306 in exif):
                        raise AttributeError
            except:
                self.err_message("No exif data for %s available" % (fil))
                return

        for i, fil in enumerate(self.paths):
            ending = fil.split(".")[-1]
            num = "%03d" % (i+1)
            # Exif stuff
            if tofind:
                im = Image.open(fil)
                exif = im._getexif()
                date = exif[306]
                time = date.split()[1].split(":")
                date = date.split()[0].split(":")
                outstring = string.replace("%Y", date[0])  # year
                outstring = outstring.replace("%m", date[1])  # month
                outstring = outstring.replace("%d", date[2])  # day
                outstring = outstring.replace("%H", time[0])  # hour
                outstring = outstring.replace("%M", time[1])  # minute
                outstring = outstring.replace("%S", time[2])  # second
            else:
                outstring = string
            # Ending
            outstring += num + "." + ending
            shutil.move(fil, outstring)

        # Reload everything
        self.reload_changes(os.path.abspath("."), True)

    def handle_key_press(self, widget, event, window):
        keyval = event.keyval
        keyname = Gdk.keyval_name(keyval)
        shiftkeys = ["space", "Return", "Tab", "Escape", "BackSpace",
                     "Up", "Down", "Left", "Right"]
        # Check for Control (^), Mod1 (Alt) or Shift
        if event.get_state() & Gdk.ModifierType.CONTROL_MASK:
            keyname = "^" + keyname
        if event.get_state() & Gdk.ModifierType.MOD1_MASK:
            keyname = "Alt+".format(keyname)
        # Shift+ for all letters and for keys that don't support it
        if (event.get_state() & Gdk.ModifierType.SHIFT_MASK and
                (len(keyname) < 2 or keyname in shiftkeys)):
            keyname = "Shift+" + keyname.lower()
        try:  # Numbers for the num_str
            if window == "COMMAND":
                raise ValueError
            int(keyname)
            self.num_append(keyname)
            return True
        except:
            try:
                # Get the relevant keybindings for the window from the various
                # sections in the keys.conf file
                keys = self.keys[window]

                # Get the command to which the pressed key is bound
                func = keys[keyname]
                if "set " in func:
                    conf_args = []
                else:
                    func = func.split()
                    conf_args = func[1:]
                    func = func[0]
                # From functions dictionary get the actual vimiv command
                func = self.functions[func]
                args = func[1:]
                args.extend(conf_args)
                func = func[0]
                func(*args)
                return True  # Deactivates default bindings
            except:
                return False

    def main(self):
        if self.paths:
            # Move to the directory of the image
            if isinstance(self.paths, list):
                os.chdir(os.path.dirname(self.paths[self.index]))
            else:
                os.chdir(self.paths)
                self.paths = []

        # Screen
        screen = Gdk.Screen()
        self.screensize = [screen.width(), screen.height()]

        # Gtk window with general settings
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('destroy', Gtk.main_quit)
        self.connect("check-resize", self.auto_resize)
        self.set_icon_name("image-x-generic")

        # Box in which everything gets packed
        self.vbox = Gtk.VBox()
        # Horizontal Box with image and treeview
        self.hbox = Gtk.HBox(False, 0)
        self.add(self.vbox)
        # Scrollable window for the image
        self.scrolled_win = Gtk.ScrolledWindow()
        self.hbox.pack_end(self.scrolled_win, True, True, 0)
        self.vbox.pack_start(self.hbox, True, True, 0)

        # Viewport
        self.viewport = Gtk.Viewport()
        self.viewport.set_shadow_type(Gtk.ShadowType.NONE)
        self.scrolled_win.add(self.viewport)
        self.image = Gtk.Image()
        self.viewport.add(self.image)
        self.scrolled_win.connect("key_press_event",
                                  self.handle_key_press, "IMAGE")
        # Command line
        self.cmd_line_box = Gtk.HBox(False, 0)
        self.cmd_line = Gtk.Entry()
        self.cmd_line.connect("activate", self.commandline.cmd_handler)
        self.cmd_line.connect("key_press_event",
                              self.handle_key_press, "COMMAND")
        self.cmd_line.connect("changed", self.cmd_check_close)
        self.cmd_line_info = Gtk.Label()
        self.cmd_line_info.set_max_width_chars(self.winsize[0]/16)
        self.cmd_line_info.set_ellipsize(Pango.EllipsizeMode.END)
        self.cmd_line_box.pack_start(self.cmd_line, True, True, 0)
        self.cmd_line_box.pack_end(self.cmd_line_info, False, False, 0)

        # Statusbar on the bottom
        self.labelbox = Gtk.HBox(False, 0)
        # Two labels for two sides of statusbar and one in the middle for
        # additional info
        self.left_label = Gtk.Label()  # Position and image name
        self.left_label.set_justify(Gtk.Justification.LEFT)
        self.right_label = Gtk.Label()  # Mode and prefixed numbers
        self.right_label.set_justify(Gtk.Justification.RIGHT)
        self.center_label = Gtk.Label()  # Zoom, marked, slideshow, ...
        self.center_label.set_justify(Gtk.Justification.CENTER)
        self.labelbox.pack_start(self.left_label, False, False, 0)
        self.labelbox.pack_start(self.center_label, True, True, 0)
        self.labelbox.pack_end(self.right_label, False, False, 0)

        # Box with the statusbar and the command line
        self.leftbox = Gtk.VBox(False, 0)
        self.leftbox.pack_start(self.labelbox, False, False, 0)
        self.leftbox.pack_end(self.cmd_line_box, False, False, 0)
        self.leftbox.set_border_width(12)
        self.vbox.pack_end(self.leftbox, False, False, 0)

        # Size for resizing image
        self.statusbar_size = self.labelbox.get_allocated_height()

        # Treeview
        self.library()
        self.hbox.pack_start(self.boxlib, False, False, 0)

        # Manipulate Bar
        self.manipulate()
        self.vbox.pack_end(self.hboxman, False, False, 0)

        # Set the window size
        self.resize(self.winsize[0], self.winsize[1])

        self.show_all()
        # Hide the manipulate bar and the command line
        self.hboxman.hide()
        self.cmd_line_box.hide()

        # Show the image if an imagelist exists
        if self.paths:
            self.move_index(True, False, 0)
            # Show library at the beginning?
            if self.library_toggled:
                self.boxlib.show()
            else:
                self.boxlib.hide()
            self.scrolled_win.grab_focus()
            # Start in slideshow mode?
            if self.slideshow:
                self.slideshow = False
                self.toggle_slideshow()
            self.toggle_statusbar()
        # Just open the library if no paths were given
        else:
            self.slideshow = False  # Slideshow without paths makes no sense
            self.toggle_statusbar()
            self.focus_library(True)
            if self.expand_lib:
                self.grid.set_size_request(self.winsize[0], 10)
            self.err_message("No valid paths, opening library viewer")

        # Finally show the main window
        Gtk.main()
