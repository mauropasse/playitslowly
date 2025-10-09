.. warning::
  **This project is currently unmaintained**.
  It has been superceded by `timestretch player <https://29a.ch/timestretch/>`_.
  *Play it slowly* will likely not work on modern linux distributions anymore.
  If someone wants to continue working on *play it slowly* I'd be glad to hand over maintainership. 


=====================
Play it Slowly Manual
=====================

About
=====
'Play it Slowly' is a tool to help you when practicing or
transcribing music. It allows you to play a piece of music
at a different speed or pitch.

New in this version:
--------------------
- **Waveform Display:**
  - The main window now shows a detailed waveform of the loaded track.
  - You can zoom, scroll, and select regions directly on the waveform.
  - The playback position and selection are visually indicated.

Dependencies
============
* Python 3.4 or newer
* PyGI (Python GObject Introspection)
* GTK3
* gstreamer 1.0 including the soundtouch/pitch element (included in gstreamer-plugins-bad)
* **pydub** (for waveform extraction)
* **numpy** (for waveform processing)
* **ffmpeg** (required by pydub for audio decoding)


Shortcuts
=========
The following keyboard shortcuts exist:
 * Alt + P or SPACE: Play/Pause
 * Alt + e: Rewind
 * CTRL + 1-9: Rewind (x seconds)


Selecting the audio output device
=================================
You can select which audiodevice playitslowly uses by passing
a gstreamer sink with the --sink commandline parameter.

Example:
playitslowly "--sink=alsasink device=plughw:GT10"
or
playitslowly "--sink=alsasink device=hw:1"

You can also use other sinks than alsa.


Generic Installation
====================
To install, you need the following libraries and tools:

 * Python 3.4 or newer
 * PyGI (Python GObject Introspection)
 * GTK3
 * gstreamer 1.0 including the soundtouch/pitch element (included in gstreamer-plugins-bad)
 * **pydub** and **numpy** (for waveform display)
 * **ffmpeg** (required by pydub)

Install Python dependencies (recommended):

.. code-block:: bash

  pip install -r requirements.txt

Install system dependencies (Debian/Ubuntu):

.. code-block:: bash

  sudo apt install ffmpeg python3-gi python3-gi-cairo gir1.2-gtk-3.0 gstreamer1.0-plugins-bad

Then install Play it Slowly:

.. code-block:: bash

  python3 setup.py install

Or, on GNOME-based systems, double-click ``install.sh`` and select run.



Waveform Feature Details
========================
The waveform display uses pydub and numpy to extract and render a detailed min/max envelope of the audio file. It supports most common audio formats (WAV, MP3, FLAC, OGG, AAC, etc.) as long as ffmpeg is installed.

You can:
 * Zoom in/out on the waveform with the mouse wheel
 * Drag start/end markers to select a region
 * Click the "Zoom Selection" button to focus on your selection
 * See the current playback position as a moving line

If you encounter issues with waveform display, ensure you have installed pydub, numpy, and ffmpeg.

Hacking
=======
The source code of play it slowly is hosted on github:

https://github.com/jwagner/playitslowly

If you have any questions or a patch just drop me a mail
or fill a pull request on github.


License
=======
Copyright (C) 2009 - 2016  Jonas Wagner

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


Bugreports / Questions
======================
If you encounter any bugs or have suggestions or just want to
thank me - I would like to hear about it!

Known Issues
============
* None


Contact
=======
http://29a.ch/about
