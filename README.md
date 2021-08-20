# Important Notice

This is the result of a couple of months of research and development on my part,
it's currently disorganized, makes use of some methods that are perhaps not the
*most* Pythonic, and unsuited for use outside of my particular environment.

At this time, it is provided here to help others, but can be considered a
work-in-progress as I expand its universality. Eventually, perhaps, it will be
ready for anyone's use.

Several values are baked-in in places where they should not be, and will cause
problems if someone attempts to use this as-is.

# How does one go about using this?

The process is fully automated, but requires some initial setup.

## Requirements

1. A File Installation Key
    * Place in `./product_licenses/`
    * Rename to the product release family e.g. `R2021b_key.txt`
2. A license.dat file
    * Place in `./product_licenses/`
    * Rename to the product release family e.g. `R2021b_license.dat`
3. A Python 3 installation
4. A Python 3 Virtual Environment
    * I recomment creating a dedicated folder for this purpose.
    * `mkdir -p ~/venv`
    * `python3 -m venv ~/venv/matlab_pkg`
    * `source ~/venv/matlab_pkg/bin/activate`
    * When finished running the script, you can exit the Virtual Environment with `deactivate`
5. The Python 3 library `jamf_upload`
    * `git clone https://github.com/grahampugh/jamf-upload`
    * `mv jamf-upload jamf_upload`
6. A hefty chunk of free disk space (approximately 30GB)

## Download the Full Installer

We will need access to every single toolbox and product definitions file to
make this process work.

Place the full installer DMG in a working directory on a drive with at least
30GB of free disk space.

## Run the script

All runs of the script will prompt for your Jamf Pro Server username and password
at the start, as it will need these credentials to access the API for package
upload and for creating various objects.

Script Help Text

```
% ./build_packages.py -h
usage: build_packages.py [-h] [-v | -q] -d DMG [-f FOLDER] [-t TARGETS]
                         [-p PRODUCTS] [-U USER] [-P PASSWORD] [-s]

Take a full MathWorks DMG and create a set of packages.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Incrementally increase output args.verbose
  -q, --quiet
  -d DMG, --dmg DMG     Path to DMG containing all of the MathWorks install
                        files.
  -f FOLDER, --folder FOLDER
                        Optional path to working folder. By default, the working
                        folder is the parent folder of the DMG.
  -t TARGETS, --targets TARGETS
                        Optional path to a text file containing a newline-
                        separated list of products to package. Default is the
                        target_software_and_toolboxes.txt file contained within
                        this repository.
  -p PRODUCTS, --products PRODUCTS
                        Optional product names to target instead of the targets
                        file. Multiple products can be specified with additional
                        switches: -p 'Product Name 1' -p 'Product Name 2'...
  -U USER, --user USER  Username with Jamf API privileges.
  -P PASSWORD, --password PASSWORD
                        Password for user.
  -s, --skip            Skips processing DMG. Use only if the DMG has been
                        processed on a previous run and the policy definitions
                        file exists.
```

### Examples

#### Run the script using the default toolboxes:

`./build_packages.py -d /path/to/matlab_R2021b_maci64.dmg`

#### Run the script targeting only a single product:

`./build_packages.py -d /path/to/matlab_R2021b_maci64.dmg -p 'Curve Fitting Toolbox'`

#### Skip processing the files in the DMG:

Note: use only if you've already run this script against all of the required
components in the DMG. The script keeps a policy definitions JSON file in the
working folder that it creates as it processes the product definitions and
components in the DMG. It can use this to create policies in subsequent runs.

`./build_packages.py -d /path/to/matlab_R2021b_maci64.dmg -s`