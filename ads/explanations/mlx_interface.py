#!/usr/bin/env python
# -*- coding: utf-8; -*-

# Copyright (c) 2020, 2022 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

from mlx import LimeExplainer
from mlx import FDExplainer, AleExplainer
from mlx import PermutationImportance
from ads.common import utils
from ads.dataset.helper import is_text_data
from mlx.whatif import WhatIf
import pandas as pd


def _reset_index(x):
    assert isinstance(x, pd.DataFrame) or isinstance(x, pd.Series)
    return x.reset_index(drop=True)


def _get_pre_selected_features(est, use_pre_selected_features=False):
    """
    If the ML model internal filters out features (e.g., AutoML),
    provide this information to MLX to skip evaluating these features
    and to improve performance.

    Parameters
    ----------
    est : ADSModel
        Model to explain.
    use_pre_selected_features : bool
        If the model, est, performs internal feature selection, pass
        the selected feature information to the explainer.

    Return
    ------
    list, None
        list of pre-selected features indices or None.
    """
    if use_pre_selected_features and hasattr(est, "selected_features_"):
        return est.selected_features_
    else:
        return None


def check_tabular_or_text(est, X):
    """
    Returns "text" if a text dataset, "tabular" otherwise.

    Parameters
    ----------
    est : ADSModel
        Model to explain.
    X : pandas.DataFrame
        Dataset.

    Return
    ------
    str
        "text" or "tabular"
    """
    return "text" if is_text_data(X) else "tabular"


def init_lime_explainer(
    explainer,
    est,
    X_train,
    y_train,
    mode,
    class_names=None,
    use_pre_selected_features=False,
    client=None,
    batch_size=16,
    surrogate_model="linear",
    num_samples=5000,
    exp_sorting="absolute",
    discretization="decile",
    scale_weight=True,
):
    """
    Initializes a local LIME Explainer. Also supports aggregate local
    explanations, which approximates a global behavior based on multiple local explanations.

    Supports both tabular and text datasets. The explainer is initialized to the defaults
    and can be updated with `MLXGlobalExplainer.configure_feature_importance()` or
    `MLXLocalExplainer.configure_local_explainer()`.

    Parameters
    ----------
    explainer : LimeExplainer, None
        If the explainer has previously been initialized, it can be passed in to avoid
        creating a new explainer object. If `None`, a new `LimeExplainer` instance will be created.
    est : ADSModel
        Model to explain.
    X_train : pandas.DataFrame
        Training dataset.
    y_train : pandas.DataFrame/Series
        Training labels.
    mode : str
        'classification' or 'regression'.
    class_names : list
        List of target names.
    use_pre_selected_features : bool
        If the `est` performs internal feature selection, pass the selected
        feature information to the explainer.
    client : Dask Client
        Specifies that Dask Client object to use in MLX. If None, no parallelization.
    batch_size : int
        Number of local explanations that are batched and processed by each Dask worker
        in parallel.
    surrogate_model : str
        Surrogate model to approximate the local behavior of the ML model. Can be
        'linear' or 'decision_tree'.
    num_samples : int
        Number of samples the local explainer generates in the local neighborhood
        around the sample to explain to fit the surrogate model.
    exp_sorting : str
        Order of how to sort the feature importances. Can be 'absolute' or 'ordered'.
        Absolute ordering orders based on the absolute values, while ordered considers
        the sign of the feature importance values.
    discretizer : str
        Method to discretize continuous features in the local explainer. Supports 'decile',
        'quartile', 'entropy', and `None`. If `None`, the continuous feature values are
        used directly. If not None, each continuous feature is discretized and treated
        as a categorical feature.
    scale_weight : bool
        Normalizes the feature importance coefficients from the local explainer to sum to one.

    Return
    ------
    :class:`mlx.LimeExplainer`
    """
    if explainer is None:
        exp = LimeExplainer()
    else:
        if not isinstance(explainer, LimeExplainer):
            raise TypeError(
                "Invalid explainer provided to "
                "init_lime_explainer: {}".format(type(explainer))
            )
        exp = explainer
    exp_type = check_tabular_or_text(est, X_train)
    exp.set_config(
        type=exp_type,
        mode=mode,
        discretizer=discretization,
        client=client,
        batch_size=batch_size,
        scale_weight=scale_weight,
        surrogate_model=surrogate_model,
        num_samples=num_samples,
        exp_sorting=exp_sorting,
        kernel_width="dynamic",
    )
    selected_features = _get_pre_selected_features(est, use_pre_selected_features)
    exp.fit(
        est,
        X_train,
        y=y_train,
        target_names=class_names,
        selected_features=selected_features,
    )
    return exp


def init_permutation_importance_explainer(
    explainer,
    est,
    X_train,
    y_train,
    mode,
    class_names=None,
    use_pre_selected_features=False,
    client=None,
    random_state=42,
):
    """
    Initializes a Global Feature Permutation Importance Explainer.

    Supported for tabular datasets only.

    The explainer is initialized to the defaults and can be updated with
    MLXGlobalExplainer.configure_feature_importance().

    Parameters
    ----------
    explainer : PermutationImportance, None
        If the explainer has previously been initialized, it can be passed in to avoid
        creating a new explainer object. If `None`, a new `PermutationImportance` explainer
        will be created.
    est : ADSModel
        Model to explain.
    X_train : pandas.DataFrame
        Training dataset.
    y_train : pandas.DataFrame/Series
        Training labels.
    mode : str
        'classification' or 'regression'.
    class_names : list, optional
        List of target names. Default value is `None`
    use_pre_selected_features : bool, optional
        If the `est` performs internal feature selection, pass the selected
        feature information to the explainer. Defaults value is `False`.
    client : Dask Client, optional
        Specifies that Dask Client object to use in MLX. If `None`, no parallelization.
    random_state : int, optional
        Random seed, by default 42.

    Return
    ------
    :class:`mlx.PermutationImportance`
    """
    if explainer is None:
        exp = PermutationImportance()
    else:
        if not isinstance(explainer, PermutationImportance):
            raise TypeError(
                "Invalid explainer provided to "
                "init_permutation_importance_explainer: {}".format(type(explainer))
            )
        exp = explainer
    if check_tabular_or_text(est, X_train) == "text":
        raise TypeError(
            "Global feature importance explainers are currently not "
            "supported for text datasets."
        )
    exp.set_config(mode=mode, client=client, random_state=random_state)
    selected_features = _get_pre_selected_features(est, use_pre_selected_features)
    exp.fit(
        est,
        X_train,
        y=y_train,
        target_names=class_names,
        selected_features=selected_features,
    )
    return exp


def init_partial_dependence_explainer(
    explainer, est, X_train, y_train, mode, class_names=None, client=None
):
    """
    Initializes a Global feature dependence explainer.

    Supports one and two feature partial dependence plots (PDP) and one feature individual
    conditional expectation plots (ICE). Currently only supported for tabular datasets
    (text is not supported).

    The explainer is initialized to the defaults and can be updated with
    `MLXGlobalExplainer.configure_partial_dependence()`.

    Parameters
    ----------
    explainer : FDExplainer
        If the explainer has previously been initialized, it can be passed in to avoid
        creating a new explainer object. If None, a new `FDExplainer` will be created.
    est : ADSModel
        Model to explain.
    X_train : pandas.DataFrame
        Training dataset.
    y_train : pandas.DataFrame/Series
        Training labels.
    mode : str
        'classification' or 'regression'.
    class_names : list
        List of target names.
    client : Dask Client
        Specifies that Dask Client object to use in MLX. If None, no parallelization.

    Return
    ------
    :class:`mlx.FDExplainer`
    """
    if explainer is None:
        exp = FDExplainer()
    else:
        if not isinstance(explainer, FDExplainer):
            raise TypeError(
                "Invalid explainer provided to "
                "init_partial_dependence_explainer: {}".format(type(explainer))
            )
        exp = explainer
    if check_tabular_or_text(est, X_train) == "text":
        raise TypeError(
            "Global partial dependence explainers are currently not "
            "supported for text datasets."
        )
    exp.set_config(mode=mode, client=client)
    exp.fit(est, X_train, y=y_train, target_names=class_names)
    return exp


def init_ale_explainer(
    explainer, est, X_train, y_train, mode, class_names=None, client=None
):
    """
    Initializes a Global Accumulated Local Effects(ALE) Explainer.

    Supports one feature ALE plots. Supported for tabular datasets
    (text is not supported).

    The explainer is initialized to the defaults and can be updated with
    `MLXGlobalExplainer.configure_accumulated_local_effects()`.

    Parameters
    ----------
    explainer : AleExplainer
        If the explainer has previously been initialized, it can be passed in to avoid
        creating a new explainer object. If None, a new AleExplainer will be created.
    est : ADSModel
        Model to explain.
    X_train : pandas.DataFrame
        Training dataset.
    y_train : pandas.DataFrame/Series
        Training labels.
    mode : str
        "classification" or "regression".
    class_names : list, optional
        List of target names. Default value is `None`.
    client : Dask Client, optional
        Specifies that Dask Client object to use in MLX. If `None`, no parallelization.

    Return
    ------
    :class:`mlx.FDExplainer`
    """
    if explainer is None:
        exp = AleExplainer()
    else:
        if not isinstance(explainer, AleExplainer):
            raise TypeError(
                "Invalid explainer provided to "
                "init_partial_dependence_explainer: {}".format(type(explainer))
            )
        exp = explainer
    if check_tabular_or_text(est, X_train) == "text":
        raise TypeError(
            "Global partial dependence explainers are currently not "
            "supported for text datasets."
        )
    exp.set_config(mode=mode, client=client)
    exp.fit(est, X_train, y=y_train, target_names=class_names)
    return exp


def init_whatif_explainer(
    explainer,
    est,
    X_test,
    y_test,
    mode,
    class_names=None,
    train=None,
    target_title="target",
    random_state=42,
    **kwargs
):
    if explainer is None:
        width = kwargs.get("width", 1100)
        exp = WhatIf(mode=mode, random_state=random_state, width=width)
    else:
        if not isinstance(explainer, WhatIf):
            raise TypeError(
                "Invalid explorer provided to "
                "init_explorer: {}".format(type(explainer))
            )
        exp = explainer
    exp_type = check_tabular_or_text(est, X_test)
    if exp_type == "text":
        raise TypeError(
            "WhatIf explainer are currently not "
            "supported for text datasets.".format(type(explainer))
        )
    exp.fit(
        model=est,
        X=X_test,
        y=y_test,
        target_names=class_names,
        train=train,
        target_title=target_title,
    )
    return exp
