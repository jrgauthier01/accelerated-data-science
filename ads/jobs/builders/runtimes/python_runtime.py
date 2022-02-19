#!/usr/bin/env python
# -*- coding: utf-8; -*-

# Copyright (c) 2021, 2022 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import json
import os
from typing import Any, Dict

from ads.jobs.builders.runtimes.base import Runtime


class CondaRuntime(Runtime):
    """Represents a job runtime with conda pack"""

    CONST_CONDA = "conda"
    CONST_CONDA_TYPE = "type"
    CONST_CONDA_TYPE_SERVICE = "service"
    CONST_CONDA_TYPE_CUSTOM = "published"
    CONST_CONDA_SLUG = "slug"
    CONST_CONDA_URI = "uri"
    CONST_CONDA_REGION = "region"

    @property
    def conda(self) -> dict:
        """The conda pack specification

        Returns
        -------
        dict
            A dictionary with "type" and "slug" as keys.
        """
        return self.get_spec(self.CONST_CONDA)

    def with_service_conda(self, slug: str):
        """Specifies the service conda pack for running the job

        Parameters
        ----------
        slug : str
            The slug name of the service conda pack

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(
            self.CONST_CONDA,
            {
                self.CONST_CONDA_TYPE: self.CONST_CONDA_TYPE_SERVICE,
                self.CONST_CONDA_SLUG: slug,
            },
        )

    def with_custom_conda(self, uri: str, region: str = None):
        """Specifies the custom conda pack for running the job

        Parameters
        ----------
        uri : str
            The OCI object storage URI for the conda pack,
            e.g. "oci://your_bucket@namespace/object_name."
            In the Environment Explorer of an OCI notebook session,
            this is shown as the "source" of the conda pack.
        region: str, optional
            The region of the bucket storing the custom conda pack, by default None.
            If region is not specified, ADS will use the region from your authentication credentials,
            * For API Key, config["region"] is used.
            * For Resource Principal, signer.region is used.

            This is required if the conda pack is stored in a different region.

        Returns
        -------
        self
            The runtime instance.

        See Also
        --------
        https://docs.oracle.com/en-us/iaas/data-science/using/conda_publishs_object.htm

        """
        conda_spec = {
            self.CONST_CONDA_TYPE: self.CONST_CONDA_TYPE_CUSTOM,
            self.CONST_CONDA_URI: uri,
        }
        if region:
            conda_spec[self.CONST_CONDA_REGION] = region
        return self.set_spec(self.CONST_CONDA, conda_spec)


class ScriptRuntime(CondaRuntime):
    """Represents job runtime with scripts and conda pack"""

    CONST_ENTRYPOINT = "entrypoint"
    CONST_SCRIPT_PATH = "scriptPathURI"

    @property
    def script_uri(self) -> str:
        """The URI of the source code"""
        return self.get_spec(self.CONST_SCRIPT_PATH)

    def with_script(self, uri: str):
        """Specifies the source code script for the job

        Parameters
        ----------
        uri : str
            URI to the Python or Shell script, which can be any URI supported by fsspec,
            including http://, https:// and OCI object storage.
            For example: oci://your_bucket@your_namespace/path/to/script.py

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(self.CONST_SCRIPT_PATH, uri)

    @property
    def source_uri(self) -> str:
        """The URI of the source code"""
        return self.get_spec(self.CONST_SCRIPT_PATH)

    def with_source(self, uri: str, entrypoint: str = None):
        """Specifies the source code for the job

        Parameters
        ----------
        uri : str
            URI to the source code,
            which can be a (.py/.sh) script, a zip/tar file or directory containing the scripts/modules
            If the source code is a single file, URI can be any URI supported by fsspec,
            including http://, https:// and OCI object storage.
            For example: oci://your_bucket@your_namespace/path/to/script.py
            If the source code is a directory, only local directory is supported.

        entrypoint : str, optional
            The relative path of the script to be set as entrypoint when source is a zip/tar/directory.
            By default None. This is not needed when the source is a single script.

        Returns
        -------
        self
            The runtime instance.
        """
        if entrypoint:
            self.set_spec(self.CONST_ENTRYPOINT, entrypoint)
        return self.with_script(uri)

    @property
    def entrypoint(self) -> str:
        """The relative path of the script to be set as entrypoint when source is a zip/tar/directory."""
        return self.get_spec(self.CONST_ENTRYPOINT)

    def with_entrypoint(self, entrypoint: str):
        """Specify the entrypoint for the job

        Parameters
        ----------
        entrypoint : str
            The relative path of the script to be set as entrypoint when source is a zip/tar/directory.

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(self.CONST_ENTRYPOINT, entrypoint)


class _PythonRuntimeMixin(Runtime):
    CONST_OUTPUT_DIR = "outputDir"
    CONST_OUTPUT_URI = "outputUri"
    CONST_PYTHON_PATH = "pythonPath"
    CONST_ENTRYPOINT = "entrypoint"
    CONST_ENTRY_FUNCTION = "entryFunction"

    def with_output(self, output_dir: str, output_uri: str):
        """Specifies the outputs of the job.
        The output files in output_dir will be copied to remote output_uri when the job is finished.

        Parameters
        ----------
        output_dir : str
            Path to the output directory in the job run.
            This path should be a relative path from the working directory.
            The source code should write all outputs into this directory.
        output_uri : str
            The OCI object storage URI prefix for saving the output files.
            For example, oci://bucket_name@namespace/path/to/directory

        Returns
        -------
        self
            The runtime instance.
        """
        self.set_spec(self.CONST_OUTPUT_DIR, output_dir)
        self.set_spec(self.CONST_OUTPUT_URI, output_uri)
        return self

    def with_python_path(self, *python_paths):
        """Specifies additional python paths for running the source code.

        Parameters
        ----------
        *python_paths :
            Additional python path(s) for running the source code.
            Each path should be a relative path from the working directory.

        Returns
        -------
        self
            The runtime instance.
        """
        python_paths = list(python_paths)
        for path in python_paths:
            if os.path.isabs(path):
                raise ValueError(
                    f"{path} is an absolute path."
                    "Please specify relative path from the working directory as python path."
                )
        return self.set_spec(self.CONST_PYTHON_PATH, python_paths)

    def with_entrypoint(self, path: str, func: str = None):
        """Specifies the entrypoint for the job.
        The entrypoint can be a script or a function in a script.

        Parameters
        ----------
        script : str
            The relative path for the script/module starting the job.
        func : str, optional
            The function name in the script for starting the job, by default None.
            If this is not specified, the script will be run with python command in a subprocess.

        Returns
        -------
        self
            The runtime instance.
        """
        self.set_spec(self.CONST_ENTRYPOINT, path)
        self.set_spec(self.CONST_ENTRY_FUNCTION, func)
        return self

    @property
    def output_dir(self) -> str:
        """Directory in the Job run container for saving output files generated in the job"""
        return self.get_spec(self.CONST_OUTPUT_DIR)

    @property
    def output_uri(self) -> str:
        """OCI object storage URI prefix for saving output files generated in the job"""
        return self.get_spec(self.CONST_OUTPUT_DIR)

    @property
    def python_path(self):
        """Additional python paths for running the source code."""
        return self.get_spec(self.CONST_PYTHON_PATH)

    @property
    def entry_script(self) -> str:
        """The path of the entry script"""
        return self.get_spec(self.CONST_ENTRYPOINT)

    @property
    def entry_function(self) -> str:
        """The name of the entry function in the entry script"""
        return self.get_spec(self.CONST_ENTRY_FUNCTION)


class PythonRuntime(ScriptRuntime, _PythonRuntimeMixin):
    """Represents a job runtime using ADS driver script to run Python code"""

    CONST_WORKING_DIR = "workingDir"

    def with_working_dir(self, working_dir: str):
        """Specifies the working directory in the job run.
        By default, the working directory will the directory containing the user code (job artifact directory).
        This can be changed by specifying a relative path to the job artifact directory.

        Parameters
        ----------
        working_dir : str
            The path of the working directory.
            This can be a relative path from the job artifact directory.

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(self.CONST_WORKING_DIR, working_dir)

    @property
    def working_dir(self) -> str:
        """The working directory for the job run."""
        return self.get_spec(self.CONST_WORKING_DIR, ".")


class NotebookRuntime(CondaRuntime):
    """Represents a job runtime with Jupyter notebook"""

    CONST_NOTEBOOK_PATH = "notebookPathURI"
    CONST_OUTPUT_URI = "outputURI"
    EXCLUDE_TAG = "excludeTags"

    @property
    def notebook_uri(self) -> str:
        """The URI of the notebook"""
        return self.get_spec(self.CONST_NOTEBOOK_PATH)

    def with_notebook(self, path: str):
        """Specifies the notebook to be converted to python script and run as a job.

        Parameters
        ----------
        path : str
            The path of the Jupyter notebook

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(self.CONST_NOTEBOOK_PATH, path)

    @property
    def exclude_tag(self) -> list:
        """A list of cell tags indicating cells to be excluded from the job"""
        return self.get_spec(self.EXCLUDE_TAG, [])

    def with_exclude_tag(self, *tags):
        """Specifies the cell tags in the notebook to exclude cells from the job script.

        Parameters
        ----------
        *tags : list
            A list of tags (strings).

        Returns
        -------
        self
            The runtime instance.
        """
        exclude_tag_list = []
        for tag in tags:
            if isinstance(tag, list):
                exclude_tag_list.extend(tag)
            else:
                exclude_tag_list.append(tag)
        return self.set_spec(self.EXCLUDE_TAG, exclude_tag_list)

    @property
    def output_uri(self) -> list:
        """URI for storing the output notebook and files"""
        return self.get_spec(self.CONST_OUTPUT_URI)

    def with_output(self, output_uri: str):
        """Specifies the output URI for storing the output notebook and files.

        Parameters
        ----------
        output_uri : str
            URI for storing the output notebook and files.
            For example, oci://bucket@namespace/path/to/dir

        Returns
        -------
        self
            The runtime instance.
        """
        return self.set_spec(self.CONST_OUTPUT_URI, output_uri)


class GitPythonRuntime(CondaRuntime, _PythonRuntimeMixin):
    """Represents a job runtime with source code from git repository"""

    CONST_GIT_URL = "url"
    CONST_BRANCH = "branch"
    CONST_COMMIT = "commit"
    CONST_GIT_SSH_SECRET_ID = "gitSecretId"
    CONST_SKIP_METADATA = "skipMetadataUpdate"

    def __init__(self, spec: Dict = None, skip_metadata_update=False) -> None:
        """Initialize Git Python Runtime.

        Parameters
        ----------
        spec : dict, optional
            Runtime specifications, by default None
        skip_metadata_update : bool, optional
            Indicate if the metadata update should be skipped after the job run, by default False.
            By default, the job run metadata will be updated with the following freeform tags:
            * repo: The URL of the Git repository
            * commit: The Git commit ID
            * module: The entry script/module
            * method: The entry function/method
            * outputs. The prefix of the output files in object storage.

            This update step also requires resource principals to have the permission to update the job run.
        """
        super().__init__(spec=spec)
        if skip_metadata_update:
            self.set_spec(self.CONST_SKIP_METADATA, True)

    @property
    def skip_metadata_update(self):
        """Indicate if the metadata update should be skipped after the job run

        Returns
        -------
        bool
            True if the metadata update will be skipped. Otherwise False.
        """
        return self.get_spec(self.CONST_SKIP_METADATA, False)

    def with_source(
        self, url: str, branch: str = None, commit: str = None, secret_ocid: str = None
    ):
        """Specifies the Git repository and branch/commit for the job source code.

        Parameters
        ----------
        url : str
            URL of the Git repository.
        branch : str, optional
            Git branch name, by default None, the default branch will be used.
        commit : str, optional
            Git commit ID (SHA1 hash), by default None, the most recent commit will be used.
        secret_ocid : str
            The secret OCID storing the SSH key content for checking out the Git repository.

        Returns
        -------
        self
            The runtime instance.
        """
        self.set_spec(self.CONST_GIT_URL, url)
        self.set_spec(self.CONST_BRANCH, branch)
        self.set_spec(self.CONST_COMMIT, commit)
        self.set_spec(self.CONST_GIT_SSH_SECRET_ID, secret_ocid)
        return self

    @property
    def url(self) -> str:
        """URL of the Git repository."""
        return self.get_spec(self.CONST_GIT_URL)

    @property
    def branch(self) -> str:
        """Git branch name."""
        return self.get_spec(self.CONST_BRANCH)

    @property
    def commit(self) -> str:
        """Git commit ID (SHA1 hash)"""
        return self.get_spec(self.CONST_COMMIT)

    @staticmethod
    def _serialize_arg(arg: Any) -> str:
        """Serialize the argument.
        This returns the argument "as is" if it is a string AND not a valid JSON payload.
        Otherwise the argument will be serialized with JSON.

        Parameters
        ----------
        arg : Any
            argument to be serialized

        Returns
        -------
        str
            Serialized argument as a string
        """
        if arg is None:
            return None
        if isinstance(arg, str):
            try:
                json.loads(arg)
            except json.JSONDecodeError:
                return arg
        return json.dumps(arg)

    def with_argument(self, *args, **kwargs):
        """Specifies the arguments for running the script/function.

        When running a python script, the arguments will be the command line arguments.
        For example, with_argument("arg1", "arg2", key1="val1", key2="val2")
        will generate the command line arguments: "arg1 arg2 --key1 val1 --key2 val2"

        When running a function, the arguments will be passed into the function.
        Arguments can also be list, dict or any JSON serializable object.
        For example, with_argument("arg1", "arg2", key1=["val1a", "val1b"], key2="val2")
        will be passed in as "your_function("arg1", "arg2", key1=["val1a", "val1b"], key2="val2")

        Returns
        -------
        self
            The runtime instance.
        """
        args = [self._serialize_arg(arg) for arg in args]
        kwargs = {k: self._serialize_arg(v) for k, v in kwargs.items()}
        return super().with_argument(*args, **kwargs)

    @property
    def ssh_secret_ocid(self):
        """The OCID of the OCI Vault secret storing the Git SSH key."""
        return self.get_spec(self.CONST_GIT_SSH_SECRET_ID)


class DataFlowRuntime(Runtime):

    CONST_SCRIPT_BUCKET = "scriptBucket"
    CONST_ARCHIVE_BUCKET = "archiveBucket"
    CONST_ARCHIVE_URI = "archiveUri"
    CONST_SCRIPT_PATH = "scriptPathURI"

    def with_archive_uri(self, uri: str) -> "DataFlowRuntime":
        """
        Set archive uri (which is a zip file containing dependencies).

        Parameters
        ----------
        uri: str
            uri to the archive zip

        Returns
        -------
        DataFlowRuntime
            runtime instance itself
        """
        return self.set_spec(self.CONST_ARCHIVE_URI, uri)

    @property
    def archive_uri(self):
        """The Uri of archive zip"""
        return self.get_spec(self.CONST_ARCHIVE_URI)

    @property
    def script_uri(self) -> str:
        """The URI of the source code"""
        return self.get_spec(self.CONST_SCRIPT_PATH)

    def with_script_uri(self, path) -> "DataFlowRuntime":
        """
        Set script uri.

        Parameters
        ----------
        uri: str
            uri to the script

        Returns
        -------
        DataFlowRuntime
            runtime instance itself
        """
        return self.set_spec(self.CONST_SCRIPT_PATH, path)

    def with_script_bucket(self, bucket) -> "DataFlowRuntime":
        """
        Set object storage bucket to save the script, in case script uri given is local.

        Parameters
        ----------
        bucket: str
            name of the bucket

        Returns
        -------
        DataFlowRuntime
            runtime instance itself
        """
        return self.set_spec(self.CONST_SCRIPT_BUCKET, bucket)

    @property
    def script_bucket(self) -> str:
        """Bucket to save script"""
        return self.get_spec(self.CONST_SCRIPT_BUCKET)

    def with_archive_bucket(self, bucket) -> "DataFlowRuntime":
        """
        Set object storage bucket to save the archive zip, in case archive uri given is local.

        Parameters
        ----------
        bucket: str
            name of the bucket

        Returns
        -------
        DataFlowRuntime
            runtime instance itself
        """
        return self.set_spec(self.CONST_ARCHIVE_BUCKET, bucket)

    @property
    def archive_bucket(self) -> str:
        """Bucket to save archive zip"""
        return self.get_spec(self.CONST_ARCHIVE_BUCKET)
