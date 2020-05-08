"""Earthquake source location inverse problems
"""
import warnings as _warnings
from typing import Union as _Union, Tuple as _Tuple

import numpy as _numpy

from hmc_tomography.Distributions import _AbstractDistribution, Normal
from hmc_tomography.Helpers import RandomMatrices as _RandomMatrices


class SourceLocation(_AbstractDistribution):
    """Earthquake source location in 2D using a single velocity for the subsurface.
    """

    name: str = "Earthquake source location in 2D"

    infer_velocity: bool = True
    """Boolean that determines whether or not the model velocity is also a free
    parameter."""

    receiver_array_x: _numpy.ndarray = None
    receiver_array_z: _numpy.ndarray = None
    number_of_events: int = None
    fixed_medium_velocity: float = None

    def __init__(
        self,
        receiver_array_x: _numpy.ndarray,
        receiver_array_z: _numpy.ndarray,
        observed_data: _numpy.ndarray,
        data_dispersion: _Union[_numpy.ndarray, float],
        misfit_function: str = "L2",
        infer_velocity: bool = True,
        fixed_medium_velocity=None,
    ):

        # Determine if velocity is a free parameter
        self.infer_velocity = infer_velocity
        if not self.infer_velocity:
            assert fixed_medium_velocity is not None
            self.fixed_medium_velocity = fixed_medium_velocity

        # Get number of events from data and array size
        assert observed_data.size % receiver_array_x.size == 0
        self.number_of_events = int(observed_data.size / receiver_array_x.size)

        # Assert that the data is a column vector
        assert observed_data.shape == (observed_data.size, 1)

        # Assert that the data and data error dispersion are the same shape
        assert observed_data.shape == data_dispersion.shape

        if misfit_function == "L2":
            # Use L2 misfit through a Gaussian distribution
            self.misfit_model = Normal(observed_data, data_dispersion)
        else:
            raise ValueError("Misfit function is not implemented")

        # Assert that the arrays are row vectors.
        assert receiver_array_x.shape == (1, receiver_array_x.size)
        assert receiver_array_z.shape == (1, receiver_array_z.size)

        self.receiver_array_x = receiver_array_x
        self.receiver_array_z = receiver_array_z

        self.dimensions: int = self.number_of_events * 3 + int(self.infer_velocity)

    def misfit(self, coordinates: _numpy.ndarray) -> float:

        # If self.fixed_medium_velocity is None, velocity is extracted from the model
        # vector.
        x, z, T, v = self.split_vector(coordinates, velocity=self.fixed_medium_velocity)

        synthetic_data = SourceLocation.forward(
            x, z, T, v, self.receiver_array_x, self.receiver_array_z
        )

        return self.misfit_model.misfit(synthetic_data)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:

        number_of_events = int(_numpy.floor(coordinates.size / 3))

        # Data gradient
        x, z, T, v = self.split_vector(coordinates, velocity=self.fixed_medium_velocity)
        data = self.forward(x, z, T, v, self.receiver_array_x, self.receiver_array_z)
        data_gradient = self.misfit_model.gradient(data)

        # Forward model gradient
        x, z, T, v = self.split_vector(coordinates, velocity=self.fixed_medium_velocity)
        forward_gradient = self.forward_gradient(
            x, z, T, v, self.receiver_array_x, self.receiver_array_z
        )

        number_of_stations = self.receiver_array_z.size

        total_gradient = forward_gradient * data_gradient

        total_gradient_x_sum = _numpy.sum(
            total_gradient[:, 0].reshape(number_of_events, number_of_stations), axis=1
        )
        total_gradient_z_sum = _numpy.sum(
            total_gradient[:, 1].reshape(number_of_events, number_of_stations), axis=1
        )
        total_gradient_T_sum = _numpy.sum(
            total_gradient[:, 2].reshape(number_of_events, number_of_stations), axis=1
        )
        total_gradient_v_sum = _numpy.sum(total_gradient[:, 3])

        total_gradient = _numpy.empty((self.dimensions, 1))

        if self.infer_velocity:
            total_gradient[0:-1:3] = total_gradient_x_sum[:, None]
            total_gradient[1:-1:3] = total_gradient_z_sum[:, None]
            total_gradient[2:-1:3] = total_gradient_T_sum[:, None]
            total_gradient[-1] = total_gradient_v_sum
        else:
            total_gradient[0::3] = total_gradient_x_sum[:, None]
            total_gradient[1::3] = total_gradient_z_sum[:, None]
            total_gradient[2::3] = total_gradient_T_sum[:, None]

        return total_gradient

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError(
            "Generating samples from this distribution is not implemented or supported."
        )

    @staticmethod
    def forward(x, z, T, v, receiver_array_x, receiver_array_z) -> _numpy.ndarray:

        # Assert that the vectors are column-shaped
        assert x.shape == (x.size, 1)
        assert z.shape == (z.size, 1)
        assert T.shape == (T.size, 1)
        # Assert that the vectors are the same length
        assert x.size == z.size and x.size == T.size

        assert receiver_array_x.shape == receiver_array_z.shape
        assert receiver_array_x.shape == (1, receiver_array_x.size)

        # Forward calculate the travel time by dividing distance (Pythagoras) by speed,
        # and adding origin time.
        #
        # This function relies heavily on matrix broadcasting in NumPy to handle
        # multiple stations. The arrays T, x and z are column vectors. By subtracting
        # the row vectors of the station coordinates, we create matrices for the
        # traveltimes, with the following structure (example data points are filled in):
        #
        #  Station:   1      2
        # Event 1:  [5.3s,  9.0s]
        # Event 2:  [2.7s,  7,4s]
        # Event 3:  [7.1s,  8.2s]

        traveltimes: _numpy.ndarray = (
            T
            + ((x - receiver_array_x) ** 2.0 + (z - receiver_array_z) ** 2.0) ** 0.5 / v
        )

        # Subsequently we flatten the array to make it compatible with the distributions
        # to use it with distributions for errors.

        return traveltimes.reshape(traveltimes.size, 1)

    @staticmethod
    def forward_gradient(
        x, z, T, v, receiver_array_x, receiver_array_z
    ) -> _numpy.ndarray:

        # Assert that the vectors are column-shaped
        assert x.shape == (x.size, 1)
        assert z.shape == (z.size, 1)
        assert T.shape == (T.size, 1)
        # Assert that the vectors are the same length
        assert x.size == z.size and x.size == T.size

        assert receiver_array_x.shape == receiver_array_z.shape
        assert receiver_array_x.shape == (1, receiver_array_x.size)

        # Forward calculate the travel time by dividing distance (Pythagoras) by speed,
        # and adding origin time.
        #
        # This function relies heavily on matrix broadcasting in NumPy to handle
        # multiple stations. The arrays T, x and z are column vectors. By subtracting
        # the row vectors of the station coordinates, we create matrices for the
        # gradients, with the following structure (example data points are filled in):
        #
        #  Station:   1      2
        # Event 1:  [5.3s,  9.0s]
        # Event 2:  [2.7s,  7,4s]
        # Event 3:  [7.1s,  8.2s]

        distances = (
            (x - receiver_array_x) ** 2.0 + (z - receiver_array_z) ** 2.0
        ) ** 0.5

        gradient_x = ((x - receiver_array_x) / (v * distances)).reshape(
            distances.size, 1
        )
        gradient_z = ((z - receiver_array_z) / (v * distances)).reshape(
            distances.size, 1
        )
        gradient_T = (_numpy.ones_like(gradient_x)).reshape(distances.size, 1)
        gradient_v = (-distances / (v * v)).reshape(distances.size, 1)

        return _numpy.hstack((gradient_x, gradient_z, gradient_T, gradient_v))

    @staticmethod
    def create_default(dimensions):
        return super().create_default(dimensions)

    @staticmethod
    def split_vector(model_vector, velocity=None) -> _Tuple:
        if velocity is None:
            assert model_vector.size % 3 == 1
            x = model_vector[0:-1:3]
            z = model_vector[1:-1:3]
            T = model_vector[2:-1:3]
            v = model_vector[-1]
            return x, z, T, v
        else:
            assert model_vector.size % 3 == 0
            x = model_vector[0::3]
            z = model_vector[1::3]
            T = model_vector[2::3]
            return x, z, T, velocity
