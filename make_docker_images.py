#!/usr/bin/env python3
#
# This script creates a number of sets of Docker images for Yandasoft. 
# One set consists of a variety of MPI implementations:
# - Generic machine, with these MPI:
#   - MPICH
#   - OpenMPI of versions 4, 3 and 2
# - Specific machine: Galaxy (This is actually MPICH)
#
# The sets are as follows:
# - Yandabase: Contains components that are seldom changed.
#   Since building the entire code is time consuming, it makes sense to
#   prebuild this part. This can then used as the base for the following.
# - Yandasoft: This is the final product, which can be either:
#   - Released version: Built from a formally released code base
#   - Develop version: The latest in "develop" git branch.
#
# Author: Paulus Lahur <paulus.lahur@csiro.au>
# Copyright: CSIRO 2020
#
#------------------------------------------------------------------------------
# USER SETTINGS
#
# Set machine targets in the list below.
# Currently, we target generic HPCs and a specific HPC: Galaxy.
# When a specific machine target is chosen, MPI target is ignored.
# Choose one or both of this list of target.
# machine_targets = ["generic", "galaxy"]
machine_targets = ["generic"]

# Set MPI implementations for generic machine in the list below.
# Note that a specific machine requires no MPI specification.
# Choose a subset (or all) of this complete list of targets:
mpi_targets = ["mpich", "openmpi4", "openmpi3", "openmpi2", "openmpi2.0"]

cmake_ver = "3.20.3"

casacore_ver = "3.3.0"

# Account name for storing images in DockerHub
docker_account = "csirocass"

mode = "normal"
# mode = "experiment"

#------------------------------------------------------------------------------
# TODO: Add logging
# TODO: Add timing
# TODO: Add error handling, as this is going to be used within CI/CD

import sys
import argparse
import subprocess
import re
import os
from pathlib import Path

nproc_available = os.cpu_count()
nproc = 1
if nproc_available > 1:
    nproc = nproc_available - 1
# print("The number of CPU cores used:", nproc)

# Header for all automatically generated Dockerfiles
header = ("# This file is automatically created by " + __file__ + "\n")

# MPI wrapper for g++
cmake_cxx_compiler = "-DCMAKE_CXX_COMPILER=mpicxx"
# cmake_cxx_compiler = "-DCMAKE_CXX_COMPILER=/usr/local/bin/mpiCC"

mpi_dir = "/usr/local"
MPI_COMPILE_FLAGS = "-I/usr/local/include -pthread"

forbidden_chars_string = "?!@#$%^&* ;<>?|\"\a\b\f\n\r\t\v"
forbidden_chars = list(forbidden_chars_string)
# print(forbidden_chars)

# Sanitizing parameters
machine_targets = list(map(str.lower, machine_targets))
mpi_targets = list(map(str.lower, mpi_targets))

# The library names are valid for Ubuntu18.04
library_list = [
    "libboost-dev",   
    "libboost-filesystem-dev", 
    "libboost-program-options-dev", 
    "libboost-python-dev", 
    "libboost-regex-dev",  
    "libboost-signals-dev",
    "libboost-system-dev",  
    "libboost-thread-dev",
    # Use these libboost names instead for Ubuntu20.04
    # "libboost1.67-dev",   
    # "libboost-filesystem1.67-dev", 
    # "libboost-program-options1.67-dev", 
    # "libboost-python1.67-dev", 
    # "libboost-regex1.67-dev",  
    # "libboost-signals1.67-dev",
    # "libboost-system1.67-dev",  
    # "libboost-thread1.67-dev",   
    "libcfitsio-dev",
    "libcppunit-dev",
    "libcurl4-openssl-dev",
    "libczmq-dev",
    "libfftw3-dev",
    "libffi-dev",     
    "libgsl-dev",        
    "libhdf5-serial-dev", 
    # Use this library instead for Ubuntu20.04
    # "libhdf5-dev", 
    "liblapacke-dev",
    "liblog4cxx-dev", 
    "libncurses5-dev",
    "libopenblas-dev",        
    "libpython2.7-dev", 
    "libpython3-dev", 
    "libreadline-dev",
    "libssl-dev",
    "libxerces-c-dev",
    "libzmq3-dev",
    "wcslib-dev"
    ]

# The tool names are valid for Ubuntu18.04
tool_list = [
    "autoconf",
    "automake",
    "bison",
    "docker",       
    "flex",
    "g++",
    "gcovr",
    "gdb",
    "gfortran",
    "git",
    "libtool",      
    "m4",
    "make",
    "patch",           
    "python-numpy",
    "python-pip",          
    "python-scipy",
    # Use this python instead for Ubuntu20.04
    # "python3-numpy",
    # "python3-pip",          
    # "python3-scipy",
    "subversion",          
    "tzdata",
    "valgrind",
    "vim",
    "wget",     
    "xsltproc",
    "zeroc-ice-all-dev",
    "zeroc-ice-all-runtime"
    ]


def is_proper_name(name):
    '''
    Return true if the name is non-empty and does not contain certain 
    characters. False otherwise.
    '''
    if type(name) != str:
        raise TypeError("Name is not string")
    if name == "":
        return False
    for c in forbidden_chars:
        if name.find(c) >= 0:
            return False
    return True


class DockerClass:
    recipe_name = ""
    image_name = ""
    recipe = ""

    def set_recipe_name(self, recipe_name):
        '''Set Dockerfile name'''
        if is_proper_name(recipe_name):
            self.recipe_name = recipe_name
        else:
            raise ValueError("Illegal recipe_name:", recipe_name)

    def set_recipe(self, recipe):
        '''Set the content of Dockerfile'''
        if type(recipe) == str:
            if recipe != "":
                self.recipe = recipe
            else:
                raise ValueError("Recipe is empty string")
        else:
            raise TypeError("Recipe is not string")

    def set_image_name(self, image_name):
        '''Set Docker image name'''
        if is_proper_name(image_name):
            self.image_name = image_name
        else:
            raise ValueError("Illegal image_name:", image_name)

    def write_recipe(self):
        '''Write recipe into Dockerfile'''
        if self.recipe_name == "":
            raise ValueError("Docker recipe file name has not been set")
        elif self.recipe == "":
            raise ValueError("Docker recipe content has not been set")
        else:
            with open(self.recipe_name, "w") as file:
                file.write(self.recipe)

    def get_build_command(self):
        '''Return build command'''
        if (self.recipe_name == ""):
            raise ValueError("Docker recipe file name has not been set")
        elif (self.image_name == ""):
            raise ValueError("Docker image file name has not been set")
        else:
            return ("docker build --no-cache --pull -t " + self.image_name + " -f " + 
                self.recipe_name + " .")
         
    def build_image(self):
        '''Build the Docker image'''
        build_command = self.get_build_command()
        if (self.recipe_name == ""):
            raise ValueError("Docker recipe file name has not been set")
        else:
            file = Path(self.recipe_name)
            if file.is_file():
                # TODO: store log file, handle error
                subprocess.run(build_command, shell=True)
            else:
                raise FileExistsError("Docker recipe file does not exist:", 
                    self.recipe_name)



def split_version_number(input_ver):
    '''
    Split a given version number in string into 3 integers.
    '''
    string_list = re.findall(r'\d+', input_ver)
    if (len(string_list) == 3):
        int_list = [int(x) for x in string_list]
        return int_list
    else:
        return []


def compose_version_number(int_list):
    '''
    Given a list of 3 integers, compose version number as a string.
    '''
    if (isinstance(int_list, list)):
        if (len(int_list) == 3):
            return (str(int_list[0]) + '.' + str(int_list[1]) + '.' + 
                str(int_list[2]))
        else:
            return ""
    else:
        return ""


def get_mpi_type_and_version(mpi_name):
    '''
    Given the full name of MPI, return MPI type (mpich / openmpi)
    and the version as a list of 3 integers.
    Input should be in one of these formats:
    - mpich
    - openmpi
    - mpich-X.Y.Z
    - openmpi-X.Y.Z
    Where "X.Y.Z" is version number.
    '''
    length = len(mpi_name)
    if (type(mpi_name) == str):
        if (length < 5):
            raise ValueError("MPI name is too short:", mpi_name)

        elif (length == 5):
            # Unspecified MPICH
            if (mpi_name == "mpich"):
                return("mpich", None)
            else:
                raise ValueError("Expecting mpich:", mpi_name)

        elif (length == 6):
            raise ValueError("Illegal MPI name:", mpi_name)

        elif (length == 7):
            # Unspecified OpenMPI
            if (mpi_name == "openmpi"):
                return("openmpi", None)
            else:
                raise ValueError("Expecting openmpi:", mpi_name)

        else:
            if (mpi_name[0:5] == "mpich"):
                # MPICH with specified version number
                int_ver = split_version_number(mpi_name[6:])
                if (len(int_ver) == 3):
                    return ("mpich", int_ver)
                else:
                    raise ValueError("Illegal mpich version:", mpi_name[6:])

            elif (mpi_name[0:7] == "openmpi"):
                # OpenMPI with specified version number
                int_ver = split_version_number(mpi_name[8:])
                if (len(int_ver) == 3):
                    return ("openmpi", int_ver)
                else:
                    raise ValueError("Illegal openmpi version:", mpi_name[8:])
            else:
                raise ValueError("Illegal MPI name:", mpi_name)
    else:
        raise TypeError("MPI name is not a string:", mpi_name)



def make_yandabase(machine, mpi, prepend, append, execute):
    '''
    Make base image for components that are seldom changed:
    base OS, upgrades, standard libraries and apps, Casacore and Casarest.
    TO DO: Move LOFAR here from Yandasoft.
    '''
    docker_target = DockerClass()

    # Install libraries and dev tools
    apt_install_part = (
        "ENV DEBIAN_FRONTEND=\"noninteractive\"\n"
        "RUN apt-get update -q \\\n"
        "    && apt-get upgrade -y \\\n"
        "    && apt-get install -y --no-install-recommends "
        )
    apt_install_list = library_list + tool_list
    for apt_install_item in apt_install_list:
        apt_install_part += " \\\n" + "        " + apt_install_item
    # apt_install_part += "\n"
    apt_install_part += "\\\n"
    # apt_install_part += "    && apt-get autoremove -y \\\n"
    apt_install_part += "    && rm -rf /var/lib/apt/lists/* \n"

    cmake_source = "cmake-" + cmake_ver + ".tar.gz"

    recipe = (
        apt_install_part +
        "# Build cmake\n"
        "RUN mkdir /usr/local/share/cmake\n"
        "WORKDIR /usr/local/share/cmake\n"
        "RUN wget https://github.com/Kitware/CMake/releases/download/v" + cmake_ver + "/" + cmake_source + " \\\n"
        "    && tar -zxf " + cmake_source + " \\\n"
        "    && rm " + cmake_source + "\n"
        "WORKDIR /usr/local/share/cmake/cmake-" + cmake_ver + "\n"
        "RUN ./bootstrap --system-curl -- -DCMAKE_BUILD_TYPE:STRING=Release \\\n"
        "    && make \\\n"
        "    && make install\\\n"
        "    && rm -rf * \n"
        "# Build the latest measures\n"
        "RUN mkdir /usr/local/share/casacore \\\n"
        "    && mkdir /usr/local/share/casacore/data\n"
        "WORKDIR /usr/local/share/casacore/data\n"
        "RUN wget ftp://ftp.astron.nl/outgoing/Measures/WSRT_Measures.ztar \\\n"
        "    && mv WSRT_Measures.ztar WSRT_Measures.tar.gz \\\n"
        "    && tar -zxf WSRT_Measures.tar.gz \\\n"
        "    && rm WSRT_Measures.tar.gz \\\n"
        "    && mkdir /var/lib/jenkins \\\n"
        "    && mkdir /var/lib/jenkins/workspace \n"
        "# Build the latest casacore\n"
        "WORKDIR /usr/local/share/casacore\n"
        "RUN wget https://github.com/casacore/casacore/archive/v" + casacore_ver + ".tar.gz \\\n"
        "    && tar -xzf v" + casacore_ver + ".tar.gz\\\n"
        "    && rm v" + casacore_ver + ".tar.gz\n"
        "WORKDIR /usr/local/share/casacore/casacore-" + casacore_ver + "\n"
        "RUN mkdir build\n"
        "WORKDIR build\n"
        "RUN cmake " + cmake_cxx_compiler + " -DUSE_FFTW3=ON -DDATA_DIR=/usr/local/share/casacore/data \\\n"
        "    -DUSE_OPENMP=ON -DUSE_HDF5=ON -DBUILD_PYTHON=ON -DUSE_THREADS=ON -DCMAKE_BUILD_TYPE=Release .. \\\n"
        "    && make -j" + str(nproc) + " \\\n"
        "    && make install\n"
        "WORKDIR /usr/local/share/casacore/\n"
        "RUN wget https://github.com/steve-ord/casarest/tarball/078f94e \\\n"
        "    && tar -xzf 078f94e \\\n"
        "    && rm 078f94e\n"
        "WORKDIR steve-ord-casarest-078f94e\n"
        "RUN mkdir build\n"
        "WORKDIR build\n"
        "RUN cmake " + cmake_cxx_compiler + " -DCMAKE_BUILD_TYPE=Release .. \\\n"
        "    && make -j" + str(nproc) + " \\\n"
        "    && make install \n"
        "WORKDIR /usr/local/share/casacore\n"
        "RUN rm -rf casacore \\\n"
        #"    && rm -rf casarest \\\n"
        "    && rm -rf steve-ord-casarest-078f94e \n"
        # "    && apt-get clean \n"
        # "# Build LOFAR\n"
        # "WORKDIR /usr/local/share\n"
        # "RUN mkdir LOFAR\n"
        # "WORKDIR /usr/local/share/LOFAR\n"
        # "RUN git clone https://bitbucket.csiro.au/scm/askapsdp/lofar-common.git\n"
        # "WORKDIR /usr/local/share/LOFAR/lofar-common\n"
        # "RUN git checkout develop \n"
        # "RUN mkdir build\n"
        # "WORKDIR /usr/local/share/LOFAR/lofar-common/build\n"
        # "RUN cmake " + cmake_cxx_compiler + " -DCMAKE_CXX_FLAGS=\"-I/usr/local/include -pthread\" \\\n"
        # "    -DCMAKE_BUILD_TYPE=Release -DENABLE_OPENMP=YES .. \\\n"
        # "    && make -j" + str(nproc) + " \\\n"
        # "    && make install\n"
        # "WORKDIR /usr/local/share/LOFAR\n"
        # "RUN git clone https://bitbucket.csiro.au/scm/askapsdp/lofar-blob.git\n"
        # "WORKDIR /usr/local/share/LOFAR/lofar-blob\n"
        # "RUN git checkout develop \n"
        # "RUN mkdir build\n"
        # "WORKDIR /usr/local/share/LOFAR/lofar-blob/build\n"
        # "RUN cmake " + cmake_cxx_compiler + " -DCMAKE_CXX_FLAGS=\"-I/usr/local/include -pthread\" \\\n"
        # "    -DCMAKE_BUILD_TYPE=Release -DENABLE_OPENMP=YES .. \\\n"
        # "    && make -j" + str(nproc) + " \\\n"
        # "    && make install\n"
        # "# Clean up\n"
        # "RUN apt-get autoremove -y \\\n"
        # "    && rm -rf /var/lib/apt \n"
        )

    if machine == "generic":
        base_part = ("FROM csirocass/base:" + mpi + " AS base_image \n")
        docker_target.set_recipe_name(".gitlab-docker-yandabase-" + mpi)
        docker_target.set_image_name(prepend + "yandabase:" + mpi + append)
    elif (machine == "galaxy"):
        base_part = ("FROM pawsey/mpich-base:3.1.4_ubuntu18.04 AS " +
            "base_image\n")
        docker_target.set_recipe_name(".gitlab-docker-yandabase-" + machine)
        docker_target.set_image_name(prepend + "yandabase:" + machine + append)
    else:
        raise ValueError("Unknown machine target:", machine)

    docker_target.set_recipe(header + base_part + recipe)
    docker_target.write_recipe()

    # If requested, actually generate the image
    if execute:
        docker_target.build_image()
    else:  # Otherwise, just echo the command to generate the image
        print(docker_target.get_build_command())

    return docker_target



def make_big_yandasoft_recipe(base_image, image, git_branch):
    '''
    Make Docker recipe for Yandasoft/ASKAPsoft.
    '''
    cmake_cxx_flags = ("-DCMAKE_CXX_FLAGS=\"" + MPI_COMPILE_FLAGS + 
            "\" -DCMAKE_BUILD_TYPE=Release -DENABLE_OPENMP=YES")
    if (image == "yandasoft"):
        cmake_build_flags = ("-DBUILD_ANALYSIS=OFF -DBUILD_PIPELINE=OFF -DBUILD_COMPONENTS=OFF " +
            "-DBUILD_SERVICES=OFF")
    elif (image == "askapsoft"):
        cmake_build_flags = ("-DBUILD_ANALYSIS=ON -DBUILD_PIPELINE=ON -DBUILD_COMPONENTS=ON " +
            "-DBUILD_SERVICES=OFF")
    else:
        raise ValueError("Illegal image name:", image)

    if ((git_branch == "develop") or (git_branch == "master")):
        recipe = (
            "# Build Yandasoft\n"
            "FROM " + base_image + " AS build_image \n"
            "WORKDIR /home\n"
            # "RUN git clone https://github.com/ATNF/all_yandasoft.git\n"
            "RUN git clone https://gitlab.com/ASKAPSDP/all_yandasoft.git\n"
            "WORKDIR /home/all_yandasoft\n"
            "RUN ./git-do clone\n"
            "RUN ./git-do checkout -b " + git_branch + "\n"
            "# To fix version problem, use develop branch in askap-cmake \n"
            "WORKDIR /home/all_yandasoft/askap-cmake \n"
            "RUN git checkout develop \n"
            "WORKDIR /home/all_yandasoft \n"
            "RUN mkdir build\n"
            "WORKDIR /home/all_yandasoft/build\n"
            "RUN cmake " + cmake_cxx_compiler + " " + cmake_cxx_flags + " " + cmake_build_flags + " .. \\\n"
            "    && make -j" + str(nproc) + " \\\n"
            "    && make install\n"
            # "    && rm -rf * \n"
        )
    else:
        # Workaround for release version
        recipe = (
            "# Build Yandasoft\n"
            "FROM " + base_image + " AS build_image \n"
            "WORKDIR /home\n"
            # "RUN git clone https://github.com/ATNF/all_yandasoft.git\n"
            "RUN git clone https://gitlab.com/ASKAPSDP/all_yandasoft.git\n"
            "WORKDIR /home/all_yandasoft\n"
            "RUN ./git-do clone\n"
            "# Workaround for versioning\n"
            "RUN ./git-do checkout -b release/" + git_branch + "\n"
            "RUN ./git-do checkout -b " + git_branch + "\n"
            "# To fix version problem, use develop branch in askap-cmake \n"
            "WORKDIR /home/all_yandasoft/askap-cmake \n"
            "RUN git checkout develop \n"
            "WORKDIR /home/all_yandasoft \n"
            "RUN mkdir build\n"
            "WORKDIR /home/all_yandasoft/build\n"
            "RUN cmake " + cmake_cxx_compiler + " " + cmake_cxx_flags + " " + cmake_build_flags + " .. \\\n"
            "    && make -j" + str(nproc) + " \\\n"
            "    && make install\n"
            # "    && rm -rf * \n"
        )
    return recipe


def make_small_yandasoft_recipe(base_image):
    '''
    Make Docker recipe for small image of Yandasoft, which is made by
    copying the files from big image of Yandasoft.
    '''
    recipe_base = (
        "# Build production image \n"
        "FROM " + base_image + " AS production_image \n"
        )

    # Libraries to be installed
    recipe_library = (
        "ENV DEBIAN_FRONTEND=\"noninteractive\" \n"
        "RUN apt-get update -q \\\n"
        "    && apt-get upgrade -y \\\n"
        "    && apt-get install -y --no-install-recommends "
        )
    for library_item in library_list:
        recipe_library += " \\\n" + "        " + library_item
    recipe_library += "\\\n"
    recipe_library += (
        "    && apt-get clean all \\\n"
        "    && rm -rf /var/lib/apt/lists/* \n"
        )

    recipe_copy = (
        "# Copy executables and libraries from build_image \n"
        "COPY --from=build_image /usr/local/bin/* /usr/local/bin/ \n"
        "COPY --from=build_image /usr/local/lib/* /usr/local/lib/ \n"
        )

    recipe_data = (
        "# Build the latest measures \n"
        "RUN mkdir /usr/local/share/casacore \\\n"
        "    && mkdir /usr/local/share/casacore/data \n"
        "WORKDIR /usr/local/share/casacore/data \n"
        "RUN wget ftp://ftp.astron.nl/outgoing/Measures/WSRT_Measures.ztar \\\n"
        "    && mv WSRT_Measures.ztar WSRT_Measures.tar.gz \\\n"
        "    && tar -zxf WSRT_Measures.tar.gz \\\n"
        "    && rm WSRT_Measures.tar.gz \n"
        )

    recipe = recipe_base + recipe_library + recipe_copy + recipe_data
    return recipe



def make_yandasoft(machine, mpi, prepend, append, git_branch, image, execute):
    '''
    Make Yandasoft recipe and image.
    '''
    docker_target = DockerClass()
    # Make recipe for big image
    if machine == "generic":
        base_image = ("csirocass/yandabase:" + mpi)
    elif (machine == "galaxy"):
        base_image = ("csirocass/yandabase:" + machine)
    else:
        raise ValueError("Unknown machine target:", machine)
    recipe = make_big_yandasoft_recipe(base_image, image, git_branch)

    if git_branch == "develop":
        if machine == "generic":
            docker_target.set_recipe_name(
                ".gitlab-docker-" + image + "-dev-" + mpi)
                # ".gitlab-docker-yandasoft-dev-" + mpi)
            # docker_target.set_image_name(prepend + "yandasoft:dev-" + 
            docker_target.set_image_name(prepend + image + ":dev-" + 
                mpi + append)
        elif (machine == "galaxy"):
            docker_target.set_recipe_name(
                ".gitlab-docker-" + image + "-dev-" + machine)
                # ".gitlab-docker-yandasoft-dev-" + machine)
            # docker_target.set_image_name(prepend + "yandasoft:dev-" + 
            docker_target.set_image_name(prepend + image + ":dev-" + 
                machine + append)
        else:
            raise ValueError("Unknown machine target:", machine)
    elif git_branch == "master":
        if machine == "generic":
            docker_target.set_recipe_name(
                ".gitlab-docker-" + image + "-" + mpi)
                # ".gitlab-docker-yandasoft-" + mpi)
            # docker_target.set_image_name(prepend + "yandasoft:" + 
            docker_target.set_image_name(prepend + image + ":" + 
                mpi + append)
        elif (machine == "galaxy"):
            docker_target.set_recipe_name(
                ".gitlab-docker-" + image + "-" + machine)
                # ".gitlab-docker-yandasoft-" + machine)
            # docker_target.set_image_name(prepend + "yandasoft:" + 
            docker_target.set_image_name(prepend + image + ":" + 
                machine + append)
        else:
            raise ValueError("Unknown machine target:", machine)
    else:
        # Release tag
        # Extract MAJOR.MINOR version from the release tag.
        # TODO: This only works for single digits (eg. 1.2)
        #       Find a more general method (eg. 12.34).
        #       Abort if version numbers cannot be extracted.
        version = git_branch[0:3]
        if machine == "generic":
            base_image = ("csirocass/base:" + mpi)
            # docker_target.set_recipe_name(".gitlab-docker-yandasoft-" + 
            docker_target.set_recipe_name(".gitlab-docker-" + image + "-" + 
                version + "-" + mpi)
            # docker_target.set_image_name(prepend + "yandasoft:" + 
            docker_target.set_image_name(prepend + image + ":" + 
                version + "-" + mpi + append)
        elif (machine == "galaxy"):
            base_image = ("pawsey/mpich-base:3.1.4_ubuntu18.04")
            # docker_target.set_recipe_name(".gitlab-docker-yandasoft-" + 
            docker_target.set_recipe_name(".gitlab-docker-" + image + "-" + 
                version + "-" + machine)
            # docker_target.set_image_name(prepend + "yandasoft:" + 
            docker_target.set_image_name(prepend + image + ":" + 
                version + "-" + machine + append)
        else:
            raise ValueError("Unknown machine target:", machine)
        recipe += make_small_yandasoft_recipe(base_image)


    recipe_end = (
        "WORKDIR /home \n"
        "CMD [\"/bin/bash\"] \n" 
    )
    recipe = header + recipe + recipe_end
    docker_target.set_recipe(recipe)
    docker_target.write_recipe()

    if execute:
        docker_target.build_image()
    else:
        print(docker_target.get_build_command())

    return docker_target



def make_batch_file(machine, mpi):
    '''
    Make sample batch files for SLURM
    '''

    batch_common_part = (
    "#!/bin/bash -l\n"
    "## This file is automatically created by " + __file__ + "\n"
    "#SBATCH --ntasks=5\n"
    "##SBATCH --ntasks=305\n"
    "#SBATCH --time=02:00:00\n"
    "#SBATCH --job-name=cimager\n"
    "#SBATCH --export=NONE\n\n"
    "module load singularity/3.5.0\n")

    (mpi_type, mpi_num) = get_mpi_type_and_version(mpi)
    mpi_ver = compose_version_number(mpi_num)
    if (mpi_type == "mpich"):
        module = "mpich/3.3.0"
        image = "yandasoft-mpich_latest.sif"
        batch_mpi_part = (
        "module load " + module + "\n\n"
        "mpirun -n 5 singularity exec " + image +
        " cimager -c dirty.in > dirty_${SLURM_JOB_ID}.log\n")

    elif (mpi_type == "openmpi"):
        if (mpi_ver != None):
            module = "openmpi/" + mpi_ver + "-ofed45-gcc"
            image = "yandasoft-" + mpi_ver + "_latest.sif"
            batch_mpi_part = (
            "module load " + module + "\n\n"
            "mpirun -n 5 -oversubscribe singularity exec " + image +
            " cimager -c dirty.in > dirty_${SLURM_JOB_ID}.log\n")

    else:
        raise ValueError("Unknown MPI target:", mpi)

    batch_file = "sample-" + machine + "-" + mpi + ".sbatch"
    print("Making batch file:", batch_file)
    with open(batch_file, "w") as file:
        file.write(batch_common_part + batch_mpi_part)



def show_targets():
    print("The list of Docker targets: ")
    for machine in machine_targets:
        print("- Machine:", machine)
        if machine == "generic":
            for mpi in mpi_targets:
                print("  - MPI:", mpi)
    print("Note that specific machine has a preset MPI target")



def main():
    parser = argparse.ArgumentParser(
        description="Make Docker images for various MPI implementations",
        epilog="The targets can be changed from inside the script " +
            "(the SETTINGS section)")
    parser.add_argument('image', help='"yandabase" or "yandasoft" or "askapsoft"', type=str)
    parser.add_argument('-g', '--git_branch', default="master", type=str,
        help='Possible values: "master" (default), "develop", release tag number (eg. "1.2.3")')
    parser.add_argument('-x', '--execute', action='store_true',
        help='Actually create the image. Otherwise only Docker recipe is produced.')
    args = parser.parse_args()

    git_branch = args.git_branch
    image = args.image

    if image == "yandabase":
        if args.execute:
            print("Making yandabase image")
        else:
            print("Making the recipe for yandabase")
    elif image == "yandasoft":
        if args.execute:
            print("Making yandasoft image from git branch", git_branch)
        else:
            print("Making the recipe for yandasoft image from git branch", git_branch)
    elif image == "askapsoft":
        if args.execute:
            print("Making askapsoft image from git branch", git_branch)
        else:
            print("Making the recipe for askapsoft image from git branch", git_branch)
    else:
        raise ValueError("Image must be either 'yandabase' or 'yandasoft")

    name_prepend = docker_account + "/"
    name_append = ""

    for machine in machine_targets:
        if machine == "generic":
            for mpi in mpi_targets:
                if image == "yandabase":
                    docker = make_yandabase(machine, mpi, name_prepend, 
                        name_append, args.execute)
                elif ((image == "yandasoft") or (image == "askapsoft")):
                    docker = make_yandasoft(machine, mpi, name_prepend, 
                        name_append, git_branch, image, args.execute)
                else:
                    raise ValueError("Unknown image:", image)
        else:
            # Specific machine
            if image == "yandabase":
                docker = make_yandabase(machine, None, name_prepend, 
                    name_append, args.execute)
            elif ((image == "yandasoft") or (image == "askapsoft")):
                docker = make_yandasoft(machine, machine, name_prepend, 
                    name_append, git_branch, image, args.execute)
            else:
                raise ValueError("Unknown image:", image)



if (__name__ == "__main__"):
    if sys.version_info[0] == 3:
        main()
    else:
        raise ValueError("Must use Python 3")
