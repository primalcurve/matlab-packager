#!/usr/bin/env python3
# encoding: utf-8
#===========================================================================
#   Objects pertaining to MathWorks Products
#


#======================================
#   Import Statements
#
import datetime
import logging
import pathlib
import re
import zipfile
import xml.etree.ElementTree as xml_et

import matlab_pkg.common as ml_common
import matlab_pkg.component as ml_component


# Create module-level LOGGER
LOGGER = logging.getLogger(__name__)


class MathWorksProduct(object):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self._archive_common = ""
        self._archive_maci64 = ""
        self._components_common = []
        self._components_maci64 = []
        self._controlling_product = None
        self._dependencies = []
        self._dependency_names = []
        self._family = ""
        self._is_controlling_product = False
        self._xml_common = None
        self._xml_maci64 = None
        self._xml_path_common = None
        self._xml_path_maci64 = None

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return (f"<MathWorksProduct('{self.name}')>")

    @property
    def archive_common(self):
        return self._archive_common

    @archive_common.setter
    def archive_common(self, new_archive):
        if new_archive.file.exists():
            self._archive_common = new_archive

    @property
    def archive_maci64(self):
        return self._archive_maci64

    @archive_maci64.setter
    def archive_maci64(self, new_archive):
        if new_archive.file.exists():
            self._archive_maci64 = new_archive

    @property
    def components_common(self):
        return self._components_common

    @property
    def components_maci64(self):
        return self._components_maci64

    @property
    def controlling_product(self):
        if not self.is_controlling_product:
            for _dep in self.dependencies:
                try:
                    _is_cont = _dep.find("isControllingProduct")
                    # Skip non-controlling products
                    if _is_cont.text == "false":
                        continue
                    self._controlling_product = _dep.find("productName").text
                except AttributeError:
                    pass
        return self._controlling_product

    @property
    def dependencies(self):
        try:
            self._dependencies = [
                _dep for _dep in
                self.xml_common.findall("./requiredProducts/product")
            ]
        except AttributeError:
            pass
        return self._dependencies

    @property
    def dependency_names(self):
        try:
            self._dependency_names = [
                _dep.find("productName").text for _dep in
                self.dependencies
            ]
        except AttributeError:
            pass
        return self._dependency_names

    @property
    def family(self):
        try:
            self._family = self.xml_common.find("./releaseFamily").text
        except AttributeError:
            pass
        return self._family

    @property
    def file_count(self):
        self._file_count = len(self.file_list)
        return self._file_count

    @property
    def file_list(self):
        return self._file_list

    @property
    def is_controlling_product(self):
        try:
            self._is_controlling_product = (
                self.xml_common.find("./isControllingProduct").text == "true"
            )
        except AttributeError:
            pass
        return self._is_controlling_product

    @property
    def version(self):
        return self.xml_common.find("./productVersion").text

    @property
    def xml_common(self):
        return self._xml_common

    @xml_common.setter
    def xml_common(self, other_xml):
        if other_xml.find("./productName").text == self.name:
            self._xml_common = other_xml

    @property
    def xml_path_common(self):
        return self._xml_path_common

    @property
    def xml_path_maci64(self):
        return self._xml_path_maci64

    @property
    def xml_maci64(self):
        return self._xml_maci64

    @xml_maci64.setter
    def xml_maci64(self, other_xml):
        if other_xml.find("./productName").text == self.name:
            self._xml_maci64 = other_xml

    def get_product_xml(self):
        """Take the two platform archives and find the productdata XML files
        """
        regex_name = self.name.replace(" ", "_")
        product_data_common = self.archive_common.find_files(
            rf".*/productdata_{regex_name}\d+_common\.xml"
        )
        for _file in product_data_common:
            self.xml_common = ml_common.read_xml(
                self.archive_common.read(_file.filename).decode()
            )
            if self.xml_common is not None:
                self._xml_path_common = _file.filename
                break
        product_data_maci64 = self.archive_maci64.find_files(
            rf".*/productdata_{regex_name}\d+_maci64\.xml"
        )
        for _file in product_data_maci64:
            self.xml_maci64 = ml_common.read_xml(
                self.archive_maci64.read(_file.filename).decode()
            )
            if self.xml_maci64 is not None:
                self._xml_path_maci64 = _file.filename
                break

    def get_components(self):
        """Takes the xml_common and xml_maci64 properties and gets the various
        components for each.
        """
        for component_name in self.xml_common.findall("./dependsOn//name"):
            _component = ml_component.MathWorksComponent(
                component_name.text, self.archive_common, True
            )
            _component.get_xml()
            self._components_common.append(_component)

        for component_name in self.xml_maci64.findall("./dependsOn//name"):
            _component = ml_component.MathWorksComponent(
                component_name.text, self.archive_maci64, False
            )
            _component.get_xml()
            self._components_maci64.append(_component)
