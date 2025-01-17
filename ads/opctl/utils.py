#!/usr/bin/env python
# -*- coding: utf-8; -*-

# Copyright (c) 2022 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/


import functools
import logging
import os
import subprocess
import sys
import tempfile
import urllib.parse
from distutils import dir_util
from subprocess import Popen, PIPE, STDOUT
from typing import Union, List, Tuple, Dict
import shlex
import yaml

import ads
from ads.common.oci_client import OCIClientFactory
from ads.opctl import logger
from ads.opctl.constants import (
    ML_JOB_IMAGE,
    OPS_IMAGE_BASE,
    ML_JOB_GPU_IMAGE,
    OPS_IMAGE_GPU_BASE,
)
from ads.common.decorator.runtime_dependency import (
    runtime_dependency,
    OptionalDependency,
)


def get_service_pack_prefix() -> Dict:
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    service_config_file = os.path.join(curr_dir, "conda", "config.yaml")
    with open(service_config_file) as f:
        service_config = yaml.safe_load(f.read())
    if all(key in os.environ for key in ["CONDA_BUCKET_NS", "CONDA_BUCKET_NAME"]):
        bucket_info = {
            "name": os.environ["CONDA_BUCKET_NAME"],
            "namespace": os.environ["CONDA_BUCKET_NS"],
        }
    else:
        bucket_info = service_config["bucket_info"].get(
            os.environ.get("NB_REGION", "default"),
            service_config["bucket_info"]["default"],
        )
    return f"oci://{bucket_info['name']}@{bucket_info['namespace']}/{service_config['service_pack_prefix']}"


def is_in_notebook_session():
    return "CONDA_PREFIX" in os.environ and "NB_SESSION_OCID" in os.environ


def parse_conda_uri(uri: str) -> Tuple[str, str, str, str]:
    parsed = urllib.parse.urlparse(uri)
    path = parsed.path
    if path.startswith("/"):
        path = path[1:]
    bucket, ns = parsed.netloc.split("@")
    slug = os.path.basename(path)
    return ns, bucket, path, slug


def list_ads_operators() -> dict:
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(curr_dir, "index.yaml"), "r") as f:
        ads_operators = yaml.safe_load(f.read())
    return ads_operators or []


def get_oci_region(auth: dict) -> str:
    if len(auth["config"]) > 0:
        return auth["config"]["region"]
    else:
        return auth["signer"].region


def get_namespace(auth: dict) -> str:
    client = OCIClientFactory(**auth).object_storage
    return client.get_namespace().data


def get_region_key(auth: dict) -> str:
    if len(auth["config"]) > 0:
        tenancy = auth["config"]["tenancy"]
    else:
        tenancy = auth["signer"].tenancy_id
    client = OCIClientFactory(**auth).identity
    return client.get_tenancy(tenancy).data.home_region_key


# Not needed at the moment
# def _get_compartment_name(compartment_id: str, auth: dict) -> str:
#     client = OCIClientFactory(**auth).identity
#     return client.get_compartment(compartment_id=compartment_id).data.name


def publish_image(image: str, registry: str = None) -> None:  # pragma: no cover
    """
    Publish an image.

    Parameters
    ----------
    image: str
        image name
    registry: str
        registry to push to

    Returns
    -------
    None
    """
    if not registry:
        run_command(["docker", "push", image])
        print(f"pushed {image}")
        return image
    else:
        run_command(
            ["docker", "tag", f"{image}", f"{registry}/{os.path.basename(image)}"]
        )
        run_command(["docker", "push", f"{registry}/{os.path.basename(image)}"])
        print(f"pushed {registry}/{os.path.basename(image)}")
        return f"{registry}/{os.path.basename(image)}"


def build_image(
    image_type: str, gpu: bool = False, source_folder: str = None, dst_image: str = None
) -> None:
    """
    Build an image for opctl.

    Parameters
    ----------
    image_type: str
        specify the image to build, can take 'job-local' or 'ads-ops-base',
        former for running job with conda pack locally,
        latter for running operators
    gpu: bool
        whether to use gpu version of image
    source_folder: str
        source folder when building custom operator, to be included in custom image
    dst_image: str
        image to save as when building custom operator

    Returns
    -------
    None
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if image_type == "ads-ops-custom":
        if not source_folder or not dst_image:
            raise ValueError(
                "Please provide both source_folder and image_name to build a image for custom operator."
            )
        proc = _build_custom_operator_image(gpu, source_folder, dst_image)
    else:
        image, dockerfile, target = _get_image_name_dockerfile_target(image_type, gpu)
        command = [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            os.path.join(curr_dir, "docker", dockerfile),
        ]
        if target:
            command += ["--target", target]
        if os.environ.get("no_proxy"):
            command += ["--build-arg", f"no_proxy={os.environ['no_proxy']}"]
        if os.environ.get("http_proxy"):
            command += ["--build-arg", f"http_proxy={os.environ['http_proxy']}"]
        if os.environ.get("https_proxy"):
            command += ["--build-arg", f"https_proxy={os.environ['https_proxy']}"]
        command += [os.path.abspath(curr_dir)]
        logger.info(f"Build image with command {command}")
        proc = run_command(command)
    if proc.returncode != 0:
        raise RuntimeError(f"Docker build failed.")


def _get_image_name_dockerfile_target(type: str, gpu: bool) -> str:
    look_up = {
        ("job-local", False): (ML_JOB_IMAGE, "Dockerfile.job", None),
        ("job-local", True): (ML_JOB_GPU_IMAGE, "Dockerfile.job.gpu", None),
        ("ads-ops-base", False): (OPS_IMAGE_BASE, "Dockerfile", "base"),
        ("ads-ops-base", True): (OPS_IMAGE_GPU_BASE, "Dockerfile.gpu", "base"),
    }
    return look_up[(type, gpu)]


@runtime_dependency(module="docker", install_from=OptionalDependency.OPCTL)
def _build_custom_operator_image(
    gpu: bool, source_folder: str, dst_image: str
) -> None:  # pragma: no cover
    operator = os.path.basename(source_folder)
    base_image_name = OPS_IMAGE_BASE if not gpu else OPS_IMAGE_GPU_BASE
    try:
        client = docker.from_env()
        client.api.inspect_image(base_image_name)
    except docker.errors.ImageNotFound:
        build_image("ads-ops-base", gpu)
    with tempfile.TemporaryDirectory() as td:
        dir_util.copy_tree(source_folder, os.path.join(td, operator))
        if os.path.exists(os.path.join(td, operator, "environment.yaml")):
            with open(os.path.join(td, "Dockerfile"), "w") as f:
                f.write(
                    f"""
FROM {base_image_name}
COPY ./{operator}/environment.yaml operators/{operator}/environment.yaml
RUN conda env update -f operators/{operator}/environment.yaml --name op_env && conda clean -afy
COPY ./{operator} operators/{operator}
                        """
                )
        else:
            with open(os.path.join(td, "Dockerfile"), "w") as f:
                f.write(
                    f"""
FROM {base_image_name}
COPY ./{operator} operators/{operator}
                        """
                )
        return run_command(["docker", "build", "-t", f"{dst_image}", "."], td)


def run_command(
    cmd: Union[str, List[str]], cwd: str = None, shell: bool = False
) -> Popen:
    proc = Popen(
        cmd, cwd=cwd, stdout=PIPE, stderr=STDOUT, universal_newlines=True, shell=shell
    )
    for x in iter(proc.stdout.readline, ""):
        print(x, file=sys.stdout, end="")
    proc.wait()
    return proc


class _DebugTraceback:
    def __init__(self, debug):
        self.cur_logging_level = logger.getEffectiveLevel()
        self.debug = debug

    def __enter__(self):
        if self.debug:
            logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.debug and exc_type:
            logger.setLevel(self.cur_logging_level)
            return False
        elif not self.debug and exc_type:
            sys.stderr.write(f"{exc_type.__name__}: {str(exc_val)} \n")
            sys.exit(1)
        return True


def suppress_traceback(debug: bool = True) -> None:
    """
    Decorator to suppress traceback when in debug mode.

    Parameters
    ----------
    debug: bool
        turn on debug mode or not

    Returns
    -------
    None
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with _DebugTraceback(debug) as tb:
                return func(*args, **kwargs)

        return wrapper

    return decorator


@runtime_dependency(module="docker", install_from=OptionalDependency.OPCTL)
def get_docker_client() -> "docker.client.DockerClient":
    process = subprocess.Popen(
        ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    process.communicate()
    if process.returncode != 0:
        raise RuntimeError("Docker is not started.")
    return docker.from_env()


class OCIAuthContext:
    def __init__(self, profile: str = None):
        self.profile = profile
        self.prev_rp_mode = ads.resource_principal_mode
        self.prev_profile = ads.oci_key_profile

    def __enter__(self):
        if self.profile:
            ads.set_auth(auth="api_key", profile=self.profile)
            logger.info(f"OCI profile set to {self.profile}")
        else:
            ads.set_auth(auth="resource_principal")
            logger.info(f"OCI auth set to resource principal")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.prev_rp_mode:
            ads.set_auth(auth="resource_principal")
        else:
            ads.set_auth(auth="api_key", profile=self.prev_profile)


@runtime_dependency(module="docker", install_from=OptionalDependency.OPCTL)
def run_container(
    image: str,
    bind_volumes: Dict,
    env_vars: Dict,
    command: str = None,
    entrypoint: str = None,
    verbose: bool = False,
):
    if verbose:
        ads.opctl.logger.setLevel(logging.INFO)
    logger.info(f"Running container with image: {image}")
    logger.info(f"bind_volumes: {bind_volumes}")
    logger.info(f"env_vars: {env_vars}")
    logger.info(f"command: {command}")
    logger.info(f"entrypoint: {entrypoint}")

    client = get_docker_client()
    try:
        client.api.inspect_image(image)
    except docker.errors.ImageNotFound:
        logger.warn(f"Image {image} not found. Try pulling it now....")
        run_command(["docker", "pull", f"{image}"], None)
    container = client.containers.run(
        image=image,
        volumes=bind_volumes,
        command=shlex.split(command) if command else None,
        environment=env_vars,
        detach=True,
        entrypoint=entrypoint,
        user=0,
        # auto_remove=True,
    )
    logger.info(f"Container ID: {container.id}")

    for line in container.logs(stream=True, follow=True):
        logger.info(line.decode("utf-8").strip())

    result = container.wait()
    container.remove()
    return result.get("StatusCode", -1)
