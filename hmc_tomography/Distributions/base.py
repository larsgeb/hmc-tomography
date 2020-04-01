"""Distribution classes and associated methods.
"""
from abc import ABC as _ABC
from abc import abstractmethod as _abstractmethod
from typing import List as _List
from typing import Union as _Union
import warnings as _warnings
import numpy as _numpy
import scipy as _scipy
import scipy.sparse as _sparse


class _AbstractDistribution(_ABC):
    """Distribution abstract base class

    """

    name: str = "abstract distribution"
    """Name of the distribution."""

    dimensions: int = -1
    """Model space dimension of the distribution."""

    lower_bounds: _Union[_numpy.ndarray, None] = None
    """Lower bounds for every parameter. If initialized to None, no bounds are used."""

    upper_bounds: _Union[_numpy.ndarray, None] = None
    """Upper bounds for every parameter. If initialized to None, no bounds are used."""

    @_abstractmethod
    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """Computes the misfit of the distribution at the given coordinates.

        Parameters
        ----------
        coordinates : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the coordinates :math:`\\mathbf{m}`.

        Returns
        -------
        misfit : float
            The distribution misfit :math:`\\chi`.


        The distribution misfit is related to the distribution probability density as:

        .. math::

            \\chi_\\text{distribution} (\\mathbf{m}) = -\\log p(\\mathbf{m}).


        This method is called many times in an HMC appraisal. It is therefore
        beneficial to optimize the implementation.
        """
        pass

    @_abstractmethod
    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """Computes the misfit gradient of the distribution at the given coordinates.

        Parameters
        ----------
        coordinates : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the coordinates :math:`\\mathbf{m}`.

        Returns
        -------
        gradient : numpy.ndarray
            The distribution misfit gradient :math:`\\nabla_\\mathbf{m}\\chi`.


        The distribution misfit gradient is related to the distribution probability density
        as:

        .. math::

            \\nabla_\\mathbf{m} \\chi_\\text{distribution} (\\mathbf{m}) = -
            \\nabla_\\mathbf{m} \\log p(\\mathbf{m}).


        This method is called many times in an HMC appraisal. It is therefore
        beneficial to optimize the implementation.
        """
        pass

    @_abstractmethod
    def generate(self) -> _numpy.ndarray:
        """Method to draw samples from the distribution.

        Returns
        -------
        sample : numpy.ndarray
            A numpy array shaped as (dimensions, 1) containing a sample of the distribution.

        Raises
        ------
        TypeError
            If the distribution does not allow generation of samples.


        This method is mostly a convenience class. The algorithm itself does not
        require the implementation. Therefore an implementation as such will suffice::

            def generate(self) -> _numpy.ndarray:
                raise NotImplementedError("This function is not implemented.")

        """
        pass

    def corrector(self, coordinates: _numpy.ndarray, momentum: _numpy.ndarray):
        """Method to correct an HMC particle, which is called after every time
        integration step.

        Parameters
        ----------
        coordinates : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the coordinates :math:`\\mathbf{m}` upon which to operate by
            reference.
        momentum : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the momenta :math:`\\mathbf{p}` upon which to operate by
            reference.

        """
        if self.lower_bounds is not None:
            # Lower bound correction
            too_low = coordinates < self.lower_bounds
            coordinates[too_low] += 2 * (
                self.lower_bounds[too_low] - coordinates[too_low]
            )
            momentum[too_low] *= -1.0
        if self.upper_bounds is not None:
            # Upper bound correction
            too_high = coordinates > self.upper_bounds
            coordinates[too_high] += 2 * (
                self.upper_bounds[too_high] - coordinates[too_high]
            )
            momentum[too_high] *= -1.0

    def update_bounds(
        self,
        lower_bounds: _Union[_numpy.ndarray, None],
        upper_bounds: _Union[_numpy.ndarray, None],
    ):
        """Method to update bounds of a distribution distribution.

        Parameters
        ==========
        lower_bounds : numpy.ndarray or `None`
            Either an array shaped as (dimensions, 1) with floats for the lower bounds,
            or `None` for no bounds. If some dimensions should be bounded, while others
            should not, use ``-numpy.inf`` within the vector as needed.
        upper_bounds : numpy.ndarray or `None`
            Either an array shaped as (dimensions, 1) with floats for the upper bounds,
            or `None` for no bounds. If some dimensions should be bounded, while others
            should not, use ``numpy.inf`` within the vector as needed.


        This method updates the bounds of a distribution. Note that invocating it,
        requires both bounds to be passed. If only one is to be updated, simply pass
        the current object of the other bound::

            distribution.update_bounds(numpy.zeros((4, 1)), distribution.upper_bounds)


        If both vectors are passed, ensure that all upper bounds are above the
        corresponding lower bounds.

        """

        # Check the types --------------------------------------------------------------
        if (
            lower_bounds is not None
            and type(lower_bounds) is not _numpy.ndarray
        ):
            raise ValueError("Lower bounds object not understood.")
        if (
            upper_bounds is not None
            and type(upper_bounds) is not _numpy.ndarray
        ):
            raise ValueError("Upper bounds object not understood.")

        # Set the bounds ---------------------------------------------------------------
        self.upper_bounds = upper_bounds
        self.lower_bounds = lower_bounds

        # Check for both arrays, if they are not None, if the dimension is correct. ----
        if (
            self.lower_bounds is not None
            and self.lower_bounds.shape != (self.dimensions, 1)
        ) or (
            self.upper_bounds is not None
            and self.upper_bounds.shape != (self.dimensions, 1)
        ):
            raise ValueError(f"Bounds vectors are of incorrect size.")

        # Check that all upper bounds are (finitely) above lower bounds ----------------
        if (
            self.lower_bounds is not None
            and self.upper_bounds is not None
            and _numpy.any(self.upper_bounds <= self.lower_bounds)
        ):
            raise ValueError("Bounds vectors are incompatible.")

    def misfit_bounds(self, coordinates: _numpy.ndarray) -> float:
        """Method to compute the misfit associated with the truncated part of the distribution.
        """
        if (
            self.lower_bounds is not None
            and _numpy.any(coordinates < self.lower_bounds)
        ) or (
            self.upper_bounds is not None
            and _numpy.any(coordinates > self.upper_bounds)
        ):
            return _numpy.inf
        return 0.0


class Normal(_AbstractDistribution):
    """Normal distribution in model space.

    Parameters
    ----------
    dimensions : int
        Dimension of the distribution.
    means : numpy.ndarray
        Numpy array shaped as (dimensions, 1) containing the means of the distribution.
    covariance : numpy.ndarray
        Numpy array shaped as either as (dimensions, dimensions) or (dimensions, 1).
        This array represents either the full covariance matrix for a multivariate
        Gaussian, or an column vector with variances for `dimensions` separate
        uncorrelated Gaussians.
    lower_bounds: numpy.ndarray
        Numpy array of shape (dimensions, 1) that contains the lower limits of each
        parameter.
    upper_bounds: numpy.ndarray
        Numpy array of shape (dimensions, 1) that contains the upper limits of each
        parameter.

    """

    def __init__(
        self,
        means: _numpy.ndarray = None,
        covariance: _Union[_numpy.ndarray, float, None] = None,
        inverse_covariance: _Union[_numpy.ndarray, float, None] = None,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        override_dimensions: int = 2,
    ):

        self.name = "Gaussian (normal) distribution"

        # Automatically get dimensionality ...
        if means is not None:
            # ... from means
            dimensions = means.size
        else:
            # If no means is provided, use 2 dimensions, and later randomly create
            # distribution
            dimensions = override_dimensions
        self.dimensions = dimensions
        """Amount of dimensions on which the distribution is defined, should agree with
        means and covariance, and optionally coordinate_transformation."""

        self.diagonal: bool = False
        """Indicator whether or not the covariance matrix is diagonal, i.e. if the
        distribution is uncorrelated."""

        self.means: _numpy.ndarray = None
        """Means in model space"""

        self.covariance: _numpy.ndarray = None
        """Covariance matrix in model space"""

        self.inverse_covariance: _numpy.ndarray = None
        """Inverse covariance matrix"""

        if means is None and covariance is None:
            # Neither means nor covariance is provided ---------------------------------
            _warnings.warn(
                "Neither means or covariance matrix provided. "
                "Generating random means and variances with dimensions 2.",
                Warning,
            )
            self.means = _numpy.random.rand(dimensions, 1)
            self.covariance = _make_spd_matrix(self.dimensions) + _numpy.eye(
                self.dimensions
            )
        elif means is None or covariance is None:
            # Only one of means or covariance is provided ------------------------------
            raise ValueError(
                "Only one of means or covariance matrix provided. Not sure what to do!"
            )
        else:
            # Both means and covariance are provided -----------------------------------

            # Parse means
            if type(means) == float or type(means) == int:
                _warnings.warn(
                    "Seems that you only passed a float/int as the means vector. "
                    "It will be used as a single mean for all dimensions.",
                    Warning,
                )
            elif means.shape != (self.dimensions, 1):
                raise ValueError("Incorrect size of means vector.")
            self.means: _numpy.ndarray = means

            # Parse covariance
            if type(covariance) == float or type(covariance) == int:
                self.diagonal = True
                _warnings.warn(
                    "Seems that you only passed a float/int as the covariance matrix. "
                    "It will be used as a single covariance for all dimensions.",
                    Warning,
                )
            elif covariance.shape == (means.size, means.size):
                # Supplied a full covariance matrix, could be either NumPy or SciPy
                # matrix.
                self.diagonal = False
            elif covariance.shape == (means.size, 1):
                # Supplied a diagonal of a covariance matrix
                self.diagonal = True
                _warnings.warn(
                    "Seems that you only passed a vector as the covariance matrix. "
                    "It will be used as the covariance diagonal.",
                    Warning,
                )
            else:
                raise ValueError("Covariance matrix shape not understood.")
            self.covariance = covariance

        # Precomputing inverses to speed up misfit and gradient computation ------------
        if inverse_covariance is not None:
            # There are many ways in which one could optimize the computation of a
            # specific PD-matrix inverse. Let the user compute and provide it if wanted.
            self.inverse_covariance = inverse_covariance
        elif self.diagonal:
            # If the user does not provide one, at least check if the covariance matrix
            # is diagonal, which makes computation of the inverse scale much better.
            self.inverse_covariance: _numpy.ndarray = 1.0 / self.covariance
        else:
            # Else, brute force calculate the inverse using numpy.
            self.inverse_covariance: _numpy.ndarray = _numpy.linalg.inv(
                self.covariance
            )

        # Process optional bounds ------------------------------------------------------
        self.update_bounds(lower_bounds, upper_bounds)

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """Method to compute the misfit of a Normal distribution distribution.
        """

        if self.diagonal:
            return self.misfit_bounds(coordinates) + 0.5 * (
                (self.means - coordinates).T
                @ (self.inverse_covariance * (self.means - coordinates))
            ).item(0)
        else:
            return self.misfit_bounds(coordinates) + 0.5 * (
                (self.means - coordinates).T
                @ self.inverse_covariance
                @ (self.means - coordinates)
            ).item(0)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """Method to compute the gradient of a Normal distribution distribution.
        """

        if self.diagonal:
            return -self.inverse_covariance * (
                self.means - coordinates
            ) + self.misfit_bounds(coordinates)
        else:
            return -self.inverse_covariance @ (
                self.means - coordinates
            ) + self.misfit_bounds(coordinates)

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError("This function is not finished yet")


class Laplace(_AbstractDistribution):
    """Laplace distribution in model space.

    Least absolute deviations, Laplace distribution, LASSO, L1

    """

    def __init__(
        self,
        means: _numpy.ndarray = None,
        dispersions: _Union[_numpy.ndarray, float, None] = None,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        override_dimensions: int = 2,
    ):
        # Automatically get dimensionality ...
        if means is not None:
            # ... from means
            dimensions = means.size
        else:
            # If no means is provided, use 2 dimensions
            dimensions = override_dimensions
        self.dimensions = dimensions
        """TODO description"""

        self.means = means
        """TODO description"""

        self.dispersions = dispersions
        """TODO description"""

        self.inverse_dispersions = 1.0 / dispersions
        """TODO description"""

        self.update_bounds(lower_bounds, upper_bounds)

        # TODO generate random distribution if means and dispersions are not provided.

    def misfit(self, coordinates) -> float:
        """Method to compute the misfit of a L1 distribution distribution.
        """

        # if self.coordinate_transformation is not None:
        #     coordinates = self.coordinate_transformation @ coordinates

        return self.misfit_bounds(coordinates) + _numpy.sum(
            _numpy.abs(coordinates - self.means) * self.inverse_dispersions
        )

    def gradient(self, coordinates):
        """Method to compute the gradient of a L1 distribution distribution.
        """

        # if self.operator is not None:
        #     coordinates = self.operator @ coordinates

        # The derivative of the function |x| is simply 1 or -1, depending on the sign
        # of x, subsequently scaled by the dispersion.
        return (
            self.misfit_bounds(coordinates)
            + _numpy.sign(coordinates - self.means) * self.inverse_dispersions
        )

    def generate(self):
        raise NotImplementedError()


# Unfinished
class L05(_AbstractDistribution):
    """L05

    TODO: Implement distribution's location other than the 0-vector.
    """

    def __init__(
        self,
        dispersion: float = 1,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        override_dimensions: int = 2,
    ):

        raise NotImplementedError("Not finished yet.")

        # TODO Add location functionality to distribution

        if dispersion is not None:
            # ... from dispersion
            dimensions = dispersion.size
        else:
            # If no means is provided, use 2 dimensions
            dimensions = override_dimensions

        self.dimensions = dimensions
        """TODO description"""

        self.dispersion = dispersion
        """TODO description"""

        self.update_bounds(lower_bounds, upper_bounds)
        """TODO description"""

    def misfit(self, coordinates) -> float:
        """Method to compute the misfit of a L1 distribution distribution.
        """
        return self.misfit_bounds(coordinates) + _numpy.sum(
            _numpy.abs(coordinates / self.dispersion) ** 0.5
        )

    def gradient(self, coordinates):
        """Method to compute the gradient of a L1 distribution distribution.
        """
        # The derivative of the function |x| is simply 1 or -1, depending on the sign
        # of x.
        return _numpy.nan_to_num(
            self.misfit_bounds(coordinates)
            + _numpy.sign(coordinates)
            * 0.5
            / (_numpy.abs(coordinates / self.dispersion) ** 0.5)
        )

    def generate(self):
        raise NotImplementedError()


# Unfinished
class LogNormal(Normal):
    """Normal distribution in logarithmic model space.


    Parameters
    ----------
    dimensions : int
        Dimension of the distribution.
    means : numpy.ndarray
        Numpy array shaped as (dimensions, 1) containing the means of the distribution
        in logarithmic model space.
    covariance : numpy.ndarray
        Numpy array shaped as either as (dimensions, dimensions) or (dimensions, 1).
        This array represents either the full covariance matrix for a multivariate
        Gaussian, or an column vector with variances for `dimensions` separate
        uncorrelated Gaussians, all in logarithmic model space.
    lower_bounds: numpy.ndarray
        Numpy array of shape (dimensions, 1) that contains the lower limits of each
        parameter.
    upper_bounds: numpy.ndarray
        Numpy array of shape (dimensions, 1) that contains the upper limits of each
        parameter.


    TODO Validate this class' methods.
    """

    def __init__(self, *args, **kwargs):
        self.name = "log Gaussian distribution"

        raise NotImplementedError("Not finished yet.")

        # Re-use the constructor of the superclass (Normal).
        super(LogNormal, self).__init__(*args, **kwargs)

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """Method to compute the misfit of a log Normal distribution distribution.
        """
        # This distribution is only non-zero for positive values of the coordinates. ----------
        if _numpy.any(coordinates <= 0):
            return _numpy.inf

        # Compute logarithmic coordinates and misfit -----------------------------------
        logarithmic_coordinates = _numpy.log(coordinates)
        if self.diagonal:
            return (
                _numpy.sum(logarithmic_coordinates).item(0)
                + 0.5
                * (
                    (self.means - logarithmic_coordinates).T
                    @ (
                        self.inverse_covariance
                        * (self.means - logarithmic_coordinates)
                    )
                ).item(0)
                + self.misfit_bounds(coordinates)
            )
        else:
            return (
                _numpy.sum(logarithmic_coordinates).item(0)
                + 0.5
                * (
                    (self.means - logarithmic_coordinates).T
                    @ self.inverse_covariance
                    @ (self.means - logarithmic_coordinates)
                ).item(0)
                + self.misfit_bounds(coordinates)
            )

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """Method to compute the gradient of a log Normal distribution distribution.

        TODO Verify these formulas!
        """
        # Compute logarithmic coordinates and gradient ---------------------------------
        logarithmic_coordinates = _numpy.log(coordinates)
        if self.diagonal:
            return (
                (
                    -self.inverse_covariance
                    * (self.means - logarithmic_coordinates)
                    / coordinates
                )
                + _numpy.sum(1.0 / coordinates)
                + self.misfit_bounds(coordinates)
            )
        else:
            return (
                (
                    -self.inverse_covariance
                    @ (self.means - logarithmic_coordinates)
                    / coordinates
                )
                + _numpy.sum(1.0 / coordinates)
                + self.misfit_bounds(coordinates)
            )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError("This function is not implemented yet.")


class Uniform(_AbstractDistribution):
    """Uniform bounded or unbouded distribution in model space.

    Parameters
    ----------
    dimensions : int
        Dimension of the distribution.
    lower_bounds: numpy.ndarray or None
        Numpy array of shape (dimensions, 1) that contains the lower limits of each
        parameter.
    upper_bounds: numpy.ndarray or None
        Numpy array of shape (dimensions, 1) that contains the upper limits of each
        parameter.

    """

    def __init__(
        self,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        override_dimensions: int = 2,
    ):
        self.name = "uniform distribution"

        # Automatically get dimensionality ...
        if lower_bounds is not None:
            # ... from means
            dimensions = lower_bounds.size
        else:
            # If no means is provided, use 2 dimensions
            dimensions = override_dimensions
        self.dimensions = dimensions
        """TODO description"""

        # TODO add empty initialization

        self.update_bounds(lower_bounds, upper_bounds)

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """Method to compute the misfit of a uniform distribution.
        """
        return self.misfit_bounds(coordinates)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """Method to compute the gradient of a uniform distribution.
        """
        return _numpy.zeros((self.dimensions, 1)) + self.misfit_bounds(
            coordinates
        )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError("This function is not implemented yet.")


class CompositeDistribution(_AbstractDistribution):
    """Distribution distribution combined from multiple unconditional distributions.

    Parameters
    ==========
    dimensions : int
        Combined dimension of all the separate distributions
    list_of_distributions : List[_AbstractDistribution]
        List of all separate distributions.


    Raises
    ======
    ValueError
        Raised if the passed dimensions do not correspond to the sum of the separate
        dimensions of each distribution.


    This class can be used when two or more sets of coordinates should be described by
    different distributions, e.g. when one set requires a Normal distribution and another a
    uniform distribution.
    """

    def __init__(
        self,
        list_of_distributions: _List[_AbstractDistribution] = None,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        override_dimensions: int = 2,
    ):
        self.name = "composite distribution"

        if list_of_distributions is not None:
            self.separate_distributions: _List[
                _AbstractDistribution
            ] = list_of_distributions
        else:
            dimensions = override_dimensions

            _warnings.warn(
                f"No subdistributions were passed, generating {dimensions} random subdistributions.",
                Warning,
            )
            available_distributions = _AbstractDistribution.__subclasses__()
            for distribution_to_remove in [
                CompositeDistribution,
                AdditiveDistribution,
                MultiplicativeDistribution,
            ]:
                available_distributions.remove(distribution_to_remove)
            selected_classes = _numpy.random.choice(
                available_distributions, dimensions
            )
            self.separate_distributions = [
                selected_class(1) for selected_class in selected_classes
            ]

        self.enumerated_dimensions: _numpy.ndarray = _numpy.empty(
            (len(self.separate_distributions))
        )
        """This object describes how many dimensions each distribution has, ordered according
        to ``CompositeDistribution.separate_distributions``. Sums to ``CompositeDistribution.dimesions``.
        """

        # Assert that the passed distributions actually do represent the correct amount of
        # dimensions, and seperately extract the size of each distribution
        computed_dimensions: int = 0
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            computed_dimensions += distribution.dimensions
            self.enumerated_dimensions[
                i_distribution
            ] = distribution.dimensions

        self.dimensions = computed_dimensions

        self.enumerated_dimensions_cumulative: _numpy.ndarray = _numpy.cumsum(
            self.enumerated_dimensions, dtype="int"
        )[:-1]
        """This object describes each separate distribution index in combined model space. Invoking
        ``numpy.split(m, CompositeDistribution.enumerated_dimensions_cumulative)[:-1])``
        splits a vector appropriately for all separate distributions.
        """

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        # Split coordinates for all sub-distributions -----------------------------------------
        split_coordinates = _numpy.split(
            coordinates, self.enumerated_dimensions_cumulative
        )

        misfit = 0.0

        # Loop over distributions and add misfit ----------------------------------------------
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            misfit += distribution.misfit(split_coordinates[i_distribution])

        return misfit + self.misfit_bounds(coordinates)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        # Split coordinates for all sub-distributions -----------------------------------------
        split_coordinates = _numpy.split(
            coordinates, self.enumerated_dimensions_cumulative
        )

        gradients = []

        # Loop over distributions and compute gradient ----------------------------------------
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            gradients.append(
                distribution.gradient(split_coordinates[i_distribution])
            )

        # Vertically stack gradients ---------------------------------------------------
        gradient = _numpy.vstack(gradients)

        assert gradient.shape == coordinates.shape

        return gradient + self.misfit_bounds(coordinates)

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError("This function is not implemented yet.")

    def collapse_bounds(self):
        """Method to restructure all composite bounds into top level object.
        """
        raise NotImplementedError()

    def corrector(self, coordinates: _numpy.ndarray, momentum: _numpy.ndarray):
        """Override method to correct an HMC particle for composite distribution, which is
        called after every time integration step. Calls all sub-correctors only if the
        object does not have bounds itself.

        Parameters
        ----------
        coordinates : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the coordinates :math:`\\mathbf{m}` upon which to operate by
            reference.
        momentum : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the momenta :math:`\\mathbf{p}` upon which to operate by
            reference.

        """
        # Start with bounds of CompositeDistribution ------------------------------------------
        if self.lower_bounds is not None:
            # Lower bound correction
            too_low = coordinates < self.lower_bounds
            coordinates[too_low] += 2 * (
                self.lower_bounds[too_low] - coordinates[too_low]
            )
            momentum[too_low] *= -1.0
        if self.upper_bounds is not None:
            # Upper bound correction
            too_high = coordinates > self.upper_bounds
            coordinates[too_high] += 2 * (
                self.upper_bounds[too_high] - coordinates[too_high]
            )
            momentum[too_high] *= -1.0

        # If they are not set, check subdistributions.
        if self.lower_bounds is None and self.upper_bounds is None:
            # Split coordinates and momenta for all sub-distributions -------------------------
            split_coordinates = _numpy.split(
                coordinates, self.enumerated_dimensions_cumulative
            )
            split_momenta = _numpy.split(
                momentum, self.enumerated_dimensions_cumulative
            )

            # And loop over separate distributions to check bounds
            for i_distribution, distribution in enumerate(
                self.separate_distributions
            ):

                if distribution.lower_bounds is not None:
                    # Lower bound correction
                    too_low = (
                        split_coordinates[i_distribution]
                        < distribution.lower_bounds
                    )
                    split_coordinates[i_distribution][too_low] += 2 * (
                        distribution.lower_bounds[too_low]
                        - split_coordinates[i_distribution][too_low]
                    )
                    split_momenta[i_distribution][too_low] *= -1.0
                if distribution.upper_bounds is not None:
                    # Upper bound correction
                    too_high = (
                        split_coordinates[i_distribution]
                        > distribution.upper_bounds
                    )
                    split_coordinates[i_distribution][too_high] += 2 * (
                        distribution.upper_bounds[too_high]
                        - split_coordinates[i_distribution][too_high]
                    )
                    split_momenta[i_distribution][too_high] *= -1.0


class AdditiveDistribution(_AbstractDistribution):
    def __init__(
        self,
        list_of_distributions: _List[_AbstractDistribution] = None,
        lower_bounds: _numpy.ndarray = None,
        upper_bounds: _numpy.ndarray = None,
        overrie_dimensions: int = 2,
    ):
        self.name = "additive distribution"

        # Automatically get dimensionality ...
        if list_of_distributions is not None:
            # ... from means
            dimensions = list_of_distributions[0].dimensions
        else:
            # If no means is provided, use 2 dimensions
            dimensions = override_dimensions
        self.dimensions = dimensions

        if list_of_distributions is not None:
            self.separate_distributions: _List[
                _AbstractDistribution
            ] = list_of_distributions
        else:
            _warnings.warn(
                f"No subdistributions were passed, generating 3 random subdistributions.",
                Warning,
            )
            available_distributions = _AbstractDistribution.__subclasses__()
            for distribution_to_remove in [
                CompositeDistribution,
                AdditiveDistribution,
            ]:
                available_distributions.remove(distribution_to_remove)
            selected_classes = _numpy.random.choice(available_distributions, 3)
            self.separate_distributions = [
                selected_class(dimensions)
                for selected_class in selected_classes
            ]

        # Assert that the passed distributions are of the right dimension
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            assert distribution.dimensions == dimensions

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        misfit = 0.0

        # Loop over distributions and add misfit ----------------------------------------------
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            misfit += distribution.misfit(coordinates)

        return misfit + self.misfit_bounds(coordinates)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        gradient = _numpy.zeros((self.dimensions, 1))

        # Loop over distributions and compute gradient ----------------------------------------
        for i_distribution, distribution in enumerate(
            self.separate_distributions
        ):
            gradient += distribution.gradient(coordinates)

        assert gradient.shape == coordinates.shape

        return gradient + self.misfit_bounds(coordinates)

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError("This function is not implemented yet.")

    def collapse_bounds(self):
        """Method to restructure all composite bounds into top level object.
        """
        raise NotImplementedError()

    def add_distribution(self, distribution: _AbstractDistribution):
        """Add a distribution to the object."""
        distribution.dimensions == dimensions
        self.separate_distributions.append(distribution)

    def corrector(self, coordinates: _numpy.ndarray, momentum: _numpy.ndarray):
        """Override method to correct an HMC particle for additive distribution, which is
        called after every time integration step. Calls all sub-correctors only if the
        object does not have bounds itself.

        Parameters
        ----------
        coordinates : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the coordinates :math:`\\mathbf{m}` upon which to operate by
            reference.
        momentum : numpy.ndarray
            Numpy array shaped as (dimensions, 1) representing a column vector
            containing the momenta :math:`\\mathbf{p}` upon which to operate by
            reference.

        """
        # Start with bounds of CompositeDistribution ------------------------------------------
        if self.lower_bounds is not None:
            # Lower bound correction
            too_low = coordinates < self.lower_bounds
            coordinates[too_low] += 2 * (
                self.lower_bounds[too_low] - coordinates[too_low]
            )
            momentum[too_low] *= -1.0
        if self.upper_bounds is not None:
            # Upper bound correction
            too_high = coordinates > self.upper_bounds
            coordinates[too_high] += 2 * (
                self.upper_bounds[too_high] - coordinates[too_high]
            )
            momentum[too_high] *= -1.0

        # TODO Fix this mess
        # # If they are not set, check subdistributions.
        # if self.lower_bounds is None and self.upper_bounds is None:
        #     # Split coordinates and momenta for all sub-distributions -------------------------
        #     split_coordinates = _numpy.split(
        #         coordinates, self.enumerated_dimensions_cumulative
        #     )
        #     split_momenta = _numpy.split(
        #         momentum, self.enumerated_dimensions_cumulative
        #     )

        #     # And loop over separate distributions to check bounds
        #     for i_distribution, distribution in enumerate(self.separate_distributions):

        #         if distribution.lower_bounds is not None:
        #             # Lower bound correction
        #             too_low = split_coordinates[i_distribution] < distribution.lower_bounds
        #             split_coordinates[i_distribution][too_low] += 2 * (
        #                 distribution.lower_bounds[too_low]
        #                 - split_coordinates[i_distribution][too_low]
        #             )
        #             split_momenta[i_distribution][too_low] *= -1.0
        #         if distribution.upper_bounds is not None:
        #             # Upper bound correction
        #             too_high = split_coordinates[i_distribution] > distribution.upper_bounds
        #             split_coordinates[i_distribution][too_high] += 2 * (
        #                 distribution.upper_bounds[too_high]
        #                 - split_coordinates[i_distribution][too_high]
        #             )
        #             split_momenta[i_distribution][too_high] *= -1.0


# Create an alias for AdditiveDistribution
class BayesRule(AdditiveDistribution):
    pass


class Himmelblau(_AbstractDistribution):
    """Himmelblau's 2-dimensional function.

    Himmelblau's function is defined as:

    .. math::

        f(x,y)=(x^{2}+y-11)^{2}+(x+y^{2}-7)^{2}
    """

    name: str = "Himmelblau's function"
    dimensions: int = 2
    annealing: float = 1
    """Float representing the annealing (:math:`T`) of Himmelblau's function.
    
    Alters the misfit function in the following way:

    .. math::

        f(x,y)_T=\\frac{f(x,y)}{T}
    """

    def __init__(self, annealing: float = 1):
        self.annealing = annealing

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """Returns the value of Himmelblau's function at the given coordinates."""
        if coordinates.shape != (self.dimensions, 1):
            raise ValueError()
        x = coordinates[0, 0]
        y = coordinates[1, 0]
        return (
            (x ** 2 + y - 11) ** 2 + (x + y ** 2 - 7) ** 2
        ) / self.annealing

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """Returns a numpy.ndarray shaped as (dimensions, 1) containing the gradient of
        Himmelblau's function at the given coordinates."""
        x = coordinates[0]
        y = coordinates[1]
        gradient = _numpy.zeros((self.dimensions, 1))
        gradient[0] = 2 * (2 * x * (x ** 2 + y - 11) + x + y ** 2 - 7)
        gradient[1] = 2 * (x ** 2 + 2 * y * (x + y ** 2 - 7) + y - 11)
        return gradient / self.annealing


def _make_spd_matrix(dim: int):
    """Generate a random symmetric, positive-definite matrix.

    Parameters
    ----------
    dim : int
        The matrix dimension.

    Returns
    -------
    x : array of shape [n_dim, n_dim]
        The random symmetric, positive-definite matrix.

    """
    # Create random matrix
    a = _numpy.random.rand(dim, dim)
    # Create random PD matrix and extract correlation structure
    u, _, v = _numpy.linalg.svd(_numpy.dot(a.T, a))
    # Reconstruct a new matrix with random variances.
    return _numpy.dot(
        _numpy.dot(u, 1.0 + _numpy.diag(_numpy.random.rand(dim))), v
    )