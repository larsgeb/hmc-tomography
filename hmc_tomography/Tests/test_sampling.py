"""A collection of integrated tests.
"""
import os as _os

import numpy as _numpy
import pytest as _pytest

import hmc_tomography as _hmc_tomography
from hmc_tomography.Helpers.CustomExceptions import (
    InvalidCaseError as _InvalidCaseError,
)

_ad = _hmc_tomography.Distributions._AbstractDistribution
_as = _hmc_tomography.Samplers._AbstractSampler

dimensions = [1, 2, 10]
distribution_classes = _ad.__subclasses__()
sampler_classes = _as.__subclasses__()
proposals = [10, 1000]  # , 731, 1500]


@_pytest.mark.parametrize("sampler_class", sampler_classes)
@_pytest.mark.parametrize("distribution_class", distribution_classes)
@_pytest.mark.parametrize("dimensions", dimensions)
@_pytest.mark.parametrize("proposals", proposals)
def test_basic_sampling(
    sampler_class: _as, distribution_class: _ad, dimensions: int, proposals: int,
):

    try:
        distribution: _ad = distribution_class.create_default(dimensions)
    except _InvalidCaseError:
        return 0

    sampler = sampler_class()

    assert isinstance(sampler, _as)

    filename = "temporary_file.h5"

    # Remove file before attempting to sample
    if _os.path.exists(filename):
        _os.remove(filename)

    sampler.sample(
        filename,
        distribution,
        proposals=proposals,
        online_thinning=10,
        ram_buffer_size=int(proposals / _numpy.random.rand() * 10),
        max_time=1.0,
    )

    # Check if the file was created. If it wasn't, fail
    if not _os.path.exists(filename):
        _pytest.fail("Samples file wasn't created")

    # Remove the file
    _os.remove(filename)


@_pytest.mark.parametrize("sampler_class", sampler_classes)
@_pytest.mark.parametrize("distribution_class", distribution_classes)
@_pytest.mark.parametrize("dimensions", dimensions)
@_pytest.mark.parametrize("proposals", proposals)
def test_samples_file(
    sampler_class: _as, distribution_class: _ad, dimensions: int, proposals: int,
):

    try:
        distribution: _ad = distribution_class.create_default(dimensions)
    except _InvalidCaseError:
        return 0

    sampler = sampler_class()

    filename = "temporary_file.h5"

    # Remove file before attempting to sample
    if _os.path.exists(filename):
        _os.remove(filename)

    sampler.sample(filename, distribution, proposals=proposals, max_time=1.0)

    # Check if the file was created. If it wasn't, fail
    if not _os.path.exists(filename):
        _pytest.fail("Samples file wasn't created")

    samples_written_expected = int(
        _numpy.floor(sampler.current_proposal / sampler.online_thinning) + 1
    )

    with _hmc_tomography.Post.Samples(filename) as samples:
        # Assert that the HDF array has the right dimensions
        assert samples.raw_samples_hdf.shape == (distribution.dimensions + 1, proposals)

        # Assert that the actual written samples have the right dimensions
        assert samples[:, :].shape == (
            distribution.dimensions + 1,
            samples_written_expected,
        )

    # Remove the file
    _os.remove(filename)