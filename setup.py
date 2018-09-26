# pygotu
# Copyright 2014 SUNAGA Takahiro

# This file is part of pygotu.
#
# pygotu is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the licence, or
# (at your option) any later version, or the BSD licence.
#
# pygotu is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENCE for more details.

from distutils.core import setup

setup(name="pygotu",
      version="0.1",
      description="iGot-U GPS GT-200 track downloader",
      license="MIT",
      author="SUNAGA Takahiro/Benjamin Bezine",
      url="https://github.com/bezineb5/pygotu",
      install_requires=[
        "pyserial==3.4",
        "pyusb==1.0.2"
      ],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
          "Programming Language :: Python :: 3.5",
          "Topic :: Multimedia"],
      py_modules=["pygotu", "gt2gpx", "connections"])
