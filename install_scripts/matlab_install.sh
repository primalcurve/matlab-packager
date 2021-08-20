#!/bin/zsh
#
# Much Simplified version of original
#==========================================================================

MATLAB_PRESTAGE_FOLDER="/private/tmp/matlab"
INSTALLER_INPUT="${MATLAB_PRESTAGE_FOLDER}/custom_install.txt"
LICENSE_DAT="${MATLAB_PRESTAGE_FOLDER}/license.dat"
# Use zsh globbing to find the install_unix executable
# This will require expansion to declare globbing via "~"
# and the expansion must be unquoted.
MATLAB_INSTALL_UNIX="${MATLAB_PRESTAGE_FOLDER}/"**"/install_unix"
INSTALL_LOG="${MATLAB_PRESTAGE_FOLDER}/install.log"

#==========================================================================
#   Script Logic
#==========================================================================
# Make sure the prestage completed before we do anything further.
if [[ ! -d "${MATLAB_PRESTAGE_FOLDER}" ]]; then
    echo "Error: The directory ${MATLAB_PRESTAGE_FOLDER} does not exist. This is necessary for this script to function as it contains all of the MatLab files."
    exit 1
# Have to use explicit test declaration rather than square bracket tests.
elif test ! -x ${~MATLAB_INSTALL_UNIX}; then
    echo "Error: Unable to locate the MatLab install_unix executable binary in ${MATLAB_PRESTAGE_FOLDER}."
    exit 1
elif [[ ! -f "${INSTALLER_INPUT}" ]] || [[ ! -f "${LICENSE_DAT}" ]]; then
    echo "Error: The Prestage files do not exist in the temporary folder: ${TEMP_DIR}"
    echo "Input file: ${INSTALLER_INPUT}"
    echo "License file: ${LICENSE_DAT}"
    echo "These are necessary for this script to function as they contain the setup instructions for the MatLab installer."
    exit 1
fi
echo "MatLab Installation Application: ${MATLAB_PRESTAGE_FOLDER}"
echo "Using Input File: ${INSTALLER_INPUT}"
echo "Using License File: ${LICENSE_DAT}"

# Much simplified version. Seems to work just fine without all of the
# additional nonsense from the prior versions of this script.
typeset -a INSTALL_CMD=(\
    ${~MATLAB_INSTALL_UNIX} \
    "-inputFile" "${INSTALLER_INPUT}" \
    "-mode" "silent" \
)

# Run the install_unix command
echo "Running installer command: ${INSTALL_CMD[@]} ..."
if ! "${INSTALL_CMD[@]}"; then
    echo "Installation failed. Logs follow:"
    cat "${INSTALL_LOG}"
    exit 1
else
    echo "MatLab installation completed successfully!"
fi

if [[ -d "${MATLAB_PRESTAGE_FOLDER}" ]]; then
    echo "Cleaning up prestage folder to free up disk space."
    if rm -rf "${MATLAB_PRESTAGE_FOLDER}"; then
        echo "Prestage folder removed successfully."
    else
        echo "Unable to completely remove prestage folder. This will be removed upon next reboot."
    fi
fi

exit 0
