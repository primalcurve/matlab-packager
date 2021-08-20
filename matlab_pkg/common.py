#!/usr/bin/env python3
# encoding: utf-8
#===========================================================================
#   MatLab Package Generator
#       Common Framework
#   matlab_pkg/common.py
#

#======================================
#   Import Statements
#
import inspect
import json
import logging
import logging.handlers
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as xml_et

import matlab_pkg.product as ml_product

MOD_PATH = pathlib.Path(inspect.getsourcefile(lambda: 0)).parent.parent
TARGET_FILE = MOD_PATH.joinpath("target_software_and_toolboxes.txt")
SETUP_FILE = MOD_PATH.joinpath("setup.json")
DATA_FOLDER = MOD_PATH.joinpath("data")
USER_DIR = pathlib.Path("~").expanduser()
USER_LIB = USER_DIR.joinpath("Library")
USER_LOG = USER_LIB.joinpath("Logs/matlab_packager")

_MW = ("MathWorks")
_ML = ("MatLab")
_YR = ("2021")
_REL = (f"{_YR}a")

_TMP = pathlib.Path("/private/tmp")

_HOME = pathlib.Path("~").expanduser()
_DESKTOP = _HOME.joinpath("Desktop")
AR_FOLDER = _DESKTOP.joinpath(
    "Projects", "Packaging",
    _MW, _ML, _YR,
    f"{_ML} {_REL}", "RAW")


def get_targets(target_file=None):
    """Reads in the contents of target_file and returns a list of products
    """
    if not target_file:
        target_file = TARGET_FILE
    with open(target_file, "r") as fp:
        return [
            ml_product.MathWorksProduct(p)
            for p in fp.read().splitlines()
        ]


def get_file_installation_key(_family):
    """Reads the file installation key for a given release family."""
    with open(MOD_PATH.joinpath(f"license/{_family}_key.txt"), "r") as fp:
        return [
            _l for _l in fp.read().splitlines()
            if "File Installation Key:" not in _l
        ][0].strip()


def get_license_hash(_family):
    """Reads the file installation key for a given release family."""
    with open(MOD_PATH.joinpath(f"license/{_family}_license.dat"), "r") as fp:
        return fp.read().splitlines()[0].split()[-1]


def read_setup():
    return read_json(SETUP_FILE)


def write_setup(setup={}):
    if not setup:
        setup = read_setup()
    defaults = dict(
        archive_folder=AR_FOLDER
        )
    setup = {**defaults, **setup}
    write_json(setup, SETUP_FILE)


def read_xml(xml_string):
    return xml_et.fromstring(
        re.sub(r"\r\n  +", "", xml_string))


def read_json(_file):
    _file = pathlib.Path(_file)
    if _file.exists():
        with open(_file, "r") as j_f:
            _record = json.load(j_f)
        # print(f"JSON {_file.name} Loaded...")
    else:
        print(f"{_file.name} does not exist. Returning empty dictionary.")
        _record = {}
    return _record


def write_json(_obj, _file, _indent=2):
    with open(_file, "w") as j_f:
        json.dump(_obj, j_f, sort_keys=True, indent=_indent)


def mount_dmg(dmg_path):
    mount_cmd = [
        "/usr/bin/hdiutil",
        "attach", f"{dmg_path}",
        "-plist", "-nobrowse"
    ]
    try:
        mount_info = plistlib.loads(subprocess.check_output(mount_cmd))
    except subprocess.CalledProcessError as err:
        print(f"hdiutil error: {err}")
        return False
    for _info in mount_info.get("system-entities"):
        mount_dev = None
        if re.match(r"/dev/disk\d+$", _info.get("dev-entry")):
            mount_dev = _info.get("dev-entry")
            break
    return mount_dev


def unmount_dmg(mount_dev):
    detach_cmd = [
        "/usr/bin/hdiutil",
        "detach", f"{mount_dev}"
    ]
    try:
        subprocess.check_call(detach_cmd)
    except subprocess.CalledProcessError as err:
        print(f"hdiutil error: {err}")
        return False
    return True


def logger_config(other_logger, _name, _verbosity=0):
    # Create a path to the log file.
    log_path = USER_LOG.joinpath(_name)
    log_path.parent.mkdir(exist_ok=True, parents=True)
    # logging Formatters
    easy_formatter = logging.Formatter("%(message)s")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # Defining the different Log StreamHandlers
    log_stderr = logging.StreamHandler()
    log_logfile = logging.handlers.TimedRotatingFileHandler(
        log_path, when="D", interval=1, backupCount=5
    )
    # Defining different log levels for each StreamHandler
    log_stderr.setLevel(logging.INFO)
    log_logfile.setLevel(logging.DEBUG)
    # Add formatters to logging Handlers.
    log_stderr.setFormatter(easy_formatter)
    log_logfile.setFormatter(file_formatter)
    # Add all of the handlers to this logging instance:
    other_logger.addHandler(log_stderr)
    other_logger.addHandler(log_logfile)
    # Determinine overall Log Level. Set the lowest level to DEBUG.
    # logger.ERROR is level 40.
    logger_verbosity = max(
        logging.DEBUG, logging.ERROR - (_verbosity * 10)
    )
    if logger_verbosity <= 10:
        # Always log debug-level messages and send INFO and above to stderr
        other_logger.setLevel(logging.DEBUG)
        other_logger.info("Debug logs written to: %s", str(log_path))
    else:
        other_logger.setLevel(logger_verbosity)
    return other_logger
