import gi
gi.require_version('Gtk','3.0')
#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :
"""
Author: Jonas Wagner

Play it Slowly
Copyright (C) 2009 - 2015 Jonas Wagner

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import getopt
import mimetypes
import os
import sys

try:
    import json
except ImportError:
    import simplejson as json

import gi
gi.require_version('Gst', '1.0')

from gi.repository import Gtk, GObject, Gst, Gio, Gdk

Gst.init(None)

from playitslowly.pipeline import Pipeline

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# always enable button images

from playitslowly import myGtk
myGtk.install()


_ = lambda s: s # may be add gettext later

NAME = "Play it Slowly"
VERSION = "1.5.1"
WEBSITE = "http://29a.ch/playitslowly/"

if sys.platform == "win32":
    CONFIG_PATH = os.path.expanduser("~/playitslowly.json")
else:
    XDG_CONFIG_HOME = os.path.expanduser(os.environ.get("XDG_CONFIG_HOME", "~/.config"))
    if not os.path.exists(XDG_CONFIG_HOME):
        os.mkdir(XDG_CONFIG_HOME)
    CONFIG_PATH = os.path.join(XDG_CONFIG_HOME, "playitslowly.json")

TIME_FORMAT = Gst.Format(Gst.Format.TIME)

def in_pathlist(filename, paths = os.environ.get("PATH").split(os.pathsep)):
    """check if an application is somewhere in $PATH"""
    return any(os.path.exists(os.path.join(path, filename)) for path in paths)

class Config(dict):
    """Very simple json config file"""
    def __init__(self, path=None):
        dict.__init__(self)
        self.path = path

    def load(self):
        with open(self.path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print("Error loading config: %s", e)
                data = {}
        self.clear()
        self.update(data)

    def save(self):
        with open(self.path, mode="w", encoding="utf-8") as f:
            json.dump(self, f)


class MainWindow(Gtk.Window):
    def __init__(self, sink, config):
        Gtk.Window.__init__(self, type=Gtk.WindowType.TOPLEVEL)

        self.set_title(NAME)

        try:
            self.set_icon(myGtk.iconfactory.get_icon("ch.x29a.playitslowly", 128))
        except GObject.GError:
            print("could not load playitslowly icon")

        self.set_default_size(600, 200)
        self.set_border_width(5)

        self.vbox = Gtk.VBox()
        self.accel_group = Gtk.AccelGroup()
        self.add_accel_group(self.accel_group)


        self.pipeline = Pipeline(sink)

        # --- Waveform Drawing Area ---
        self.waveform_area = Gtk.DrawingArea()
        self.waveform_area.set_size_request(600, 100)
        self.waveform_area.connect("draw", self.on_waveform_draw)
        self.waveform_samples = None
        self.waveform_loaded = False
        self.waveform_view_start = 0.0   # fraction of total waveform (0.0–1.0)
        self.waveform_view_end = 1.0     # fraction of total waveform (0.0–1.0)
        self.vbox.pack_start(self.waveform_area, False, False, 4)

        # --- Enable mouse interaction on waveform ---
        self.waveform_area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.waveform_area.connect("button-press-event", self.on_waveform_click)
        self.waveform_area.connect("button-release-event", self.on_waveform_release)
        self.waveform_area.connect("motion-notify-event", self.on_waveform_motion)

        # Add mouse wheel zoom
        self.waveform_area.add_events(Gdk.EventMask.SCROLL_MASK)
        self.waveform_area.connect("scroll-event", self.on_waveform_scroll)

        # Zoom control button
        self.zoom_button = Gtk.Button(label="Zoom Selection")
        self.zoom_button.connect("clicked", self.on_zoom_selection)
        self.vbox.pack_start(self.zoom_button, False, False, 4)

        # --- Waveform Height Zoom ---
        self.waveform_height_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.5, 3.0, 0.1
        )
        self.waveform_height_scale.set_value(1.0)
        self.waveform_height_scale.set_digits(1)
        self.waveform_height_scale.connect("value-changed", lambda w: self.waveform_area.queue_draw())
        self.vbox.pack_start(self.waveform_height_scale, False, False, 2)

        self.dragging_marker = None  # "start", "end" or None

        # --- File chooser, speed/pitch/position controls ---        # Connect signals for zooming when start/end sliders move
        self.filedialog = myGtk.FileChooserDialog(None, self, Gtk.FileChooserAction.OPEN)
        self.filedialog.connect("response", self.filechanged)
        self.filedialog.set_local_only(False)
        filechooserhbox = Gtk.HBox()
        self.filechooser = Gtk.FileChooserButton.new_with_dialog(self.filedialog)
        self.filechooser.set_local_only(False)
        filechooserhbox.pack_start(self.filechooser, True, True, 0)
        self.recentbutton = Gtk.Button(label=_("Recent"))
        self.recentbutton.connect("clicked", self.show_recent)
        filechooserhbox.pack_end(self.recentbutton, False, False, 0)

        self.speedchooser = myGtk.TextScaleReset(Gtk.Adjustment.new(1.00, 0.10, 4.0, 0.05, 0.05, 0))
        self.speedchooser.scale.connect("value-changed", self.speedchanged)
        self.speedchooser.scale.connect("button-press-event", self.speedpress)
        self.speedchooser.scale.connect("button-release-event", self.speedrelease)
        self.speedchangeing = False

        pitch_adjustment = Gtk.Adjustment.new(0.0, -24.0, 24.0, 1.0, 1.0, 1.0)
        self.pitchchooser = myGtk.TextScaleReset(pitch_adjustment)
        self.pitchchooser.scale.connect("value-changed", self.pitchchanged)

        self.pitchchooser_fine = myGtk.TextScaleReset(Gtk.Adjustment.new(0.0, -50, 50, 1.0, 1.0, 1.0))
        self.pitchchooser_fine.scale.connect("value-changed", self.pitchchanged)

        self.positionchooser = myGtk.ClockScale(Gtk.Adjustment.new(0.0, 0.0, 100.0, 0, 0, 0))
        self.positionchooser.scale.connect("button-press-event", self.start_seeking)
        self.positionchooser.scale.connect("button-release-event", self.positionchanged)
        self.seeking = False

        self.startchooser = myGtk.TextScaleWithCurPos(self.positionchooser, Gtk.Adjustment.new(0.0, 0, 100.0, 0, 0, 0))
        self.startchooser.scale.connect("button-press-event", self.start_seeking)
        self.startchooser.scale.connect("button-release-event", self.seeked)
        self.startchooser.add_accelerator("clicked", self.accel_group, ord('['), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        self.startchooser.add_accelerator("clicked", self.accel_group, ord('['), 0, Gtk.AccelFlags.VISIBLE)

        self.endchooser = myGtk.TextScaleWithCurPos(self.positionchooser, Gtk.Adjustment.new(1.0, 0, 100.0, 0.01, 0.01, 0))
        self.endchooser.scale.connect("button-press-event", self.start_seeking)
        self.endchooser.scale.connect("button-release-event", self.seeked)
        self.endchooser.add_accelerator("clicked", self.accel_group, ord(']'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        self.endchooser.add_accelerator("clicked", self.accel_group, ord(']'), 0, Gtk.AccelFlags.VISIBLE)
        self.startchooser.scale.connect("value-changed", self.on_selection_changed)
        self.endchooser.scale.connect("value-changed", self.on_selection_changed)

        self.vbox.pack_start(filechooserhbox, False, False, 0)
        self.vbox.pack_start(self.positionchooser, True, True, 0)
        self.vbox.pack_start(myGtk.form([
            ("Speed (times)", self.speedchooser),
            ("Pitch (semitones)", self.pitchchooser),
            ("Fine Pitch (cents)", self.pitchchooser_fine),
            ("Start Position (seconds)", self.startchooser),
            ("End Position (seconds)", self.endchooser)
        ]), False, False, 0)

        buttonbox = Gtk.HButtonBox()
        myGtk.add_style_class(buttonbox, 'buttonBox')
        self.vbox.pack_end(buttonbox, False, False, 0)

        self.play_button = Gtk.ToggleButton(label='Play')
        self.play_button.connect("toggled", self.play)

        self.play_button.set_sensitive(False)
        buttonbox.pack_start(self.play_button, True, True, 0)
        self.play_button.add_accelerator("clicked", self.accel_group, ord(' '), 0, Gtk.AccelFlags.VISIBLE)

        self.back_button = Gtk.Button.new_with_mnemonic('Rewind')
        self.back_button.connect("clicked", self.back)
        #self.back_button.set_use_stock(True)
        self.back_button.set_sensitive(False)
        buttonbox.pack_start(self.back_button, True, True, 0)

        self.volume_button = Gtk.VolumeButton()
        self.volume_button.set_value(1.0)
        self.volume_button.set_relief(Gtk.ReliefStyle.NORMAL)
        self.volume_button.connect("value-changed", self.volumechanged)
        buttonbox.pack_start(self.volume_button, True, True, 0)

        self.save_as_button = Gtk.Button.new_with_mnemonic('Save As')
        self.save_as_button.connect("clicked", self.save)
        self.save_as_button.set_sensitive(False)
        buttonbox.pack_start(self.save_as_button, True, True, 0)

        button_about = Gtk.Button.new_with_mnemonic("About")
        button_about.connect("clicked", self.about)
        buttonbox.pack_end(button_about, True, True, 0)

        self.connect("key-release-event", self.key_release)

        self.add(self.vbox)
        self.connect("destroy", Gtk.main_quit)

        self.config = config
        self.config_saving = False
        self.load_config()

        # --- Periodic waveform refresh (for moving playback line) ---
        from gi.repository import GLib

        def refresh_waveform():
            # Always repaint if window is visible
            try:
                if self.waveform_loaded and self.waveform_area.get_mapped():
                    self.waveform_area.queue_draw()
            except Exception as e:
                logging.debug(f"refresh_waveform error: {e}")
            return True

        # Start after GTK mainloop is fully running (50ms delay)
        GLib.timeout_add(50, lambda: GLib.timeout_add(16, refresh_waveform))

    # ------------------------------------------------------------
    # Waveform mouse interaction
    # ------------------------------------------------------------
    def on_waveform_click(self, widget, event):
        if not self.waveform_loaded:
            return False
        width = widget.get_allocation().width
        total = self.endchooser.get_adjustment().get_upper()
        if total <= 0:
            return False

        # Convert time fraction to pixel X positions
        start_frac = self.startchooser.get_value() / total
        end_frac = self.endchooser.get_value() / total

        def frac_to_x(f):
            return (f - self.waveform_view_start) / (
                self.waveform_view_end - self.waveform_view_start
            ) * width

        x1 = frac_to_x(start_frac)
        x2 = frac_to_x(end_frac)

        # Detect click proximity (within 5 px)
        if abs(event.x - x1) < 5:
            self.dragging_marker = "start"
        elif abs(event.x - x2) < 5:
            self.dragging_marker = "end"
        else:
            self.dragging_marker = None
        return True

    def on_waveform_motion(self, widget, event):
        if not self.dragging_marker or not self.waveform_loaded:
            return False

        width = widget.get_allocation().width
        total = self.endchooser.get_adjustment().get_upper()
        frac = event.x / max(1, width)
        abs_frac = self.waveform_view_start + frac * (
            self.waveform_view_end - self.waveform_view_start
        )
        new_time = abs_frac * total

        if self.dragging_marker == "start":
            new_time = max(0.0, min(new_time, self.endchooser.get_value() - 0.01))
            self.startchooser.set_value(new_time)
        elif self.dragging_marker == "end":
            new_time = min(total, max(new_time, self.startchooser.get_value() + 0.01))
            self.endchooser.set_value(new_time)

        self.on_selection_changed(None)
        return True

    def on_waveform_release(self, widget, event):
        self.dragging_marker = None
        return True

    def on_waveform_scroll(self, widget, event):
        """Zoom in/out centered on cursor position."""
        if not self.waveform_loaded:
            return False

        zoom_factor = 0.8 if event.direction == Gdk.ScrollDirection.UP else 1.25

        # Cursor fraction within the widget
        width = widget.get_allocation().width
        cursor_frac = event.x / max(1, width)

        total_len = 1.0
        view_center = self.waveform_view_start + cursor_frac * (self.waveform_view_end - self.waveform_view_start)
        current_width = self.waveform_view_end - self.waveform_view_start
        new_width = min(1.0, max(0.0001, current_width * zoom_factor))

        self.waveform_view_start = max(0.0, view_center - new_width / 2.0)
        self.waveform_view_end = min(1.0, self.waveform_view_start + new_width)

        # Adjust if we go out of range
        if self.waveform_view_end > 1.0:
            shift = self.waveform_view_end - 1.0
            self.waveform_view_start -= shift
            self.waveform_view_end = 1.0
        if self.waveform_view_start < 0.0:
            self.waveform_view_end -= self.waveform_view_start
            self.waveform_view_start = 0.0

        self.waveform_area.queue_draw()
        return True

    def on_zoom_selection(self, button):
        """Zoom so selection fits roughly from 10% to 90% of width."""
        total = self.endchooser.get_adjustment().get_upper()
        if total <= 0:
            return

        sel_start = self.startchooser.get_value() / total
        sel_end = self.endchooser.get_value() / total
        sel_width = max(0.0001, sel_end - sel_start)

        # Compute zoomed region to place selection 10%-90% of view
        view_width = sel_width / 0.8
        view_center = (sel_start + sel_end) / 2.0

        self.waveform_view_start = max(0.0, view_center - view_width / 2.0)
        self.waveform_view_end = min(1.0, self.waveform_view_start + view_width)

        if self.waveform_view_end > 1.0:
            shift = self.waveform_view_end - 1.0
            self.waveform_view_start -= shift
            self.waveform_view_end = 1.0
        if self.waveform_view_start < 0.0:
            self.waveform_view_end -= self.waveform_view_start
            self.waveform_view_start = 0.0

        self.waveform_area.queue_draw()

    def on_waveform_draw(self, widget, cr):
        import cairo
        if not self.waveform_loaded or self.waveform_samples is None:
            return False

        alloc = widget.get_allocation()
        width, height = alloc.width, alloc.height
        samples = self.waveform_samples
        if len(samples) == 0:
            return False

        max_val = max(abs(samples.max()), abs(samples.min()))
        if max_val == 0:
            return False

        import numpy as np
        norm_samples = samples / max_val

        # --- Compute zoomed region indices ---
        total_len = len(norm_samples)
        view_start_idx = int(self.waveform_view_start * total_len)
        view_end_idx = int(self.waveform_view_end * total_len)
        view_end_idx = min(view_end_idx, total_len - 1)

        # --- Slice zoom region ---
        visible = norm_samples[view_start_idx:view_end_idx]
        if len(visible) < 2:
            return False

        # --- Resample to match widget width ---
        # This keeps the zoomed region filling the entire view width
        x = np.linspace(0, len(visible) - 1, width)
        points = np.interp(x, np.arange(len(visible)), visible)

        mid = height // 2
        vertical_zoom = self.waveform_height_scale.get_value() if hasattr(self, "waveform_height_scale") else 1.0

        # Apply vertical zoom (clamp so it doesn't overflow)
        amp = int((height // 2 - 2) * vertical_zoom)

        # Fill background to make waveform visible
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Draw waveform
        cr.set_source_rgb(0.2, 0.6, 1.0)
        cr.set_line_width(1)
        cr.move_to(0, mid)
        for x, y in enumerate(points):
            cr.line_to(x, mid - int(y * amp))
        cr.stroke()

        # --- Draw selection area ---
        total = self.endchooser.get_adjustment().get_upper()
        if total > 0:
            start_frac = self.startchooser.get_value() / total
            end_frac = self.endchooser.get_value() / total

            # Map absolute fractions to local visible window
            def frac_to_x(f):
                return (f - self.waveform_view_start) / (self.waveform_view_end - self.waveform_view_start) * width

            x1 = frac_to_x(start_frac)
            x2 = frac_to_x(end_frac)

            # --- Selection (loop region) overlay ---
            cr.set_source_rgba(0.9, 0.3, 0.4, 0.25)  # translucent pink/red
            cr.rectangle(min(x1, x2), 0, abs(x2 - x1), height)
            cr.fill()

            try:
                # Robust position/duration query from GStreamer
                ok_pos, pos_ns = self.pipeline.playbin.query_position(Gst.Format.TIME)
                ok_dur, dur_ns = self.pipeline.playbin.query_duration(Gst.Format.TIME)

                if not ok_pos:
                    pos_ns = 0
                if not ok_dur or dur_ns == 0:
                    # fall back to endchooser upper bound if duration not known yet
                    dur_ns = int(self.endchooser.get_adjustment().get_upper() * Gst.SECOND)

                # Convert to seconds
                pos_time = pos_ns / Gst.SECOND
                dur_time = dur_ns / Gst.SECOND
                total_time = max(dur_time, 0.001)

                pos_frac = min(1.0, max(0.0, pos_time / total_time))
                logging.debug(f"Playback line: {pos_time:.2f}s / {total_time:.2f}s -> {pos_frac:.2%}")
            except Exception as e:
                logging.debug(f"Waveform position query failed: {e}")
                pos_frac = 0.0

            x_pos = frac_to_x(pos_frac)

            # draw blue overlay for played region
            if x_pos > 0:
                cr.set_source_rgba(0.3, 0.6, 1.0, 0.25)
                cr.rectangle(0, 0, min(x_pos, width), height)
                cr.fill()

                # --- Moving playback line ---
                cr.set_source_rgb(1.0, 1.0, 1.0)  # white line
                cr.set_line_width(1.0)
                if 0 <= x_pos <= width:
                    cr.move_to(x_pos, 0)
                    cr.line_to(x_pos, height)
                    cr.stroke()

                # optional small circle marker at mid height
                cr.arc(x_pos, mid, 2.0, 0, 2 * np.pi)
                cr.fill()

            # --- Start/End marker lines (contrasting color) ---
            cr.set_source_rgb(1.0, 0.6, 0.0)  # bright orange markers
            cr.set_line_width(1.2)
            for xline in (x1, x2):
                if 0 <= xline <= width:
                    cr.move_to(xline, 0)
                    cr.line_to(xline, height)
            cr.stroke()

        return False


    def on_selection_changed(self, sender):
        """Update waveform zoom when start or end slider moves."""
        try:
            total = self.endchooser.get_adjustment().get_upper()
            start = self.startchooser.get_value()
            end = self.endchooser.get_value()
            if end <= start or total <= 0:
                return

            # Convert start/end to fractional range
            sel_start = start / total
            sel_end = end / total

            # Center waveform view on selection, keeping it ~80% of window
            sel_center = (sel_start + sel_end) / 2.0
            sel_width = max(0.0001, sel_end - sel_start)

            view_width = min(1.0, sel_width / 0.8)
            view_start = max(0.0, sel_center - view_width / 2.0)
            view_end = min(1.0, view_start + view_width)

            # Adjust if we hit end boundary
            if view_end > 1.0:
                shift = view_end - 1.0
                view_start = max(0.0, view_start - shift)
                view_end = 1.0

            self.waveform_view_start = view_start
            self.waveform_view_end = view_end

            self.waveform_area.queue_draw()
        except Exception as e:
            print(f"[ERROR] on_selection_changed: {e}")


    def load_waveform(self, filename):
        try:
            from playitslowly.waveform import WaveformExtractor
        except Exception as e:
            logging.error(f"Could not import WaveformExtractor: {e}")
            self.waveform_loaded = False
            return

        try:
            extractor = WaveformExtractor(filename)
            self.waveform_samples = extractor.get_samples(50000)
            self.waveform_loaded = True
        except Exception as e:
            logging.error(f"Waveform load error: {e}")
            self.waveform_samples = None
            self.waveform_loaded = False

        self.waveform_area.queue_draw()

    def speedpress(self, *args):
        self.speedchangeing = True

    def speedrelease(self, *args):
        self.speedchangeing = False
        self.speedchanged()

    def get_pitch(self):
        return self.pitchchooser.get_value()+self.pitchchooser_fine.get_value()*0.01

    def set_pitch(self, value):
        semitones = round(value)
        cents = round((value-semitones)*100)
        self.pitchchooser.set_value(semitones)
        self.pitchchooser_fine.set_value(cents)

    def add_recent(self, uri):
        manager = Gtk.RecentManager.get_default()
        app_exec = "playitslowly \"%s\"" % uri
        mime_type, certain = Gio.content_type_guess(uri)
        if mime_type:
            recent_data = Gtk.RecentData()
            recent_data.app_name = "playitslowly"
            recent_data.app_exec = "playitslowly"
            recent_data.mime_type = mime_type
            manager.add_full(uri, recent_data)
            logging.debug(f"Added to recents: {uri} ({mime_type})")


    def show_recent(self, sender=None):
        dialog = Gtk.RecentChooserDialog(_("Recent Files"), self, None,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        filter = Gtk.RecentFilter()
        filter.set_name("playitslowly")
        filter.add_application("playitslowly")
        dialog.add_filter(filter)

        filter2 = Gtk.RecentFilter()
        filter2.set_name(_("All"))
        filter2.add_mime_type("audio/*")
        dialog.add_filter(filter2)

        dialog.set_local_only(False)

        dialog.set_filter(filter)

        if dialog.run() == Gtk.ResponseType.OK and dialog.get_current_item():
            uri = dialog.get_current_item().get_uri()
            if isinstance(uri, bytes):
                uri = uri.decode('utf-8')
            self.set_uri(uri)
        dialog.destroy()

    def set_uri(self, uri):
        logging.info(f"Opening: {uri}")
        self.filedialog.set_uri(uri)
        self.filechooser.set_uri(uri)
        self.filechanged(uri=uri)

    def load_config(self):
        self.config_saving = True # do not save while loading
        lastfile = self.config.get("lastfile")
        if lastfile:
            self.set_uri(lastfile)
        self.config_saving = False

    def reset_settings(self):
        self.speedchooser.set_value(1.0)
        self.speedchanged()
        self.set_pitch(0.0)
        self.startchooser.get_adjustment().set_property("upper", 0.0)
        self.startchooser.set_value(0.0)
        self.endchooser.get_adjustment().set_property("upper", 1.0)
        self.endchooser.set_value(1.0)

    def load_file_settings(self, filename):
        logging.debug(f"Loading file settings for: {filename}")
        self.add_recent(filename)
        if not self.config or not filename in self.config["files"]:
            self.reset_settings()
            self.pipeline.set_file(filename)
            self.pipeline.pause()
            from gi.repository import GLib
            GLib.timeout_add(100, self.update_position)
            return
        settings = self.config["files"][filename]
        self.speedchooser.set_value(settings["speed"])
        self.set_pitch(settings["pitch"])
        self.startchooser.get_adjustment().set_property("upper", settings["duration"])
        self.startchooser.set_value(settings["start"])
        self.endchooser.get_adjustment().set_property("upper", settings["duration"] or 1.0)
        self.endchooser.set_value(settings["end"])
        self.volume_button.set_value(settings["volume"])

    def save_config(self):
        """saves the config file with a delay"""
        if self.config_saving:
            return
        from gi.repository import GLib
        GLib.timeout_add(1000, self.save_config_now)
        self.config_saving = True

    def save_config_now(self):
        self.config_saving = False
        lastfile = self.filedialog.get_uri()
        self.config["lastfile"] = lastfile
        settings = {}
        settings["speed"] = self.speedchooser.get_value()
        settings["pitch"] = self.get_pitch()
        settings["duration"] = self.startchooser.get_adjustment().get_property("upper")
        settings["start"] = self.startchooser.get_value()
        settings["end"] = self.endchooser.get_value()
        settings["volume"] = self.volume_button.get_value()
        self.config.setdefault("files", {})[lastfile] = settings

        self.config.save()

    def key_release(self, sender, event):
        if not event.get_state() & Gdk.ModifierType.CONTROL_MASK:
            return
        try:
            val = int(chr(event.keyval))
        except ValueError:
            return
        self.back(self, val)

    def volumechanged(self, sender, foo):
        self.pipeline.set_volume(sender.get_value())
        self.save_config()

    def save(self, sender):
        dialog = myGtk.FileChooserDialog(_("Save modified version as"),
                self, Gtk.FileChooserAction.SAVE)
        dialog.set_current_name("export.wav")
        if dialog.run() == Gtk.ResponseType.OK:
            self.pipeline.set_file(self.filedialog.get_uri())
            self.foo = self.pipeline.save_file(dialog.get_filename())
        dialog.destroy()

    def filechanged(self, sender=None, response_id=Gtk.ResponseType.OK, uri=None):
        filename = None
        try:
            filename = self.filedialog.get_filename()
        except Exception as e:
            print(f"[ERROR] filedialog.get_filename() failed: {e}")

        # If not found, try the URI conversion
        if not filename and uri:
            try:
                from gi.repository import Gio
                gfile = Gio.File.new_for_uri(uri)
                filename = gfile.get_path()
            except Exception as e:
                print(f"[ERROR] Failed to resolve URI to path: {e}")

        # Final fallback: if sender is FileChooserButton
        if not filename and hasattr(sender, "get_filename"):
            try:
                filename = sender.get_filename()
            except Exception as e:
                print(f"[ERROR] sender.get_filename() failed: {e}")

        if not filename:
            print("[ERROR] Could not resolve any valid filename, skipping waveform load")
            return

        # --- Load waveform ---
        try:
            self.load_waveform(filename)
        except Exception as e:
            logging.error(f"Waveform load failed: {e}")

        self.play_button.set_sensitive(True)
        self.back_button.set_sensitive(True)
        self.save_as_button.set_sensitive(True)
        self.play_button.set_active(False)

        self.pipeline.reset()
        self.seek(0)
        self.save_config()

        if uri:
            self.load_file_settings(uri)
        else:
            from gi.repository import GLib
            GLib.timeout_add(1, lambda: self.load_file_settings(self.filedialog.get_uri()))

    def start_seeking(self, sender, foo):
        self.seeking = True

    def seeked(self, sender, foo):
        self.seeking = False
        self.save_config()

    def positionchanged(self, sender, foo):
        self.seek(sender.get_value())
        self.seeking = False
        self.save_config()

    def seek(self, pos=0):
        if self.positionchooser.get_value() != pos:
            self.positionchooser.set_value(pos)
        pos = self.pipeline.pipe_time(pos)
        self.pipeline.playbin.seek_simple(TIME_FORMAT, Gst.SeekFlags.FLUSH, pos or 0)

    def speedchanged(self, *args):
        if self.speedchangeing:
            return
        pos = self.positionchooser.get_value()
        self.pipeline.set_speed(self.speedchooser.get_value())
        # hack to get gstreamer to calculate the position again
        self.seek(pos)
        self.save_config()

    def pitchchanged(self, sender):
        self.pipeline.set_pitch(2**(self.get_pitch()/12.0))
        self.save_config()

    def back(self, sender, amount=None):
        position, fmt = self.pipeline.playbin.query_position(TIME_FORMAT)
        if position is None:
            return
        if amount:
            t = self.pipeline.song_time(position)-amount
            if t < 0:
                t = 0
        else:
            t = self.startchooser.get_value()
        self.seek(t)

    def play(self, sender):
        if sender.get_active():
            self.pipeline.set_file(self.filedialog.get_uri())
            self.pipeline.play()
            GObject.timeout_add(100, self.update_position)
        else:
            self.pipeline.pause()

    def update_position(self):
        """update the position of the scales and pipeline"""
        if self.seeking:
            return self.play_button.get_active()

        _, position = self.pipeline.playbin.query_position(TIME_FORMAT)
        _, duration = self.pipeline.playbin.query_duration(TIME_FORMAT)
        if position is None or duration is None:
            return self.play_button.get_active()
        position = position
        duration = duration
        position = self.pipeline.song_time(position)
        duration = self.pipeline.song_time(duration)

        if duration is None or duration <= 0:
            return self.play_button.get_active()

        if self.positionchooser.get_adjustment().get_property("upper") != duration:
            self.positionchooser.set_range(0.0, max(0.001, duration))
            self.save_config()

        end_adjustment = self.endchooser.get_adjustment()
        delta = end_adjustment.get_value() - end_adjustment.get_upper()

        if delta <= -duration:
            delta = 0

        self.startchooser.set_range(0.0, duration)
        self.endchooser.set_range(0.0, duration)
        self.endchooser.set_value(duration+delta)

        self.positionchooser.set_value(position)
        self.positionchooser.queue_draw()

        start = self.startchooser.get_value()
        end = self.endchooser.get_value()

        if end <= start:
            self.play_button.set_active(False)
            return False

        if position >= end or position < start:
            self.seek(start+0.01)
            return True

        return self.play_button.get_active()

    def about(self, sender):
        """show an about dialog"""
        about = Gtk.AboutDialog()
        about.set_transient_for(self)
        about.set_logo(myGtk.iconfactory.get_icon("ch.x29a.playitslowly", 128))
        about.set_name(NAME)
        about.set_program_name(NAME)
        about.set_version(VERSION)
        about.set_authors(["Jonas Wagner", "Elias Dorneles"])
        about.set_translator_credits(_("translator-credits"))
        about.set_copyright("Copyright (c) 2009 - 2015 Jonas Wagner")
        about.set_website(WEBSITE)
        about.set_website_label(WEBSITE)
        about.set_license("""
Copyright (C) 2009 - 2015 Jonas Wagner
This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
""")
        about.run()
        about.destroy()

css = b"""
.buttonBox GtkButton GtkLabel { padding-left: 4px; }
"""





def main():
    sink = "autoaudiosink"
    if in_pathlist("gstreamer-properties"):
        sink = "gconfaudiosink"
    options, arguments = getopt.getopt(sys.argv[1:], "h", ["help", "sink="])
    for option, argument in options:
        if option in ("-h", "--help"):
            print("Usage: playitslowly [OPTIONS]... [FILE]")
            print("Options:")
            print('--sink=sink      specify gstreamer sink for playback')
            sys.exit()
        elif option == "--sink":
            print("sink", argument)
            sink = argument
    config = Config(CONFIG_PATH)
    try:
        config.load()
    except IOError:
        pass

    style_provider = Gtk.CssProvider()

    style_provider.load_from_data(css)

    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    win = MainWindow(sink, config)

    if arguments:
        uri = arguments[0]
        if not uri.startswith("file://"):
            uri = "file://" + os.path.abspath(uri)
        win.set_uri(uri)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
