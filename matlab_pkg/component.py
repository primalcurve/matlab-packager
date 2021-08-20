#!/usr/bin/env python3
# encoding: utf-8
#===========================================================================
#   Objects pertaining to the components of MathWorks Products
#


#======================================
#   Import Statements
#
import datetime
import logging
import pathlib
import re
import zipfile
import matlab_pkg.common as ml_common
import xml.etree.ElementTree as xml_et


# Create module-level LOGGER
LOGGER = logging.getLogger(__name__)


class MathWorksComponent(object):
    def __init__(self, name, archive, is_common, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.archive = archive
        self.is_common = is_common
        self._path = ""
        self._xml = None
        self._xml_path = ""

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return (f"<MathWorksComponent('{self.name}', '{self.archive}')>")

    @property
    def path(self):
        self._path = self.xml.find(
            ".//component/componentFileName"
        ).text
        return self._path

    @property
    def xml(self):
        return self._xml

    @xml.setter
    def xml(self, new_xml):
        _xml = ml_common.read_xml(new_xml)
        xml_name = _xml.find(".//component/componentName")
        if xml_name is not None and xml_name.text == self.name:
            self._xml = _xml

    @property
    def xml_path(self):
        return self._xml_path

    def get_xml(self):
        """Finds its own XML in the archive
        """
        regex_name = self.name.replace(" ", "_")
        regex_search = rf".*{regex_name}_\d+\.xml"
        for _file in self.archive.find_files(regex_search):
            self.xml = self.archive.read(_file.filename).decode()
            if self.xml is not None:
                LOGGER.debug("Component XML: %s", _file.filename)
                self._xml_path = _file.filename
                break

