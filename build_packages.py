#!/usr/bin/env python3
# encoding: utf-8
# ===========================================================================
#   Package Builder
#

# ======================================
#   Import Statements
#
import argparse
import io
import logging
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as xml_et
import zipfile

from xml.dom import minidom
import matlab_pkg.archive as ml_archive
import matlab_pkg.common as ml_common
import matlab_pkg.product as ml_product
import matlab_pkg.jamf_api as jamf_api


# Create module-level LOGGER
LOGGER = logging.getLogger(__name__)


def get_args():
    parser = argparse.ArgumentParser(
        description=(
            "Take a full MathWorks DMG and create a set of packages."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=("Incrementally increase output args.verbose"),
    )
    group.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "-d", "--dmg", type=pathlib.Path, required=True,
        help=(
            "Path to DMG containing all of the MathWorks install files."
        )
    )
    parser.add_argument(
        "-f", "--folder", type=pathlib.Path,
        help=(
            "Optional path to working folder. By default, the working folder "
            "is the parent folder of the DMG."
        )
    )
    parser.add_argument(
        "-t", "--targets", type=pathlib.Path,
        help=(
            "Optional path to a text file containing a newline-separated list "
            "of products to package. Default is the "
            "target_software_and_toolboxes.txt file contained within this "
            "repository."
        )
    )
    parser.add_argument(
        "-p", "--products", action="append",
        help=(
            "Optional product names to target instead of the targets file. "
            "Multiple products can be specified with additional switches: "
            "-p 'Product Name 1' -p 'Product Name 2'..."
        )
    )
    parser.add_argument(
        "-U", "--user",
        help=(
            "Username with Jamf API privileges."
        )
    )
    parser.add_argument(
        "-P", "--password",
        help=(
            "Password for user."
        )
    )
    parser.add_argument(
        "-s", "--skip", action="store_true",
        help=("Skips processing DMG. Use only if the DMG has been processed "
              "on a previous run and the policy definitions file exists.")
    )
    args = parser.parse_args()
    return args


def clean_directory(dir_to_clean):
    """Cleans up directory (if it exists)
    """
    if dir_to_clean.exists():
        shutil.rmtree(dir_to_clean)
        return True
    return False


def compress_nlm(product, nlm_root, platform):
    """Takes the Network License Manager files and creates compressed archives
    for both platforms.
    """
    short_version = product.version.replace(".", "")
    zip_root = nlm_root.joinpath(platform)
    zip_file = nlm_root.joinpath(
        f"Network_License_Manager{short_version}_{platform}.zip"
    )
    # Create the XML file stored in the zip.
    mw_contents_file = f"mwcontents_{zip_file.stem}.xml"
    mw_root = minidom.Document()
    mw_contents = mw_root.createElement("contents")
    with zipfile.ZipFile(zip_file, "w") as new_zip:
        for _file in zip_root.rglob("*"):
            sub_e = None
            if _file.name == ".DS_Store":
                continue
            stored_name = str(_file).replace(f"{nlm_root}/{platform}/", "")
            # Add the XML nodes for each file.
            sub_e_text = mw_root.createTextNode(stored_name)
            if _file.suffix == ".enc":
                sub_e = mw_root.createElement("componentFiles")
                sub_e.appendChild(sub_e_text)
            elif _file.suffix == ".xml":
                sub_e = mw_root.createElement("definitions")
                sub_e.appendChild(sub_e_text)
            if sub_e is not None:
                mw_contents.appendChild(sub_e)
            new_zip.write(_file, arcname=stored_name)
            LOGGER.debug(
                "Network License Manager: Added file to zip archive: %s",
                stored_name
            )
        # Write the contents file to the zip
        mw_root.appendChild(mw_contents)
        mw_contents_str = mw_root.toprettyxml(indent="  ", standalone=True)
        new_zip.writestr(mw_contents_file, mw_contents_str)

    LOGGER.info(
        "Network License Manager: Successfully created archive: %s",
        zip_file
    )
    return zip_file


def create_anchor_policy(product_name, policy_definition, enc_creds):
    """Creates the anchor policy based on the policy definition."""
    LOGGER.info("%s: Attempting to create anchor policy.", product_name)
    policy_name = policy_definition.get("anchor_name")
    policy_exists, policy_id = jamf_api.policy_name_exists(
        policy_name,
        enc_creds
    )
    # Create a new policy if an existing one is missing.
    if not policy_exists:
        LOGGER.warning(
            "%s: Policy '%s' does not exist. Creating from template.",
            product_name,
            policy_name
        )
        policy_xml = jamf_api.template_load("anchor_template.xml")
    else:
        LOGGER.warning(
            "%s: Policy '%s' (%s) exists!",
            product_name,
            policy_name,
            policy_id
        )
        policy_xml = jamf_api.policy_get_xml(policy_id, enc_creds)

    # Iterate over the values important to the Anchor Policy.
    for _key, _value in policy_definition.items():
        if _key == "anchor_category":
            policy_xml.find(".//general/category/name").text = _value
        elif _key == "anchor_category_id":
            policy_xml.find(".//general/category/id").text = _value
        elif _key == "anchor_name":
            policy_xml.find(".//general/name").text = _value
            policy_xml.find(
                ".//self_service/notification_subject"
            ).text = _value
        elif _key == "anchor_trigger":
            policy_xml.find(".//general/trigger_other").text = _value
        elif _key == "package_id":
            policy_xml.find(
                ".//package_configuration/packages/package/id"
            ).text = _value
        elif _key == "package_name":
            policy_xml.find(
                ".//package_configuration/packages/package/name"
            ).text = _value

    # Make the changes
    if not policy_exists:
        jamf_api.policy_post(policy_xml, enc_creds)
    else:
        jamf_api.policy_put(policy_id, policy_xml, enc_creds)
    # Check to make sure new/updated policy exists
    policy_exists, policy_id = jamf_api.policy_name_exists(
        policy_name,
        enc_creds
    )
    if not policy_exists:
        return False
    return policy_id


def create_self_service_policy(product_name, policy_definition, enc_creds):
    """Creates the Self Service policy based on the policy definition."""
    LOGGER.info("%s: Attempting to create Self Service policy.", product_name)
    policy_name = policy_definition.get("self_service_name")
    policy_exists, policy_id = jamf_api.policy_name_exists(
        policy_name,
        enc_creds
    )

    # Create a new policy if an existing one is missing.
    if policy_definition.get("is_toolbox"):
        template_name = "toolbox_self_service_template.xml"
    else:
        template_name = "self_service_template.xml"

    if not policy_exists:
        LOGGER.warning(
            "%s: Policy '%s' does not exist. Creating from template.",
            product_name,
            policy_name
        )
        policy_xml = jamf_api.template_load(template_name)
    else:
        LOGGER.warning(
            "%s: Policy '%s' (%s) exists!",
            product_name,
            policy_name,
            policy_id
        )
        policy_xml = jamf_api.policy_get_xml(policy_id, enc_creds)

    scripts_xml = [
        _s for _s in policy_xml.findall(".//scripts/script")
        if _s.find(".//name").text == "MatLab.Prestage"
    ][0]

    for _key, _value in policy_definition.items():
        if _key == "dependencies":
            # Need to make sure the product itself is represented.
            if product_name != "Install All":
                _value.insert(1, product_name)
            scripts_xml.find(".//parameter7").text = (
                ",".join(_value or ["MATLAB"])
            )
        elif _key == "family":
            scripts_xml.find(".//parameter4").text = _value
        elif _key == "license_hash":
            scripts_xml.find(".//parameter6").text = _value
        elif _key == "license_key":
            scripts_xml.find(".//parameter5").text = _value
        elif _key == "scope_id":
            policy_xml.find(
                ".//scope/computer_groups/computer_group/id"
            ).text = _value
        elif _key == "scope_name":
            policy_xml.find(
                ".//scope/computer_groups/computer_group/name"
            ).text = _value
        elif _key == "self_service_name":
            policy_xml.find(".//general/name").text = _value
            policy_xml.find(
                ".//self_service/notification_subject"
            ).text = _value
            policy_xml.find(
                ".//self_service/self_service_display_name"
            ).text = _value
        elif _key == "self_service_category":
            policy_xml.find(".//general/category/name").text = _value
            policy_xml.find(
                ".//self_service_categories/category/name"
            ).text = _value
        elif _key == "self_service_category_id":
            policy_xml.find(".//general/category/id").text = _value
            policy_xml.find(
                ".//self_service_categories/category/id"
            ).text = _value

    # Make the changes
    if not policy_exists:
        jamf_api.policy_post(policy_xml, enc_creds)
    else:
        jamf_api.policy_put(policy_id, policy_xml, enc_creds)
    # Check to make sure new/updated policy exists
    policy_exists, policy_id = jamf_api.policy_name_exists(
        policy_name,
        enc_creds
    )
    if not policy_exists:
        return False
    return policy_id


def create_installer(installer_folder, pkg_root, pkg_dest, pkg_prefix):
    """Finds the installer "binary" in the app and extracts the embedded zip.
    """
    installer_pkg = pkg_root.parent.joinpath(
        f"packages/{pkg_prefix}Installer.pkg"
    )
    if installer_pkg.exists():
        LOGGER.warning(
            f"MathWorks Installer: %s Exists. Skipping installer creation.",
            installer_pkg.name
        )
        return True, installer_pkg
    installer_file = installer_folder.joinpath("InstallForMacOSX")
    # Find the tail command in the script in the head of the file. This will
    # tell us which line number to seek to.
    installer_tail = find_tail(installer_file)
    # Open the installer file, seek to the line number, and combine the rest.
    with open(installer_file, "rb") as fp:
        installer_zip = b"".join(fp.readlines()[installer_tail-1:])
    pkg_dest.mkdir(parents=True, exist_ok=True)
    # # Read the zip into a ZipFile object by creating a file-like object
    # # since it is currently just a bytestring.
    # installer_zipfile = zipfile.ZipFile(io.BytesIO(installer_zip))
    # # Extract the installer zip to the file.
    # installer_zipfile.extractall(path=pkg_dest)
    pkg_root.parent.joinpath("tmp").mkdir(parents=True, exist_ok=True)
    with open(pkg_root.parent.joinpath("tmp/zip.zip"), "wb") as fp:
        fp.write(installer_zip)
    subprocess.check_call([
        "/usr/bin/unzip", "-q",
        pkg_root.parent.joinpath("tmp/zip.zip"),
        "-d", pkg_dest
    ])
    # Create the PKG installer for the installer
    return create_package(pkg_root, installer_pkg), installer_pkg


def create_package(pkg_root, package_path):
    """Uses `pkgbuild` to create a package from the package root.
    """
    pkg_build_cmd = [
        "/usr/bin/pkgbuild",
        "--root", pkg_root,
        "--identifier", package_path.stem,
        package_path
    ]
    # subprocess.check_call returns the return code, and, in Python, 0 is
    # False, so we instead check if the return is 0, if so, this returns
    # True
    return subprocess.check_call(pkg_build_cmd) == 0


def create_product(product, pkg_archives, app_archives):
    """Takes a product, initiates its self-discovery, and extracts its files.
    """
    print_newlines()
    LOGGER.warning("%s: Beginning Product Creation.", product.name)
    LOGGER.debug(
        "%s: Preparing working directory: %s",
        product.name,
        pkg_archives
    )
    pkg_archives.mkdir(parents=True, exist_ok=True)
    LOGGER.info("%s: Parsing Product XML...", product.name)
    product.get_product_xml()
    LOGGER.warning(
        "%s: Parsing Product Components (this may take some time)...",
        product.name
    )
    product.get_components()
    LOGGER.warning("%s: Extracting/Copying Common Components...", product.name)
    make_platform_files(product, pkg_archives, app_archives, "common")
    LOGGER.warning("%s: Extracting/Copying Maci64 Components...", product.name)
    make_platform_files(product, pkg_archives, app_archives, "maci64")


def find_tail(installer_file):
    """Reads the script in the head of the Installer File and finds the line
    in which the zip file begins.
    """
    with open(installer_file, "rb") as fp:
        for _line in fp.readlines():
            line_match = re.match(r"tail -n \+(\d+)", _line.decode())
            if line_match:
                return int(line_match.groups()[0])


def make_platform_files(product, pkg_archives, app_archives, platform):
    """Extracts the XML from the platform archive, and copies the files from
    the archives folder in the DMG to the PKG root in the working folder.
    """
    # Get the platform-specific product attributes
    platform_archive = getattr(product, f"archive_{platform}")
    platform_xml_path = getattr(product, f"xml_path_{platform}")
    platform_components = getattr(product, f"components_{platform}")
    # Extract product XML
    platform_archive.extract(
        platform_xml_path,
        path=pkg_archives
    )
    LOGGER.info(
        "%s: Reading product data from: %s",
        product.name,
        platform_xml_path
    )
    # Extract all product components
    for component in platform_components:
        file_source = app_archives.joinpath(
            f"{platform}/{component.path}"
        )
        file_destination = pkg_archives.joinpath(
            f"{platform}/{component.path}"
        )
        file_destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(file_source, file_destination)
        except FileNotFoundError:
            # Some files are kept in other folders. Try to find them.
            alt_source = [
                _f for _f in
                file_source.parent.parent.rglob(f"*{component.path}")
            ][0]
            shutil.copy2(alt_source, file_destination)
        platform_archive.extract(
            component.xml_path,
            path=pkg_archives
        )
    LOGGER.info("%s: Completed copying files to target folder.", product.name)


def print_newlines():
    """Prints two newlines to stderr."""
    sys.stderr.write("\n\n")
    sys.stderr.flush()


def main(args):
    """Main program
    """
    # =========================================================================
    #                                                              Check Phase
    #
    # Don't start processing until we've confirmed all of the necessary
    # prerequisites.

    # Make sure we can get a user/pass for the API portion of the script.
    enc_creds = jamf_api.enc_creds_get(args)
    if not enc_creds:
        return 1, None

    # Make sure the DMG actually exists.
    if not args.dmg.exists():
        LOGGER.fatal("Path: %s does not exist.", args.dmg)
        return 1, None

    # If we are passed an argument to work out of a specific folder, check
    # to make sure that folder exists.
    if args.folder:
        work_folder = args.folder
        # Attempt to make the folder if it does not exist.
        if not work_folder.exists():
            try:
                work_folder.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                LOGGER.fatal(
                    "Unable to create Work Folder: %s :: %s",
                    work_folder,
                    err
                )
                return 1, None
    else:
        # Work out of the folder in which the DMG resides.
        work_folder = args.dmg.parent

    # Make sure we can mount the DMG
    mount_dev = ml_common.mount_dmg(args.dmg)
    if not mount_dev:
        LOGGER.fatal("Unable to mount DMG!")
        return 1, None

    # Find the mount point (whose name will vary depending upon the DMG)
    mount_point = [d for d in pathlib.Path("/Volumes").glob("matlab_*")][0]
    # This folder contains all of the encrypted MathWorks product files and
    # their accompanying XML definitions.
    app_archives = mount_point.joinpath(
        "InstallForMacOSX.app/Contents/MacOS/archives"
    )
    # Get the archive files from the mounted DMG. In the full installer, these
    # contain all of the XML definitions files for the common and maci64
    # platforms. These need to be located alongside their encrypted
    # counterparts in order for the License Key install to work.
    archive_common = ml_archive.MatLabArchive(
        app_archives.joinpath("platform_common.zip")
    )
    archive_maci64 = ml_archive.MatLabArchive(
        app_archives.joinpath("platform_maci64.zip")
    )
    # Quit if files do not exist.
    if not archive_common.file.exists():
        LOGGER.fatal("Unable to find archive: %s", archive_common.file)
        return 1, mount_dev
    if not archive_maci64.file.exists():
        LOGGER.fatal("Unable to find archive: %s", archive_maci64.file)
        return 1, mount_dev

    # This path will temporarily contain all of the product files before they
    # are packaged up. ROOT is the base folder to be passed to `pkgbuild`.
    # When the package is installed later, the files will be installed to
    # `/private/tmp/matlab/archives`
    pkg_root = work_folder.joinpath("ROOT")
    pkg_archives = pkg_root.joinpath("private/tmp/matlab/archives")
    # This path will be where the products are created.
    pkg_destination = work_folder.joinpath("packages")
    pkg_destination.mkdir(parents=True, exist_ok=True)

    # Get list of products in the definitions file
    if args.products:
        target_products = [
            ml_product.MathWorksProduct(_p) for _p in args.products
        ]
    else:
        target_products = ml_common.get_targets(args.targets)

    if not target_products:
        LOGGER.fatal(
            "There was an error getting a list of "
            "MathWorks Products to target!"
        )
        return 1, mount_dev

    LOGGER.warning(
        "Targeting the following products: " +
        ", ".join([str(t) for t in target_products])
    )

    # =========================================================================
    #                                                         Processing Phase
    #
    # Now that we are in an acceptable initial condition with the DMG mounted,
    # the work folder ready, the two archive files discovered, and a list of
    # targets, start processing.

    # Create the Network License Manager zip files. These both need to be
    # inside of every package, so we perform this task once and add these at
    # each package creation stage.
    nlm_product = ml_product.MathWorksProduct("Network License Manager")
    nlm_product.archive_common = archive_common
    nlm_product.archive_maci64 = archive_maci64
    # Create the Network License Manager products outside of the packaging
    # root, as they need to be compressed and added to each product package
    # individually.
    nlm_root = work_folder.joinpath("Network License Manager")
    create_product(nlm_product, nlm_root, app_archives)
    LOGGER.warning(
        "Network License Manager: Creating Version: %s",
        nlm_product.version
    )
    nlm_zip_common = compress_nlm(nlm_product, nlm_root, "common")
    nlm_zip_maci64 = compress_nlm(nlm_product, nlm_root, "maci64")

    # Get Release Family (aka "R2021a")
    # While we could deduce this information from the file name, it is much
    # more accurate to get this from the XML itself. We only need this
    # information once, so collecting it here will be slightly less
    # IO-intensive (this process is very heavy on IO so might as well)
    target_family = nlm_product.family
    print_newlines()
    LOGGER.warning("MathWorks Family: %s", target_family)
    # Various labels for different stages of the process.
    category_label = f"MathWorks {target_family}"
    category_label_toolbox = f"{category_label} Toolboxes"
    # mathworks_prefix is used by the products to produce the policy name,
    # custom trigger name, and package name.
    mathworks_prefix = f"MathWorks.{target_family}."
    category_label_anchor = f"{mathworks_prefix}Anchor"
    category_label_anchor_toolbox = f"{category_label_anchor}.Toolboxes"
    # Static Group name
    static_group_name = f"{mathworks_prefix}Advertised.STG"

    # Prep package root.
    if clean_directory(pkg_root):
        LOGGER.debug("Cleaned up prior package root.")
    # Create the MathWorks installer. We need this to perform the install with
    # every product
    print_newlines()
    LOGGER.warning("Installer: Creating Package...")
    installer_success, installer_file = create_installer(
        app_archives.parent,
        pkg_root,
        pkg_archives.parent,
        mathworks_prefix
    )
    if not installer_success:
        LOGGER.fatal("Installer: There was a problem creating the package!")
        return 1, mount_dev

    # Upload the installer. We fail here because this part is essential
    # to installing any MathWorks software.
    installer_pkg_id = jamf_api.package_upload(installer_file, enc_creds)
    if not installer_pkg_id:
        LOGGER.fatal("Installer: There was a problem uploading the package!")
        return 1, mount_dev

    # Create Categories
    LOGGER.info("Attempting to create category: %s", category_label)
    category_label_id = jamf_api.category_create(category_label, enc_creds)
    # Policies cannot be uploaded via the API without a category, so we fail
    # here if this does not succeed.
    if not category_label_id:
        LOGGER.error("Cannot create category: %s!", category_label)
        return 1, mount_dev
    LOGGER.info("Attempting to create category: %s", category_label_toolbox)
    category_label_toolbox_id = jamf_api.category_create(
        category_label_toolbox,
        enc_creds
    )
    if not category_label_toolbox_id:
        LOGGER.error("Cannot create category: %s!", category_label_toolbox)
        return 1, mount_dev
    LOGGER.info("Attempting to create category: %s", category_label_anchor)
    category_label_anchor_id = jamf_api.category_create(
        category_label_anchor,
        enc_creds
    )
    if not category_label_anchor_id:
        LOGGER.error("Cannot create category: %s!", category_label_anchor)
        return 1, mount_dev
    LOGGER.info(
        "Attempting to create category: %s",
        category_label_anchor_toolbox
    )
    category_label_anchor_toolbox_id = jamf_api.category_create(
        category_label_anchor_toolbox,
        enc_creds
    )
    if not category_label_anchor_toolbox_id:
        LOGGER.error(
            "Cannot create category: %s!",
            category_label_anchor_toolbox
        )
        return 1, mount_dev

    LOGGER.warning(
        "Categories: %s (%s) :: %s (%s) :: %s (%s) :: %s (%s)",
        category_label,
        category_label_id,
        category_label_toolbox,
        category_label_toolbox_id,
        category_label_anchor,
        category_label_anchor_id,
        category_label_anchor_toolbox,
        category_label_anchor_toolbox_id
    )

    print_newlines()
    # Create Static Group
    LOGGER.info("Attempting to create group: %s", static_group_name)
    static_group_id = jamf_api.group_create(
        static_group_name,
        enc_creds
    )
    if not static_group_id:
        LOGGER.error("Cannot create group: %s!", static_group_name)
        return 1, mount_dev
    LOGGER.warning("Static Group: %s (%s)", static_group_name, static_group_id)

    # Get license information for use by all of the products.
    license_key = ml_common.get_file_installation_key(target_family)
    license_hash = ml_common.get_license_hash(target_family)
    LOGGER.info("Key: %s :: Hash: %s", license_key, license_hash)

    # Read in any policy definitions file that exists in the work folder.
    # If it does not exist, it will be created at the end of the run. This
    # exists mostly as a troubleshooting step.
    policy_definitions_json = work_folder.joinpath("policy_definitions.json")
    policy_definitions = ml_common.read_json(policy_definitions_json)
    policy_definitions.update({
        "Installer": {
            "anchor_category": category_label_anchor,
            "anchor_category_id": category_label_anchor_id,
            "anchor_name": installer_file.stem,
            "anchor_trigger": f"@{installer_file.stem}",
            "dependencies": [],
            "is_toolbox": False,
            "package_id": installer_pkg_id,
            "package_name": installer_file.name,
            "scope_id": static_group_id,
            "scope_name": static_group_name,
            "self_service_name": False,
            "self_service_category": False,
        }
    })
    LOGGER.debug(policy_definitions)

    # Iterate over products
    for product in target_products:
        if args.skip:
            print_newlines()
            LOGGER.warning("Skipping product processing!")
            break
        # At the beginning of every loop, we check if the package root exists
        # and clean it out, so that it doesn't interfere with each new pkg
        if clean_directory(pkg_root):
            LOGGER.debug("Cleaned up prior package root.")
        # =====================================================================
        #                                                        Parsing Phase
        # Add the archives to the products
        product.archive_common = archive_common
        product.archive_maci64 = archive_maci64
        # This function copies the product files from the DMG, and extracts
        # the XML from the zip archives and places them next to the product
        # files.
        create_product(product, pkg_archives, app_archives)
        # Add Network License Manager zip archives to the product.
        shutil.copy2(nlm_zip_common, pkg_archives.joinpath("common"))
        shutil.copy2(nlm_zip_maci64, pkg_archives.joinpath("maci64"))

        # =====================================================================
        #                                              Policy Definition Phase
        policy_definitions.update({product.name: {}})
        product_policy = policy_definitions.get(product.name)
        # Determine whether or not the product is a toolbox and change
        # things accordingly.
        if not product.is_controlling_product:
            LOGGER.info(
                "%s: Controlled by: %s.",
                product.name,
                product.controlling_product
            )
            if not product.controlling_product:
                return 1, mount_dev
            # product_full_name is used for the policy, but also the package
            # and the custom trigger. In the case of a toolbox, we add the
            # controlling product's name.
            # Example:
            #   MathWorks.R2021a.MATLAB.Curve.Fitting.Toolbox
            product_full_name = (
                f"{mathworks_prefix}{product.controlling_product}." +
                product.name.replace(" ", ".")
            )
            # Human-readable variant
            # Example:
            #   Add Curve Fitting Toolbox to MATLAB R2021a
            self_service_name = (
                f"Add {product.name} to {product.controlling_product} "
                f"{target_family}"
            )
            policy_category = category_label_toolbox
            policy_category_id = category_label_toolbox_id
            anchor_category = category_label_anchor_toolbox
            anchor_category_id = category_label_anchor_toolbox_id
        # For controlling products (not toolboxes) like MATLAB and Simulink
        else:
            LOGGER.info("%s: is a controlling product.", product.name)
            product_full_name = (
                mathworks_prefix + product.name.replace(" ", ".")
            )
            self_service_name = (
                f"{product.name} {target_family}"
            )
            product.dependency_names.append(product.name)
            policy_category = category_label
            policy_category_id = category_label_id
            anchor_category = category_label_anchor
            anchor_category_id = category_label_anchor_id

        anchor_trigger = f"@{product_full_name}"
        package_name = f"{product_full_name}.pkg"
        product_policy.update(
            anchor_category=anchor_category,
            anchor_category_id=anchor_category_id,
            anchor_name=product_full_name,
            anchor_trigger=anchor_trigger,
            dependencies=product.dependency_names,
            family=target_family,
            is_toolbox=not product.is_controlling_product,
            license_hash=license_hash,
            license_key=license_key,
            package_name=package_name,
            scope_id=static_group_id,
            scope_name=static_group_name,
            self_service_name=self_service_name,
            self_service_category=policy_category,
            self_service_category_id=policy_category_id,
        )
        package_path = pkg_destination.joinpath(package_name)

        # =====================================================================
        #                                                      Packaging Phase
        # Create the product package
        if package_path.exists():
            LOGGER.warning(
                "%s: Skipping package creation: %s",
                product.name,
                package_path
            )
        elif not create_package(pkg_root, package_path):
            LOGGER.error(
                "%s: There was an error creating package %s",
                product.name,
                package_path.name
            )
            # Restart the loop to prevent further processing of this product
            continue

        # =====================================================================
        #                                                         Upload Phase
        package_id = None
        package_id = jamf_api.package_upload(package_path, enc_creds)
        if not package_id:
            LOGGER.error(
                "%s: Package not uploaded. Skipping further processing.",
                product.name
            )
            continue

        product_policy.update(package_id=package_id)

    print_newlines()
    LOGGER.warning(
        "Package creation phase complete. "
        "Processing extrapolated policy definitions..."
    )

    # =========================================================================
    #                                                    Policy Creation Phase
    print_newlines()
    # Create Installer Anchor
    LOGGER.info("Attempting to create policy: %s", installer_file.stem)
    install_success = create_anchor_policy(
        "Installer",
        policy_definitions.get("Installer"),
        enc_creds
    )

    # We need all of the products accounted for in order to process all of
    # the dependencies. Hence the new loop here.
    for product in target_products:
        print_newlines()
        product_policy = policy_definitions.get(product.name)
        LOGGER.debug(
            "%s: Targeting Policy Definition: %s",
            product.name,
            product_policy
        )
        LOGGER.info(
            "%s: Dependencies: %s",
            product.name,
            ", ".join(product_policy.get("dependencies"))
        )
        # Create the Anchor policy
        new_anchor_id = create_anchor_policy(
            product.name,
            product_policy,
            enc_creds
        )
        if not new_anchor_id:
            LOGGER.error(
                ("%s: There was a problem creating the anchor policy! "
                 "Skipping further processing."),
                product.name
            )
            continue
        LOGGER.warning(
            "%s: Policy: %s (%s) Successfully created!",
            product.name,
            product_policy.get("anchor_name"),
            new_anchor_id
        )
        product_policy.update(anchor_id=new_anchor_id)
        # Create the Self Service policy
        new_self_service_id = create_self_service_policy(
            product.name,
            product_policy,
            enc_creds
        )
        if not new_self_service_id:
            LOGGER.error(
                ("%s: There was a problem creating the Self Service policy! "
                 "Skipping further processing."),
                product.name
            )
            continue
        LOGGER.warning(
            "%s: Policy: %s (%s) Successfully created!",
            product.name,
            product_policy.get("self_service_name"),
            new_self_service_id
        )
        product_policy.update(self_service_id=new_self_service_id)

    print_newlines()
    # Create policy for all products
    policy_all_name = "Install All"
    policy_all_dict = dict(
        dependencies=[_t.name for _t in target_products],
        family=target_family,
        is_toolbox=False,
        license_hash=license_hash,
        license_key=license_key,
        scope_id=static_group_id,
        scope_name=static_group_name,
        self_service_name=f"MATLAB {target_family} and All Toolboxes",
        self_service_category=category_label,
        self_service_category_id=category_label_id,
    )
    policy_all_id = create_self_service_policy(
        policy_all_name,
        policy_all_dict,
        enc_creds
    )
    if not policy_all_id:
        LOGGER.error(
            ("%s: There was a problem creating the Self Service policy! "
             "Skipping further processing."),
            policy_all_name
        )
    else:
        LOGGER.warning(
            "%s: Policy: %s (%s) Successfully created!",
            policy_all_name,
            policy_all_name,
            policy_all_id
        )
        policy_all_dict.update(self_service_id=policy_all_id)
    policy_definitions.update({policy_all_name: policy_all_dict})

    ml_common.write_json(
        policy_definitions,
        work_folder.joinpath("policy_definitions.json")
    )
    return 0, mount_dev


if __name__ == "__main__":
    # Read in command-line arguments.
    ARG_V = get_args()
    # Get root LOGGER when running as script
    LOGGER = logging.getLogger("")
    # Setup logging
    LOGGER = ml_common.logger_config(
        LOGGER, "build_packages.log", ARG_V.verbose
    )
    # Run the main program, which returns an exit code and a mount point for
    # the DMG.
    RETURN_CODE, MOUNT_DEV = main(ARG_V)
    # Always unmount the DMG before exiting.
    if MOUNT_DEV and not ml_common.unmount_dmg(MOUNT_DEV):
        LOGGER.error(f"Unmount: Cannot unmount DMG.")
        sys.exit(1)
    sys.exit(RETURN_CODE)
