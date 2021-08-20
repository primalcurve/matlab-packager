#!/usr/bin/env python3
# encoding: utf-8
#===========================================================================
#   Objects pertaining to the archives containing MathWorks Products
#


#======================================
#   Import Statements
#
import datetime
import pathlib
import re
import zipfile
import xml.etree.ElementTree as xml_et

import matlab_pkg.common as ml_common
import matlab_pkg.product as ml_product


class MatLabArchive(zipfile.ZipFile):
    def __init__(self, file, *args, **kwargs):
        super().__init__(file, *args, **kwargs)
        self.file = pathlib.Path(self.filename)
        self._all_product_xml = []

    def __str__(self):
        return f"{self.file}"

    def __repr__(self):
        return (
            f"<MatLabArchive(file={self.file.name}, "
            f"products={self.product_names}, "
            f"num_files={self.num_files})>")

    @property
    def all_files(self):
        self._all_files = set(self.infolist())
        return self._all_files

    @property
    def num_files(self):
        self._num_files = len(self.all_files)
        return self._num_files

    @property
    def all_product_xml(self):
        return self._all_product_xml

    @property
    def product_names(self):
        self._product_names = set([
            _d.find("productName").text for _d in self.products])
        return self._product_names

    def common(self, others):
        return self.all_files - self._others(others)

    def get_all_product_xml(self):
        self._all_product_xml = []
        for _file in self.find_files(r".*/productdata_.*\.xml"):
            self._all_product_xml.append(
                ml_product.MathWorksProduct(
                    self.read(_file).decode()
                )
            )

    def find_files(self, re_search):
        return [
            f for f in self.all_files
            if re.match(rf"{re_search}", f.filename)
        ]

    def unique(self, others):
        return self.all_files - self._others(others)

    def _others(self, others):
        return {f for a in others for f in a.all_files if a != self}

    def to_json(self):
        """Converts major attributes to JSON-serializable objects.
        """
        archive_json = {
            f"{self.file.name}": {
                "name": self.name,
                "dependencies": self.deps,
                "common": [],
                "unique": [],
            }
        }
        common_files = archive_json.get(self.file.name, {}).get("common")
        unique_files = archive_json.get(self.file.name, {}).get("unique")
        for _file in self.common.keys():
            common_files.append(_file)
        for _file in self.unique.keys():
            unique_files.append(_file)

        return self._dict(vars(self))
