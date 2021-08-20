#!/usr/bin/env python3
# encoding: utf-8
"""
===========================================================================
    Prestage MATLAB Install

How to use this script in a policy:
There are several parameters that need to be considered:
Required:
    matlab_version: This is the release string e.g. "R2020a"
    fi_key: The File Installation Key
    dat_hash: The Hash from the generated license.dat file
    addons_csv: A comma-separated list of toolboxes to install,
                "All" to install all of the available toolboxes, or
                "None" to only install MATLAB.
Optional:
    server: A server other than the default global server defined here
           --server=other-server.license.company.com <Note: No quotes!>
    verbose: A number of vs to indicate level of verbosity
            -v will show a lot of messages to stderr
            -vv will show debug messages to the log file as well
"""

#======================================
#   Import Statements
#
# Import the needed modules.
import argparse
import json
import logging
import logging.handlers
import os
import pathlib
import re
import subprocess
import sys
import time

SCRIPT_NAME = ("prestage_matlab")
MAIN_LIBRARY = pathlib.Path("/Library/")
TMP_DIR = pathlib.Path("/private/tmp")
STAGING_FOLDER = TMP_DIR.joinpath("matlab")
LICENSE_FILE = STAGING_FOLDER.joinpath("license.dat")
INPUT_FILE = STAGING_FOLDER.joinpath("custom_install.txt")
# All strings with {} in them are holders for later formatting.
LICENSE_DAT = ("SERVER {} {}\nUSE_SERVER")
MATLAB_SERVER = ("your.matlab.license.server")
MAIN_ERROR = ("There was a problem during Step %s. See logs for detail. "
              "If necessary, add a -v to the script parameters to increase "
              "log verbosity.")
# This average (in bytes), is derived from the 13GBs of 27 packages
AVERAGE_FILESIZE = (500000000)

INSTALLER_INPUT = """fileInstallationKey={}
agreeToLicense=yes
outputFile=/private/tmp/matlab/install.log
licensePath={}
"""


LOGGER = logging.getLogger(__name__)


def available_bytes():
    # available blocks * fragment size (4096 in 10.15)
    return os.statvfs("/").f_bavail * os.statvfs("/").f_frsize


def check_matlab_install(controlling_product, args):
    """Runs a command in MATLAB that returns the installed version
    and any installed Toolboxes.
    """
    controlling_product_dir = pathlib.Path(
        f"/Applications/{controlling_product}_{args.matlab_version}.app/"
    )
    ml_cmd = [
        controlling_product_dir.joinpath("bin/matlab"),
        "-nojvm", "-nodisplay", "-nosplash", "-batch",
        (
            "v = ver; "
            "for k = 1:length(v) fprintf('%s,', v(k).Name); end; "
            "quit force"
        )
    ]
    LOGGER.debug("Attempting command: %s", ml_cmd)
    try:
        ml_out = subprocess.check_output(ml_cmd).decode()
        LOGGER.debug("MATLAB output: %s", ml_out)
        ml_ver = [ml for li in ml_out.splitlines() if "Warning" not in li
                  for ml in li.split(",") if ml and ml != "MATLAB"]
        LOGGER.debug("Cleaned output: %s", ml_ver)
        return set(ml_ver)
    except subprocess.CalledProcessError as err:
        LOGGER.debug("Error: %s", err)
        # return empty set. If something's wrong we'll just plow over it.
        return set()


def controlling_product_installed(controlling_product, args):
    # Read in requested MATLAB version.
    controlling_product_dir = pathlib.Path(
        f"/Applications/{controlling_product}_{args.matlab_version}.app/"
    )
    if controlling_product_dir.is_dir():
        LOGGER.debug(
            "%s installed to: %s",
            controlling_product,
            controlling_product_dir
        )
        return True
    return False


def double_check_jamf_errors(_event):
    # Build a portion of the the pkg name from the event name.
    _pkg = _event.replace("@", "") + ".pkg"
    LOGGER.debug("Implied pkg: %s", _pkg)
    _regex = rf"Successfully installed .*{_pkg}"
    LOGGER.debug("Regular Expression: %s", _regex)
    log_events = log_show(log_predicate=(
        "process == 'jamf' AND subsystem == 'com.jamf.management.binary'")
    )
    for _log in log_events:
        if "jamf" in _log.get("processImagePath", ""):
            LOGGER.debug("jamf log event dict: %s", _log)
            _msg = _log.get("eventMessage")
            LOGGER.info("log eventMessage: %s", _msg)
            if re.findall(_regex, _msg):
                return True
    return False


def get_args():
    parser = argparse.ArgumentParser(
        description=(
            "Prestage MATLAB installation."))
    parser.add_argument("jamfargs", nargs=3,
                        help="Built-in Jamf Arguments")
    parser.add_argument("matlab_version",
                        help="Release family for MATLAB. e.g. 'R2021a'")
    parser.add_argument("fi_key",
                        help="File Installation Key")
    parser.add_argument("dat_hash",
                        help="Hash from license.dat")
    parser.add_argument("addons_csv",
                        help="Additional Toolboxes, etc, in CSV format.")
    parser.add_argument("-s", "--server", default=MATLAB_SERVER,
                        help="Alternative MATLAB License Server URL.")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity. Increases with each level.")
    args = parser.parse_known_args()[0]
    # Cleanup parameter input from any common mistyped elements.
    for _arg in vars(args):
        # Ignore if the arg is not a string. We only need to worry about strs
        if not isinstance(getattr(args, _arg), str):
            continue
        # vars returns a list of each attribute's name in the args object's
        # NameSpace as a string, not as the object itself, so we need to get
        # the object by its name before we can then set it by setattr.
        setattr(args, _arg,
                re.sub(r"\"|'", "", getattr(args, _arg, "")).strip())
    # One specific to the MATLAB Version
    args.matlab_version = (
        re.sub(r"^r", "R", re.sub(r"A$", "a", args.matlab_version)))
    return args


def giga_bytes(byte_size):
    return round(byte_size / 1000.0 / 1000.0 / 1000.0, 1)


def is_space_available(addons_list):
    # Assume double the space is needed as the install will take up as much
    # space (if not more) than the install
    total_bytes = 2 * len(addons_list) * AVERAGE_FILESIZE
    LOGGER.debug("total(%s) = length(%s) * average(%s)",
                 total_bytes, len(addons_list), AVERAGE_FILESIZE)
    LOGGER.warning("Probable space required for installation: %sGB",
                   giga_bytes(total_bytes))
    LOGGER.warning("Available capacity: %sGB", giga_bytes(available_bytes()))
    # This will return True/False
    return total_bytes < available_bytes()


def jamf_event(_event):
    """Attempts to call Custom Event name from the Jamf Pro Server."""
    LOGGER.debug("Incoming Event Request: %s", _event)
    try:
        jamf_cmd = ["/usr/local/jamf/bin/jamf", "policy", "-event", _event]
        LOGGER.debug("Jamf Command Syntax: %s", jamf_cmd)
        _out = subprocess.check_output(jamf_cmd).decode()
        if "No policies were found" in _out:
            LOGGER.info("'No policies were found' in: %s", _out)
            return False
        LOGGER.debug("Jamf Binary Output: %s", _out)
        return True
    except subprocess.CalledProcessError as err:
        if double_check_jamf_errors(_event):
            return True
        LOGGER.error("Error calling event %s. Error follows.", _event)
        LOGGER.error(err)
        return False


def log_show(_time="1m", log_predicate=None):
    log_cmd = ["/usr/bin/log", "show", "--style", "JSON", "--last", _time]
    if log_predicate:
        log_cmd.extend(["--predicate", log_predicate])
    LOGGER.debug("Log Command Syntax: %s", log_cmd)
    try:
        _out = subprocess.check_output(log_cmd)
        return json.loads(_out)
    except subprocess.CalledProcessError as err:
        LOGGER.debug("Error pulling logs. Error follows.")
        LOGGER.debug(err)
        return False


def logger_config(other_logger, _name, _verbosity=0):
    """Configures the LOGGER for this script."""
    # Create a path to the log file.
    log_path = MAIN_LIBRARY.joinpath(f"Logs/{_name}/{_name}.log")
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


def parse_addons(args):
    """Read in the requested software and determine if it is already
    installed. Therefore we don't waste disk space and bandwidth trying
    to install extant software.
    """
    # Split along commas, removing any trailing or leading whitespace.
    all_requested = re.split(r" ?, ?", args.addons_csv)
    controlling_product = all_requested[0]
    # Sets are unordered iterables. They have advantages, the biggest one being
    # they automatically ignore duplicates. Additionally, set logic can be
    # used to find differences.
    addons_set = set(all_requested[1:])
    already_installed = set()
    if controlling_product_installed(controlling_product, args):
        already_installed = check_matlab_install(controlling_product, args)
        LOGGER.warning("Previously-installed toolboxes: %s",
                       ", ".join(already_installed))
    else:
        LOGGER.info(
            "%s %s not yet installed.",
            controlling_product,
            args.matlab_version
        )
    # Convert back into ordered list for further processing.
    return (
        controlling_product,
        return_difference(addons_set, already_installed)
    )


def prestage_install_files(controlling_product, addons_list, args):
    """Requests the packages from the Jamf Pro Server by their event.
    Since these events were created by the build_packages script, they
    are standardized based on the name and controlling product.
    """
    if not controlling_product_installed(controlling_product, args):
        LOGGER.warning(
            "Requesting Prestage of Controlling Product: %s %s",
            controlling_product,
            args.matlab_version,
        )
        controlling_product_event = (
            f"@MathWorks.{args.matlab_version}.{controlling_product}"
        )
        if not try_event(controlling_product_event):
            return False
    for _install in addons_list:
        LOGGER.warning("Requesting Prestage of the Following: %s", _install)
        # Build up the event name.
        _event = (
            f"@MathWorks.{args.matlab_version}.{controlling_product}." +
            _install.replace(" ", ".")
        )
        LOGGER.debug("Constructed Event: %s", _event)
        if not try_event(_event):
            return False
    return True


def prestage_installer(args):
    """Triggers the event that places the installer in the temp folder."""
    return try_event(f"@MathWorks.{args.matlab_version}.Installer")


def prestage_license(args, controlling_product, addons_list):
    """Creates the files needed for the installation"""
    # Make sure directory exists before we start adding files.
    if not STAGING_FOLDER.is_dir():
        LOGGER.debug("Creating folder: %s", STAGING_FOLDER)
        STAGING_FOLDER.mkdir(exist_ok=True, parents=True)
    # Create license.dat file:
    LOGGER.debug("Creating license file: %s", LICENSE_FILE)
    lf_contents = LICENSE_DAT.format(args.server, args.dat_hash)
    LOGGER.debug("License file contents: %s", lf_contents)
    with open(LICENSE_FILE, "w") as l_f:
        l_f.write(lf_contents)
    # Create installer_input.txt
    LOGGER.debug("Creating input file: %s", INPUT_FILE)
    if_contents = INSTALLER_INPUT.format(args.fi_key, LICENSE_FILE)
    if not controlling_product_installed(controlling_product, args):
        to_install = [controlling_product] + addons_list
    else:
        to_install = addons_list
    if_contents += ("\n".join(
        ["product." + re.sub(r" ", "_", _i) for _i in to_install])
    )
    LOGGER.debug("Input file contents %s", if_contents)
    with open(INPUT_FILE, "w") as i_f:
        i_f.write(if_contents)
    return True


def return_difference(main_set, difference_set):
    """Update main_set by removing anything it contains that is also in
    difference_set. Convert the updated set to a list, and return that
    list sorted."""
    main_set.difference_update(difference_set)
    LOGGER.debug("Updated set: %s", main_set)
    # Returns ordered, sorted list
    main_list = sorted(list(main_set))
    LOGGER.debug("Returning sorted list: %s", main_list)
    return main_list


def try_event(_event):
    """Attempts to call Custom Event name from the Jamf Pro Server, if
    it fails, it will attempt two more times. If this still fails, it
    will fail completely.
    """
    # Attempt install 3 times
    LOGGER.info("Requesting Jamf Event: %s", _event)
    for attempt in range(1, 4):
        if jamf_event(_event):
            return True
        # Sleep for 5 seconds to keep from spamming the jamf binary.
        time.sleep(5)
    return False


#======================================
#   Main Function (Core Logic)
#
def main(args):
    """Main Program"""
    # The following are in this order due to IO concerns. If something's wrong
    # with the shorter steps, the script will not need to wait for the
    # downloads before it catches them.
    install_controlling_product = True
    _step = 1
    LOGGER.warning("Step %d: Parsing Requested Software", _step)
    controlling_product, addons_list = parse_addons(args)
    LOGGER.debug("%s: addons_list: %s", controlling_product, addons_list)
    if controlling_product_installed(controlling_product, args):
        LOGGER.warning(
            "%s %s is already installed!",
            controlling_product,
            args.matlab_version,
        )
        install_controlling_product = False
        # If, after checking the status of installed addons, the requested
        # addons are already installed, this list will return empty.
        if not addons_list:
            LOGGER.error(
                ("After checking the requested software and Toolboxes, "
                 "it's been determined that %s %s is already installed "
                 "with the requested Toolboxes: %s"),
                controlling_product,
                args.matlab_version,
                ", ".join(args.addons_csv.split(",")[1:]),
            )
            # Write a file so the next script will know to skip trying
            # to install.
            status_file = pathlib.Path("/private/tmp/matlab/status.txt")
            status_file.parent.mkdir(exist_ok=True, parents=True)
            with open(status_file, "w") as fp:
                fp.write("skip")
            # Return success here so clients don't see this as a "Failure"
            return 0
        LOGGER.warning(
            "%s %s: Requesting Additional Toolboxes: %s",
            controlling_product,
            args.matlab_version,
            ", ".join(addons_list)
        )
    LOGGER.info("Step %d: Success!", _step)
    _step += 1
    LOGGER.warning("Step %d: Checking Available Disk Space", _step)
    if install_controlling_product:
        to_install = [controlling_product] + addons_list
    else:
        to_install = addons_list
    if not is_space_available(to_install):
        LOGGER.error(
            ("%s %s: There does not appear to be enough "
             "free disk space for this installation."),
            controlling_product,
            args.matlab_version,
        )
        return 1
    LOGGER.info("Step %d: Success!", _step)
    _step += 1
    LOGGER.warning("Step %d: Creating License Files", _step)
    if not prestage_license(args, controlling_product, addons_list):
        LOGGER.error(MAIN_ERROR, _step)
        return 1
    LOGGER.info("Step %d: Success!", _step)
    _step += 1
    LOGGER.warning("Step %d: Setting Up MATLAB Installer", _step)
    if not prestage_installer(args):
        LOGGER.error(MAIN_ERROR, _step)
        return 1
    LOGGER.info("Step %d: Success!", _step)
    _step += 1
    LOGGER.warning("Step %d: Prestaging Software", _step)
    if not prestage_install_files(controlling_product, addons_list, args):
        LOGGER.error(MAIN_ERROR, _step)
        return 1
    LOGGER.info("Step %d: Success!", _step)

    LOGGER.warning("MATLAB Prestage Complete!")
    return 0


if __name__ == "__main__":
    # Get root LOGGER when running as script
    LOGGER = logging.getLogger("")
    ARG_V = get_args()
    # Configure LOGGER
    LOGGER = logger_config(LOGGER, SCRIPT_NAME, ARG_V.verbose)
    sys.exit(main(ARG_V))
