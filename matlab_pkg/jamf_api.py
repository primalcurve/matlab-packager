#!/usr/bin/env python3
# encoding: utf-8

import getpass
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET

from pkg_resources import packaging

from jamf_upload.jamf_upload_lib import api_connect, curl  # noqa: E402
import matlab_pkg.common as ml_common

# Create module-level LOGGER
LOGGER = logging.getLogger(__name__)

# Define Globals
JAMF_URL = "https://yourjamfserver.jamfcloud.com"
ID_CATEGORY_ANCHOR = 1
RE_TRIES = 3
TEMPLATES_DIR = ml_common.MOD_PATH.joinpath("templates")


def category_create(category_name, enc_creds):
    """Checks if category exists by searching for the category name"""
    # Don't re-upload the category.
    category_exists, category_id = category_name_exists(
        category_name,
        enc_creds
    )
    if category_exists:
        LOGGER.warning("%s (%s) already uploaded!", category_name, category_id)
        return category_id
    # Otherwise, create the new category.
    category_xml = template_load("category_template.xml")
    category_xml.find("name").text = category_name
    if not category_post(category_xml, enc_creds):
        return False
    # If the category creation succeeded, get the category ID.
    return category_get_id(category_name, enc_creds)


def category_post(category_xml, enc_creds):
    """POST new Anchor to Jamf"""
    # Build a URL to send the POST
    _url = url_encode(f"{JAMF_URL}/JSSResource/categories/id/0")
    return _xml_post(
        _url,
        enc_creds,
        category_xml,
    )


def category_get_all(enc_creds):
    """Retrieves a list of all categories in the JPC."""
    _url = url_encode(f"{JAMF_URL}/JSSResource/categories")
    return _xml_get(_url, enc_creds).findall("category")


def category_get_id(category_name, enc_creds):
    """Returns category ID from the JPS"""
    _url = url_encode(
        f"{JAMF_URL}/JSSResource/categories/name/{category_name}"
    )
    r_dict = _json_get(_url, enc_creds)
    if r_dict:
        try:
            obj_id = str(r_dict["category"]["id"])
        except KeyError:
            obj_id = "-1"
    else:
        obj_id = "-1"
    LOGGER.debug("Returned Object ID: %s", obj_id)
    return obj_id


def category_name_exists(category_name, enc_creds):
    """Checks if category exists by searching for the category name"""
    category_id = category_get_id(category_name, enc_creds)
    if category_id != "-1":
        return True, category_id
    return False, category_id


def enc_creds_get(args):
    """Returns encoded credentials for interacting with the API"""
    try:
        if not args.user:
            args.user = input(
                "Enter a Jamf Pro user with API rights: "
            )
        if not args.password:
            args.password = getpass.getpass(
                "Enter the password for '{}': ".format(args.user)
            )
    except KeyboardInterrupt:
        LOGGER.error("Cancelled by user.")
        return False
    if not args.password:
        LOGGER.error("No password provided.")
        return False
    enc_creds = api_connect.encode_creds(args.user, args.password)
    # Blank the password from memory
    args.password = ""
    return enc_creds


def group_create(group_name, enc_creds, static=True):
    """Checks if group exists by searching for the group name"""
    # Don't re-upload the group.
    group_exists, group_id = group_name_exists(
        group_name,
        enc_creds
    )
    if group_exists:
        LOGGER.warning(
            "%s (%s) already uploaded!",
            group_name,
            group_id
        )
        return group_id
    # Otherwise, create the new group.
    if static:
        group_xml = template_load("group_static_template.xml")
    else:
        group_xml = template_load("group_smart_template.xml")
    group_xml.find("name").text = group_name
    if not group_post(group_xml, enc_creds):
        return False
    # If the group creation succeeded, get the group ID.
    return group_get_id(group_name, enc_creds)


def group_post(group_xml, enc_creds):
    """POST new Anchor to Jamf"""
    # Build a URL to send the POST
    _url = url_encode(f"{JAMF_URL}/JSSResource/computergroups/id/0")
    return _xml_post(
        _url,
        enc_creds,
        group_xml,
    )


def group_get_all(enc_creds):
    """Retrieves a list of all categories in the JPC."""
    _url = url_encode(f"{JAMF_URL}/JSSResource/computergroups")
    return _xml_get(_url, enc_creds).findall("computer_group")


def group_get_id(group_name, enc_creds):
    """Returns group ID from the JPS"""
    _url = url_encode(
        f"{JAMF_URL}/JSSResource/computergroups/name/{group_name}"
    )
    r_dict = _json_get(_url, enc_creds)
    if r_dict:
        try:
            obj_id = str(r_dict["computer_group"]["id"])
        except KeyError:
            obj_id = "-1"
    else:
        obj_id = "-1"
    LOGGER.debug("Returned Object ID: %s", obj_id)
    return obj_id


def group_name_exists(group_name, enc_creds):
    """Checks if group exists by searching for the group name"""
    group_id = group_get_id(group_name, enc_creds)
    if group_id != "-1":
        return True, group_id
    return False, group_id


def package_delete(pkg_id, enc_creds):
    """Deletes package from the JPS"""
    package_url = (f"{JAMF_URL}/JSSResource/packages/id/{pkg_id}")
    if not _delete_object(package_url, enc_creds):
        LOGGER.debug("Unable to delete package: ID: %s", pkg_id)
        return False, package_url
    LOGGER.debug("Package deleted: ID: %s", pkg_id)
    return True, package_url


def package_get_all(enc_creds):
    """Retrieves a list of all packages in the JPC."""
    _url = url_encode(f"{JAMF_URL}/JSSResource/packages")
    return _xml_get(_url, enc_creds).findall("package")


def package_get_id(pkg_name, enc_creds):
    """Returns package ID from the JPS"""
    _url = url_encode(f"{JAMF_URL}/JSSResource/packages/name/{pkg_name}")
    r_dict = _json_get(_url, enc_creds)
    if r_dict:
        try:
            obj_id = str(r_dict["package"]["id"])
        except KeyError:
            obj_id = "-1"
    else:
        obj_id = "-1"
    LOGGER.debug("Returned Object ID: %s", obj_id)
    return obj_id


def package_name_exists(pkg_name, enc_creds):
    """Checks if package exists by searching for the package name"""
    pkg_id = package_get_id(pkg_name, enc_creds)
    if pkg_id != "-1":
        return True, pkg_id
    return False, pkg_id


def package_upload(pkg_path, enc_creds):
    """Uploads the package to the JPS"""
    # Don't re-upload the package.
    pkg_exists, pkg_id = package_name_exists(pkg_path.name, enc_creds)
    if pkg_exists:
        LOGGER.warning("%s (%s) already uploaded!", pkg_path.name, pkg_id)
        return pkg_id
    for _attempt in range(1, RE_TRIES + 1):
        LOGGER.warning(
            "Attempting Upload: %s :: Attempt %d of %d",
            pkg_path.name,
            _attempt,
            RE_TRIES
        )
        # post the package to Jamf Pro Cloud Distribution Point
        upload_response = _curl_package(
            pkg_path.name,
            pkg_path,
            enc_creds
        )
        LOGGER.debug(
            "Decoded Response:\n%s",
            upload_response.decode("ascii"),
        )
        try:
            parsed_response = ET.fromstring(upload_response)
            pkg_id = parsed_response.findtext("id")
            upload_success = parsed_response.findtext("successful") == "true"
            if not upload_success:
                LOGGER.error("Upload was unsuccessful! Trying again...")
                continue
            elif pkg_id:
                LOGGER.warning(
                    "Package uploaded successfully, ID=%s",
                    pkg_id,
                )
                return pkg_id
        except ET.ParseError:
            LOGGER.error("Could not parse XML.")
    return False


def policy_get_id(policy_name, enc_creds):
    """Returns policy ID from the JPS"""
    _url = url_encode(f"{JAMF_URL}/JSSResource/policies/name/{policy_name}")
    r_dict = _json_get(_url, enc_creds)
    if r_dict:
        try:
            obj_id = str(r_dict["policy"]["general"]["id"])
        except KeyError:
            obj_id = "-1"
    else:
        obj_id = "-1"
    LOGGER.debug("Returned Object ID: %s", obj_id)
    return obj_id


def policy_get_xml(policy_id, enc_creds):
    """Retrieves the XML for the policy, as previously we've worked with the
    JSON. Updating classic API objects requires XML.
    """
    return _xml_get(
        f"{JAMF_URL}/JSSResource/policies/id/{policy_id}",
        enc_creds,
    )


def policy_name_exists(policy_name, enc_creds):
    """Checks if policy exists by searching for the policy name"""
    policy_id = policy_get_id(policy_name, enc_creds)
    if policy_id != "-1":
        return True, policy_id
    return False, policy_id


def policy_post(policy_xml, enc_creds):
    """POST new Anchor to Jamf"""
    # Build a URL to send the POST
    _url = url_encode(f"{JAMF_URL}/JSSResource/policies/id/0")
    return _xml_post(
        _url,
        enc_creds,
        policy_xml,
    )


def policy_put(policy_id, policy_xml, enc_creds):
    """POST new Anchor to Jamf"""
    # Build a URL to send the POST
    _url = url_encode(f"{JAMF_URL}/JSSResource/policies/id/{policy_id}")
    return _xml_put(
        _url,
        enc_creds,
        policy_xml,
    )


def policy_get_all_in_category(_category, enc_creds):
    """Get a list of all policies in a category"""
    LOGGER.debug("Category: %s", _category)
    return api_get.get_policies_in_category(
        JAMF_URL, _category, enc_creds, 0
    )


def template_load(template_name):
    """Loads an XML template from the templates directory"""
    return ET.parse(TEMPLATES_DIR.joinpath(template_name)).getroot()


def url_encode(_url):
    """Returns a URL with special characters replaced."""
    return (
        _url
        .replace("$", "%24")
        .replace("&", "%26")
        .replace("+", "%2B")
        .replace(",", "%2C")
        .replace(";", "%3B")
        .replace("=", "%3D")
        .replace("?", "%3F")
        .replace("@", "%40")
        .replace(" ", "%20")
        .replace("\"", "%22")
        .replace("<", "%3C")
        .replace(">", "%3E")
        .replace("#", "%23")
        .replace("{", "%7B")
        .replace("}", "%7D")
        .replace("|", "%7C")
        .replace("\\", "%5C")
        .replace("^", "%5E")
        .replace("~", "%7E")
        .replace("[", "%5B")
        .replace("]", "%5D")
        .replace("`", "%60")
    )


def _curl_package(pkg_name, pkg_path, enc_creds):
    """uploads the package using curl"""
    _url = (f"{JAMF_URL}/dbfileupload")
    additional_headers = [
        "--header",
        "DESTINATION: 0",
        "--header",
        f"OBJECT_ID: -1",
        "--header",
        "FILE_TYPE: 0",
        "--header",
        f"FILE_NAME: {pkg_name}",
        "--connect-timeout",
        str("7200"),
        "--max-time",
        str("7200"),
    ]
    _response = curl.request(
        "POST", _url, enc_creds, 1, pkg_path, additional_headers
    )
    return _response.output


def _delete_object(_url, enc_creds):
    """Private function for deleting an object from the JPS"""
    _response = curl.request("DELETE", _url, enc_creds, 0)
    if _response.status_code in (200, 201):
        return True
    LOGGER.debug(
        "HTTP Response Code: %d :: Output: %s",
        _response.status_code,
        _response.output,
    )
    # Return False if there's an error above.
    return False


def _json_get(_url, enc_creds):
    """Private function for getting JSON back from curl.request"""
    LOGGER.debug("URL: %s", _url)
    _response = curl.request("GET", _url, enc_creds, 0)
    LOGGER.debug(
        "HTTP Response Code: %d :: Output: %s",
        _response.status_code,
        _response.output,
    )
    if _response.status_code in (200, 201):
        return json.loads(_response.output)


def _xml_get(_url, enc_creds):
    """Private function for getting XML back from curl.request"""
    LOGGER.debug("URL: %s", _url)
    _response = curl.request("GET", _url, enc_creds, 0, xml="xml")
    LOGGER.debug(
        "HTTP Response Code: %d :: Output: %s",
        _response.status_code,
        _response.output,
    )
    if _response.status_code in (200, 201):
        xml_content = ET.fromstring(_response.output)
        LOGGER.debug("Received XML: %s", xml_content)
        return xml_content
    # Return False if there's an error above.
    return False


def _xml_put(_url, _creds, _xml):
    """Runs PUTs for multiple functions"""
    LOGGER.debug("URL: %s", _url)
    _file = curl.write_temp_file(ET.tostring(_xml).decode())
    # range will not return the stop value, so 1 must be added to it.
    for _attempt in range(1, RE_TRIES + 1):
        # Send the command to PUT the data
        _response = curl.request("PUT", _url, _creds, 0, _file)
        LOGGER.debug(
            "HTTP Response: URL: %s :: Code: %d",
            _url,
            _response.status_code,
        )
        # If we succeeded, return True
        if _response.status_code in (200, 201):
            return True
        LOGGER.error(
            (
                "There was a problem uploading the new XML to URL: %s :: "
                "Trying again, this is attempt %d of %d."
            ),
            _url,
            _attempt,
            RE_TRIES,
        )

    # If we didn't succeed at all above (even with retries), return False
    return False


def _xml_post(_url, _creds, _xml):
    """Runs POSTs for multiple functions"""
    LOGGER.debug("URL: %s", _url)
    _file = curl.write_temp_file(ET.tostring(_xml).decode())
    # range will not return the stop value, so 1 must be added to it.
    for _attempt in range(1, RE_TRIES + 1):
        # Send the command to POST the data
        _response = curl.request("POST", _url, _creds, 0, _file)
        LOGGER.debug(
            "HTTP Response: URL: %s :: Code: %d",
            _url,
            _response.status_code,
        )
        # If we succeeded, return True
        if _response.status_code in (200, 201):
            return True
        LOGGER.error(
            (
                "There was a problem uploading the new XML to URL: %s :: "
                "Trying again, this is attempt %d of %d."
            ),
            _url,
            _attempt,
            RE_TRIES,
        )

    # If we didn't succeed at all above (even with retries), return False
    return False
